"""Recompute a terminal original-chunk projection diagnostic on the server CPU."""
import argparse
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,os,pathlib,sys
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['PYTHONDONTWRITEBYTECODE']='1'
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch'];pid=receipt['batch_pid']
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
execution=pathlib.Path(receipt['frozen_runner']).parent
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_bytes())!=receipt:raise ValueError('exact launch receipt differs')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=digest:raise ValueError('frozen source differs: '+name)
status=json.loads((directory/('status_batch'+str(batch)+'.json')).read_bytes())
if status.get('state')!='complete_measurements_pending_review':raise ValueError('terminal measurements required')
def terminal(identity):
 stat=pathlib.Path('/proc')/str(identity['pid'])/'stat'
 if not stat.exists():return True
 fields=stat.read_text().rpartition(') ')[2].split()
 if int(fields[19])!=identity['start_ticks']:raise ValueError('captured process birth reused')
 return fields[0]=='Z'
if not terminal({'pid':pid,'start_ticks':status['batch_start_ticks']}):raise ValueError('batch remains live')
lock=pathlib.Path('/data2/_shared/gpu.lock')
if lock.exists() and json.loads(lock.read_bytes()).get('owner')==rid:raise ValueError('owned lock remains')
sys.path.insert(0,str(execution))
import t17_projection_runner as runner
import torch
prior=runner.retained.prerequisite()
warm,cold=directory/'projection_warm',directory/'projection_cold'
handles={}
for arm in (warm,cold):
 handle=json.loads((arm/'process_identity.json').read_bytes())
 if json.loads((arm/'stop_identity.json').read_bytes())!={'terminal':True,**handle} or not terminal(handle):
  raise ValueError('service terminal identity differs')
 handles[arm.name]=handle
case=json.loads((directory/'real_inputs.json').read_bytes())['cases'][0]
if sha(directory/'real_inputs.json')!=receipt['source_files']['real_inputs.json']:
 raise ValueError('retained actual input cases changed')
hot_response=json.loads((warm/'short.json').read_bytes())['response']
cool_response=json.loads((cold/'query.json').read_bytes())['response']
hot,hot_tensors=runner.projection(warm,hot_response['uid'],8192)
cool,cool_tensors=runner.projection(cold,cool_response['uid'],4608)
roles=runner.compare_projections(hot_tensors,cool_tensors)
raw=runner.artifacts.validate_case({'name':'projection-8192','length':8192,'trace_index':case['trace_index'],
 'context':case['expected_ngram']},cold,warm,tail=65,cold_request='query',hit_request='short',state_root=warm/'dump')
hot_state=runner.helper.load_dump_record(warm/'dump',kind='donate',length=8256,uid=str(hot_response['uid']))
cool_state=runner.helper.load_dump_record(cold/'dump',kind='donate',length=8256,uid=str(cool_response['uid']))
suffix=runner.original.tensor_comparison(warm/'dump',hot_state,cold/'dump',cool_state)
path=directory/('diagnostic_batch'+str(batch)+'.json');measured=json.loads(path.read_bytes())
if (measured['projection_roles']!=roles or measured['suffix_8256']!=suffix or measured['raw_validator']!=raw
 or measured['warm_receipt']!=hot or measured['cold_receipt']!=cool or measured['FT_LM_CHUNK']!=4096
 or measured['diagnostic_only'] is not True):raise ValueError('CPU recomputation differs from actual measurement')
print(json.dumps({'schema':'ft_t17_projection_cpu_review/v1','rid':rid,'batch':batch,'diagnostic_only':True,
 'FT_LM_CHUNK':4096,'projection_roles':roles,'suffix_8256':suffix,'tokens_equal':raw['tokens_bitwise_equal'],
 'text_equal':raw['full_text_equal'],'raw_validator':raw,'arms':handles,'warm_coordinates':{k:hot[k] for k in ('uid','slot','cached_tokens','device_tokens','extend_tokens')},
 'cold_coordinates':{k:cool[k] for k in ('uid','slot','cached_tokens','device_tokens','extend_tokens')},
 'token_count':{'cold':len(raw['cold_token_ids']),'hit':len(raw['hit_token_ids'])},
 'first_token_fork':next((i for i,(a,b) in enumerate(zip(raw['cold_token_ids'],raw['hit_token_ids'])) if a!=b),None),
 'restored_roles':{role:record['bitwise_equal'] for role,record in raw['state_roles'].items()},
 'status':status,'original_T17':prior,'diagnostic_sha256':sha(path),'cuda_initialized':torch.cuda.is_initialized()}))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    options = parser.parse_args()
    if not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', options.rid):
        raise ValueError('exact diagnostic RID required')
    receipt = json.loads((HERE / ('t17_projection_' + options.rid + '_launch_receipt.json')).read_bytes())
    if receipt['rid'] != options.rid or receipt.get('FT_LM_CHUNK') != 4096 or receipt.get('diagnostic_only') is not True:
        raise ValueError('exact projection launch receipt required')
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(receipt)) + ')\n' + PROGRAM
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                             '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
    if result.returncode:
        print(result.stderr.decode())
        raise SystemExit(result.returncode)
    report = json.loads(result.stdout)
    if report['cuda_initialized']:
        raise ValueError('CPU reader initialized CUDA')
    (HERE / ('t17_projection_' + options.rid + '_read.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
