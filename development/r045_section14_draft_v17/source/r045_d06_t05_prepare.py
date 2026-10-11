#!/usr/bin/env python3
"""Prepare/run combined E2-R045 D06 G3/G4 plus T05 raw evidence.

Omitting --run is CPU-only and never binds a socket, starts a service, or
touches the GPU.  --run writes raw pending_review evidence only; D04 owns any
formal round/manifest closure.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, re
from pathlib import Path
import shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from types import SimpleNamespace

ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1-p1'; VENV=ROOT/'venv'; HERE=Path(__file__).resolve().parent
RUNS=ROOT/'runs/dev_T05'; LOCK=Path('/data2/_shared/gpu.lock'); ROUND=Path('/data2/_shared/runs/ft_rounds/E2-R045')
RID='E2-R045'; CANDIDATE='effb9969706922ddad9e59b96377e46469ebe97f'; MODEL='Qwen3.8-Flash-Next-NVFP4'
PARENT='0aa23431e5b800797543bdecbf35a01045131d7d'
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'; TRACE=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json')
TRACE_SHA='055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899'
OWNED_SOURCE=ROOT/'runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools'; OWNED_SHA='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'
HARNESS_VERSION='r045-section14-v17'
ORDINARY_ADAPTER=HERE/'r049_t21_ordinary_adapter_v9.py'; ORDINARY_CLIENT=HERE/'r049_t21_ordinary_client_v9.py'; ORDINARY_STARTUP=HERE/'r046c_t06_ordinary_startup_v4.py'

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
ENV_RECORD_KEYS=('CUDA_VISIBLE_DEVICES','PYTHONPATH','VIRTUAL_ENV','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED')
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
def ordinary_module(path:Path,name:str):
 if path.is_symlink() or not path.is_file():raise RuntimeError('ordinary T05 runtime source missing: '+str(path))
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);assert spec.loader;sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
def ordinary_adapter():return ordinary_module(ORDINARY_ADAPTER,'r045_ordinary_adapter')
def ordinary_client():return ordinary_module(ORDINARY_CLIENT,'r045_ordinary_client')
def r055_failed_metadata()->dict:
 """Section 10 preserves failed rounds and six reviewed cold arms; no kept gate."""
 retained=d06_module().pause_module('r055b_owned_launch.py').require_retained_cold(SimpleNamespace(ROOT=ROOT))
 path=d07_helpers().require_closed_round('E2-R055b-gate-D06','failed_harness')
 if sha(path)!='13915b0d4657cf9e4ea1e40c64331c938d653f5b318ae16ebaac6f68b8503a4f' or sha(path.with_name('MANIFEST.sha256'))!='4961ee160759810533dd5702196d38a7760d4f556e6783e8e1f417e84a23432c':raise RuntimeError('R055b sealed failure metadata differs')
 return {'schema':'ft_r045_section10_basis/v1','r055_gate_ended':True,'r055c_authorized':False,'default_path':retained,'r055b_failed_round':str(path),'r055b_round_sha256':sha(path),'r055b_manifest_sha256':sha(path.with_name('MANIFEST.sha256')),'pause_chain_validation':'R045 D06 G3/G4 actual pause/cancel/resume','raw_arms_replayed':False}
def d16_failed_metadata()->dict:
 """Bind retained D16 failures; they remain metadata-only, never substitutes."""
 retained={'E2-R040a':'six_anchors','E2-R040c':'six_cases','E2-R040d':'failed_measurement'}
 rows={}
 for rid,scope in retained.items():
  path=d07_helpers().require_closed_round(rid,'failed_harness');manifest=path.with_name('MANIFEST.sha256')
  value=json.loads(path.read_text())
  if value.get('round_id')!=rid or value.get('verdict')!='failed_harness':raise RuntimeError(f'{rid} retained D16 closure differs')
  rows[rid]={'round':str(path),'round_sha256':sha(path),'manifest_sha256':sha(manifest),'retained_scope':scope}
 return {'schema':'ft_r045_section14_d16_failed_metadata/v2','metadata_only':True,'rounds':rows,
         'retained_anchor_count':6,'retained_case_count':6,
         'performance_reuse_forbidden':True}
def run_d06_g3g4(directory:Path,*,file_dry_run:bool=False)->dict:
 """Use D06 clients/validators in the R045 child; never call its execute/lock path."""
 d=d06_module();directory.mkdir();p=port();proc=None
 if file_dry_run:
  # These are the D06 client/validator output locations, prepared without its
  # frozen start_server path so no process or request is possible.
  d.prepare_service_files(directory,WT,p)
  probes=[probe(directory/name,'formal D06 G3/G4 and pause-chain output') for name in ('serve.log','owned_process.json','g3.json','g3.rep0.way0.tokens.json','g3.rep0.way1.tokens.json','g4.json','d0_decode_steps.jsonl','d0_decode_timeline.jsonl','d0_prefill.jsonl','before.json','pause_completed.json','pause_cancel.json','after_cancel.json','pause_observations.jsonl','model_process_cuda.jsonl','cuda_memory_summary.json','pause_chain.json')]
  return {'schema':'ft_r045_d06_g3g4_cpu_file_dry_run/v9','harness_version':HARNESS_VERSION,'directory':'g3g4','port':p,'cpu_file_probes':probes,'service_command_sha256':sha(directory/'SERVE_CMD.json'),'observer_sha256':sha(directory/'d06_pause_observer_v3.py'),'startup_sha256':sha(directory/'d06_pause_startup_v3.py')}
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
 return {'schema':'ft_r045_d06_g3g4_raw/v9','harness_version':HARNESS_VERSION,'directory':'g3g4','g3':g3,'g4':g4,'pause_chain':pause_chain,'memory_ratio':0.88,'owned_cleanup':True}

def env(arm:Path)->dict:
 e=os.environ.copy()
 for k in list(e):
  if k.startswith(('FT_','R055')) or k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES'):e.pop(k)
 e.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONPATH=str(WT/'python'),VIRTUAL_ENV=str(VENV),PATH=str(VENV/'bin')+':'+e.get('PATH',''),CUDA_VISIBLE_DEVICES='0')
 return e
def serve_argv(p:int)->list[str]:return [str(VENV/'bin/ft'),'serve','--model-path',str(MODEL_PATH),'--served-model-name',MODEL,'--host','127.0.0.1','--port',str(p),'--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--quant-backend','moe.nvfp4=triton','--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','98304','--max-seq-len-override','98304','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--tool-call-parser','qwen3_coder','--reasoning-parser','qwen3','--prefill-layer-major','--mamba-host-slots','0']
def prepare_service_files(arm:Path,p:int,*,file_dry_run:bool=False)->tuple[dict,list[str]]:
 arm.mkdir(parents=True,exist_ok=True);e=env(arm);a=serve_argv(p);record={key:e[key] for key in ENV_RECORD_KEYS if key in e}
 if any(key in e for key in ('FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_D0_TIMELINE','FT_DEV_D0_TIMELINE_STEPS','FT_DEV_ROUTE_TRACE')):raise RuntimeError('T05 performance must disable D0 and route trace')
 if any(flag in a for flag in ('--route-trace','--enable-route-trace')):raise RuntimeError('T05 performance command enables route trace')
 (arm/'ENV.json').write_text(json.dumps(record,sort_keys=True)+'\n',encoding='utf-8')
 (arm/'ENV.txt').write_text(''.join(f'{key}={record[key]}\n' for key in sorted(record)),encoding='utf-8')
 observer=arm/'ordinary_observer';observer.mkdir(mode=0o700,exist_ok=False)
 launch=[str(VENV/'bin/python'),str(ORDINARY_STARTUP),'--observer-dir',str(observer),'--',*a[1:]]
 (arm/'SERVE_CMD.txt').write_text(json.dumps({'argv':launch,'protocol_argv':a,'port':p},sort_keys=True)+'\n',encoding='utf-8')
 (arm/'serve_argv.json').write_text(json.dumps({'argv':launch,'protocol_argv':a,'port':p,'env':record},sort_keys=True)+'\n',encoding='utf-8')
 (arm/'serve.log').open('x',encoding='utf-8').close()
 if file_dry_run:
  for name in ('owned_process.json','health.json','serve_args.txt'):probe(arm/name,'formal service lifecycle output')
 return e,launch
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
def suite_plan(arm:Path,trace:Path|None=None)->list[dict]:
 """The frozen T05 six-suite card, expressed without a dev-ACK client command.

 T05 uses normal SSE only.  H1 remains a D06 diagnostic because its published
 H counters have no ordinary-observer equivalent; callers must fail closed
 instead of accidentally starting the candidate's ft_dev probe.
 """
 trace=TRACE if trace is None else trace
 return [
  {'name':'a_two_decode_diff','kind':'ordinary_two_decode','same_prompt':False,'reps':3,'ctx':32000,'max_tokens':512,'output':arm/'a_two_decode_diff.json'},
  {'name':'a_two_decode_same','kind':'ordinary_two_decode','same_prompt':True,'reps':1,'ctx':32000,'max_tokens':512,'output':arm/'a_two_decode_same.json'},
  {'name':'b_stall_cold32k','kind':'ordinary_stall','prefill_kind':'cold32k','reps':3,'delay_s':3,'output':arm/'b_stall_cold32k.json'},
  {'name':'b_stall_agent','kind':'ordinary_stall','prefill_kind':'agent_turn','trace':trace,'round':6,'reps':3,'delay_s':3,'output':arm/'b_stall_agent.json'},
  {'name':'c_pair_short','kind':'ordinary_pair_short','rounds':(3,4),'reps':3,'trace':trace,'output':arm/'c_pair_short.json'},
  {'name':'d_h1','kind':'d06_diagnostic_only','H':(1,8,32),'reps':3,'prefill_target':32052,'output':arm/'d_h1.json',
   'reason':'H1 requires D0 UID steps/counters and the pause endpoint; ordinary SSE worker sidecars cannot establish these metrics'},
 ]
def commands(arm:Path,p:int,trace:Path|None=None)->list[list[str]]:
 """Compatibility view for CPU callers; never a candidate stream invocation."""
 rows=[]
 for item in suite_plan(arm,trace):
  rows.append(['ordinary-sse',item['kind'],'--base-url',f'http://127.0.0.1:{p}/v1','--out',str(item['output']),'--reps',str(item['reps'])])
 return rows
def probe_module():
 probe=WT/'scripts/multisession_probe.py'
 if probe.is_symlink() or not probe.is_file():raise RuntimeError('candidate frontend probe missing')
 spec=importlib.util.spec_from_file_location('t05_probe',probe);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod);return mod
def ordinary_payload(messages:list[dict],*,max_tokens:int,ignore_eos:bool=False)->dict:
 payload={'model':MODEL,'messages':messages,'max_tokens':max_tokens,'temperature':0,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}
 if ignore_eos:payload['ignore_eos']=True
 return payload
def cold_first(arm:Path,p:int)->None:
 """One normal-SSE cold request bound to worker input and sampled tokens."""
 mod=probe_module();tokenizer=mod.load_tokenizer(str(MODEL_PATH));messages,ids=mod.make_messages(tokenizer,32052,f'{RID}-{arm.name}-first')
 source=arm/'first_shot.input.json';source.write_text(json.dumps(ordinary_payload(messages,max_tokens=128),ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 adapter=ordinary_adapter();client=ordinary_client();api=arm/'first_shot.api.json';adapter.ordinary_stream_request(f'http://127.0.0.1:{p}/v1',source,api)
 binding=client.bind(source,api,None,None,arm/'ordinary_observer/inputs.jsonl',arm/'ordinary_observer/tokens.jsonl',arm/'first_shot.binding.json')
 record=adapter.ordinary_binding(binding);expected=hashlib.sha256(json.dumps(ids,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()
 if record['input_ids_sha256']!=expected or record['input_tokens']!=len(ids) or record['completion_tokens']<=0:raise RuntimeError('T05 cold ordinary physical token binding differs')
 write(arm/'first_shot.json',{'frontend_token_count':len(ids),'prompt_sha256':mod.prompt_sha256(ids),'ordinary_binding':record})
def ordinary_parser():
 source=Path(__file__).with_name('candidate_agent_trace_original.py')
 if source.is_symlink() or not source.is_file():raise RuntimeError('ordinary response parser missing')
 return ordinary_module(source,'r045_candidate_agent_trace_original')
def require_t05_ordinary_capability()->None:
 """The card is split into performance and diagnostic phases, never weakened."""
 plan=suite_plan(Path('.'))
 if not any(item['kind']=='d06_diagnostic_only' for item in plan):raise RuntimeError('T05 diagnostic H1 phase absent')
def _payload_file(path:Path,payload:dict)->None:
 path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
def _planned_ids(mod,tokenizer,messages):
 return mod.frontend_ids(tokenizer,messages)
def _run_pair_ordinary(arm:Path,p:int,name:str,left_messages,right_messages,left_ids,right_ids,*,max_tokens:int,ignore_eos:bool,reps:int)->dict:
 adapter=ordinary_adapter();parser=ordinary_parser();inputs=arm/'ordinary_observer/inputs.jsonl';tokens=arm/'ordinary_observer/tokens.jsonl';log=arm/'serve.log';rows=[]
 for rep in range(reps):
  directory=arm/f'{name}.rep{rep}';left=arm/f'{name}.rep{rep}.left.input.json';right=arm/f'{name}.rep{rep}.right.input.json'
  _payload_file(left,ordinary_payload(left_messages,max_tokens=max_tokens,ignore_eos=ignore_eos));_payload_file(right,ordinary_payload(right_messages,max_tokens=max_tokens,ignore_eos=ignore_eos))
  before=log.stat().st_size if log.is_file() else 0
  result=adapter.run_pair(f'http://127.0.0.1:{p}/v1',left,right,directory,inputs,tokens,{'left':left_ids,'right':right_ids},parser,expected_completion=max_tokens if ignore_eos else None,require_fixed_length=ignore_eos)
  after=log.stat().st_size if log.is_file() else 0
  if after<before:raise RuntimeError('serve.log shrank during pair repetition')
  result['serve_log_interval']={'path':str(log),'byte_start':before,'byte_end':after,'captured':log.is_file()}
  rows.append(result)
 value={'schema':'ft_r045_t05_ordinary_pair/v16','name':name,'ordinary_sse':True,'physical_token_sidecar':str(tokens),'reps':rows,'max_tokens':max_tokens,'ignore_eos':ignore_eos}
 write(arm/f'{name}.json',value);return value
def run_two_decode_ordinary(arm:Path,p:int,*,same_prompt:bool,reps:int)->dict:
 mod=probe_module();tokenizer=mod.load_tokenizer(str(MODEL_PATH));seed=f'{RID}-{arm.name}-two-{same_prompt}'
 left,left_ids=mod.make_messages(tokenizer,32000,seed+'-left')
 right,right_ids=(left,left_ids) if same_prompt else mod.make_messages(tokenizer,32000,seed+'-right')
 return _run_pair_ordinary(arm,p,'a_two_decode_same' if same_prompt else 'a_two_decode_diff',left,right,left_ids,right_ids,max_tokens=512,ignore_eos=True,reps=reps)
def _wait_first_observed_token(path:Path,uid:int,deadline:float)->dict:
 while time.monotonic()<deadline:
  if path.is_file():
   for line in path.read_text(encoding='utf-8').splitlines():
    row=json.loads(line)
    if row.get('uid')==uid:
     if type(row.get('time_ns')) is not int or type(row.get('next_token')) is not int:raise RuntimeError('ordinary physical first token differs')
     return row
  time.sleep(.01)
 raise RuntimeError(f'ordinary physical observer lacks first token for UID {uid}')
def _worker_input_time(record:dict)->int:
 value=record['evidence']['worker_input'].get('time_ns')
 if type(value) is not int or value<=0:raise RuntimeError('ordinary worker input timestamp differs')
 return value
def _physical_timing(decode:dict,prefill:dict,network_marker:dict)->dict:
 """Compute only within each clock domain; SSE chunk clocks are never token clocks."""
 decode_times=[row.get('time_ns') for row in decode['token_events']]
 if not decode_times or any(type(value) is not int or value<=0 for value in decode_times):raise RuntimeError('decode physical token timestamps differ')
 start,end=_worker_input_time(prefill),prefill['token_events'][0].get('time_ns')
 if type(end) is not int or end<=start:raise RuntimeError('prefill physical interval differs')
 gaps=[right-left for left,right in zip(decode_times,decode_times[1:])]
 in_window=[value for value in decode_times if start<value<=end]
 return {'schema':'ft_r045_sc2_physical_timing/v1','physical_clock':'worker_sidecar_time_ns','decode_token_time_ns':decode_times,'prefill_worker_input_time_ns':start,'prefill_first_token_time_ns':end,'max_decode_gap_ns':max(gaps,default=None),'interference_decode_tokens':len(in_window),'interference_duration_ns':end-start,'interference_throughput_tokens_per_s':len(in_window)*1_000_000_000/(end-start),'network_sse_clock':'monotonic_ns','prefill_dispatch_time_ns':network_marker['prefill_dispatch_time_ns'],'prefill_dispatch_monotonic_ns':network_marker['prefill_dispatch_monotonic_ns'],'first_sse_time_ns':network_marker['sse_first']['time_ns'],'first_sse_monotonic_ns':network_marker['sse_first']['monotonic_ns'],'clock_domains_must_not_be_subtracted':True}
def run_stall_ordinary(arm:Path,p:int,*,name:str,prefill_messages:list[dict],decode_messages:list[dict],decode_ids:list[int],prefill_ids:list[int],reps:int,delay_s:float)->dict:
 """Read decode SSE continuously; an independent worker schedules interference."""
 adapter=ordinary_adapter();client=ordinary_client();inputs=arm/'ordinary_observer/inputs.jsonl';tokens=arm/'ordinary_observer/tokens.jsonl';rows=[]
 for rep in range(reps):
  decode_input=arm/f'{name}.rep{rep}.decode.input.json';prefill_input=arm/f'{name}.rep{rep}.prefill.input.json';decode_api=arm/f'{name}.rep{rep}.decode.api.json';prefill_api=arm/f'{name}.rep{rep}.prefill.api.json'
  _payload_file(decode_input,ordinary_payload(decode_messages,max_tokens=1500));_payload_file(prefill_input,ordinary_payload(prefill_messages,max_tokens=1))
  marker={};first_seen=threading.Event();interference_done=threading.Event();failures=[];guard=threading.Lock()
  def first(uid,event):
   with guard:
    if first_seen.is_set():raise RuntimeError('ordinary decode produced multiple first-real callbacks')
    marker.update(decode_uid=uid,sse_first=event);first_seen.set()
  def interference():
   try:
    if not first_seen.wait(1800):raise RuntimeError('ordinary decode never reached first real SSE event')
    marker['worker_first']=_wait_first_observed_token(tokens,marker['decode_uid'],time.monotonic()+1800)
    time.sleep(delay_s);marker['prefill_dispatch_time_ns']=time.time_ns();marker['prefill_dispatch_monotonic_ns']=time.monotonic_ns()
    adapter.ordinary_stream_request(f'http://127.0.0.1:{p}/v1',prefill_input,prefill_api)
   except BaseException as exc:
    failures.append(('interference',exc))
   finally:interference_done.set()
  def decode():
   try:adapter.ordinary_stream_request(f'http://127.0.0.1:{p}/v1',decode_input,decode_api,on_first_real=first)
   except BaseException as exc:failures.append(('decode',exc))
  decode_worker=threading.Thread(target=decode,name='r045-ordinary-stall-decode');interference_worker=threading.Thread(target=interference,name='r045-ordinary-stall-prefill')
  decode_worker.start();interference_worker.start();decode_worker.join(3600);interference_worker.join(3600)
  if decode_worker.is_alive() or interference_worker.is_alive():raise RuntimeError('ordinary stall network workers did not terminate before timeout')
  if failures or not first_seen.is_set() or not interference_done.is_set():raise RuntimeError('ordinary stall stream/callback failed: '+repr(failures))
  decode_bind=client.bind(decode_input,decode_api,None,None,inputs,tokens,arm/f'{name}.rep{rep}.decode.binding.json');prefill_bind=client.bind(prefill_input,prefill_api,None,None,inputs,tokens,arm/f'{name}.rep{rep}.prefill.binding.json')
  decode_record,prefill_record=adapter.ordinary_binding(decode_bind),adapter.ordinary_binding(prefill_bind)
  for record,want in ((decode_record,decode_ids),(prefill_record,prefill_ids)):
   digest=hashlib.sha256(json.dumps(want,separators=(',',':')).encode()).hexdigest()
   if record['input_ids_sha256']!=digest or record['prompt_tokens']!=len(want):raise RuntimeError('ordinary stall frontend/worker token binding differs')
  sc2=_physical_timing(decode_record,prefill_record,marker)
  rows.append({'decode':decode_record,'prefill':prefill_record,'first_sse':marker['sse_first'],'first_worker_token':marker['worker_first'],'prefill_dispatch_monotonic_ns':marker['prefill_dispatch_monotonic_ns'],'sc2':sc2,'timing_basis':'physical Detoken sidecar for token counts/gaps; SSE monotonic for transport dispatch/first only'})
 value={'schema':'ft_r045_t05_ordinary_stall/v11','ordinary_sse':True,'physical_token_sidecar':str(tokens),'delay_s':delay_s,'reps':rows}
 write(arm/f'{name}.json',value);return value
PREFILL_NEW_SEQ=re.compile(r'#new-seq:\s*(?P<new_seq>\d+),\s*#new-token:\s*(?P<new_token>\d+),\s*#cached-token:\s*(?P<cached_token>\d+)')
def sc3_prefill_evidence(arm:Path,pair:dict)->dict:
 log=arm/'serve.log';raw=log.read_bytes() if log.is_file() else b'';classifications=[]
 reps=pair.get('reps') if isinstance(pair,dict) else None
 if not isinstance(reps,list) or len(reps)!=3:raise RuntimeError('SC3 requires exactly three pair repetitions')
 for index,rep in enumerate(reps):
  records=rep.get('records') if isinstance(rep,dict) else None;interval=rep.get('serve_log_interval') if isinstance(rep,dict) else None
  if not isinstance(records,list) or len(records)!=2:raise RuntimeError('pair result/schema lacks two physical records')
  if any(type(row.get('uid')) is not int or not isinstance(row.get('input_ids_sha256'),str) or len(row['input_ids_sha256'])!=64 for row in records):raise RuntimeError('pair physical UID/input binding differs')
  if not isinstance(interval,dict) or interval.get('captured') is not True:
   classifications.append({'rep':index,'state':'not_captured','serve_log_interval':interval,'uids':[row['uid'] for row in records],'worker_input_sha256':[row['input_ids_sha256'] for row in records]});continue
  start,end=interval.get('byte_start'),interval.get('byte_end')
  if type(start) is not int or type(end) is not int or not (0<=start<=end<=len(raw)):raise RuntimeError('pair log interval differs')
  text=raw[start:end].decode('utf-8',errors='replace');events=[]
  for line_no,line in enumerate(text.splitlines(),1):
   found=PREFILL_NEW_SEQ.search(line)
   if found:events.append({'relative_line':line_no,'text':line,'new_seq':int(found['new_seq']),'new_token':int(found['new_token']),'cached_token':int(found['cached_token'])})
  state='merged' if any(event['new_seq']==2 for event in events) else 'not_merged'
  classifications.append({'rep':index,'state':state,'serve_log_interval':interval,'prefill_events':events,'uids':[row['uid'] for row in records],'worker_input_sha256':[row['input_ids_sha256'] for row in records],'api_paths':[row.get('evidence',{}).get('api',{}).get('path') for row in records],'client_dispatches_only_pair':True})
 complete=all(row['state']!='not_captured' for row in classifications);k=sum(row['state']=='merged' for row in classifications)
 value={'schema':'ft_r045_sc3_prefill/v3','serve_log':str(log),'serve_log_sha256':sha(log) if log.is_file() else None,'repetitions':classifications,'k_same_batch_new_seq_2':k,'denominator':3,'complete_capture':complete,'k_zero_valid':complete and k==0,'log_uid_binding':'UIDs/input hashes are direct API/worker bindings; bounded serve.log windows classify only this client-pair dispatch and are not presented as direct UID evidence'}
 write(arm/'sc3_prefill_evidence.json',value);return value

def analyze_d02_timeline(base:Path,pairs:list[list[int]])->dict:
 paths={name:base.with_name(base.name+suffix) for name,suffix in {'steps':'_decode_steps.jsonl','timeline':'_decode_timeline.jsonl','prefill':'_prefill.jsonl'}.items()}
 if any(path.is_symlink() or not path.is_file() for path in paths.values()):raise RuntimeError('D02 timeline/step/prefill artifacts missing')
 rows={name:[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] for name,path in paths.items()}
 step_index={}
 for row in rows['steps']:
  if type(row.get('step')) is not int or type(row.get('t')) not in (int,float) or not math.isfinite(row['t']) or type(row.get('bs')) is not int or not isinstance(row.get('rids'),list):raise RuntimeError('D02 step schema differs')
  step_index.setdefault(row['step'],[]).append(row)
 coverage=[]
 for index,trow in enumerate(rows['timeline']):
  step=trow.get('step');candidates=step_index.get(step,[])
  srow=next((candidate for candidate in candidates if trow.get('t')==candidate.get('t') and trow.get('rids')==candidate.get('rids') and trow.get('bs')==candidate.get('bs')),None)
  if srow is None or type(trow.get('bs')) is not int or not isinstance(trow.get('layers'),list) or not trow['layers']:raise RuntimeError('D02 step/timeline binding differs')
  for expected,layer in enumerate(trow['layers']):
   values=[layer.get(key) for key in ('copy_start_ms','copy_end_ms','compute_start_ms','compute_end_ms')]
   if layer.get('layer')!=expected or any(type(value) not in (int,float) or not math.isfinite(value) for value in values) or values[1]<values[0] or values[3]<values[2]:raise RuntimeError('D02 per-layer copy/compute schema differs')
  key=(trow['step'],trow['t'],tuple(trow['rids']),trow['bs'])
  coverage.append({'index':index,'key':key,'row':trow})
 if len(pairs)!=3 or any(not isinstance(pair,list) or len(pair)!=2 or any(type(uid) is not int for uid in pair) or pair[0]==pair[1] for pair in pairs):raise RuntimeError('SC5 requires three actual two-UID repetitions')
 all_uids=[uid for pair in pairs for uid in pair]
 if len(set(all_uids))!=6:raise RuntimeError('SC5 cross-repetition UID reuse differs')
 used=set();bound=[]
 for rep,pair in enumerate(pairs):
  match=next((item for item in coverage if item['key'] not in used and set(pair)<=set(item['row']['rids'])),None)
  if match is None:raise RuntimeError(f'D02 timeline lacks unique two-UID step for repetition {rep}')
  used.add(match['key']);row=match['row']
  bound.append({'rep':rep,'uids':pair,'step':row['step'],'t':row['t'],'actual_bs':row['bs'],'actual_rids':row['rids'],'timeline_row':match['index']})
 return {'schema':'ft_r045_sc5_d02_timeline/v4','base':str(base),'artifacts':{name:{'path':str(path),'sha256':sha(path)} for name,path in paths.items()},'repetitions':bound,'timeline_rows':len(rows['timeline']),'layer_rows':sum(len(item['row']['layers']) for item in coverage),'diagnostic_only':True,'token_cap':512,'exact_512_not_claimed':True}

def sc5_timeline(arm:Path)->dict:
 observer=arm/'ordinary_observer';rows=[]
 for name in ('inputs.jsonl','tokens.jsonl'):
  path=observer/name
  if not path.is_file():raise RuntimeError('SC5 ordinary observer sidecar missing: '+str(path))
  for index,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
   if line.strip():rows.append({'source':name,'line':index,'row':json.loads(line)})
 value={'schema':'ft_r045_sc5_ordinary_timeline/v1','clock':'time_ns','sidecars':{name:{'path':str(observer/name),'sha256':sha(observer/name)} for name in ('inputs.jsonl','tokens.jsonl')},'timeline':rows}
 write(arm/'sc5_timeline.json',value);return value

def run_t05_performance(arm:Path,p:int,trace:Path)->dict:
 mod=probe_module();tokenizer=mod.load_tokenizer(str(MODEL_PATH));diff=run_two_decode_ordinary(arm,p,same_prompt=False,reps=3);same=run_two_decode_ordinary(arm,p,same_prompt=True,reps=1)
 decode,decode_ids=mod.make_messages(tokenizer,4000,f'{RID}-{arm.name}-stall-decode')
 cold,cold_ids=mod.make_messages(tokenizer,32052,f'{RID}-{arm.name}-stall-cold')
 agent=mod._trace_messages(trace,6);agent_ids=mod.frontend_ids(tokenizer,agent)
 stall_cold=run_stall_ordinary(arm,p,name='b_stall_cold32k',prefill_messages=cold,decode_messages=decode,decode_ids=decode_ids,prefill_ids=cold_ids,reps=3,delay_s=3)
 stall_agent=run_stall_ordinary(arm,p,name='b_stall_agent',prefill_messages=agent,decode_messages=decode,decode_ids=decode_ids,prefill_ids=agent_ids,reps=3,delay_s=3)
 left,right=mod._trace_messages(trace,3),mod._trace_messages(trace,4);pair=_run_pair_ordinary(arm,p,'c_pair_short',left,right,mod.frontend_ids(tokenizer,left),mod.frontend_ids(tokenizer,right),max_tokens=200,ignore_eos=False,reps=3)
 return {'schema':'ft_r045_t05_performance/v11','d0_enabled':False,'pause_enabled':False,'route_trace_enabled':False,'ordinary_sse_only':True,'results':{'a_two_decode_diff':diff,'a_two_decode_same':same,'b_stall_cold32k':stall_cold,'b_stall_agent':stall_agent,'c_pair_short':pair},'sc3':sc3_prefill_evidence(arm,pair),'sc5':sc5_timeline(arm),'h1':'separate_diagnostic_phase'}
def run_t05_h1_diagnostic(directory:Path,worktree:Path,p:int)->dict:
 """Run D02 diagnostic requests; final timeline sealing follows owned-service stop."""
 d=d06_module();e=d.environment(worktree,directory/'d0');two=directory/'timeline_two_decode.json'
 subprocess.run([str(VENV/'bin/python'),str(worktree/d.PROBE),'two-decode','--base-url',f'http://127.0.0.1:{p}/v1','--model',MODEL,'--ctx','32000','--max-tokens','512','--same-prompt','0','--reps','3','--out',str(two)],cwd=worktree,env=e,check=True,timeout=3600)
 two_raw=json.loads(two.read_text());pairs=[]
 for rep in two_raw.get('reps',[]):
  ways=rep.get('per_way',[]);pairs.append([row.get('uid') for row in ways])
 output=directory/'d_h1.json'
 subprocess.run([str(VENV/'bin/python'),str(worktree/d.PROBE),'h1','--base-url',f'http://127.0.0.1:{p}/v1','--model',MODEL,'--H','1,8,32','--reps','3','--prefill-target','32052','--out',str(output)],cwd=worktree,env=e,check=True,timeout=3600)
 raw=json.loads(output.read_text());reps=raw.get('reps') if isinstance(raw,dict) else None
 if not isinstance(reps,list) or len(reps)!=3:raise RuntimeError('T05 H1 diagnostic requires exactly three raw repetitions')
 validated=[{'rep':index,'validator':d.validate_g4({**raw,'reps':[rep]},directory/'serve.log')} for index,rep in enumerate(reps)]
 return {'schema':'ft_r045_t05_h1_diagnostic/v16','d0_enabled':True,'pause_enabled':True,'performance_numeric_reuse_forbidden':True,'timeline_two_decode':two_raw,'timeline_uid_pairs':pairs,'raw_h1':raw,'per_rep_validator':validated,'output':str(output),'output_sha256':sha(output),'sc5_pending_owned_service_stop':True}

def run_t05_h1_diagnostic_arm(directory:Path)->dict:
 d=d06_module();directory.mkdir();p=port();proc=None;value=None
 try:
  proc=d.start_server(directory,WT,p)
  value=run_t05_h1_diagnostic(directory,WT,p)
 except BaseException as error:
  error.owned_process=getattr(error,'owned_process',proc);raise
 finally:
  if proc is not None:d.load_owned_lifecycle().stop_owned_process(proc)
 if value is None:raise RuntimeError('T05 diagnostic value missing after owned service stop')
 value['sc5_d02_timeline']=analyze_d02_timeline(directory/'d0',value.pop('timeline_uid_pairs'))
 value['sc5_pending_owned_service_stop']=False
 return value

def _ordinary_request_probes(arm:Path,stem:str,side:str)->list[dict]:
 base=f'{stem}.{side}'
 return [probe(arm/f'{base}.input.json','formal ordinary request input'),probe(arm/f'{base}.api.json','formal ordinary API capture'),probe(arm/f'{base}.api.sse','formal ordinary raw SSE'),probe(arm/f'{base}.api.events.jsonl','formal ordinary SSE event clocks'),probe(arm/f'{base}.binding.json','formal ordinary worker binding')]
def dry_workloads(arm:Path,p:int,trace:Path)->list[dict]:
 probes=[probe(arm/'first_shot.input.json','formal T05 cold input'),probe(arm/'first_shot.api.json','formal T05 cold API'),probe(arm/'first_shot.api.sse','formal T05 cold raw SSE'),probe(arm/'first_shot.api.events.jsonl','formal T05 cold clocks'),probe(arm/'first_shot.binding.json','formal T05 cold binding'),probe(arm/'first_shot.json','formal T05 cold result')]
 observer=arm/'ordinary_observer'
 for name in ('inputs.jsonl','tokens.jsonl','shutdown.json','input-0.json'):
  probes.append(probe(observer/name,'formal ordinary observer output'))
 for item in suite_plan(arm,trace):
  if item['kind']=='d06_diagnostic_only':continue
  probes.append(probe(item['output'],'formal T05 ordinary-SSE suite output'))
  if item['kind'] in ('ordinary_two_decode','ordinary_pair_short'):
   for rep in range(item['reps']):
    for side in ('left','right'):
     probes.extend(_ordinary_request_probes(arm,f"{item['name']}.rep{rep}",side))
    probes.append(probe(arm/f"{item['name']}.rep{rep}/result.json",'formal ordinary pair result'))
  if item['kind']=='ordinary_stall':
   for rep in range(item['reps']):
    for side in ('decode','prefill'):probes.extend(_ordinary_request_probes(arm,f"{item['name']}.rep{rep}",side))
 probes.extend([probe(arm/'sc3_prefill_evidence.json','formal SC3 serve prefill lines'),probe(arm/'sc5_timeline.json','formal SC5 physical timeline')])
 return probes
def dry_h1_diagnostic(directory:Path,p:int)->list[dict]:
 # Reuse D06's real writer to create its observer/environment/startup sources;
 # this stops before Popen and request dispatch.
 d=d06_module();d.prepare_service_files(directory,WT,p)
 names=('serve.log','owned_process.json','SERVE_CMD.json','d06_pause_observer_v3.py','d06_pause_startup_v3.py','timeline_two_decode.json','timeline_two_decode.rep0.way0.tokens.json','timeline_two_decode.rep0.way1.tokens.json','timeline_two_decode.rep1.way0.tokens.json','timeline_two_decode.rep1.way1.tokens.json','timeline_two_decode.rep2.way0.tokens.json','timeline_two_decode.rep2.way1.tokens.json','d_h1.json','d0_decode_steps.jsonl','d0_decode_timeline.jsonl','d0_prefill.jsonl','model_process_cuda.jsonl','cuda_memory_summary.json','owned_cleanup.json')
 return [probe(directory/name,'formal D06 H1 diagnostic output') if not (directory/name).exists() else {'path':str(directory/name),'sha256':sha(directory/name),'purpose':'formal D06 H1 diagnostic writer'} for name in names]

def normalized_serve(arm:Path)->dict:
 record=json.loads((arm/'serve_argv.json').read_text())
 command=json.loads((arm/'SERVE_CMD.txt').read_text())
 if set(command)!={'argv','protocol_argv','port'} or any(command[key]!=record.get(key) for key in command):raise RuntimeError('wrapper command records differ')
 argv=record.get('argv');protocol=record.get('protocol_argv');p=record.get('port')
 if not isinstance(argv,list) or not isinstance(protocol,list) or type(p) is not int:raise RuntimeError('wrapper command schema differs')
 expected_observer=(arm/'ordinary_observer').resolve()
 if len(argv)<6 or argv[0]!=str(VENV/'bin/python') or argv[1]!=str(ORDINARY_STARTUP) or argv[2]!='--observer-dir' or Path(argv[3]).resolve()!=expected_observer or argv[4]!='--':raise RuntimeError('ordinary wrapper argv differs')
 if protocol!=serve_argv(p) or argv[5:]!=protocol[1:]:raise RuntimeError('ordinary wrapper/server argv suffix differs')
 return {'protocol_argv':protocol,'port':p}
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
 paths=(Path(__file__).resolve(),ORDINARY_ADAPTER.resolve(),ORDINARY_CLIENT.resolve(),ORDINARY_STARTUP.resolve(),Path(__file__).with_name('r046c_t06_ordinary_client_v2.py').resolve(),Path(__file__).with_name('r046e_t06_ordinary_client_v6.py').resolve(),Path(__file__).with_name('r058_concurrent_request.py').resolve(),Path(__file__).with_name('d06_g3g4_prepare.py').resolve(),Path(__file__).with_name('d07_g3g4_prepare.py').resolve(),Path(__file__).with_name('r045_round_json_append_v1.py').resolve(),*(Path(__file__).with_name(name).resolve() for name in d06_module().PAUSE_SOURCE_NAMES),(Path(__file__).parent/'d04_original/serve_args_diff.py').resolve(),Path(__file__).with_name('t16_full_tail_base_runner.py').resolve(),(WT/'scripts/multisession_probe.py').resolve(),Path(__file__).with_name('candidate_agent_trace_original.py').resolve(),*(OWNED_SOURCE/'helpers/raw'/name for name in ('cold_eq.py','probe_ft_cold32k.py')))
 return {str(path):sha(path) for path in paths}
def archive_sources(target:Path)->list[dict]:
 target.mkdir(mode=0o700)
 rows=[]
 for source in map(Path,source_hashes()):
  destination=target/(('candidate/'+source.name) if source==WT/'scripts/multisession_probe.py' else ('cold_helpers/'+source.name) if source.parent==OWNED_SOURCE/'helpers/raw' else ('d04_original/'+source.name) if source.parent.name=='d04_original' else source.name)
  destination.parent.mkdir(parents=True,exist_ok=True);rows.append(copy_runtime(source,destination))
 write(target/'source_identity.json',{'schema':'ft_r045_source_identity/v16','harness_version':HARNESS_VERSION,'source_sha256':source_hashes(),'copies':rows})
 return rows
def dry_run_directory(round_path=None)->Path:
 round_path=ROUND if round_path is None else round_path
 return round_path.parent/f'.dryrun_R045_section14_v17_{RID}'
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
  diagnostic=target/f'{name}_h1_diagnostic';diagnostic.mkdir(mode=0o700)
  diagnostic_outputs=dry_h1_diagnostic(diagnostic,fixture_port)
  arms.append({'name':name,'port':fixture_port,'outputs':outputs,'diagnostic_directory':str(diagnostic),'diagnostic_outputs':diagnostic_outputs,'env_sha256':sha(arm/'ENV.json'),'env_txt_sha256':sha(arm/'ENV.txt'),'serve_cmd_sha256':sha(arm/'SERVE_CMD.txt')})
 probes=[probe(target/name,'formal T05 metadata') for name in ('preflight.json','result.json','history.json','MANIFEST.sha256')]
 receipt={'schema':'ft_r045_dry_run/v17','harness_version':HARNESS_VERSION,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'passed':True,'source_sha256':source_hashes(),'source_copies':copies,'cold_helpers':cold_helpers,'owner':{'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')},'cwd':os.getcwd(),'worktree':{'path':str(WT),'parent':str(WT.parent)},'formal_rid_directory_created':False,'formal_directory':str(ROUND),'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'candidate':candidate,'port':fixture_port,'g3g4':g3g4,'arms':arms,'cpu_file_probes':probes}
 write(target/'dry_run_receipt.json',receipt);path=target/'dry_run_receipt.json';path.chmod(0o444)
 return {**receipt,'dry_run_directory':str(target),'receipt_sha256':sha(path)}
def require_dry_run_receipt()->dict:
 path=dry_run_directory()/'dry_run_receipt.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R045 dry-run receipt absent or writable')
 value=json.loads(path.read_text());owner={'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')}
 if (value.get('schema')!='ft_r045_dry_run/v17' or value.get('harness_version')!=HARNESS_VERSION or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=PARENT or value.get('passed') is not True or value.get('source_sha256')!=source_hashes() or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('worktree')!={'path':str(WT),'parent':str(WT.parent)} or any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated'))):raise RuntimeError('R045 dry-run receipt identity differs')
 return {'path':str(path),'sha256':sha(path)}
def require_startup_review(dry_receipt:dict)->dict:
 path=RUNS/'reviews'/f'{RID}_section14_startup_review_v17.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R045 startup review absent or writable')
 value=json.loads(path.read_text());expected={'schema':'ft_r045_startup_review/v17','harness_version':HARNESS_VERSION,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'approved':True,'verdict':'PASS','source_sha256':source_hashes(),'dry_run_receipt':dry_receipt['path'],'dry_run_receipt_sha256':dry_receipt['sha256']}
 if any(value.get(k)!=v for k,v in expected.items()):raise RuntimeError('R045 startup review binding differs')
 return {'path':str(path),'sha256':sha(path)}


R040G_MEASUREMENT_COMMIT = "effb9969706922ddad9e59b96377e46469ebe97f"
HISTORICAL_T20_COMMIT = "0aa23431e5b800797543bdecbf35a01045131d7d"
def require_r040g_measurement(closure):
    document = json.loads(Path(closure).read_text())
    if (document.get("base", {}).get("commit") != R040G_MEASUREMENT_COMMIT
            or document.get("experimental", {}).get("candidate_commit") != R040G_MEASUREMENT_COMMIT):
        raise RuntimeError("E2-R040g measured closure is not bound to effb996")
    return closure

def run(*,owned_child:bool=False,batch:int|None=None,launch_receipt:Path|None=None)->dict:
 shared=d07_helpers()
 if owned_child:
  if batch is None or launch_receipt is None:raise RuntimeError('T05 owned child requires reserved batch and receipt')
  shared.require_child_receipt(launch_receipt,batch,WT,RUNS,rid=RID,expected_argv=child_argv(batch,launch_receipt),schema='ft_t05_owned_launch/v1')
 candidate=git_checked();verify_pause_helpers()
 dry_receipt=require_dry_run_receipt();review=require_startup_review(dry_receipt)
 r041,t20=require_kept('E2-R041-gate-D17'),d07_helpers().require_t20_failed_harness();r040f=shared.require_closed_round('E2-R040f','failed_harness');r040g=require_r040g_measurement(shared.require_closed_round('E2-R040g','measured'));d16_failed=d16_failed_metadata();r055=r055_failed_metadata()
 if ROUND.exists():raise RuntimeError('E2-R045 directory already exists')
 # Do not reserve a GPU batch for a card whose H1 metric cannot be established
 # under the required no-D0/no-pause performance environment.
 require_t05_ordinary_capability()
 if not owned_child:
  if LOCK.exists() or LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists; T05 remains queued')
  owned=lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py','a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf','t05_batch')
  batch=helper.next_batch(Path('/data2/_shared/runs/ft_rounds'));RUNS.mkdir(parents=True,exist_ok=True);receipt_path=RUNS/f'launch_{RID}_batch{batch}.json';argv=child_argv(batch,receipt_path)
  reserved={'schema':'ft_t05_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':shared.argv_sha256(argv),'controller':shared.process_birth(),'dry_run_receipt':dry_receipt,'startup_review':review,'section10_basis':r055,'prerequisites':{'E2-R041-gate-D17':sha(r041),'E2-R040':sha(t20),'E2-R040f_failed':sha(r040f),'E2-R040g':sha(r040g),'historical_t20_commit':HISTORICAL_T20_COMMIT,'D16_failed_metadata_only':d16_failed,'R055_failed_metadata_only':r055,'combined_d06_g3g4':'local' }}
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
    proc=start(arm,p);cold_first(arm,p);performance=run_t05_performance(arm,p,bound_trace)
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
   diagnostic=run_t05_h1_diagnostic_arm(raw/f'{name}_h1_diagnostic')
   arms.append({'name':name,'port':p,'files':{f:sha(arm/f) for f in ('first_shot.json','a_two_decode_diff.json','a_two_decode_same.json','b_stall_cold32k.json','b_stall_agent.json','c_pair_short.json')},'performance':performance,'diagnostic_h1':diagnostic,'d0_disabled':True,'route_trace_disabled':True,'pause_disabled':True})
  if normalized_serve(raw/'P1')!=normalized_serve(raw/'P2'):raise RuntimeError('P1/P2 service arguments differ; only log PID differences are permitted')
  strict_log_args(raw/'P1'/'serve.log',raw/'P2'/'serve.log')
  result={'schema':'ft_t05_raw_measurement/v1','rid':RID,'candidate_commit':CANDIDATE,'candidate':candidate,'state':'pending_review','proposed_verdict':'measured','raw_measurement_before_D04':True,'batch':batch,'owner':owner,'r041_sha256':sha(r041),'t20_sha256':sha(t20),'r040f_sha256':sha(r040f),'d16_failed_metadata':d16_failed,'section10_basis':r055,'harness_version':HARNESS_VERSION,'g3g4':g3g4,'trace_input':'trace_input.json','trace_sha256':TRACE_SHA,'arms':arms,'s_batch_slot':'pending: use only the separately delivered D16 command'}
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
  a=Path(x);plan=suite_plan(a);c=commands(a,34567)
  assert len(c)==6 and all(row[0]=='ordinary-sse' and '8095' not in row for row in c)
  assert ['--kv-reserve-tokens','98304']==serve_argv(34567)[serve_argv(34567).index('--kv-reserve-tokens'):serve_argv(34567).index('--kv-reserve-tokens')+2]
  assert plan[0]['same_prompt'] is False and plan[1]['same_prompt'] is True and plan[-1]['kind']=='d06_diagnostic_only'
 print('SELFTEST PASS: T05 ordinary SSE plan, 98304 window, H1 D06-only fail-closed')
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--self-test',action='store_true');p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS);p.add_argument('--batch',type=int,help=argparse.SUPPRESS);p.add_argument('--launch-receipt',type=Path,help=argparse.SUPPRESS);a=p.parse_args(argv)
 if a.self_test:self_test();return 0
 if a.dry_run:
  if a.run or a.owned_child or a.batch is not None or a.launch_receipt is not None:raise RuntimeError('--dry-run cannot mix run, child, batch, or receipt')
  print(json.dumps(dry_run()));return 0
 if not a.run:print(json.dumps({'rid':RID,'candidate_commit':CANDIDATE,'cpu_only':True,'worktree':str(WT),'trace':str(TRACE),'arms':['P1','P2'],'kv_window':98304,'commands_per_arm':6,'cpu_only_not_formal_ready':True,'ordinary_h1_separate_diagnostic_phase':True}));return 0
 print(json.dumps(run(owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt)));return 0
if __name__=='__main__':raise SystemExit(main())

