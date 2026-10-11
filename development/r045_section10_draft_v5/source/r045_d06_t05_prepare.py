#!/usr/bin/env python3
"""Prepare/run combined E2-R045 D06 G3/G4 plus T05 raw evidence.

Omitting --run is CPU-only and never binds a socket, starts a service, or
touches the GPU.  --run writes raw pending_review evidence only; D04 owns any
formal round/manifest closure.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path
import shutil, socket, subprocess, sys, tempfile, time, urllib.request
from types import SimpleNamespace

ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1-p1'; VENV=ROOT/'venv'
RUNS=ROOT/'runs/dev_T05'; LOCK=Path('/data2/_shared/gpu.lock'); ROUND=Path('/data2/_shared/runs/ft_rounds/E2-R045')
RID='E2-R045'; CANDIDATE='effb9969706922ddad9e59b96377e46469ebe97f'; MODEL='Qwen3.8-Flash-Next-NVFP4'
PARENT='0aa23431e5b800797543bdecbf35a01045131d7d'
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'; TRACE=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json')
TRACE_SHA='055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899'
OWNED_SOURCE=ROOT/'runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools'; OWNED_SHA='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'
HARNESS_VERSION='r045-section10-v5'

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
ENV_RECORD_KEYS=('CUDA_VISIBLE_DEVICES','PYTHONPATH','VIRTUAL_ENV','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_D0_TIMELINE','FT_DEV_D0_TIMELINE_STEPS','FT_DEV_PAUSE_ENDPOINT')
def probe(path:Path,purpose:str)->dict:
 write(path,{'schema':'ft_r045_cpu_file_probe/v1','kind':'CPU_FILE_PROBE','not_measurement':True,'purpose':purpose})
 return {'path':str(path),'sha256':sha(path),'purpose':purpose}
def copy_runtime(source:Path,target:Path)->dict:
 if source.is_symlink() or not source.is_file():raise RuntimeError('runtime source unavailable: '+str(source))
 shutil.copyfile(source,target);target.chmod(0o600)
 return {'source':str(source),'source_sha256':sha(source),'copy':str(target),'copy_sha256':sha(target),'mode':oct(target.stat().st_mode&0o777)}
def lifecycle():
 return d07_helpers().load_owned_lifecycle()
def port()->int:
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def git_checked()->dict:
 if WT.is_symlink():raise RuntimeError('candidate worktree is a symlink')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 probe=WT/'scripts/multisession_probe.py'
 if head!=CANDIDATE or dirty or probe.is_symlink() or not probe.is_file():raise RuntimeError('clean E2-base.1 candidate/probe required')
 return {'worktree':str(WT),'commit':head,'probe_raw_sha256':sha(probe)}
def d07_helpers():
 source=Path(__file__).with_name('d07_g3g4_prepare.py')
 if source.is_symlink() or not source.is_file():raise RuntimeError('D07 sealed-round gate source missing')
 spec=importlib.util.spec_from_file_location('t05_sealed_round_gate',source);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod);mod.CANDIDATE=CANDIDATE;mod.WORKTREE=WT;mod.RID=RID
 return mod

def require_kept(rid:str)->Path:
 return d07_helpers().require_closed_round(rid,'kept')
def verify_pause_helpers()->dict:
 return d07_helpers().verify_frozen_cold_helpers(OWNED_SOURCE)
def d06_module():
 source=Path(__file__).with_name("d06_g3g4_prepare.py");spec=importlib.util.spec_from_file_location("r045_d06_adapter",source);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod);mod.CANDIDATE=CANDIDATE;mod.WORKTREE=WT;mod.RID=RID;return mod
def r055_failed_metadata()->dict:
 """Section 10 preserves failed rounds and six reviewed cold arms; no kept gate."""
 retained=d06_module().pause_module('r055b_owned_launch.py').require_retained_cold(SimpleNamespace(ROOT=ROOT))
 path=d07_helpers().require_closed_round('E2-R055b-gate-D06','failed_harness')
 if sha(path)!='13915b0d4657cf9e4ea1e40c64331c938d653f5b318ae16ebaac6f68b8503a4f' or sha(path.with_name('MANIFEST.sha256'))!='4961ee160759810533dd5702196d38a7760d4f556e6783e8e1f417e84a23432c':raise RuntimeError('R055b sealed failure metadata differs')
 return {'schema':'ft_r045_section10_basis/v1','r055_gate_ended':True,'r055c_authorized':False,'default_path':retained,'r055b_failed_round':str(path),'r055b_round_sha256':sha(path),'r055b_manifest_sha256':sha(path.with_name('MANIFEST.sha256')),'pause_chain_validation':'R045 D06 G3/G4 actual pause/cancel/resume','raw_arms_replayed':False}
def run_d06_g3g4(directory:Path,*,file_dry_run:bool=False)->dict:
 """Use D06 clients/validators in the R045 child; never call its execute/lock path."""
 d=d06_module();directory.mkdir();p=port();proc=None
 if file_dry_run:
  # These are the D06 client/validator output locations, prepared without its
  # frozen start_server path so no process or request is possible.
  d.prepare_service_files(directory,WT,p)
  probes=[probe(directory/name,'formal D06 G3/G4 and pause-chain output') for name in ('serve.log','owned_process.json','g3.json','g3.rep0.way0.tokens.json','g3.rep0.way1.tokens.json','g4.json','d0_decode_steps.jsonl','d0_decode_timeline.jsonl','d0_prefill.jsonl','before.json','pause_completed.json','pause_cancel.json','after_cancel.json','pause_observations.jsonl','model_process_cuda.jsonl','cuda_memory_summary.json','pause_chain.json')]
  return {'schema':'ft_r045_d06_g3g4_cpu_file_dry_run/v5','harness_version':HARNESS_VERSION,'directory':'g3g4','port':p,'cpu_file_probes':probes,'service_command_sha256':sha(directory/'SERVE_CMD.json'),'observer_sha256':sha(directory/'d06_pause_observer_v3.py'),'startup_sha256':sha(directory/'d06_pause_startup_v3.py')}
 try:
  proc=d.start_server(directory,WT,p);base=f"http://127.0.0.1:{p}/v1";e=d.environment(WT,directory/'d0');g3p=directory/'g3.json';g4p=directory/'g4.json'
  subprocess.run([str(VENV/'bin/python'),str(WT/d.PROBE),'two-decode','--base-url',base,'--model',MODEL,'--ctx','32000','--max-tokens','512','--same-prompt','1','--reps','1','--out',str(g3p)],cwd=WT,env=e,check=True,timeout=1800)
  g3=d.validate_g3(json.loads(g3p.read_text()))
  subprocess.run([str(VENV/'bin/python'),str(WT/d.PROBE),'h1','--base-url',base,'--model',MODEL,'--H','1,8,32','--reps','1','--prefill-target','32000','--out',str(g4p)],cwd=WT,env=e,check=True,timeout=1800)
  g4=d.validate_g4(json.loads(g4p.read_text()),directory/'serve.log')
  pause_chain=d.run_pause_chain(directory,WT,p)
 except BaseException as error:
  proc=getattr(error,'owned_process',proc)
  error.owned_process=proc
  raise
 finally:
  if proc is not None:
   try:d.load_owned_lifecycle().stop_owned_process(proc)
   except BaseException as cleanup_error:
    cleanup_error.owned_process=proc
    cleanup_error.owned_cleanup_failed=True
    raise
 return {'schema':'ft_r045_d06_g3g4_raw/v5','harness_version':HARNESS_VERSION,'directory':'g3g4','g3':g3,'g4':g4,'pause_chain':pause_chain,'memory_ratio':0.88,'owned_cleanup':True}

def env(arm:Path)->dict:
 e=os.environ.copy()
 for k in list(e):
  if k.startswith(('FT_','R055')) or k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES'):e.pop(k)
 e.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONPATH=str(WT/'python'),VIRTUAL_ENV=str(VENV),PATH=str(VENV/'bin')+':'+e.get('PATH',''),CUDA_VISIBLE_DEVICES='0',FT_DEV_D0='1',FT_DEV_D0_PATH=str(arm/'d0'),FT_DEV_D0_TIMELINE='1',FT_DEV_D0_TIMELINE_STEPS='20000',FT_DEV_PAUSE_ENDPOINT='1')
 return e
def serve_argv(p:int)->list[str]:return [str(VENV/'bin/ft'),'serve','--model-path',str(MODEL_PATH),'--served-model-name',MODEL,'--host','127.0.0.1','--port',str(p),'--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--quant-backend','moe.nvfp4=triton','--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','73728','--max-seq-len-override','73728','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--tool-call-parser','qwen3_coder','--reasoning-parser','qwen3','--prefill-layer-major','--mamba-host-slots','0']
def prepare_service_files(arm:Path,p:int,*,file_dry_run:bool=False)->tuple[dict,list[str]]:
 arm.mkdir(parents=True,exist_ok=True);e=env(arm);a=serve_argv(p);record={key:e[key] for key in ENV_RECORD_KEYS if key in e}
 (arm/'ENV.json').write_text(json.dumps(record,sort_keys=True)+'\n',encoding='utf-8')
 (arm/'ENV.txt').write_text(''.join(f'{key}={record[key]}\n' for key in sorted(record)),encoding='utf-8')
 (arm/'SERVE_CMD.txt').write_text(json.dumps({'argv':a,'port':p},sort_keys=True)+'\n',encoding='utf-8')
 (arm/'serve_argv.json').write_text(json.dumps({'argv':a,'env':record},sort_keys=True)+'\n',encoding='utf-8')
 (arm/'serve.log').open('x',encoding='utf-8').close()
 if file_dry_run:
  for name in ('owned_process.json','health.json','serve_args.txt'):probe(arm/name,'formal service lifecycle output')
 return e,a
def start(arm:Path,p:int):
 e,a=prepare_service_files(arm,p);log=(arm/'serve.log').open('a');proc=subprocess.Popen(a,cwd=WT,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=lifecycle().process_identity(proc.pid)
  if birth is None or birth.get('pgid')!=proc.pid or birth.get('session')!=proc.pid:raise RuntimeError('service lacks private PGID/session')
  write(arm/'owned_process.json',{'pid':proc.pid,'birth':birth,'port':p})
  until=time.monotonic()+900
  while time.monotonic()<until:
   if proc.poll() is not None:raise RuntimeError('service exited before ready')
   try:
     with urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=3) as r:
      health=json.load(r)
     if health.get('status')=='ok':
      write(arm/'health.json',health)
      lines=(arm/'serve.log').read_text(encoding='utf-8',errors='replace').splitlines();parsed='\n'.join(line for line in lines if 'Parsed arguments' in line or 'ServerArgs(' in line)
      if not parsed.strip():raise RuntimeError('service log lacks Parsed arguments')
      (arm/'serve_args.txt').write_text(parsed+'\n',encoding='utf-8');return proc
   except (OSError,ValueError):pass
   time.sleep(2)
  raise TimeoutError('service readiness timeout')
 except BaseException:
  try:lifecycle().stop_owned_process(proc)
  except BaseException as cleanup_error:
   cleanup_error.owned_process=proc
   raise
  raise
def commands(arm:Path,p:int,trace:Path|None=None)->list[list[str]]:
 trace=TRACE if trace is None else trace
 base=[str(VENV/'bin/python'),str(WT/'scripts/multisession_probe.py')];common=['--base-url',f'http://127.0.0.1:{p}/v1','--model',MODEL]
 return [base+['two-decode']+common+['--ctx','32000','--max-tokens','512','--same-prompt','0','--reps','3','--out',str(arm/'a_two_decode_diff.json')],base+['two-decode']+common+['--ctx','32000','--max-tokens','512','--same-prompt','1','--reps','1','--out',str(arm/'a_two_decode_same.json')],base+['stall']+common+['--decode-ctx','4000','--decode-max-tokens','1500','--prefill-kind','cold32k','--prefill-target','32052','--delay','3','--reps','3','--out',str(arm/'b_stall_cold32k.json')],base+['stall']+common+['--decode-ctx','4000','--decode-max-tokens','1500','--prefill-kind','agent_turn','--trace',str(trace),'--round','6','--delay','3','--reps','3','--out',str(arm/'b_stall_agent.json')],base+['pair-short']+common+['--trace',str(trace),'--rounds','3,4','--reps','3','--out',str(arm/'c_pair_short.json')],base+['h1']+common+['--H','1,8,32','--reps','3','--prefill-target','32052','--out',str(arm/'d_h1.json')]]
def cold_first(arm:Path,p:int)->None:
 """One real 32,052-token cold request using the candidate D06 ACK client."""
 probe=WT/'scripts/multisession_probe.py';spec=importlib.util.spec_from_file_location('t05_probe',probe);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
 tokenizer=mod.load_tokenizer(str(MODEL_PATH));messages,ids=mod.make_messages(tokenizer,32052,f'{RID}-{arm.name}-first')
 record=mod.stream_request(base_url=f'http://127.0.0.1:{p}/v1',model=MODEL,timeout=1800,messages=messages,max_tokens=128)
 write(arm/'first_shot.json',{'frontend_token_count':len(ids),'prompt_sha256':mod.prompt_sha256(ids),'record':record})
def dry_workloads(arm:Path,p:int,trace:Path)->list[dict]:
 probes=[probe(arm/'first_shot.json','formal T05 first cold output')]
 for command in commands(arm,p,trace):
  probes.append(probe(Path(command[command.index('--out')+1]),'formal T05 client output'))
  if command[2]=='two-decode':
   output=Path(command[command.index('--out')+1])
   for rep in range(int(command[command.index('--reps')+1])):
    for way in (0,1):probes.append(probe(output.with_name(f'{output.stem}.rep{rep}.way{way}.tokens.json'),'formal ACK sidecar output'))
 for name in ('d0_decode_steps.jsonl','d0_decode_timeline.jsonl','d0_prefill.jsonl'):probes.append(probe(arm/name,'formal D0 output'))
 return probes
def normalized_serve(arm:Path)->dict:
 record=json.loads((arm/'serve_argv.json').read_text())
 return {'argv':record['argv']}
def strict_log_args(left:Path,right:Path)->None:
 source=Path(__file__).with_name('d04_original')/'serve_args_diff.py';spec=importlib.util.spec_from_file_location('t05_args_diff',source);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
 source=Path(__file__).with_name('t16_full_tail_base_runner.py');spec=importlib.util.spec_from_file_location('t05_strict_args',source);strict=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(strict)
 strict.strict_args(mod.parse(left),mod.parse(right),{})
def lock(batch:int)->dict:
 born=lifecycle().process_identity(os.getpid());owner={'owner':RID,'batch':batch,'birth':born};token=json.dumps(owner,sort_keys=True)
 try:fd=os.open(LOCK,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 except FileExistsError as x:raise RuntimeError('foreign GPU lock exists') from x
 with os.fdopen(fd,'w') as f:f.write(token);f.flush();os.fsync(f.fileno())
 s=LOCK.stat();return {**owner,'token':token,'inode':s.st_ino,'device':s.st_dev}
def unlock(owner:dict)->None:
 s=LOCK.stat()
 if LOCK.is_symlink() or (s.st_ino,s.st_dev)!=(owner['inode'],owner['device']) or LOCK.read_text()!=owner['token']:raise RuntimeError('refuse foreign lock release')
 LOCK.unlink()
def child_argv(batch:int,receipt:Path)->list[str]:
 return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]
def source_hashes()->dict:
 paths=(Path(__file__).resolve(),Path(__file__).with_name('d06_g3g4_prepare.py').resolve(),Path(__file__).with_name('d07_g3g4_prepare.py').resolve(),*(Path(__file__).with_name(name).resolve() for name in d06_module().PAUSE_SOURCE_NAMES),(Path(__file__).parent/'d04_original/serve_args_diff.py').resolve(),Path(__file__).with_name('t16_full_tail_base_runner.py').resolve(),(WT/'scripts/multisession_probe.py').resolve(),*(OWNED_SOURCE/'helpers/raw'/name for name in ('cold_eq.py','probe_ft_cold32k.py')))
 return {str(path):sha(path) for path in paths}
def archive_sources(target:Path)->list[dict]:
 target.mkdir(mode=0o700)
 rows=[]
 for source in map(Path,source_hashes()):
  destination=target/(('candidate/'+source.name) if source==WT/'scripts/multisession_probe.py' else ('cold_helpers/'+source.name) if source.parent==OWNED_SOURCE/'helpers/raw' else ('d04_original/'+source.name) if source.parent.name=='d04_original' else source.name)
  destination.parent.mkdir(parents=True,exist_ok=True);rows.append(copy_runtime(source,destination))
 write(target/'source_identity.json',{'schema':'ft_r045_source_identity/v5','harness_version':HARNESS_VERSION,'source_sha256':source_hashes(),'copies':rows})
 return rows
def dry_run_directory(round_path=None)->Path:
 round_path=ROUND if round_path is None else round_path
 return round_path.parent/f'.dryrun_R045_section10_v5_{RID}'
def dry_run()->dict:
 """Execute only the formal filesystem portion in a sibling; return before lock/Popen/requests."""
 candidate=git_checked();cold_helpers=verify_pause_helpers();target=dry_run_directory()
 if target.exists():raise RuntimeError('R045 dry-run sibling already exists')
 target.mkdir(mode=0o700);target.chmod(0o700)
 if target.parent!=ROUND.parent or not target.name.startswith('.dryrun_R045_'):raise RuntimeError('R045 dry-run target differs')
 if TRACE.is_symlink() or not TRACE.is_file():raise RuntimeError('retained T2 trace missing')
 trace_bytes=TRACE.read_bytes()
 if hashlib.sha256(trace_bytes).hexdigest()!=TRACE_SHA:raise RuntimeError('retained trace differs from FTD T2 trace.json registered SHA')
 copies=archive_sources(target/'source_tools')
 trace=target/'trace_input.json';trace.write_bytes(trace_bytes);trace.chmod(0o444)
 with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:sock.bind(('127.0.0.1',0));fixture_port=sock.getsockname()[1]
 if fixture_port==8095:raise RuntimeError('R045 dry-run allocated forbidden port')
 g3g4=run_d06_g3g4(target/'g3g4',file_dry_run=True);arms=[]
 for name in ('P1','P2'):
  arm=target/name;prepare_service_files(arm,fixture_port,file_dry_run=True);outputs=dry_workloads(arm,fixture_port,trace)
  arms.append({'name':name,'port':fixture_port,'outputs':outputs,'env_sha256':sha(arm/'ENV.json'),'env_txt_sha256':sha(arm/'ENV.txt'),'serve_cmd_sha256':sha(arm/'SERVE_CMD.txt')})
 probes=[probe(target/name,'formal T05 metadata') for name in ('preflight.json','result.json','history.json','MANIFEST.sha256')]
 receipt={'schema':'ft_r045_dry_run/v5','harness_version':HARNESS_VERSION,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'passed':True,'source_sha256':source_hashes(),'source_copies':copies,'cold_helpers':cold_helpers,'owner':{'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')},'cwd':os.getcwd(),'worktree':{'path':str(WT),'parent':str(WT.parent)},'formal_rid_directory_created':False,'formal_directory':str(ROUND),'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'candidate':candidate,'port':fixture_port,'g3g4':g3g4,'arms':arms,'cpu_file_probes':probes}
 write(target/'dry_run_receipt.json',receipt);path=target/'dry_run_receipt.json';path.chmod(0o444)
 return {**receipt,'dry_run_directory':str(target),'receipt_sha256':sha(path)}
def require_dry_run_receipt()->dict:
 path=dry_run_directory()/'dry_run_receipt.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R045 dry-run receipt absent or writable')
 value=json.loads(path.read_text());owner={'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')}
 if (value.get('schema')!='ft_r045_dry_run/v5' or value.get('harness_version')!=HARNESS_VERSION or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=PARENT or value.get('passed') is not True or value.get('source_sha256')!=source_hashes() or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('worktree')!={'path':str(WT),'parent':str(WT.parent)} or any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated'))):raise RuntimeError('R045 dry-run receipt identity differs')
 return {'path':str(path),'sha256':sha(path)}
def require_startup_review(dry_receipt:dict)->dict:
 path=RUNS/'reviews'/f'{RID}_section10_startup_review_v5.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R045 startup review absent or writable')
 value=json.loads(path.read_text());expected={'schema':'ft_r045_startup_review/v5','harness_version':HARNESS_VERSION,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'approved':True,'verdict':'PASS','source_sha256':source_hashes(),'dry_run_receipt':dry_receipt['path'],'dry_run_receipt_sha256':dry_receipt['sha256']}
 if any(value.get(k)!=v for k,v in expected.items()):raise RuntimeError('R045 startup review binding differs')
 return {'path':str(path),'sha256':sha(path)}

def run(*,owned_child:bool=False,batch:int|None=None,launch_receipt:Path|None=None)->dict:
 shared=d07_helpers()
 if owned_child:
  if batch is None or launch_receipt is None:raise RuntimeError('T05 owned child requires reserved batch and receipt')
  shared.require_child_receipt(launch_receipt,batch,WT,RUNS,rid=RID,expected_argv=child_argv(batch,launch_receipt),schema='ft_t05_owned_launch/v1')
 candidate=git_checked();verify_pause_helpers()
 dry_receipt=require_dry_run_receipt();review=require_startup_review(dry_receipt)
 r041,t20=require_kept('E2-R041-gate-D17'),d07_helpers().require_t20_failed_harness();r040a=shared.require_closed_round('E2-R040a','measured');r055=r055_failed_metadata()
 if ROUND.exists():raise RuntimeError('E2-R045 directory already exists')
 if not owned_child:
  if LOCK.exists() or LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists; T05 remains queued')
  owned=lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py','a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf','t05_batch')
  batch=helper.next_batch(Path('/data2/_shared/runs/ft_rounds'));RUNS.mkdir(parents=True,exist_ok=True);receipt_path=RUNS/f'launch_{RID}_batch{batch}.json';argv=child_argv(batch,receipt_path)
  reserved={'schema':'ft_t05_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':shared.argv_sha256(argv),'controller':shared.process_birth(),'dry_run_receipt':dry_receipt,'startup_review':review,'section10_basis':r055,'prerequisites':{'E2-R041-gate-D17':sha(r041),'E2-R040':sha(t20),'E2-R040a':sha(r040a),'R055_failed_metadata_only':r055,'combined_d06_g3g4':'local' }}
  receipt=owned.reserve_process(helper,batch,RID,argv,receipt_path,reserved);identity=owned.process_identity(receipt['batch_pid'])
  if identity is None or identity.get('pid')!=receipt['batch_pid'] or type(identity.get('start_ticks')) is not int:raise RuntimeError('T05 reserved child birth is unavailable')
  return shared.publish_child_binding(receipt_path,receipt,{'pid':identity['pid'],'start_ticks':identity['start_ticks'],'execution_id':f"{identity['pid']}:{identity['start_ticks']}"},lifecycle=owned)
 owner=lock(batch);raw=None;proc=None;cleanup_failed=False
 try:
  used=[int(x) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).splitlines() if x.strip()]
  if not used or any(x>=1000 for x in used):raise RuntimeError(f'GPU not idle: {used}')
  if not TRACE.is_file() or TRACE.is_symlink():raise RuntimeError('retained T2 trace missing')
  trace_bytes=TRACE.read_bytes()
  if hashlib.sha256(trace_bytes).hexdigest()!=TRACE_SHA:raise RuntimeError('retained trace differs from FTD T2 trace.json registered SHA')
  raw=ROUND;raw.mkdir(parents=True);archive_sources(raw/'source_tools');write(raw/'section10_basis.json',r055)
  bound_trace=raw/'trace_input.json';bound_trace.write_bytes(trace_bytes);bound_trace.chmod(0o444)
  g3g4=run_d06_g3g4(raw/'g3g4')
  arms=[]
  fixture_port=port()
  for name in ('P1','P2'):
   arm=raw/name;arm.mkdir();p=fixture_port;proc=None
   try:
    proc=start(arm,p);cold_first(arm,p)
    for cmd in commands(arm,p,trace=bound_trace):subprocess.run(cmd,cwd=WT,env=env(arm),check=True,timeout=3600)
   except BaseException as error:
    proc=getattr(error,'owned_process',proc)
    raise
   finally:
    if proc is not None:
     try:lifecycle().stop_owned_process(proc)
     except BaseException:
      cleanup_failed=True
      raise
     proc=None
   for evidence in (arm/'d0_decode_steps.jsonl',arm/'d0_decode_timeline.jsonl'):
    if evidence.is_symlink() or not evidence.is_file() or not evidence.read_bytes().strip():raise RuntimeError(f'{name} lacks required D0 evidence: {evidence.name}')
   arms.append({'name':name,'port':p,'files':{f:sha(arm/f) for f in ('first_shot.json','a_two_decode_diff.json','a_two_decode_same.json','b_stall_cold32k.json','b_stall_agent.json','c_pair_short.json','d_h1.json')},'timeline':str(arm/'d0_decode_timeline.jsonl')})
  if normalized_serve(raw/'P1')!=normalized_serve(raw/'P2'):raise RuntimeError('P1/P2 service arguments differ; only log PID differences are permitted')
  strict_log_args(raw/'P1'/'serve.log',raw/'P2'/'serve.log')
  result={'schema':'ft_t05_raw_measurement/v1','rid':RID,'candidate_commit':CANDIDATE,'candidate':candidate,'state':'pending_review','proposed_verdict':'measured','raw_measurement_before_D04':True,'batch':batch,'owner':owner,'r041_sha256':sha(r041),'t20_sha256':sha(t20),'section10_basis':r055,'harness_version':HARNESS_VERSION,'g3g4':g3g4,'trace_input':'trace_input.json','trace_sha256':TRACE_SHA,'arms':arms,'s_batch_slot':'pending: use only the separately delivered D16 command'}
  write(raw/'result.json',result);return result
 except BaseException as error:
  proc=getattr(error,'owned_process',proc)
  cleanup_failed=cleanup_failed or bool(getattr(error,'owned_cleanup_failed',False))
  if raw is not None:write(raw/'failed_harness.json',{'rid':RID,'batch':batch,'owner':owner,'error':repr(error),'raw_measurement_preserved':True})
  raise
 finally:
  if cleanup_failed:
   if raw is not None:write(raw/'owned_cleanup.json',{'schema':'ft_t05_owned_cleanup/v1','rid':RID,'batch':batch,'owner':owner,'lock_released':False,'cleanup_failed':True})
   raise RuntimeError('T05 owned cleanup failed; GPU lock preserved')
  if proc is not None and lifecycle().owned_group_alive(proc.pid):raise RuntimeError('T05 owned service still alive; GPU lock preserved')
  unlock(owner)
  if raw is not None:write(raw/'owned_cleanup.json',{'schema':'ft_t05_owned_cleanup/v1','rid':RID,'batch':batch,'owner':owner,'lock_released':True})
def self_test()->None:
 with tempfile.TemporaryDirectory() as x:
  a=Path(x);c=commands(a,34567);assert len(c)==6 and all('8095' not in z for q in c for z in q);assert ['--kv-reserve-tokens','73728']==serve_argv(34567)[serve_argv(34567).index('--kv-reserve-tokens'):serve_argv(34567).index('--kv-reserve-tokens')+2];assert c[0][c[0].index('--same-prompt')+1]=='0' and c[1][c[1].index('--same-prompt')+1]=='1';assert all('--reps' in q for q in c)
 print('SELFTEST PASS: T05 two-arm 73728 command shape, no 8095')
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--self-test',action='store_true');p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS);p.add_argument('--batch',type=int,help=argparse.SUPPRESS);p.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS);a=p.parse_args(argv)
 if a.self_test:self_test();return 0
 if a.dry_run:
  if a.run or a.owned_child or a.batch is not None or a.launch_receipt is not None:raise RuntimeError('--dry-run cannot mix run, child, batch, or receipt')
  print(json.dumps(dry_run()));return 0
 if not a.run:print(json.dumps({'rid':RID,'candidate_commit':CANDIDATE,'cpu_only':True,'worktree':str(WT),'trace':str(TRACE),'arms':['P1','P2'],'kv_window':73728,'commands_per_arm':6,'raw_only_pending_review':True}));return 0
 print(json.dumps(run(owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt)));return 0
if __name__=='__main__':raise SystemExit(main())

