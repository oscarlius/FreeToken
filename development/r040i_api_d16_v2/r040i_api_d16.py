#!/usr/bin/env python3
"""Root-operated D16 interleave6 SDK plan; FILEdry writes only development output."""
from __future__ import annotations
import argparse, getpass, hashlib, importlib.util, json, os, shutil, shlex, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1-p1'; VENV=ROOT/'venv'; EVAL=ROOT/'evaluation/d16_api'
ROUNDS=Path('/data2/_shared/runs/ft_rounds'); DEV=ROOT/'runs/dev_D16'; RID='E2-R040i-api-D16'; CANDIDATE='effb9969706922ddad9e59b96377e46469ebe97f'
D07=ROOT/'runs/dev_T16/r063_default_gate_v1/d07_g3g4_prepare.py'; PAIR=ROOT/'runs/dev_D16/r040h_v1_cpu_20261008_1610/runtime/ft_batch_port_pair_v1.py'
REVIEW=DEV/'R040h_startup_review_v1'; D07_SHA='c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0'; PAIR_SHA='415c1255ebbba81027c4526acd377f68f87889e31bfb4a58b79053c8abb73a34'; REVIEW_SHA='bb023e0e2603b26287c6e6e7eac0889919b2bf2361af2f85c6ce1527e74e06d3'
HERE=Path(__file__).resolve().parent

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def argv_sha(v): return hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); assert s.loader; s.loader.exec_module(m); return m
def write(p,v):
 with Path(p).open('x',encoding='utf-8') as f: json.dump(v,f,ensure_ascii=False,sort_keys=True,indent=2); f.write('\n')

def sources():
 names={
  'runner.py':HERE/'r040i_api_d16.py','runner_test.py':HERE/'test_r040i_api_d16.py','sdk_completions.py':EVAL/'sdk_completions.py','sse_contract_test.py':EVAL/'test_completions_sse_contract.py','live_scope.py':EVAL/'live_scope.py','live_scope_test.py':EVAL/'test_live_scope.py','live_scope_contract_test.py':EVAL/'test_live_scope_contract.py','scope_comparison_test.py':EVAL/'test_scope_comparison.py','scope_payloads.json':EVAL/'scope_payloads.json','interleave_input_binding.json':EVAL/'interleave_input_binding.json','request_schema.json':EVAL/'request_schema.json','d07.py':D07,'port_pair.py':PAIR}
 if any(p.is_symlink() or not p.is_file() for p in names.values()): raise RuntimeError('source closure unavailable')
 return names

def startup_review():
 pin,review=REVIEW/'pin.json',REVIEW/'review.json'
 if any(p.is_symlink() or not p.is_file() for p in (pin,review)) or sha(review)!=REVIEW_SHA: raise RuntimeError('R040h startup review differs')
 doc=json.loads(pin.read_text())
 if doc.get('immutable') is not True or doc.get('review_sha256')!=REVIEW_SHA or doc.get('rid')!='E2-R040h': raise RuntimeError('R040h startup-review pin differs')
 return {'pin':str(pin),'pin_sha256':sha(pin),'review':str(review),'review_sha256':REVIEW_SHA}

def candidate():
 if WT.is_symlink() or sha(D07)!=D07_SHA or sha(PAIR)!=PAIR_SHA: raise RuntimeError('pinned lifecycle source differs')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip(); dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 if head!=CANDIDATE or dirty: raise RuntimeError('clean effb996 candidate required')
 return {'worktree':str(WT),'commit':head,'tracked_clean':True}

def serve_argv(port):
 d07=load(D07,'r040i_d07_argv'); base=d07.serve_argv(port)
 for flag,value in {'--max-running-requests':'4','--cuda-graph-max-bs':'4','--kv-reserve-tokens':'98304','--max-seq-len-override':'98304'}.items(): base[base.index(flag)+1]=value
 if any(key.startswith(('FT_D16_','FT_T17_','FT_DEV_STATE_DUMP')) for key in os.environ): raise RuntimeError('native capture environment is forbidden')
 return ['numactl','--cpunodebind=0,1','--interleave=all',*base]

def plan():
 pair=load(PAIR,'r040i_pair'); port=pair.dynamic_port(); command=serve_argv(port); scope=json.loads((EVAL/'scope_payloads.json').read_text()); binding=json.loads((EVAL/'interleave_input_binding.json').read_text())
 if scope.get('services')!=6 or len(scope.get('calls',[]))!=8 or len(binding.get('inputs',[]))!=2 or not all(x.get('retokenized_matches_original') is True for x in binding['inputs']): raise RuntimeError('approved D16 6/8 mapping differs')
 for flag,value in {'--memory-ratio':'0.88','--max-running-requests':'4','--cuda-graph-max-bs':'4','--kv-reserve-tokens':'98304','--max-seq-len-override':'98304'}.items():
  if command[command.index(flag)+1]!=value: raise RuntimeError('final argv differs')
 return {'schema':'ft_r040i_api_d16_plan/v2','rid':RID,'candidate':candidate(),'historical_r040h_startup_review':str(REVIEW),'source_sha256':{k:sha(v) for k,v in sources().items()},'port_pair':pair.port_receipt(port),'serve_argv':command,'serve_argv_sha256':argv_sha(command),'scope':'interleave6_services_8_calls_only','warm':'deferred_no_actual_hit_evidence','limits':['SDK API behavior equivalence only','text mapping is not worker token-input proof','API overlap is not physical batching','no native collector/cache/watchdog']}

