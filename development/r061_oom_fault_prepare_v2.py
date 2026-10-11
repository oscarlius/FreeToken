#!/usr/bin/env python3
"""R061 v2: sealed-admission wrapper around the tested physical OOM protocol.

The v1 runner is immutable.  This entry supplies the missing launch identity,
file-dry and failure-terminal boundaries before delegating its measurement body.
"""
from __future__ import annotations
import argparse, getpass, hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

RID='E2-R061-OOM'; BASE='0aa23431e5b800797543bdecbf35a01045131d7d'; CANDIDATE='608251f00deea85a0b12b31cc1f43725f45fbf9b'
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); HERE=Path(__file__).resolve().parent
V1=HERE/'r061_oom_fault_prepare_v1.py'; R060=HERE/'r060_oom_owned_launch_v2.py'; D07=HERE/'d07_g3g4_prepare.py'; PAIR=HERE/'ft_batch_port_pair_v1.py'; ORDINARY=HERE/'r046c_t06_ordinary_client_v3.py'; STARTUP=HERE/'r046c_t06_ordinary_startup_v4.py'
NATIVE=ROOT/'runs/dev_OOM/r060_608251_native_provenance_20261007.json'; GUARD=ROOT/'runs/dev_R046/r046b_section12_source_v4/cpu_guard/sitecustomize.py'; REVIEW_ROOT=ROOT/'runs/dev_OOM/reviews/E2-R061-OOM-v2'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def md5(p): return hashlib.md5(Path(p).read_bytes()).hexdigest()
def sources(): return (Path(__file__),V1,R060,D07,PAIR,ORDINARY,STARTUP,GUARD)
def source_hashes(): return {str(p):sha(p) for p in sources()}
def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,sort_keys=True,indent=2);f.write('\n')
    path.chmod(0o600)
def load(path,name):
    if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 v2 source unavailable')
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def v1(): return load(V1,'r061_v2_v1')
def r060(): return load(R060,'r061_v2_r060')
def sealed(path,label):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError(f'R061 v2 {label} is absent or writable')
    return path
def candidate(worktree):
    worktree=Path(worktree)
    if worktree != ROOT/'wt/e2oom-recovery' or worktree.is_symlink(): raise RuntimeError('R061 v2 candidate worktree differs')
    if subprocess.check_output(['git','-C',str(worktree),'rev-parse','HEAD'],text=True).strip()!=CANDIDATE: raise RuntimeError('R061 v2 candidate HEAD differs')
    if subprocess.check_output(['git','-C',str(worktree),'status','--porcelain','--untracked-files=no'],text=True): raise RuntimeError('R061 v2 candidate is dirty')
    return worktree
def input_hashes(reference,affected,queued):
    rows={}
    for key,path in {'reference':reference,'affected':affected,'queued':queued}.items():
        path=Path(path)
        if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 v2 current input is unavailable')
        rows[key]={'path':str(path.resolve()),'sha256':sha(path),'md5':md5(path)}
    if len({x['sha256'] for x in rows.values()})!=1: raise RuntimeError('R061 v2 three current input hashes differ')
    return rows
def actual_argv(d07,pair,origin=None):
    argv=list((origin or d07.serve_argv)(pair['api']))
    for flag,value in (('--kv-reserve-tokens','98304'),('--max-seq-len-override','98304'),('--memory-ratio','0.88')):
        if flag not in argv: raise RuntimeError('R061 v2 actual serve argv lacks required setting')
        argv[argv.index(flag)+1]=value
        if argv[argv.index(flag)+1]!=value: raise RuntimeError('R061 v2 actual serve argv differs')
    return argv
