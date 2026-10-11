"""CPU-only re-read of a frozen HC diagnostic; it performs no lifecycle mutation."""
import argparse
import json
from pathlib import Path
import re
import subprocess


HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,os,pathlib,sys
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['PYTHONDONTWRITEBYTECODE']='1'
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch'];directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
execution=pathlib.Path(receipt['frozen_runner']).parent;server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_bytes())!=receipt:raise ValueError('exact launch receipt differs')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=digest:raise ValueError('frozen source differs: '+name)
status=json.loads((directory/('status_batch'+str(batch)+'.json')).read_bytes())
if status.get('state')!='complete_measurements_pending_review':raise ValueError('terminal measurement status required')
def terminal(identity):
 stat=pathlib.Path('/proc')/str(identity['pid'])/'stat'
 if not stat.exists():return True
 fields=stat.read_text().rpartition(') ')[2].split()
 if int(fields[19])!=identity['start_ticks']:raise ValueError('process birth reused')
 return fields[0]=='Z'
batch_identity={'pid':receipt['batch_pid'],'start_ticks':status['batch_start_ticks']}
if not terminal(batch_identity):raise ValueError('batch remains live')
lock=pathlib.Path('/data2/_shared/gpu.lock')
if lock.exists() and json.loads(lock.read_bytes()).get('owner')==rid:raise ValueError('owned lock remains')
sys.path.insert(0,str(execution));import t17_hc_runner as runner;import torch
prior=runner.retained.prerequisite();warm,cold=directory/'hc_warm',directory/'hc_cold'
handles={}
for arm in (warm,cold):
 handle=json.loads((arm/'process_identity.json').read_bytes())
 if json.loads((arm/'stop_identity.json').read_bytes())!={'terminal':True,**handle} or not terminal(handle):raise ValueError('terminal service identity differs')
 handles[arm.name]=handle
case=json.loads((directory/'real_inputs.json').read_bytes())['cases'][0]
if sha(directory/'real_inputs.json')!=receipt['source_files']['real_inputs.json']:raise ValueError('actual input changed')
donor=json.loads((warm/'donor.json').read_bytes())['response'];hit=json.loads((warm/'short.json').read_bytes())['response'];cold_response=json.loads((cold/'query.json').read_bytes())['response']
hot,hot_tensors=runner.observation(warm,donor['uid'],device=8193,extend=3585);cool,cool_tensors=runner.observation(cold,cold_response['uid'],device=8257,extend=3649)
roles=runner.compare_tensors(hot_tensors,cool_tensors)
raw=runner.artifacts.validate_case({'name':'hc-8192','length':8192,'trace_index':case['trace_index'],'context':case['expected_ngram']},cold,warm,tail=65,cold_request='query',hit_request='short',state_root=warm/'dump')
hot_state=runner.helper.load_dump_record(warm/'dump',kind='donate',length=8256,uid=str(hit['uid']));cool_state=runner.helper.load_dump_record(cold/'dump',kind='donate',length=8256,uid=str(cold_response['uid']))
suffix=runner.original.tensor_comparison(warm/'dump',hot_state,cold/'dump',cool_state)
measured_path=directory/('diagnostic_batch'+str(batch)+'.json');measured=json.loads(measured_path.read_bytes())
if (measured['hc_roles']!=roles or measured['suffix_8256']!=suffix or measured['raw_validator']!=raw or measured['warm_observation']!=hot or measured['cold_observation']!=cool or measured['FT_LM_CHUNK']!=4096 or measured['diagnostic_only'] is not True):raise ValueError('CPU re-evaluation differs')
print(json.dumps({'schema':'ft_t17_hc_cpu/v1','rid':rid,'batch':batch,'diagnostic_only':True,'FT_LM_CHUNK':4096,'hc_roles':roles,'suffix_8256':suffix,'raw_validator':raw,'arms':handles,'status':status,'original_T17':prior,'diagnostic_sha256':sha(measured_path),'cuda_initialized':torch.cuda.is_initialized()},sort_keys=True))
'''


def remote_read(host: str, receipt: dict) -> dict:
    source_sha = __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()
    wire = ('import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(receipt)) + ')\n' + PROGRAM)
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
                             '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True, timeout=240)
    if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace')[-4000:])
    report = json.loads(result.stdout)
    if report.get('cuda_initialized'): raise ValueError('CPU reader initialized CUDA')
    report['reader_source_sha256'] = source_sha
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('rid'); parser.add_argument('--host', default='9'); parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    if not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid): raise ValueError('exact diagnostic RID required')
    launch = HERE / ('t17_hc_' + options.rid + '_launch_receipt.json')
    receipt = json.loads(launch.read_bytes())
    if receipt.get('rid') != options.rid or receipt.get('FT_LM_CHUNK') != 4096 or receipt.get('diagnostic_only') is not True: raise ValueError('exact HC launch receipt required')
    report = remote_read(options.host, receipt)
    if options.output:
        with options.output.open('x', encoding='utf-8') as stream: json.dump(report, stream, sort_keys=True, indent=2); stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
