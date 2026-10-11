#!/usr/bin/env python3
"""R066 3/6 binding over immutable J/D07 lifecycle; root controls admission and launch."""
from __future__ import annotations
import argparse, getpass, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2oom-protocol-restart'
RID='E2-R066-d16-discriminate-v2'; CANDIDATE='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'; DEV=ROOT/'runs/dev_D16'; ROUNDS=Path('/data2/_shared/runs/ft_rounds')
AUTH=ROOT/'runs/plan_batches/R066_DISCRIMINATE_V2_AUTHORIZATION_20261009.md'; AUTH_SHA='928accf380c55e0d463ea65cd715430b7bfe8b496bfe8a646ebb12b548ef7b26'
PROOF=DEV/'R066_D_EXISTING_SCHEDULE_GEOMETRY_20261009_v1.json'; PROOF_SHA='df6b05a1f4e147c2ff00711d87fb005bdf40051b42d77415596a0c4a1e3fc176'
J_PATH=HERE.parent/'r040j_api_d16_v1/r040j_api_d16.py'; J_SHA='474915503b87d1f80d0bc6fe6245b6b365df09071c9ae0a53e48da0d998ac734'; SCHEDULE=HERE/'d_existing_schedule.json'
HISTORICAL_2_5={'path':str(DEV/'r066_d16_filedry_20261009_084844'),'status':'historical_incomplete_2_services_5_calls','source_manifest_sha256':'41bc80c5a87b376c0039c09e4b55a99210f99c2bb52203278e00d87f61355efc','preflight_sha256':'6ed5e01fcd2447157d346a45244573d7bd3752541c4edf3eebfd3164e328f325','filedry_sha256':'12fbfddcf391e425f4a197b06c5c2bc31801145cc1b0bcab2298fe50ede14fc8'}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); assert s.loader; s.loader.exec_module(m); return m
if sha(J_PATH)!=J_SHA: raise RuntimeError('frozen J differs')
j=load(J_PATH,'r066_immutable_j'); write=j.write
def candidate():
 if WT.is_symlink() or sha(j.D07)!=j.D07_SHA or sha(j.PAIR)!=j.PAIR_SHA: raise RuntimeError('pinned J/D07 lifecycle differs')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip(); dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 if head!=CANDIDATE or dirty: raise RuntimeError('clean R066 candidate required')
 return {'worktree':str(WT),'commit':head,'tracked_clean':True}
def geometry():
 if PROOF.is_symlink() or not PROOF.is_file() or PROOF.stat().st_mode&0o222 or sha(PROOF)!=PROOF_SHA: raise RuntimeError('existing D geometry proof differs')
 proof=json.loads(PROOF.read_text()); rows=json.loads(SCHEDULE.read_text())
 if proof.get('actual_existing_parse_admit')!='PASS' or proof.get('candidate_commit')!=CANDIDATE or proof.get('existing_schedule')!=rows or proof.get('rewind_alignment')!=64 or proof.get('fla_chunk_size')!=64: raise RuntimeError('D geometry proof/source differs')
 name='r066_schedule_admit'; spec=importlib.util.spec_from_file_location(name,WT/'python/freetoken/scheduler/dev_prefill_schedule.py'); module=importlib.util.module_from_spec(spec); sys.modules[name]=module; assert spec.loader; spec.loader.exec_module(module); schedule=module.parse(SCHEDULE.read_text())
 module.admit(schedule,prompt_len=8257,cached_len=0,device_len=8257,request_count=1,first_generation=True,has_multimodal=False,disk_ple=False,rewind_alignment=64,fla_chunk_size=64)
 return {'path':str(SCHEDULE),'sha256':sha(SCHEDULE),'proof_path':str(PROOF),'proof_sha256':PROOF_SHA,'rows':rows,'cold_only':True}