def require_admission(worktree,reference,affected,queued,dry,review,pin):
    worktree=candidate(worktree); inputs=input_hashes(reference,affected,queued)
    for p,label in ((NATIVE,'native proof'),(dry,'FILEDRY'),(review,'review'),(pin,'pin')): sealed(p,label)
    native=json.loads(NATIVE.read_text()); dry_doc=json.loads(Path(dry).read_text()); review_doc=json.loads(Path(review).read_text()); pin_doc=json.loads(Path(pin).read_text())
    if native.get('candidate_commit')!=CANDIDATE or sha(NATIVE)!='0d09b38c508783c0dd9d9e743a6d9174e3f126667791e1d40cd53f5def1eeb3d': raise RuntimeError('R061 v2 native proof differs')
    expected={'schema':'ft_r061_file_dry/v2','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'worktree':str(worktree),'source_sha256':source_hashes(),'input_sha256':inputs,'passed':True}
    if any(dry_doc.get(k)!=v for k,v in expected.items()) or any(dry_doc.get(k) is not False for k in ('service_started','requests_sent','gpu_lock_taken','batch_allocated','formal_rid_directory_created','popen_reached')): raise RuntimeError('R061 v2 FILEDRY binding differs')
    if (review_doc.get('schema')!='ft_r061_startup_review/v2' or review_doc.get('rid')!=RID or review_doc.get('candidate_commit')!=CANDIDATE or review_doc.get('parent_commit')!=BASE or review_doc.get('approved') is not True or review_doc.get('verdict')!='PASS' or review_doc.get('source_sha256')!=source_hashes() or review_doc.get('input_sha256')!=inputs or review_doc.get('file_dry_sha256')!=sha(dry) or pin_doc.get('schema')!='ft_r061_startup_pin/v2' or pin_doc.get('approved') is not True or pin_doc.get('verdict')!='PASS' or pin_doc.get('review_sha256')!=sha(review) or pin_doc.get('file_dry_sha256')!=sha(dry)): raise RuntimeError('R061 v2 sealed review/pin differs')
    return {'native_sha256':sha(NATIVE),'file_dry_sha256':sha(dry),'review_sha256':sha(review),'pin_sha256':sha(pin),'input_sha256':inputs}
def copy_source(src,target):
    sealed(src,'runtime source'); shutil.copyfile(src,target);target.chmod(0o600)
    if sha(src)!=sha(target) or md5(src)!=md5(target): raise RuntimeError('R061 v2 runtime copy differs')
    return {'source':str(src),'copy':str(target),'sha256':sha(target),'md5':md5(target),'mode':oct(target.stat().st_mode&0o777)}
def pair():
    mod=load(PAIR,'r061_v2_pair'); api=mod.dynamic_port();value=mod.port_receipt(api)
    if value.get('api')!=api or value.get('tcpstore')!=api+1: raise RuntimeError('R061 v2 port pair differs')
    return value
def file_dry(directory,worktree,reference,affected,queued):
    if sys.platform!='linux': raise RuntimeError('R061 v2 FILEDRY requires Linux')
    root=Path(directory)
    if root.exists() or root.is_symlink() or (ROUNDS/RID).exists(): raise RuntimeError('R061 v2 dry/formal path exists')
    worktree=candidate(worktree);inputs=input_hashes(reference,affected,queued)
    for p in sources()+ (NATIVE,): sealed(p,'source')
    root.mkdir(mode=0o700,parents=True); runtime=root/'runtime';runtime.mkdir(mode=0o700)
    copies=[copy_source(p,runtime/p.name) for p in sources() if p!=GUARD]
    d07=v1().r060().load_d07(CANDIDATE,worktree);ports=pair();argv=actual_argv(d07,ports)
    env={'CUDA_VISIBLE_DEVICES':'','PYTHONPATH':str(GUARD.parent)+':'+str(worktree/'python'),'MASTER_PORT':str(ports['tcpstore']),'FT_DEV_OOM_INJECT':'0','FT_DEV_ROUTE_TRACE':'0','FT_DEV_PAUSE_ENDPOINT':'0','FT_DEV_D0':'0'}
    imported=subprocess.check_output([str(ROOT/'venv/bin/python'),'-c','import freetoken,freetoken.kernel._cpu_moe,freetoken.kernel._pinned_tensor;print(freetoken.__file__)'],cwd=worktree,env={**os.environ,**env},text=True).strip()
    if imported!=str(worktree/'python/freetoken/__init__.py'): raise RuntimeError('R061 v2 candidate import differs')
    probes=[]
    for name in ('ENV.json','SERVE_CMD.txt','serve.log','owned_process.json','health.before.json','health.restarting.json','health.ready.json','reference.api.json','affected.api.sse','queued.api.json','result.json','failed_harness.json','owned_cleanup.json'):
        p=root/'outputs'/name;p.parent.mkdir(parents=True,exist_ok=True);p.open('x').write('R061 FILEDRY ONLY\n');p.chmod(0o600);probes.append({'path':name,'sha256':sha(p),'mode':oct(p.stat().st_mode&0o777)})
    doc={'schema':'ft_r061_file_dry/v2','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':BASE,'worktree':str(worktree),'cwd':os.getcwd(),'uid':os.getuid(),'user':getpass.getuser(),'source_sha256':source_hashes(),'input_sha256':inputs,'runtime_copies':copies,'actual_import':imported,'port_pair':ports,'actual_argv':argv,'environment':env,'output_probes':probes,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'popen_reached':False,'passed':True};write_new(root/'receipt.json',doc);(root/'receipt.json').chmod(0o444);return doc
def child_argv(batch,receipt,worktree,reference,affected,queued,dry,review,pin): return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--worktree',str(worktree),'--reference-input',str(reference),'--affected-input',str(affected),'--queued-input',str(queued),'--file-dry-receipt',str(dry),'--startup-review',str(review),'--startup-pin',str(pin)]
def controller(worktree,reference,affected,queued,dry,review,pin):
    proof=require_admission(worktree,reference,affected,queued,dry,review,pin);d=v1().r060().load_d07(CANDIDATE,Path(worktree))
    if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists')
    owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r061_v2_atomic');batch=helper.next_batch(ROUNDS);receipt=ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{batch}.json';argv=child_argv(batch,receipt,worktree,reference,affected,queued,dry,review,pin)
    row=owned.reserve_process(helper,batch,RID,argv,receipt,{'schema':'ft_r061_owned_launch/v2','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'admission':proof,'controller':d.process_birth()});birth=owned.process_identity(row['batch_pid'])
    if birth is None: raise RuntimeError('R061 v2 child birth missing')
    return d.publish_child_binding(receipt,row,{k:birth[k] for k in ('pid','start_ticks','execution_id')},lifecycle=owned)
def terminal(run,batch,owner,error,cleanup):
    write_new(run/'failed_harness.json',{'schema':'ft_r061_failed_harness/v2','rid':RID,'batch':batch,'error_type':type(error).__name__,'error':str(error),'raw_preserved':True,'cleanup_attempted':True,'cleanup_succeeded':cleanup})
    if cleanup: write_new(run/'owned_cleanup.json',{'schema':'ft_r061_owned_cleanup/v2','rid':RID,'batch':batch,'owner':owner,'lock_released':True})
def child(batch,receipt,worktree,reference,affected,queued,dry,review,pin):
    proof=require_admission(worktree,reference,affected,queued,dry,review,pin);m=v1();rv=m.r060();d=rv.load_d07(CANDIDATE,Path(worktree));d.require_child_receipt(receipt,batch,Path(worktree),ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt,worktree,reference,affected,queued,dry,review,pin),schema='ft_r061_owned_launch/v2')
    # v1 owns the exact physical API/SSE protocol; patch its service seam with the v2 98K/.88/TCPStore contract.
    old_argv,old_env=d.serve_argv,d.clean_environment
    def env(wt,**kw):
        value=old_env(wt,**kw);value['MASTER_PORT']=str(current_pair['tcpstore']);return value
    current_pair=pair();rv.private_port_pair=lambda:current_pair;d.serve_argv=lambda _port:actual_argv(d, current_pair, old_argv);d.clean_environment=env
    run=ROUNDS/RID
    try: return {**m.run_fault_protocol(batch,CANDIDATE,Path(worktree),reference,affected,queued,d),'admission':proof}
    except BaseException as error:
        cleanup=not d.LOCK.exists();terminal(run,batch,None,error,cleanup);raise
    finally: d.serve_argv, d.clean_environment=old_argv,old_env
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--file-dry-run',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--worktree',type=Path,required=True);p.add_argument('--reference-input',type=Path,required=True);p.add_argument('--affected-input',type=Path,required=True);p.add_argument('--queued-input',type=Path,required=True);p.add_argument('--file-dry-receipt',type=Path);p.add_argument('--startup-review',type=Path);p.add_argument('--startup-pin',type=Path);a=p.parse_args(argv)
    if a.file_dry_run: print(json.dumps(file_dry(a.file_dry_run,a.worktree,a.reference_input,a.affected_input,a.queued_input),sort_keys=True));return 0
    if not a.run: p.error('use --file-dry-run or --run')
    if not all((a.file_dry_receipt,a.startup_review,a.startup_pin)): p.error('--run requires sealed FILEDRY/review/pin')
    value=child(a.batch,a.launch_receipt,a.worktree,a.reference_input,a.affected_input,a.queued_input,a.file_dry_receipt,a.startup_review,a.startup_pin) if a.owned_child else controller(a.worktree,a.reference_input,a.affected_input,a.queued_input,a.file_dry_receipt,a.startup_review,a.startup_pin);print(json.dumps(value,sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