def freeze(out):
 root=out/'runtime_sources'; root.mkdir(); manifest={}
 for name,path in sources().items():
  target=root/name; shutil.copyfile(path,target); target.chmod(0o444); manifest[name]=sha(target)
 write(out/'source_manifest.json',{'schema':'ft_r040i_api_source_manifest/v1','files':manifest}); return manifest

def admission(path):
 if path is None or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('root D04 admission pin is required')
 doc=json.loads(path.read_text()); needed=('rid','candidate_commit','worktree','cwd','user','filedry_path','filedry_sha256','preflight_path','preflight_sha256','source_manifest_path','source_manifest_sha256','independent_review_path','independent_review_sha256')
 if any(not isinstance(doc.get(k),str) or not doc[k] for k in needed) or doc['rid']!=RID or doc['candidate_commit']!=CANDIDATE or doc['worktree']!=str(WT) or doc['cwd']!=str(Path.cwd()) or doc['user']!=getpass.getuser(): raise RuntimeError('D04 admission identity differs')
 filedry,preflight,manifest,review=(Path(doc[k]) for k in ('filedry_path','preflight_path','source_manifest_path','independent_review_path'))
 if any(p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 for p in (filedry,preflight,manifest,review)): raise RuntimeError('D04 admission artifact is unsafe')
 if [sha(filedry),sha(preflight),sha(manifest),sha(review)]!=[doc['filedry_sha256'],doc['preflight_sha256'],doc['source_manifest_sha256'],doc['independent_review_sha256']]: raise RuntimeError('D04 admission evidence differs')
 if json.loads(filedry.read_text()).get('no_formal_rid_batch_lock_popen_or_request') is not True: raise RuntimeError('D04 FILEdry did not succeed')
 current={k:sha(v) for k,v in sources().items()}
 if json.loads(manifest.read_text()).get('files')!=current or doc.get('source_sha256')!=current or json.loads(preflight.read_text()).get('candidate')!=candidate(): raise RuntimeError('D04 admission source closure is stale')
 review_doc=json.loads(review.read_text())
 if (review_doc.get('schema')!='ft_r040i_api_independent_review/v1' or review_doc.get('rid')!=RID or review_doc.get('candidate_commit')!=CANDIDATE or review_doc.get('scope')!={'services':6,'calls':8,'warm':'deferred_no_actual_expert_hit_proof'} or review_doc.get('source_manifest_sha256')!=doc['source_manifest_sha256'] or review_doc.get('source_sha256')!=current or not (review_doc.get('approved') is True or review_doc.get('verdict') in ('PASS','approved'))): raise RuntimeError('independent review is not identity-bound approved')
 return {'path':str(path),'sha256':sha(path),**doc}