def sources():
 r065=HERE.parent/'r065_d16_discriminate_v1'; files={p.name:p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.md')}
 files.update({'authorization.md':AUTH,'geometry_proof.json':PROOF,'frozen_j.py':J_PATH,'d07.py':j.D07,'port_pair.py':j.PAIR,'r065_sdk_adapter.py':r065/'sdk_adapter.py','r065_inputs.json':r065/'inputs.json','sdk_completions.py':j.EVAL/'sdk_completions.py'})
 if any(p.is_symlink() or not p.is_file() for p in files.values()): raise RuntimeError('source closure unavailable')
 return files
def child_argv(batch,receipt,admit): return [str(j.VENV/'bin/python'),str(HERE/'r066_runner.py'),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--admission',str(admit)]
def plan():
 if Path.cwd()!=WT or getpass.getuser()!='dell': raise RuntimeError('canonical cwd/user required')
 if AUTH.is_symlink() or AUTH.stat().st_mode&0o222 or sha(AUTH)!=AUTH_SHA: raise RuntimeError('authorization receipt differs')
 port=j.load(j.PAIR,'r066_pair_plan').dynamic_port(); command=j.serve_argv(port)
 return {'schema':'ft_r066_d16_plan/v2','rid':RID,'candidate':candidate(),'scope':{'services':3,'calls':6},'source_sha256':{k:sha(v) for k,v in sources().items()},'serve_argv':command,'serve_argv_sha256':j.argv_sha(command),'port_pair':j.load(j.PAIR,'r066_pair_receipt').port_receipt(port),'authorization':{'path':str(AUTH),'sha256':AUTH_SHA},'geometry':geometry(),'historical_incomplete':HISTORICAL_2_5,'canonical_cwd':str(WT),'actual_child_entry':str(HERE/'r066_runner.py'),'no_readiness_generation':True,'original_token_counts':[8257,512]}
def freeze(out):
 runtime=out/'runtime_sources'; runtime.mkdir(); manifest={}
 for name,path in sources().items(): target=runtime/name; shutil.copyfile(path,target); target.chmod(0o444); manifest[name]=sha(target)
 write(out/'source_manifest.json',{'schema':'ft_r066_source_manifest/v1','files':manifest}); (out/'source_manifest.json').chmod(0o444)
def admission(path):
 if path is None or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('immutable root admission required')
 doc=json.loads(path.read_text()); current={k:sha(v) for k,v in sources().items()}; needed={'rid':RID,'candidate_commit':CANDIDATE,'worktree':str(WT),'cwd':str(Path.cwd()),'user':getpass.getuser(),'source_sha256':current}
 if any(doc.get(k)!=v for k,v in needed.items()): raise RuntimeError('admission identity/source differs')
 for kind in ('filedry','preflight','source_manifest','independent_review'):
  p=Path(doc[kind+'_path'])
  if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 or sha(p)!=doc[kind+'_sha256']: raise RuntimeError('unsafe/stale admission '+kind)
 review=json.loads(Path(doc['independent_review_path']).read_text()); fd=json.loads(Path(doc['filedry_path']).read_text()); manifest=json.loads(Path(doc['source_manifest_path']).read_text()); preflight=json.loads(Path(doc['preflight_path']).read_text())
 if fd.get('rid')!=RID or fd.get('no_formal_rid_batch_lock_popen_or_request') is not True or manifest.get('files')!=current or preflight.get('source_sha256')!=current or preflight.get('scope')!={'services':3,'calls':6} or preflight.get('geometry')!=geometry() or review.get('schema')!='ft_r066_d16_independent_review/v1' or review.get('rid')!=RID or review.get('candidate_commit')!=CANDIDATE or review.get('scope')!={'services':3,'calls':6} or review.get('source_sha256')!=current or review.get('filedry_sha256')!=doc['filedry_sha256'] or review.get('preflight_sha256')!=doc['preflight_sha256'] or review.get('source_manifest_sha256')!=doc['source_manifest_sha256'] or not (review.get('approved') is True or review.get('verdict') in ('PASS','approved')): raise RuntimeError('R066 independent review differs')
 return {'path':str(path),'sha256':sha(path),**doc}
ORIGINAL_PLAN=j.service_plan
def service_plan(d07,directory,port):
 env,cmd=ORIGINAL_PLAN(d07,directory,port)
 if directory.name=='D':
  geo=geometry(); env['FT_DEV_PREFILL_SCHEDULE']=geo['path']; write(directory/'d_schedule.json',{'environment':{'FT_DEV_PREFILL_SCHEDULE':geo['path']},'geometry':geo})
 return env,cmd
def execute_owned(batch,receipt,admit):
 d07=j.load(j.D07,'r066_d07_child'); d07.CANDIDATE=CANDIDATE; d07.RID=RID; accepted=admission(admit); d07.require_child_receipt(receipt,batch,WT,ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt,admit),schema='ft_r040j_api_owned_launch/v2'); owner=process=None; run=ROUNDS/RID
 try:
  owner=d07.take_d07_gpu_lock(RID,batch); d07.require_gpu_idle(); run.mkdir(); freeze(run); write(run/'preflight.json',{**plan(),'admission':accepted})
  for service in ('B','D','C'):
   directory=run/service; directory.mkdir(); port=j.load(j.PAIR,'r066_pair_run').dynamic_port()
   try:
    try: process=j.start(d07,directory,port)
    except BaseException as exc: process=getattr(exc,'owned_process',None); raise
    env={**d07.clean_environment(WT),'CUDA_VISIBLE_DEVICES':'','NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost','R066_API_BASE_URL':f'http://127.0.0.1:{port}','R066_API_SERVICE':service,'R066_API_RUN_DIR':str(run),'R066_D_ENABLED':'1'}
    subprocess.run([str(ROOT/'evaluation/toolchain/venv-eval/bin/python'),'-m','pytest','-q',str(HERE/'test_live_service.py')],cwd=WT,env=env,check=True)
   finally:
    if process is not None: d07.load_owned_lifecycle().stop_owned_process(process,120,30); process=None
  write(run/'execution_complete.json',{'schema':'ft_r066_execution/v1','sdk_pytest_completed':True,'root_seal_required':True}); return {'run_dir':str(run)}
 finally:
  if process is not None and d07.load_owned_lifecycle().owned_group_alive(process.pid): raise RuntimeError('owned service remains; preserve lock')
  if owner is not None: d07.release_d07_gpu_lock(owner)
def filedry():
 out=DEV/f'r066_d16_filedry_{time.strftime("%Y%m%d_%H%M%S")}'; out.mkdir(parents=True); package=plan(); freeze(out); write(out/'preflight.json',package); (out/'preflight.json').chmod(0o444); d07=j.load(j.D07,'r066_d07_dry')
 for service in ('B','D','C'):
  directory=out/service; directory.mkdir(); port=j.load(j.PAIR,'r066_pair_dry').dynamic_port(); service_plan(d07,directory,port); write(directory/'no_start.json',{'filedry':True,'popen':False,'request':False,'port_pair':j.load(j.PAIR,'r066_pair_receipt2').port_receipt(port)})
 write(out/'filedry.json',{'schema':'ft_r066_d16_filedry/v2','rid':RID,'candidate_commit':CANDIDATE,'output':str(out),'admission_required_before_run':True,'no_formal_rid_batch_lock_popen_or_request':True}); (out/'filedry.json').chmod(0o444); return {'output':str(out),'source_manifest_sha256':sha(out/'source_manifest.json'),'preflight_sha256':sha(out/'preflight.json'),'filedry_sha256':sha(out/'filedry.json')}
for key,value in {'WT':WT,'RID':RID,'CANDIDATE':CANDIDATE,'HERE':HERE,'candidate':candidate,'plan':plan,'freeze':freeze,'admission':admission,'child_argv':child_argv,'execute_owned':execute_owned,'service_plan':service_plan}.items(): setattr(j,key,value)
def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--filedry',action='store_true'); p.add_argument('--run',action='store_true'); p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS); p.add_argument('--batch',type=int,help=argparse.SUPPRESS); p.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS); p.add_argument('--admission',type=Path); a=p.parse_args(argv)
 if a.owned_child:
  if not a.run or a.filedry or a.batch is None or a.launch_receipt is None or a.admission is None:p.error('owned child needs run, batch, receipt and admission')
  print(json.dumps(execute_owned(a.batch,a.launch_receipt,a.admission),sort_keys=True)); return 0
 if a.filedry==a.run:p.error('choose exactly one mode')
 print(json.dumps(filedry() if a.filedry else j.launch(a.admission),sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
