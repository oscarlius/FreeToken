"""Independently recompute one completed matched diagnostic from CPU tensors and raw tokens."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,importlib.util,json,os,pathlib,sys
os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['PYTHONDONTWRITEBYTECODE']='1'
receipt=json.load(sys.stdin);rid=receipt['rid'];batch=receipt['batch'];pid=receipt['batch_pid']
directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/rid
execution=pathlib.Path(receipt['frozen_runner']).parent
server=pathlib.Path('/data2/FreeToken/runs/dev_D14')/('launch_'+rid+'.json')
if json.loads(server.read_bytes())!=receipt:raise ValueError('exact diagnostic receipt differs')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
original=directory.parent/'E2-R023-gate-T17'
if (sha(original/'round.json')!='92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d'
 or json.loads((original/'round.json').read_bytes()).get('verdict')!='not_met'):
 raise ValueError('exact original T17 not_met counterexample changed')
for name,digest in receipt['source_files'].items():
 path=execution/name
 if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=digest:raise ValueError('frozen source differs: '+name)
status=json.loads((directory/('status_batch'+str(batch)+'.json')).read_bytes())
if status.get('state')!='complete_measurements_pending_review':raise ValueError('completed measurement required')
def terminal(identity):
 stat=pathlib.Path('/proc')/str(identity['pid'])/'stat'
 if not stat.exists():return True
 fields=stat.read_text().rpartition(') ')[2].split()
 if int(fields[19])!=identity['start_ticks']:raise ValueError('captured process birth reused')
 return fields[0]=='Z'
if not terminal({'pid':pid,'start_ticks':status['batch_start_ticks']}):raise ValueError('batch remains live')
lock=pathlib.Path('/data2/_shared/gpu.lock')
if lock.exists() and json.loads(lock.read_bytes()).get('owner')==rid:raise ValueError('owned GPU lock remains')
sys.path.insert(0,str(execution))
spec=importlib.util.spec_from_file_location('matched_cpu_artifacts',execution/'t17_d14_artifacts.py')
artifact=importlib.util.module_from_spec(spec);spec.loader.exec_module(artifact)
import torch
warm,cold=directory/'matched_warm',directory/'matched_cold'
arms={}
for arm in [warm,cold]:
 identity=json.loads((arm/'process_identity.json').read_bytes())
 stopped=json.loads((arm/'stop_identity.json').read_bytes())
 if stopped!={'terminal':True,**identity} or not terminal(identity):raise ValueError('service terminal proof differs')
 arms[arm.name]=identity
inputs=json.loads((directory/'real_inputs.json').read_bytes());case=inputs['cases'][0]
raw=artifact.validate_case({'name':'matched-8192','length':8192,'trace_index':case['trace_index'],
 'context':case['expected_ngram']},cold,warm,tail=65,cold_request='query',hit_request='short',state_root=warm/'dump')
def load_prefix(arm,uid):
 final=json.loads((arm/'matched'/('final_'+str(uid)+'.json')).read_bytes())
 if final.get('valid') is not True or str(final.get('uid'))!=str(uid):raise ValueError('prefix final incomplete')
 path=arm/'matched'/final['receipt_file']
 if path.is_symlink() or (arm/'matched').resolve() not in path.resolve().parents or sha(path)!=final['receipt_sha256']:
  raise ValueError('prefix receipt file differs')
 record=json.loads(path.read_bytes())
 if (record['boundary'],record['cached_tokens'],record['extend_tokens'],record['device_tokens'])!=(8192,512,7680,8192):
  raise ValueError('actual aligned prefix coordinates differ')
 installs=[json.loads(p.read_bytes()) for p in (arm/'matched').glob('installed_*.json')]
 if len(installs)!=1 or installs[0]['FT_LM_CHUNK']!='7680':raise ValueError('matched worker environment differs')
 if (installs[0]['observer_source_sha256']!=receipt['source_files']['t17_matched_observe.py']
   or installs[0]['startup_source_sha256']!=receipt['source_files']['t17_matched_startup.py']):
  raise ValueError('worker installation source differs')
 layers=record['linear_layers_by_local']
 if ([r['local_index'] for r in layers]!=list(range(installs[0]['num_linear_layers']))
   or len({r['decoder_layer_idx'] for r in layers})!=len(layers)
   or len({r['gdn_layer_id'] for r in layers})!=len(layers)):raise ValueError('local layer identity incomplete')
 return record
donor=json.loads((warm/'donor.json').read_bytes())['response']['uid']
query=json.loads((cold/'query.json').read_bytes())['response']['uid']
hit=json.loads((warm/'short.json').read_bytes())['response']['uid']
prefix_hot,prefix_cold=load_prefix(warm,donor),load_prefix(cold,query)
def compare(a,b):
 compatible=a.shape==b.shape and a.dtype==b.dtype
 byte_a=a.contiguous().view(torch.uint8).flatten();byte_b=b.contiguous().view(torch.uint8).flatten()
 return {'equal':compatible and torch.equal(byte_a,byte_b),'shape_left':list(a.shape),'shape_right':list(b.shape),
 'dtype_left':str(a.dtype),'dtype_right':str(b.dtype),'max_abs':float((a.float()-b.float()).abs().max()) if compatible and a.numel() else None,
 'different_values':int((a!=b).sum()) if compatible else None,
 'different_bytes':int((byte_a!=byte_b).sum()) if compatible else None}
prefix_roles={}
for role in artifact.ROLES:
 tensors=[]
 for arm,record in [(warm,prefix_hot),(cold,prefix_cold)]:
  item=record['roles'][role];path=arm/'matched'/item['file']
  if path.is_symlink() or (arm/'matched').resolve() not in path.resolve().parents or sha(path)!=item['sha256']:
   raise ValueError('raw prefix tensor differs')
  tensor=artifact.load_tensor(path)
  if list(tensor.shape)!=item['shape'] or str(tensor.dtype)!=item['dtype']:raise ValueError('actual prefix shape/dtype differs')
  tensors.append(tensor)
 prefix_roles[role]=compare(*tensors)
donation_live_roles={}
donation_record=artifact.one([r for r in artifact.jsonl(warm/'dump/index.jsonl')
 if r['kind']=='donate' and str(r['uid'])==str(donor) and r['length']==8192],'donor prefix donation')
for role in artifact.ROLES:
 live=artifact.load_tensor(warm/'matched'/prefix_hot['roles'][role]['file'])
 donated,item=artifact.state_file(warm/'dump',donation_record,role,artifact.load_tensor)
 original_shape=list(donated.shape)
 if role in ['conv_states','recurrent_states']:
  if tuple(donated.shape)!=(live.shape[0],1,*live.shape[1:]):raise ValueError('donation singleton batch layout differs')
  donated=donated.squeeze(1)
 else:
  if tuple(donated.shape)!=(1,1,*live.shape):raise ValueError('donation PLE singleton layer/batch layout differs')
  donated=donated.squeeze(0).squeeze(0)
 donation_live_roles[role]={**compare(live,donated),'raw_donation_shape':original_shape,
                          'comparison_layout':'recorded singleton batch/layer axes removed; no element reordering'}
suffix_roles={}
for role in artifact.ROLES:
 tensors=[]
 for arm,uid in [(warm,hit),(cold,query)]:
  rows=artifact.jsonl(arm/'dump/index.jsonl')
  record=artifact.one([r for r in rows if r['kind']=='donate' and str(r['uid'])==str(uid) and r['length']==8256],'suffix state')
  tensor,item=artifact.state_file(arm/'dump',record,role,artifact.load_tensor)
  tensors.append(tensor)
 suffix_roles[role]=compare(*tensors)
observed=json.loads((directory/('diagnostic_batch'+str(batch)+'.json')).read_bytes())
for key,values in [('prefix_8192',prefix_roles),('suffix_8256',suffix_roles)]:
 for role,value in values.items():
  if value['equal']!=observed[key][role]['equal'] or value['max_abs']!=observed[key][role]['max_abs']:
   raise ValueError('saved role comparison fails independent CPU recomputation')
forks=[i for i,(a,b) in enumerate(zip(raw['cold_token_ids'],raw['hit_token_ids'])) if a!=b]
if observed['tokens_equal']!=raw['tokens_bitwise_equal'] or observed['text_equal']!=raw['full_text_equal']:
 raise ValueError('saved actual token/text comparison differs')
print(json.dumps({'schema':'ft_t17_matched_cpu_review/v1','rid':rid,'batch':batch,'diagnostic_only':True,
 'original_T17_verdict':'not_met_retained','prefix_8192':prefix_roles,'suffix_8256':suffix_roles,
 'donation_vs_live_8192':donation_live_roles,
 'tokens_equal':raw['tokens_bitwise_equal'],'text_equal':raw['full_text_equal'],'first_token_fork':forks[0] if forks else None,
 'token_forks':forks,'token_count':{'cold':len(raw['cold_token_ids']),'hit':len(raw['hit_token_ids'])},
 'token_id_sha256':{'cold':raw['cold_token_ids_sha256'],'hit':raw['hit_token_ids_sha256']},
 'restored_roles':{k:v['bitwise_equal'] for k,v in raw['state_roles'].items()},
 'actual_cached_tokens':raw['actual_cached_tokens'],'cuda_initialized':torch.cuda.is_initialized(),
 'arms':arms,'status':status,'diagnostic_sha256':sha(directory/('diagnostic_batch'+str(batch)+'.json'))},ensure_ascii=False))
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rid')
    options = parser.parse_args()
    if '/' in options.rid or '\\' in options.rid or not options.rid.endswith('-diagnostic-T17'):
        raise ValueError('exact diagnostic RID required')
    receipt = json.loads((HERE / ('t17_matched_' + options.rid + '_launch_receipt.json')).read_text(encoding='utf-8'))
    if receipt.get('rid') != options.rid or receipt.get('diagnostic_only') is not True:
        raise ValueError('exact actual launch receipt required')
    wire = 'import io,sys\nsys.stdin=io.StringIO(' + repr(json.dumps(receipt)) + ')\n' + PROGRAM
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-'],
                             input=wire.encode('utf-8'), capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    print(json.dumps(json.loads(process.stdout), ensure_ascii=False, indent=2))
