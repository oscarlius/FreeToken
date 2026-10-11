"""CPU-recompute all retained GDN replay outputs from one exact launch receipt."""
import argparse
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,itertools,json,pathlib,sys
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch']
if receipt.get('schema')!='ft_t17_gemm_launch/v1' or receipt.get('operator_only') is not True:
 raise ValueError('exact operator launch receipt required')
root=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
 if p.is_symlink() or not p.is_file():raise ValueError('regular evidence file required: '+str(p))
 return json.loads(p.read_bytes())
if load(pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json'))!=receipt:
 raise ValueError('server launch receipt differs')
frozen=pathlib.Path(receipt['frozen_runner']).parent
for name,want in receipt['source_files'].items():
 p=frozen/name
 if p.is_symlink() or p.stat().st_mode&0o222 or sha(p)!=want:raise ValueError('frozen runtime source changed: '+name)
sys.path.insert(0,str(frozen))
import t17_gemm_launch as launcher
cpu=launcher.checked_stage(pathlib.Path(receipt['source_stage']),receipt['cpu_stage_sha256'])
if cpu['source_files']!=receipt['source_files']:raise ValueError('CPU/runtime source binding differs')
import t17_gemm_runner as runner
runner.source_round()
import t17_hc_gemm_execute as execute
import torch
if torch.cuda.is_initialized():raise ValueError('CPU read must not initialize CUDA')
plan=load(root/'plan.json')
if plan!=load(frozen/'plan.json'):raise ValueError('executed plan differs from frozen preparation')
identity=load(root/'process_identity.json');status=load(root/('status_batch'+str(batch)+'.json'))
if (identity['pid']!=receipt['batch_pid'] or identity['pgid']!=identity['pid'] or identity['session']!=identity['pid']
 or status.get('state')!='complete_measurements_pending_review' or status.get('rid')!=rid or status.get('batch')!=batch
 or status.get('batch_pid')!=identity['pid'] or status.get('batch_start_ticks')!=identity['start_ticks']):
 raise ValueError('complete batch identity/status required')
stat=pathlib.Path('/proc')/str(identity['pid'])/'stat';terminal={'present':False}
if stat.exists():
 fields=stat.read_text().rpartition(') ')[2].split()
 if int(fields[19])!=identity['start_ticks'] or fields[0]!='Z':raise ValueError('batch is live or PID was reused')
 terminal={'present':True,'state':'Z','start_ticks':int(fields[19])}
lock=pathlib.Path('/data2/_shared/gpu.lock')
if lock.exists() and json.loads(lock.read_bytes()).get('owner')==rid:raise ValueError('owned GPU lock not released')
report=load(root/'gemm/receipt.json')
if report!=load(root/'diagnostic.json') or report.get('rid')!=rid or report.get('operator')!='gdn':
 raise ValueError('replay receipts differ')
proof=report['ownership']
if proof['rid']!=rid or proof['pid']!=identity['pid'] or proof['start_ticks']!=identity['start_ticks']:
 raise ValueError('execution ownership receipt differs')
token=json.loads(proof['lock_token'])
if token['owner']!=rid or token['pid']!=identity['pid'] or proof['global_lock_path']!='/data2/_shared/gpu.lock':
 raise ValueError('archived lock ownership proof differs')
weight,checkpoint,layout=execute._checkpoint_weight(plan['checkpoint'],'gdn')
attestation={'fusion':layout,'shape':list(weight.shape),'dtype':str(weight.dtype),
 'tensor_sha256':hashlib.sha256(execute._bytes(weight)).hexdigest()}
if (checkpoint!=report['checkpoint'] or attestation!=plan['cpu_weight_preparation']
 or report.get('cpu_weight_preparation')!=attestation or report['weight_tensor_sha256']!=attestation['tensor_sha256']):
 raise ValueError('current CPU checkpoint/fused weight differs')
live={name:execute._load_tensor(plan['arms'][name]['roles']['gdn_qkv_output']) for name in ('warm','cold')}
inputs={name:execute._load_tensor(plan['arms'][name]['roles']['gdn_qkv_input']) for name in ('warm','cold')}
if execute._bytes(inputs['warm'])!=execute._bytes(inputs['cold']):raise ValueError('real inputs differ')
observed={};primary={};raw_outputs={}
for run in plan['runs']:
 name=run['name'];row=report['outputs'][name];items=[]
 if row['M']!=run['M'] or row['artificial_rows']!=run['artificial_rows'] or row['repeat_count']!=3:
  raise ValueError('replay run dimensions/repeats differ')
 if len(row['outputs'])!=3:raise ValueError('three retained repeat files required')
 for index,record in enumerate(row['outputs'],1):
  if record['file']!=name+'_repeat'+str(index)+'.pt':raise ValueError('exclusive repeat filename differs')
  path=root/'gemm'/record['file'];meta={**record,'file':str(path)}
  items.append(execute._load_tensor(meta));raw_outputs[record['file']]=sha(path)
 metrics={'vs_warm_live':execute.byte_metrics(items[0],live['warm']),
  'vs_cold_live':execute.byte_metrics(items[0],live['cold']),
  'repeat_pair_metrics':[execute.byte_metrics(items[0],item) for item in items[1:]]}
 metrics['repeats_equal']=all(item['bitwise_equal'] for item in metrics['repeat_pair_metrics'])
 if any(row[key]!=value for key,value in metrics.items()):raise ValueError('recorded replay metrics differ: '+name)
 observed[name]={'M':row['M'],'artificial_rows':row['artificial_rows'],**metrics};primary[name]=items[0]
pairs={'warm_full_m__cold_full_m':execute.byte_metrics(primary['warm_full_m'],primary['cold_full_m'])}
for name in ('matched_m_4096','m1_oracle'):
 if name in primary:
  pairs['warm_full_m__'+name]=execute.byte_metrics(primary['warm_full_m'],primary[name])
  pairs['cold_full_m__'+name]=execute.byte_metrics(primary['cold_full_m'],primary[name])
if pairs!=report['pair_metrics']:raise ValueError('recorded pair metrics differ')
if torch.cuda.is_initialized():raise ValueError('CPU read created CUDA context')
print(json.dumps({'schema':'ft_t17_gemm_cpu_read/v1','rid':rid,'batch':batch,'diagnostic_only':True,
 'cuda_initialized':False,'identity':identity,'status':status,'terminal':terminal,'source_round':plan['source_round'],
 'diagnostic_sha256':sha(root/'diagnostic.json'),'replay_receipt_sha256':sha(root/'gemm/receipt.json'),
 'plan_sha256':sha(root/'plan.json'),'weight':attestation,'real_inputs_equal':True,
 'runs':observed,'pair_metrics':pairs,'raw_output_files':raw_outputs,
 'precision':report['precision'],'device':report['device'],'torch':report['torch'],'cuda':report['cuda'],
 'kernel':report['kernel'],'limitations':report['limitations']}))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', args.rid):
        raise ValueError('exact operator RID required')
    receipt = json.loads((HERE / ('t17_gemm_' + args.rid + '_launch_receipt.json')).read_bytes())
    if receipt['rid'] != args.rid:
        raise ValueError('launch RID differs')
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(receipt)) + ')\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'], input=wire.encode(), capture_output=True)
    if process.returncode:
        raise RuntimeError(process.stderr.decode() or process.stdout.decode())
    value = json.loads(process.stdout)
    value['reader_source_sha256'] = __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest()
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    print(json.dumps(value, indent=2))
