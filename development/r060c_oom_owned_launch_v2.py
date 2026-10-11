#!/usr/bin/env python3
"""R060a: one outer GPU-lock owner around the reviewed full R059 runner."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys
from pathlib import Path

RID='E2-R060c-gate-OOM'; BASE='0aa23431e5b800797543bdecbf35a01045131d7d'; CANDIDATE='4c878f6b3251cca273d8548e7f5cf58a56711d3a'
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); HERE=Path(__file__).resolve().parent
V2=HERE/'r060c_oom_owned_launch_v1.py'; R060=HERE/'r060c_oom_t16_prepare_v1.py'; REVIEW=ROOT/'runs/dev_OOM/reviews/E2-R060c-gate-OOM-v1'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def v2(): return load(V2,'r060a_v2')
def r060(): return load(R060,'r060a_prepare')
def sources():
 m=v2(); return {str(Path(__file__).resolve()):sha(__file__),**m.source_hashes()}
def dry_dir(): return ROUNDS/'.dryrun_R060c_v2_E2-R060c-gate-OOM'
def dry_receipt(): return dry_dir()/'dry_run_receipt.json'
def write_new(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f:json.dump(d,f,sort_keys=True,indent=2);f.write('\n')
def sealed(p): return not(p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222)
def binding():
 wt=ROOT/'wt/e2oom-recovery-r061fix';r060().candidate_binding(CANDIDATE,wt);return wt

def actual_file_dry():
 """Invoke CandidateRunner.execute(file_dry_run=True); it stops before Popen."""
 if sys.platform!='linux':raise RuntimeError('Linux only')
 if dry_dir().exists() or (ROUNDS/RID).exists():raise RuntimeError('fresh hidden dry sibling required')
 m,wt=v2(),binding(); r=r060(); r.require_r060_native_provenance()
 for p in (Path(__file__),V2,R060):
  if not sealed(p):raise RuntimeError('R060a source must be frozen before FILEDRY')
 dry_dir().mkdir(mode=0o700); wrapper=dry_dir()/'dry_wrapper.sh';wrapper.write_text('#!/bin/sh\n');wrapper.chmod(0o600)
 runner=r.build_r059_oom_runner(CANDIDATE,wt,1,lambda:r.require_r060_native_provenance())
 runner.options.rid=RID; runner.options.file_dry_run=True; runner.options.dry_run_wrapper=str(wrapper)
 runner.directory=dry_dir()/'runner';runner.status=runner.directory/'status_batch1.json'
 runner.execute()
 for p in runner.directory.rglob('*'):
  if p.is_file() and (p.name.startswith(('runner_','base_runner_','batch')) or p.suffix in ('.py','.sh')):p.chmod(0o600)
 complete=json.loads((runner.directory/'file_dry_run_complete.json').read_text())
 doc={'schema':'ft_r060c_file_dry/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'script':str(Path(__file__).resolve()),'cwd':os.getcwd(),'uid':os.getuid(),'source_sha256':sources(),'native_sha256':sha(r.NATIVE_PROVENANCE),'runner_directory':str(runner.directory),'arms':complete['arms'],'passed':True,'formal_rid_directory_created':False,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'popen_reached':False}
 write_new(dry_receipt(),doc);dry_receipt().chmod(0o444);return doc

def admission():
 d=dry_receipt();review,pin=REVIEW/'review.json',REVIEW/'pin.json'
 if not all(sealed(p) for p in (d,review,pin)):raise RuntimeError('R060a sealed FILEDRY/R review/pin is absent or writable')
 x=json.loads(d.read_text());want={'schema':'ft_r060c_file_dry/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'script':str(Path(__file__).resolve()),'cwd':os.getcwd(),'uid':os.getuid(),'source_sha256':sources(),'passed':True}
 if any(x.get(k)!=v for k,v in want.items()) or any(x.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated','popen_reached')):raise RuntimeError('R060a FILEDRY binding differs')
 rv,pv=json.loads(review.read_text()),json.loads(pin.read_text())
 if rv.get('rid')!=RID or rv.get('verdict')!='PASS' or rv.get('approved') is not True or rv.get('source_sha256')!=sources() or rv.get('file_dry_sha256')!=sha(d) or pv.get('review_sha256')!=sha(review):raise RuntimeError('R060a R review/pin binding differs')
 return {'file_dry_sha256':sha(d),'review_sha256':sha(review)}
def argv(batch,receipt):return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]

def run_owned_runner(runner,owner,d07):
 """Only outer controller owns O_EXCL; inner runner verifies and never opens it."""
 base=type(runner)
 class OuterOwned(base):
  def lock_take(self):
   lock=d07.LOCK
   if not lock.exists() or lock.is_symlink() or lock.stat().st_ino!=self._owner['lock_inode'] or lock.read_text()!=self._owner['lock_token']:raise RuntimeError('R060a outer lock ownership changed')
   self.token,self.lock_inode=self._owner['lock_token'],self._owner['lock_inode']
  def lock_release(self): return None
 runner.__class__=OuterOwned;runner._owner=owner;return runner.execute()

def controller():
 if sys.platform!='linux':raise RuntimeError('Linux only')
 proof=admission();d=v2().load_d07();binding();r060().require_r060_native_provenance()
 if d.LOCK.exists() or d.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists')
 owned=d.load_owned_lifecycle();h=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r060a_atomic');b=h.next_batch(ROUNDS);p=ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{b}.json';a=argv(b,p);got=owned.reserve_process(h,b,RID,a,p,{'schema':'ft_r060c_owned_launch/v1','state':'reserved','rid':RID,'batch':b,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(a),'startup_proof':proof});birth=owned.process_identity(got['batch_pid']);return d.publish_child_binding(p,got,{k:birth[k] for k in ('pid','start_ticks','execution_id')},lifecycle=owned)
def child(batch,receipt):
 proof=admission();d=v2().load_d07();wt=binding();d.require_child_receipt(receipt,batch,wt,ROUNDS,rid=RID,expected_argv=argv(batch,receipt),schema='ft_r060c_owned_launch/v1');owner=d.take_d07_gpu_lock(RID,batch);runner=None
 try:
  d.require_gpu_idle();runner=r060().build_r059_oom_runner(CANDIDATE,wt,batch,lambda:r060().require_r060_native_provenance());runner.options.rid=RID;runner.directory=ROUNDS/RID;runner.status=runner.directory/f'status_batch{batch}.json';run_owned_runner(runner,owner,d);return {'proposed_verdict':'kept','startup_proof':proof}
 finally:
  if runner is None or runner.proc is None:d.release_d07_gpu_lock(owner)
def main(a=None):
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);x=p.parse_args(a)
 if x.file_dry_run:print(json.dumps(actual_file_dry(),sort_keys=True));return
 if x.run:print(json.dumps(child(x.batch,x.launch_receipt) if x.owned_child else controller(),sort_keys=True));return
 print(json.dumps({'rid':RID,'state':'prepared'}))
if __name__=='__main__':main()
