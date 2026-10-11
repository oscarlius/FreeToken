#!/usr/bin/env python3
"""R061c v1 controller with hash-bound real R060c kept admission: strict sealed admission around the v3 physical body.

The v3 module is intentionally only a protocol body.  This module is the sole
formal entry: it rechecks the sealed current source/input/FILEDRY/review/pin
closure before either reserving a batch or accepting a child receipt.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, sys
from pathlib import Path

RID='E2-R061c-OOM'; BASE='0aa23431e5b800797543bdecbf35a01045131d7d'; CANDIDATE='4c878f6b3251cca273d8548e7f5cf58a56711d3a'
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); HERE=Path(__file__).resolve().parent
V3=HERE/'r061c_oom_runtime_prepare_v1.py'; NATIVE=ROOT/'runs/dev_OOM/r060c_4c878f6_native_provenance_20261008.json'
NATIVE_SHA='e9cd249ad68029528688644a575d3b9411e69ba6a259b35b133346ecf2785ee8'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def md5(p): return hashlib.md5(Path(p).read_bytes()).hexdigest()
def write_new(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f: json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
 p.chmod(0o600)
def sealed(p,label='artifact'):
 p=Path(p)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222: raise RuntimeError(f'R061c v1 {label} is absent or writable')
 return p
def require_r060c_kept():
 rid = 'E2-R060c-gate-OOM'
 pin = sealed(ROOT / 'runs/plan_batches/closed_round_pins' / (rid + '.json'), 'R060c kept pin')
 value = json.loads(pin.read_text())
 if (value.get('schema') != 'ft_closed_round_pin/v1' or value.get('rid') != rid
     or value.get('verdict') != 'kept' or value.get('candidate_commit') != CANDIDATE):
  raise RuntimeError('R061c requires the current candidate R060c kept closure')
 directory = ROUNDS / rid
 round_path = sealed(directory / 'round.json', 'R060c round')
 manifest = sealed(directory / 'MANIFEST.sha256', 'R060c manifest')
 if value.get('round_sha256') != sha(round_path) or value.get('manifest_sha256') != sha(manifest):
  raise RuntimeError('R061c R060c closed metadata SHA differs')
 doc = json.loads(round_path.read_text())
 if (doc.get('round_id') != rid or doc.get('verdict') != 'kept'
     or doc.get('base', {}).get('commit') != CANDIDATE
     or doc.get('base', {}).get('parent_commit') != BASE):
  raise RuntimeError('R061c R060c closed round identity differs')
 return {'rid': rid, 'verdict': 'kept', 'candidate_commit': CANDIDATE,
         'pin_path': str(pin), 'pin_sha256': sha(pin),
         'round_sha256': sha(round_path), 'manifest_sha256': sha(manifest),
         'independent_review_sha256': value.get('independent_review_sha256')}

def load():
 sealed(V3,'v3 body');s=importlib.util.spec_from_file_location('r061c_v1_body',V3);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def closure(): return (Path(__file__).resolve(),)+load().closure()+(NATIVE,)
def source_hashes(): return {str(p):sha(p) for p in closure()}
def candidate(wt):
 wt=Path(wt)
 if wt!=ROOT/'wt/e2oom-recovery-r061fix' or wt.is_symlink(): raise RuntimeError('R061c v1 candidate worktree differs')
 import subprocess
 if subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()!=CANDIDATE: raise RuntimeError('R061c v1 candidate HEAD differs')
 if subprocess.check_output(['git','-C',str(wt),'status','--porcelain','--untracked-files=no'],text=True): raise RuntimeError('R061c v1 candidate is dirty')
 return wt
def input_hashes(r,a,q):
 rows={}
 for name,path in {'reference':r,'affected':a,'queued':q}.items():
  path=sealed(path,f'{name} input');rows[name]={'path':str(path.resolve()),'sha256':sha(path),'md5':md5(path)}
 if len({x['sha256'] for x in rows.values()})!=1: raise RuntimeError('R061c v1 input SHA differs')
 return rows
def file_dry(root,wt,r,a,q):
 """Run the exact v3 writer/bootstrap path, then seal v4's outer identity receipt."""
 if sys.platform!='linux': raise RuntimeError('R061c v1 FILEDRY requires Linux')
 gate_proof=require_r060c_kept()
 root=Path(root)
 if root.exists() or root.is_symlink() or (ROUNDS/RID).exists(): raise RuntimeError('R061c v1 dry/formal path exists')
 wt=candidate(wt);ins=input_hashes(r,a,q)
 for p in closure(): sealed(p,'source/proof')
 if sha(NATIVE)!=NATIVE_SHA: raise RuntimeError('R061c v1 native proof SHA differs')
 root.mkdir(mode=0o700,parents=True)
 body=load(); inner=body.file_dry(root/'protocol_writer',wt,r,a,q)
 copied=[]
 runtime=root/'runtime';runtime.mkdir(mode=0o700)
 for src in closure():
  if src==body.GUARD: continue
  dst=runtime/src.name;shutil.copyfile(src,dst);dst.chmod(0o600)
  if sha(src)!=sha(dst) or md5(src)!=md5(dst): raise RuntimeError('R061c v1 runtime source copy differs')
  copied.append({'source':str(src),'copy':str(dst),'sha256':sha(dst),'md5':md5(dst),'mode':oct(dst.stat().st_mode&0o777)})
 doc={'r060c_kept':gate_proof,'schema':'ft_r061c_file_dry/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'worktree':str(wt),'source_sha256':source_hashes(),'input_sha256':ins,'native_proof_sha256':sha(NATIVE),'protocol_writer_receipt':str(root/'protocol_writer/receipt.json'),'protocol_writer_sha256':sha(root/'protocol_writer/receipt.json'),'runtime_copies':copied,'bootstrap':inner['bootstrap'],'actual_import':inner['actual_import'],'port_pair':inner['port_pair'],'actual_argv':inner['actual_argv'],'environment':inner['environment'],'output_probes':inner['output_probes'],'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'popen_reached':False,'passed':True}
 write_new(root/'receipt.json',doc);(root/'receipt.json').chmod(0o444);return doc