def child_argv(batch,receipt,admit): return [str(VENV/'bin/python'),str(HERE/'r040i_api_d16.py'),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--admission',str(admit)]

def service_plan(d07,directory,port):
 env=d07.clean_environment(WT); env['CUDA_VISIBLE_DEVICES']='0'; env['MASTER_PORT']=str(port+1); command=serve_argv(port); selected={k:env[k] for k in ('CUDA_VISIBLE_DEVICES','PYTHONPATH','VIRTUAL_ENV','MASTER_PORT')}
 write(directory/'service_environment.json',{'selected':selected,'native_capture_keys':[]}); (directory/'SERVE_CMD.txt').write_text('env '+shlex.join([f'{k}={v}' for k,v in selected.items()])+' '+shlex.join(command)+'\n'); return env,command

def start(d07,directory,port):
 env,command=service_plan(d07,directory,port)
 log=(directory/'serve.log').open('x',encoding='utf-8'); process=subprocess.Popen(command,cwd=WT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=d07.load_owned_lifecycle().process_identity(process.pid)
  if birth is None or birth.get('pgid')!=process.pid or birth.get('session')!=process.pid: raise RuntimeError('owned service identity differs')
  write(directory/'owned_process.json',{'birth':birth,'port':port})
  for _ in range(450):
   if process.poll() is not None: raise RuntimeError(f'service exited: {process.returncode}')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as response: health=json.load(response)
    if health.get('status')=='ok': write(directory/'health.json',health); return process
   except (OSError,ValueError): time.sleep(2)
  raise TimeoutError('service did not become healthy')
 except BaseException:
  try: d07.load_owned_lifecycle().stop_owned_process(process,120,30)
  except BaseException as cleanup: cleanup.owned_process=process; raise
  raise

def execute_owned(batch,receipt_path,admit):
 d07=load(D07,'r040i_d07_child'); d07.CANDIDATE=CANDIDATE; d07.RID=RID; admitted=admission(admit); d07.require_child_receipt(receipt_path,batch,WT,ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt_path,admit),schema='ft_r040i_api_owned_launch/v2'); package={**plan(),'admission':admitted}; owner=None; process=None; run_dir=ROUNDS/RID
 try:
  owner=d07.take_d07_gpu_lock(RID,batch)
  d07.require_gpu_idle(); run_dir.mkdir(); freeze(run_dir); write(run_dir/'preflight.json',package)
  for service in (f'interleave_{n}' for n in range(6)):
   directory=run_dir/service; directory.mkdir(); port=load(PAIR,'r040i_pair_run').dynamic_port()
   try:
    try: process=start(d07,directory,port)
    except BaseException as exc: process=getattr(exc,'owned_process',None); raise
    env={**os.environ,'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost','D16_API_BASE_URL':f'http://127.0.0.1:{port}','D16_API_MODEL':'Qwen3.8-Flash-Next-NVFP4','D16_API_SERVICE':service,'D16_API_OUTPUT':str(directory/'calls')}; subprocess.run([str(ROOT/'evaluation/toolchain/venv-eval/bin/python'),'-m','pytest','-q',str(EVAL/'test_live_scope.py')],cwd=EVAL,env=env,check=True)
   finally:
    if process is not None: d07.load_owned_lifecycle().stop_owned_process(process,120,30); process=None
  subprocess.run([str(ROOT/'evaluation/toolchain/venv-eval/bin/python'),'-m','pytest','-q',str(EVAL/'test_scope_comparison.py')],cwd=EVAL,env={**os.environ,'D16_API_RUN_DIR':str(run_dir)},check=True); write(run_dir/'execution_complete.json',{'schema':'ft_r040i_api_execution/v2','sdk_pytest_completed':True,'four_pair_comparison_completed':True,'d04_seal_required_from_root':True}); return {'run_dir':str(run_dir)}
 finally:
  if process is not None and d07.load_owned_lifecycle().owned_group_alive(process.pid): raise RuntimeError('owned service remains; preserve lock')
  if owner is not None: d07.release_d07_gpu_lock(owner)

def launch(admit):
 if sys.platform!='linux': raise RuntimeError('Linux host required')
 os.chdir(WT)
 d07=load(D07,'r040i_d07_controller'); d07.CANDIDATE=CANDIDATE; d07.RID=RID; admitted=admission(admit); package={**plan(),'admission':admitted}; owned=d07.load_owned_lifecycle(); helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d07.ATOMIC_HELPER_SHA,'r040i_atomic')
 if (ROUNDS/RID).exists() or d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError('formal RID or GPU lock already exists')
 batch=helper.next_batch(ROUNDS); DEV.mkdir(exist_ok=True); receipt_path=DEV/f'launch_{RID}_batch{batch}.json'; command=child_argv(batch,receipt_path,admit); reserved={'schema':'ft_r040i_api_owned_launch/v2','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':argv_sha(command),'controller':d07.process_birth(),'packet_sha256':hashlib.sha256(json.dumps(package,sort_keys=True).encode()).hexdigest(),'atomic_helper_sha256':d07.ATOMIC_HELPER_SHA,'admission_sha256':admitted['sha256']}
 receipt=owned.reserve_process(helper,batch,RID,command,receipt_path,reserved); child=d07.process_birth(receipt['batch_pid']); d07.publish_child_binding(receipt_path,receipt,child,lifecycle=owned); return {'receipt':str(receipt_path),'batch':batch,'child':child}

def filedry():
 out=DEV/f'r040i_api_d16_v2_filedry_{time.strftime("%Y%m%d_%H%M%S")}'; out.mkdir(parents=True); package=plan(); freeze(out); write(out/'preflight.json',package)
 d07=load(D07,'r040i_d07_filedry')
 for service in (f'interleave_{n}' for n in range(6)):
  directory=out/service; directory.mkdir(); pair=load(PAIR,'r040i_pair_dry'); port=pair.dynamic_port(); service_plan(d07,directory,port); write(directory/'no_start.json',{'filedry':True,'popen':False,'request':False,'port_pair':pair.port_receipt(port)})
 write(out/'filedry.json',{'schema':'ft_r040i_api_d16_filedry/v2','output':str(out),'admission_required_before_run':True,'no_formal_rid_batch_lock_popen_or_request':True}); return {'output':str(out),'packet_sha256':hashlib.sha256(json.dumps(package,sort_keys=True).encode()).hexdigest()}

def main(argv=None):
 p=argparse.ArgumentParser(); p.add_argument('--filedry',action='store_true'); p.add_argument('--run',action='store_true'); p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS); p.add_argument('--batch',type=int,help=argparse.SUPPRESS); p.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS); p.add_argument('--admission',type=Path); a=p.parse_args(argv)
 if a.owned_child:
  if not a.run or a.filedry or a.batch is None or a.launch_receipt is None or a.admission is None: p.error('owned child needs --run, batch, receipt and admission')
  print(json.dumps(execute_owned(a.batch,a.launch_receipt,a.admission),sort_keys=True)); return 0
 if a.filedry==a.run: p.error('choose exactly one mode')
 print(json.dumps(filedry() if a.filedry else launch(a.admission),sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
