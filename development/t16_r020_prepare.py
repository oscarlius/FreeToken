"""Prepare, but never seal, the independently reviewed R020 D06 gate."""
from __future__ import annotations
import argparse, hashlib, json, math, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

RID="E2-R020-gate-D06"; BATCH=48
CANONICAL_ROUND=Path('/data2/_shared/runs/ft_rounds')/RID
PARENT="23f2e2caa3395837c9474735ffc83321f3b9b5a1"; CANDIDATE="03692633df48456fb0baa78de7b64e5628a12ab1"
RAW_SHA="b90f82b9484205ca8bdeba4edb60fb419b43e723d235ee4f6df7afb4532326a0"
BINDING_SHA="68b26775e03d6079ec0a95de4494d09fce97737824b4edf6ae4f4442dce3f5f5"
RECEIPT_SHA="913d82b367dd8c0f736b7767f323c7e1075cbc2d327ad4b43a515ce8f1d221b8"
RECEIPT_PATH=Path('/data2/FreeToken/runs/dev_D06/launch_E2-R020-gate-D06.json')
RUNNER_SHA="d29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1"; BASE_SHA="66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125"; WRAPPER_SHA="73e6ab5ed555aef2979c9b7c501df91635030e7a32f098192b78df4366ed0b0e"
REVIEW_SHA="67a895cc4e6913e6e5530fa3a4b20ed13e9a1d2fc4bfeabde4713c98375c3dc4"
ARMS=("PARENT_b48","NEW_b48","PARENT_P_b48","NEW_P_b48"); CONTROL=("round.json","round_history","MANIFEST.sha256")
PID_RE=re.compile(r"['\"]?\.pid=(\d+)['\"]?")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text(encoding='utf-8'))
 except Exception as e:raise ValueError(f'invalid JSON: {p}') from e
def jb(v):return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def require(p):
 p=Path(p)
 if not p.is_file() or p.is_symlink() or not p.stat().st_size:raise ValueError(f'missing or empty artifact: {p}')
 return p
def guarded_path(path):
 raw=Path(os.path.abspath(path)); cur=raw
 while True:
  if cur.is_symlink():raise ValueError(f'symlink path or ancestor rejected: {cur}')
  if cur==cur.parent:break
  cur=cur.parent
 return raw.resolve(strict=True)
def exact_round(path):
 p=guarded_path(path)
 if p!=CANONICAL_ROUND:raise ValueError('exact canonical R020 round required')
 return p
def terminal(pid):
 if type(pid) is not int or pid<=0:raise ValueError('positive owned PID required')
 p=Path(f'/proc/{pid}/stat')
 if not p.exists():return True
 fields=p.read_text().rpartition(') ')[2].split()
 return len(fields)>=4 and fields[0]=='Z'
def owned(d):
 uid=os.geteuid() if hasattr(os,'geteuid') else None
 for p in [d,*d.rglob('*')]:
  if p.is_symlink() or (uid is not None and p.stat().st_uid!=uid):raise ValueError(f'foreign owner or symlink rejected: {p}')
def finite(v):
 if isinstance(v,bool):return
 if isinstance(v,(int,float)):
  if not math.isfinite(v):raise ValueError('nonfinite metric')
 elif isinstance(v,list):
  for x in v:finite(x)
 elif isinstance(v,dict):
  for x in v.values():finite(x)
def arm(d,name):
 p=d/name
 for f in ('SERVE_CMD.txt','serve.log','serve_args.txt','ENV.txt','tax.json','prefill_seq.txt','det.json'):require(p/f)
 ids=PID_RE.findall((p/'serve_args.txt').read_text())
 if len(ids)!=1 or not terminal(int(ids[0])):raise ValueError(f'live or ambiguous service PID: {name}')
 expected=PARENT if name.startswith('PARENT') else CANDIDATE
 if expected not in (p/'ENV.txt').read_text():raise ValueError(f'wrong source commit: {name}')
 return {'serve_cmd':f'{name}/SERVE_CMD.txt','serve_args':f'{name}/serve_args.txt','environment_snapshot':f'{name}/ENV.txt','owned_service_pid':int(ids[0])}