def require_admission(wt,r,a,q,dry,review,pin):
 gate_proof=require_r060c_kept()
 wt=candidate(wt);ins=input_hashes(r,a,q)
 for p,name in ((NATIVE,'native proof'),(dry,'FILEDRY'),(review,'review'),(pin,'pin')): sealed(p,name)
 if sha(NATIVE)!=NATIVE_SHA: raise RuntimeError('R061c v1 native proof differs')
 drydoc=json.loads(Path(dry).read_text()); rev=json.loads(Path(review).read_text()); pindoc=json.loads(Path(pin).read_text())
 expected={'r060c_kept':gate_proof,'schema':'ft_r061c_file_dry/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'worktree':str(wt),'source_sha256':source_hashes(),'input_sha256':ins,'native_proof_sha256':NATIVE_SHA,'passed':True}
 if any(drydoc.get(k)!=v for k,v in expected.items()) or any(drydoc.get(k) is not False for k in ('service_started','requests_sent','gpu_lock_taken','batch_allocated','formal_rid_directory_created','popen_reached')): raise RuntimeError('R061c v1 FILEDRY binding differs')
 boot=drydoc.get('bootstrap')
 if not isinstance(boot,dict): raise RuntimeError('R061c v1 FILEDRY bootstrap absent')
 for path_key,sha_key in (('startup','startup_sha256'),('observer','observer_sha256'),('hook','hook_sha256')):
  path=Path(boot.get(path_key,''))
  if path.is_symlink() or not path.is_file() or sha(path)!=boot.get(sha_key): raise RuntimeError('R061c v1 FILEDRY bootstrap SHA differs')
 if (rev.get('r060c_kept')!=gate_proof or rev.get('schema')!='ft_r061c_startup_review/v1' or rev.get('rid')!=RID or rev.get('candidate_commit')!=CANDIDATE or rev.get('parent_commit')!=BASE or rev.get('approved') is not True or rev.get('verdict')!='PASS' or rev.get('source_sha256')!=source_hashes() or rev.get('input_sha256')!=ins or rev.get('file_dry_sha256')!=sha(dry) or pindoc.get('schema')!='ft_r061c_startup_pin/v1' or pindoc.get('rid')!=RID or pindoc.get('approved') is not True or pindoc.get('verdict')!='PASS' or pindoc.get('review_sha256')!=sha(review) or pindoc.get('file_dry_sha256')!=sha(dry)): raise RuntimeError('R061c sealed review/pin binding differs')
 return {'r060c_kept':gate_proof,'native_sha256':NATIVE_SHA,'file_dry_sha256':sha(dry),'review_sha256':sha(review),'pin_sha256':sha(pin),'input_sha256':ins}
def child_argv(batch,receipt,wt,r,a,q,dry,review,pin): return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--worktree',str(wt),'--reference-input',str(r),'--affected-input',str(a),'--queued-input',str(q),'--file-dry-receipt',str(dry),'--startup-review',str(review),'--startup-pin',str(pin)]
def controller(wt,r,a,q,dry,review,pin):
 proof=require_admission(wt,r,a,q,dry,review,pin);body=load();m,rv=body.runtime();d=rv.load_d07(CANDIDATE,Path(wt))
 if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists')
 owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r061c_v1_atomic');batch=helper.next_batch(ROUNDS);receipt=ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{batch}.json';argv=child_argv(batch,receipt,wt,r,a,q,dry,review,pin)
 row=owned.reserve_process(helper,batch,RID,argv,receipt,{'schema':'ft_r061c_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'admission':proof,'controller':d.process_birth()});birth=owned.process_identity(row['batch_pid'])
 if birth is None: raise RuntimeError('R061c v1 child birth missing')
 return d.publish_child_binding(receipt,row,{k:birth[k] for k in ('pid','start_ticks','execution_id')},lifecycle=owned)
def child(batch,receipt,wt,r,a,q,dry,review,pin):
 proof=require_admission(wt,r,a,q,dry,review,pin);body=load();m,rv=body.runtime();d=rv.load_d07(CANDIDATE,Path(wt));d.RID=RID
 d.require_child_receipt(receipt,batch,Path(wt),ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt,wt,r,a,q,dry,review,pin),schema='ft_r061c_owned_launch/v1')
 run=ROUNDS/RID
 try: return {**body.child(batch,wt,r,a,q),'admission':proof}
 except BaseException as error:
  # Preserve the original exception and raw service logs.  A failed cleanup never removes a lock.
  cleanup=not d.LOCK.exists()
  if run.exists() and not (run/'failed_harness.json').exists():
   write_new(run/'failed_harness.json',{'schema':'ft_r061c_failed_harness/v1','rid':RID,'batch':batch,'error_type':type(error).__name__,'error':str(error),'raw_preserved':True,'cleanup_attempted':True,'cleanup_succeeded':cleanup})
   if cleanup: write_new(run/'owned_cleanup.json',{'schema':'ft_r061c_owned_cleanup/v1','rid':RID,'batch':batch,'lock_released':True})
  raise
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--worktree',type=Path,required=True);p.add_argument('--reference-input',type=Path,required=True);p.add_argument('--affected-input',type=Path,required=True);p.add_argument('--queued-input',type=Path,required=True);p.add_argument('--file-dry-receipt',type=Path);p.add_argument('--startup-review',type=Path);p.add_argument('--startup-pin',type=Path);x=p.parse_args(argv)
 if x.file_dry_run:
  if x.run or x.owned_child or x.batch is not None or x.launch_receipt: p.error('FILEDRY accepts no launch arguments')
  print(json.dumps(file_dry(x.file_dry_run,x.worktree,x.reference_input,x.affected_input,x.queued_input),sort_keys=True));return 0
 if not x.run or not all((x.file_dry_receipt,x.startup_review,x.startup_pin)): p.error('--run requires sealed FILEDRY/review/pin')
 value=child(x.batch,x.launch_receipt,x.worktree,x.reference_input,x.affected_input,x.queued_input,x.file_dry_receipt,x.startup_review,x.startup_pin) if x.owned_child else controller(x.worktree,x.reference_input,x.affected_input,x.queued_input,x.file_dry_receipt,x.startup_review,x.startup_pin)
 print(json.dumps(value,sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
