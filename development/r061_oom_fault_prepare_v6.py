#!/usr/bin/env python3
"""R061a v6 single-runtime launcher; v1/v2 remain frozen evidence."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path
RID='E2-R061a-OOM';CANDIDATE='608251f00deea85a0b12b31cc1f43725f45fbf9b';BASE='0aa23431e5b800797543bdecbf35a01045131d7d';ROOT=Path('/data2/FreeToken');ROUNDS=Path('/data2/_shared/runs/ft_rounds');HERE=Path(__file__).resolve().parent
V1=HERE/'r061_oom_fault_prepare_v1.py';R060=HERE/'r060_oom_t16_prepare_v1.py';OWNED=HERE/'r060_oom_owned_launch_v2.py';D07=HERE/'d07_g3g4_prepare.py';PAIR=HERE/'ft_batch_port_pair_v1.py';ORD3=HERE/'r046c_t06_ordinary_client_v3.py';ORD2=HERE/'r046c_t06_ordinary_client_v2.py';STARTUP=HERE/'r046c_t06_ordinary_startup_v4.py';HOOK=HERE/'r061_oom_backend_handle_hook_v1.py';GUARD=ROOT/'runs/dev_R046/r046b_section12_source_v4/cpu_guard/sitecustomize.py';NATIVE=ROOT/'runs/dev_OOM/r060_608251_native_provenance_20261007.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def md5(p):return hashlib.md5(Path(p).read_bytes()).hexdigest()
def closure():return (Path(__file__),V1,R060,OWNED,D07,PAIR,ORD3,ORD2,STARTUP,HOOK,GUARD)
def hashes():return {str(p):sha(p) for p in closure()}
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def runtime():
 m=load(V1,'r061a_v6_v1');rv=load(R060,'r061a_v6_r060');m.RID=RID;m.r060=lambda:rv;rv.RID=RID;return m,rv
def sealed(p):
 p=Path(p)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222:raise RuntimeError('R061a v6 sealed source/proof differs')
 return p
def inputs(r,a,q):
 out={}
 for n,p in {'reference':r,'affected':a,'queued':q}.items():
  p=Path(p);sealed(p);out[n]={'path':str(p.resolve()),'sha256':sha(p),'md5':md5(p)}
 if len({x['sha256'] for x in out.values()})!=1:raise RuntimeError('R061a v6 input SHA differs')
 return out
def argv(d,pair,origin=None):
 a=list((origin or d.serve_argv)(pair['api']))
 for f,v in (('--kv-reserve-tokens','98304'),('--max-seq-len-override','98304'),('--memory-ratio','0.88')):
  if f not in a:raise RuntimeError('R061a v6 argv flag absent')
  a[a.index(f)+1]=v
 if str(pair['api']) not in a:raise RuntimeError('R061a v6 API port not bound')
 return a
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,sort_keys=True);f.write('\n')
 p.chmod(0o600)
def epoch_observer_index(root,epoch,uid):
    """Index the immutable raw WorkerObserver PID directory without moving it."""
    root=Path(root); hits=[]
    for directory in sorted((root/'workers').glob('*')):
        inputs,tokens=directory/'inputs.jsonl',directory/'tokens.jsonl'
        if inputs.is_file() and tokens.is_file() and any(json.loads(line).get('uid')==uid for line in inputs.read_text().splitlines() if line):hits.append(directory)
    if len(hits)!=1:raise RuntimeError('R061a v6 UID has no unique raw worker observer')
    raw=hits[0]; index=root/f'epoch-{epoch}-uid-{uid}.json'
    if index.exists():raise RuntimeError('R061a v6 epoch index already exists')
    write(index,{'schema':'ft_r061_epoch_observer_index/v1','epoch':epoch,'uid':uid,'worker_dir':str(raw),'inputs_sha256':sha(raw/'inputs.jsonl'),'tokens_sha256':sha(raw/'tokens.jsonl'),'input_ids_paths_preserved':True})
    return raw
def observed_worker_births(lifecycle,observer_root,api_pid):
    """Use only PIDs with real WorkerObserver receipts, never every API-PGID helper."""
    rows=[];base=Path(observer_root)/'workers'
    for directory in sorted(base.glob('*')) if base.is_dir() else ():
        if not directory.name.isdecimal():continue
        birth=lifecycle.process_identity(int(directory.name))
        if birth is None or birth['pid']==api_pid:raise RuntimeError('R061a v6 observed worker birth missing')
        rows.append(birth)
    if not rows:raise RuntimeError('R061a v6 has no physical observer worker')
    return rows
def backend_handle_births(lifecycle,root,epoch):
    row=json.loads((Path(root)/'backend_handles'/f'epoch-{epoch}.json').read_text())
    if row.get('schema')!='ft_r061_backend_handle/v1' or row.get('epoch')!=epoch or not row.get('workers'):raise RuntimeError('R061a v6 BackendHandle record differs')
    births=[]
    for worker in row['workers']:
        current=lifecycle.process_identity(worker['pid'])
        if current is None or current.get('start_ticks')!=worker.get('start_ticks'):raise RuntimeError('R061a v6 BackendHandle worker birth differs')
        births.append(current)
    return births
def backend_startup_writer(original):
    """One startup writer for both FILEDRY and the formal child."""
    def writer(directory):
        value=original(directory);hook=Path(directory)/'runtime'/HOOK.name;shutil.copyfile(HOOK,hook);hook.chmod(0o600)
        target=Path(value['startup']);observer=Path(value['observer']);root=Path(directory)/'ordinary_observer'
        # Do not run observer.py as __main__: multiprocessing would then lose this wrapper
        # as its spawn main file and never enter our __mp_main__ branch.
        text=("import importlib.util,os,sys\n"
              "def _load(n,p):\n s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m\n"
              "_hook=_load('r061_handles',%r);_observer=_load('r061_observer',%r)\n"
              "if __name__=='__mp_main__':\n _observer.install(__import__('pathlib').Path(os.environ['R046C_T06_OBSERVER_DIR'])/'workers'/str(os.getpid()))\n"
              "elif __name__=='__main__':\n _hook.install(%r);sys.argv=[%r,'--observer-dir',os.environ['R046C_T06_OBSERVER_DIR'],'--',*sys.argv[1:]];_observer.main()\n")%(str(hook),str(observer),str(root),str(observer))
        target.chmod(0o600);target.write_text(text);target.chmod(0o600);return value
    return writer
def file_dry(root,wt,r,a,q):
 root=Path(root);wt=Path(wt)
 if root.exists() or (ROUNDS/RID).exists():raise RuntimeError('R061a v6 dry/formal path exists')
 if wt!=ROOT/'wt/e2oom-recovery' or subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()!=CANDIDATE:raise RuntimeError('R061a v6 candidate differs')
 ins=inputs(r,a,q)
 for p in closure()+(NATIVE,):sealed(p)
 root.mkdir(mode=0o700,parents=True);runtime_dir=root/'runtime'
 m,rv=runtime();m.write_fault_startup=backend_startup_writer(m.write_fault_startup);boot=m.write_fault_startup(root)
 copies=[]
 for p in closure():
  if p==GUARD:continue
  t=runtime_dir/p.name;shutil.copyfile(p,t);t.chmod(0o600)
  if sha(p)!=sha(t):raise RuntimeError('R061a v6 copy differs')
  copies.append({'source':str(p),'copy':str(t),'sha256':sha(t),'md5':md5(t),'mode':oct(t.stat().st_mode&0o777)})
 d=rv.load_d07(CANDIDATE,wt);mod=load(PAIR,'r061a_v6_pair');port=mod.dynamic_port();pair=mod.port_receipt(port);actual=argv(d,pair)
 env={'CUDA_VISIBLE_DEVICES':'','PYTHONPATH':str(GUARD.parent)+':'+str(wt/'python'),'MASTER_PORT':str(pair['tcpstore']),'FT_DEV_OOM_INJECT':'0'}
 imported=subprocess.check_output([str(ROOT/'venv/bin/python'),'-c','import freetoken,freetoken.kernel._cpu_moe,freetoken.kernel._pinned_tensor;print(freetoken.__file__)'],cwd=wt,env={**os.environ,**env},text=True).strip()
 if imported!=str(wt/'python/freetoken/__init__.py'):raise RuntimeError('R061a v6 import differs')
 probes=[]
 for n in ('ENV.json','SERVE_CMD.txt','serve.log','owned_process.json','health.before.json','health.restarting.json','health.ready.json','reference.api.json','affected.api.sse','queued.api.json','result.json','failed_harness.json','owned_cleanup.json'):
  p=root/'outputs'/n;p.parent.mkdir(parents=True,exist_ok=True);p.open('x').write('FILEDRY\n');p.chmod(0o600);probes.append(n)
 doc={'schema':'ft_r061_file_dry/v3','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'worktree':str(wt),'source_sha256':hashes(),'input_sha256':ins,'runtime_copies':copies,'bootstrap':boot,'actual_import':imported,'port_pair':pair,'actual_argv':actual,'environment':env,'output_probes':probes,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'popen_reached':False,'passed':True};write(root/'receipt.json',doc);(root/'receipt.json').chmod(0o444);return doc
def child(batch,wt,r,a,q):
    m,rv=runtime();d=rv.load_d07(CANDIDATE,Path(wt));d.RID=RID;pair_mod=load(PAIR,'r061a_v6_pair_run');p=pair_mod.dynamic_port();pair=pair_mod.port_receipt(p);oldargv,oldenv=d.serve_argv,d.clean_environment
    # v1 moved observer directories into epoch names.  That invalidates the absolute
    # input_ids_path stored in immutable input receipts.  V3 writes an index beside the
    # raw PID directory and returns that raw directory to the physical binder.
    # Resource trackers can share the API PGID but never create WorkerObserver receipts.
    # Select only physical Engine workers proven by their PID observer directory.
    m._epoch_observer=epoch_observer_index
    m._worker_births=lambda lifecycle,_pgid,_api_pid:backend_handle_births(lifecycle,ROUNDS/RID/'ordinary_observer',0)
    original_startup=m.write_fault_startup;m.write_fault_startup=backend_startup_writer(original_startup)
    rv.private_port_pair=lambda:pair
    d.serve_argv=lambda _:argv(d,pair,oldargv)
    d.clean_environment=lambda w,**kw:{**oldenv(w,**kw),'MASTER_PORT':str(pair['tcpstore'])}
    try:return m.run_fault_protocol(batch,CANDIDATE,Path(wt),r,a,q,d)
    finally:d.serve_argv,d.clean_environment=oldargv,oldenv;m.write_fault_startup=original_startup
def main(x=None):
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--batch',type=int,default=0);p.add_argument('--worktree',type=Path,required=True);p.add_argument('--reference-input',type=Path,required=True);p.add_argument('--affected-input',type=Path,required=True);p.add_argument('--queued-input',type=Path,required=True);a=p.parse_args(x)
 if a.file_dry_run:print(json.dumps(file_dry(a.file_dry_run,a.worktree,a.reference_input,a.affected_input,a.queued_input),sort_keys=True));return 0
 if a.run:print(json.dumps(child(a.batch,a.worktree,a.reference_input,a.affected_input,a.queued_input),sort_keys=True));return 0
 p.error('select --file-dry-run or --run')
if __name__=='__main__':raise SystemExit(main())