def validate(d,review):
 d=exact_round(d); review=guarded_path(review)
 if REVIEW_SHA is None:raise ValueError('independent review SHA is not pinned')
 if any((d/x).exists() for x in CONTROL):raise ValueError('assigned unsealed round required')
 if review!=d/f'review_batch{BATCH}.json':raise ValueError('exact independent review path required')
 owned(d); review_path=require(review)
 if sha(review_path)!=REVIEW_SHA:raise ValueError('frozen independent review bytes mismatch')
 gate_path=require(d/f'gate_batch{BATCH}.json'); status_path=require(d/f'status_batch{BATCH}.json'); binding=require(d/'candidate_binding.json'); wrapper=require(d/f'batch{BATCH}.sh')
 if sha(gate_path)!=RAW_SHA or sha(binding)!=BINDING_SHA or sha(wrapper)!=WRAPPER_SHA:raise ValueError('raw gate/binding/wrapper SHA differs')
 gate,status,b=load(gate_path),load(status_path),load(binding)
 if gate.get('arms')!=list(ARMS) or gate.get('gate')!='D06' or gate.get('candidate_case')!='D06' or gate.get('parent_commit')!=PARENT or gate.get('new_commit')!=CANDIDATE:raise ValueError('gate identity/arms mismatch')
 pre=gate.get('layer_major',{}).get('prefill',{})
 if pre.get('parent_rows')!=13 or pre.get('new_rows')!=13 or 'non_layer_major' in gate:raise ValueError('R020 must contain only 13-row layer-major profile')
 if status.get('state')!='complete_measurements_pending_review' or status.get('batch')!=BATCH or status.get('rid')!=RID or status.get('candidate_case')!='D06' or status.get('batch_pid')!=3817162 or not terminal(3817162):raise ValueError('terminal status mismatch')
 if b.get('candidate_runner_sha256')!=RUNNER_SHA or b.get('base_runner_sha256')!=BASE_SHA or b.get('ordinary_prefill') is not False or any(b.get(k)!=v for k,v in {'case':'D06','card':'D06','parent_commit':PARENT,'new_commit':CANDIDATE,'parent_wt':'e2base','new_wt':'e2d06','base_runner_filename':'t16_full_tail_base_runner.py'}.items()):raise ValueError('binding mismatch')
 if sha(require(d/'runner_batch48.py'))!=RUNNER_SHA or sha(require(d/'base_runner_batch48.py'))!=BASE_SHA:raise ValueError('archived runner bytes mismatch')
 receipt=load(require(RECEIPT_PATH))
 if sha(RECEIPT_PATH)!=RECEIPT_SHA or any(receipt.get(k)!=v for k,v in {'schema':'ft_candidate_gate_launch/v1','state':'launched','rid':RID,'batch':BATCH,'case':'D06','card':'D06','candidate_commit':CANDIDATE,'parent_commit':PARENT,'runner_sha256':RUNNER_SHA,'base_runner_sha256':BASE_SHA,'wrapper_sha256':WRAPPER_SHA,'batch_pid':3817162,'batch_pgid':3817162}.items()):raise ValueError('launch receipt mismatch')
 need={'schema':'ft_independent_raw_review/v1','reviewer':'/root/d06_server_review','scope':'raw measurement replay and source integrity; not formal acceptance','rid':RID,'batch':BATCH,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'runner_sha256':RUNNER_SHA,'base_runner_sha256':BASE_SHA,'wrapper_sha256':WRAPPER_SHA,'batch_pid':3817162,'receipt_sha256':RECEIPT_SHA,'formal_verdict':'pending_review','verdict':'PASS','gate_sha256':RAW_SHA,'candidate_binding_sha256':BINDING_SHA}
 review_doc=load(review_path)
 if any(review_doc.get(k)!=v for k,v in need.items()):raise ValueError('independent review binding mismatch')
 finite(gate); return d,gate,binding,wrapper
def prepare(directory,review,now=None):
 d,gate,binding,wrapper=validate(directory,review); out=d/'initial_metadata.json'
 if out.exists():raise FileExistsError('initial metadata retained')
 arms={name:arm(d,name) for name in ARMS}; archive=d/'batch.sh'
 if archive.exists() and archive.read_bytes()!=wrapper.read_bytes():raise ValueError('aliased wrapper mismatch')
 created=(now or datetime.now(timezone(timedelta(hours=8)))).strftime('%F %T CST')
 doc={'schema':'ft_round/v2','round_id':RID,'epoch':2,'card':'T16','title':'D06 full-tail gate','created_at':created,'parent':'E2-pre-gate-D00','base':{'repo':'fork/FreeToken','commit':PARENT,'epoch_baseline_commit':PARENT,'code_version':'E2-base@23f2e2c','branch':'e2/base','worktree':'/data2/FreeToken/wt/e2base','freetoken_file':'/data2/FreeToken/wt/e2base/python/freetoken/__init__.py'},'experimental':{'candidate_commit':CANDIDATE,'branch':'exp/e2d06','worktree':'/data2/FreeToken/wt/e2d06','freetoken_file':'/data2/FreeToken/wt/e2d06/python/freetoken/__init__.py','path_source':f'gate_batch{BATCH}.json'},'design':{'batch':BATCH,'gate':'D06','serve_order':list(ARMS),'epoch_baseline_commit':PARENT},'serve':{'arms':arms},'results':{'layer_major':gate['layer_major']},'first_shots':[{'profile':'layer_major','side':side,'case':'det','records':gate['layer_major'][side]['det']['records'],'claim':'timing preserved; not a performance verdict'} for side in ('D0','PROD')],'diagnostics':{'gate_path':f'gate_batch{BATCH}.json','gate_sha256':RAW_SHA,'candidate_binding_sha256':BINDING_SHA,'review_sha256':REVIEW_SHA,'receipt_sha256':RECEIPT_SHA,'batch_wrapper_sha256':WRAPPER_SHA,'anomaly_reference':'E2-R019-gate-D06 failed launch retained as anomaly only'},'sub_conclusions':[{'id':'SC1','status':'pending','text':'D06 gate evidence awaits formal independent review.'}],'verdict':'pending_review','proposed_verdict':None,'verdict_history':[],'retractions':[],'histories':[]}
 with out.open('xb') as f:f.write(jb(doc))
 if not archive.exists():
  with archive.open('xb') as f:f.write(wrapper.read_bytes())
 return {'initial_metadata_sha256':sha(out),'batch_sha256':sha(archive)}
def main():
 p=argparse.ArgumentParser();p.add_argument('--round-dir',type=Path);p.add_argument('--review',type=Path);a=p.parse_args()
 if not a.round_dir or not a.review:p.error('--round-dir and --review required')
 print(json.dumps(prepare(a.round_dir,a.review),sort_keys=True))
if __name__=='__main__':main()
