#!/usr/bin/env python3
"""Prepare/run raw E2-R045 T05 only after its queued prerequisites.

Omitting --run is CPU-only and never binds a socket, starts a service, or
touches the GPU.  --run writes raw pending_review evidence only; D04 owns any
formal round/manifest closure.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path
import shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1-ordinary-rewind'; VENV=ROOT/'venv'
RUNS=ROOT/'runs/dev_T05'; LOCK=Path('/data2/_shared/gpu.lock'); ROUND=Path('/data2/_shared/runs/ft_rounds/E2-R045')
RID='E2-R045'; CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'; MODEL='Qwen3.8-Flash-Next-NVFP4'
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'; TRACE=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json')
OWNED_SOURCE=ROOT/'runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools'; OWNED_SHA='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path:Path,value:dict)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def lifecycle():
 p=OWNED_SOURCE/'t17_owned_launch_protocol.py'
 if p.is_symlink() or sha(p)!=OWNED_SHA:raise RuntimeError('pinned owned lifecycle differs')
 spec=importlib.util.spec_from_file_location('t05_lifecycle',p);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod);return mod
def port()->int:
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def git_checked()->dict:
 if WT.is_symlink():raise RuntimeError('candidate worktree is a symlink')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 probe=WT/'scripts/multisession_probe.py'
 if head!=CANDIDATE or dirty or probe.is_symlink() or not probe.is_file():raise RuntimeError('clean E2-base.1 candidate/probe required')
 return {'worktree':str(WT),'commit':head,'probe_raw_sha256':sha(probe)}
def require_kept(rid:str)->Path:
 source=Path(__file__).with_name('d07_g3g4_prepare.py')
 if source.is_symlink() or not source.is_file():raise RuntimeError('D07 sealed-round gate source missing')
 spec=importlib.util.spec_from_file_location('t05_sealed_round_gate',source);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
 return mod.require_closed_round(rid,'kept')
def require_d06()->Path:
 hits=[]
 for p in (ROOT/'runs/dev_D06').glob('E2-R042_*/result.json'):
  try:
   d=json.loads(p.read_text());g3=d.get('g3',{});g4=d.get('g4',{})
   cleanup=p.with_name('owned_cleanup.json')
   c=json.loads(cleanup.read_text())
   if d.get('schema')=='ft_d06_g3g4_result/v1' and d.get('verdict')=='development_selfcheck_pass' and d.get('rid')=='E2-R042' and d.get('candidate_commit')==CANDIDATE and g3.get('per_way_decode_tps') and g4.get('idle_start_wallclock_s') is not None and c.get('schema')=='ft_d06_owned_cleanup/v1' and c.get('rid')=='E2-R042' and c.get('candidate_commit')==CANDIDATE and c.get('batch')==d.get('batch') and c.get('owner')==d.get('owner') and c.get('lock_released') is True:hits.append(p)
  except (OSError,ValueError):pass
 if len(hits)!=1:raise RuntimeError(f'exactly one completed D06 G3/G4 result required, found {len(hits)}')
 return hits[0]
def env(arm:Path)->dict:
 e=os.environ.copy()
 for k in list(e):
  if k.startswith('FT_') or k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES'):e.pop(k)
 e.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONPATH=str(WT/'python'),VIRTUAL_ENV=str(VENV),PATH=str(VENV/'bin')+':'+e.get('PATH',''),CUDA_VISIBLE_DEVICES='0',FT_DEV_D0='1',FT_DEV_D0_PATH=str(arm/'d0'),FT_DEV_D0_TIMELINE='1',FT_DEV_D0_TIMELINE_STEPS='20000',FT_DEV_PAUSE_ENDPOINT='1')
 return e
def serve_argv(p:int)->list[str]:return [str(VENV/'bin/ft'),'serve','--model-path',str(MODEL_PATH),'--served-model-name',MODEL,'--host','127.0.0.1','--port',str(p),'--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--quant-backend','moe.nvfp4=triton','--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','73728','--max-seq-len-override','73728','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--tool-call-parser','qwen3_coder','--reasoning-parser','qwen3','--prefill-layer-major','--mamba-host-slots','0']
def start(arm:Path,p:int):
 e=env(arm);a=serve_argv(p);(arm/'serve_argv.json').write_text(json.dumps({'argv':a,'env':{k:e[k] for k in ('CUDA_VISIBLE_DEVICES','FT_DEV_D0','FT_DEV_D0_PATH','FT_DEV_D0_TIMELINE','FT_DEV_D0_TIMELINE_STEPS','FT_DEV_PAUSE_ENDPOINT')}})+'\n')
 log=(arm/'serve.log').open('x');proc=subprocess.Popen(a,cwd=WT,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=lifecycle().process_identity(proc.pid)
  if birth is None or birth.get('pgid')!=proc.pid or birth.get('session')!=proc.pid:raise RuntimeError('service lacks private PGID/session')
  write(arm/'owned_process.json',{'pid':proc.pid,'birth':birth,'port':p})
  until=time.monotonic()+900
  while time.monotonic()<until:
   if proc.poll() is not None:raise RuntimeError('service exited before ready')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=3) as r:
     if json.load(r).get('status')=='ok':return proc
   except (OSError,ValueError):pass
   time.sleep(2)
  raise TimeoutError('service readiness timeout')
 except BaseException:
  try:lifecycle().stop_owned_process(proc)
  except BaseException as cleanup_error:
   cleanup_error.owned_process=proc
   raise
  raise
def commands(arm:Path,p:int)->list[list[str]]:
 base=[str(VENV/'bin/python'),str(WT/'scripts/multisession_probe.py')];common=['--base-url',f'http://127.0.0.1:{p}/v1','--model',MODEL]
 return [base+['two-decode']+common+['--ctx','32000','--max-tokens','512','--same-prompt','0','--reps','3','--out',str(arm/'a_two_decode_diff.json')],base+['two-decode']+common+['--ctx','32000','--max-tokens','512','--same-prompt','1','--reps','1','--out',str(arm/'a_two_decode_same.json')],base+['stall']+common+['--decode-ctx','4000','--decode-max-tokens','1500','--prefill-kind','cold32k','--prefill-target','32052','--delay','3','--reps','3','--out',str(arm/'b_stall_cold32k.json')],base+['stall']+common+['--decode-ctx','4000','--decode-max-tokens','1500','--prefill-kind','agent_turn','--trace',str(TRACE),'--round','6','--delay','3','--reps','3','--out',str(arm/'b_stall_agent.json')],base+['pair-short']+common+['--trace',str(TRACE),'--rounds','3,4','--reps','3','--out',str(arm/'c_pair_short.json')],base+['h1']+common+['--H','1,8,32','--reps','3','--prefill-target','32052','--out',str(arm/'d_h1.json')]]
def cold_first(arm:Path,p:int)->None:
 """One real 32,052-token cold request using the candidate D06 ACK client."""
 probe=WT/'scripts/multisession_probe.py';spec=importlib.util.spec_from_file_location('t05_probe',probe);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
 tokenizer=mod.load_tokenizer(str(MODEL_PATH));messages,ids=mod.make_messages(tokenizer,32052,f'{RID}-{arm.name}-first')
 record=mod.stream_request(base_url=f'http://127.0.0.1:{p}/v1',model=MODEL,timeout=1800,messages=messages,max_tokens=128)
 write(arm/'first_shot.json',{'frontend_token_count':len(ids),'prompt_sha256':mod.prompt_sha256(ids),'record':record})
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
def run()->dict:
 candidate=git_checked()
 r041,t20,d06=require_kept('E2-R041-gate-D17'),require_kept('E2-R040'),require_d06()
 if ROUND.exists():raise RuntimeError('E2-R045 directory already exists')
 helper=lifecycle().verified_module(ROOT/'runs/plan_batches/e2_launch.py','a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf','t05_batch');batch=helper.next_batch(Path('/data2/_shared/runs/ft_rounds'));owner=lock(batch);raw=None;proc=None
 try:
  used=[int(x) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).splitlines() if x.strip()]
  if not used or any(x>=1000 for x in used):raise RuntimeError(f'GPU not idle: {used}')
  if not TRACE.is_file() or TRACE.is_symlink():raise RuntimeError('retained T2 trace missing')
  raw=RUNS/(RID+'_'+time.strftime('%Y%m%d_%H%M%S'));raw.mkdir(parents=True);shutil.copy2(__file__,raw/Path(__file__).name)
  arms=[]
  fixture_port=port()
  for name in ('P1','P2'):
   arm=raw/name;arm.mkdir();p=fixture_port;proc=None
   try:
    proc=start(arm,p);cold_first(arm,p)
    for cmd in commands(arm,p):subprocess.run(cmd,cwd=WT,env=env(arm),check=True,timeout=3600)
   except BaseException as error:
    proc=getattr(error,'owned_process',proc)
    raise
   finally:
    if proc is not None:
     lifecycle().stop_owned_process(proc)
     proc=None
   for evidence in (arm/'d0_decode_steps.jsonl',arm/'d0_decode_timeline.jsonl'):
    if evidence.is_symlink() or not evidence.is_file() or not evidence.read_bytes().strip():raise RuntimeError(f'{name} lacks required D0 evidence: {evidence.name}')
   arms.append({'name':name,'port':p,'files':{f:sha(arm/f) for f in ('first_shot.json','a_two_decode_diff.json','a_two_decode_same.json','b_stall_cold32k.json','b_stall_agent.json','c_pair_short.json','d_h1.json')},'timeline':str(arm/'d0_decode_timeline.jsonl')})
  if normalized_serve(raw/'P1')!=normalized_serve(raw/'P2'):raise RuntimeError('P1/P2 service arguments differ; only log PID differences are permitted')
  strict_log_args(raw/'P1'/'serve.log',raw/'P2'/'serve.log')
  result={'schema':'ft_t05_raw_measurement/v1','rid':RID,'candidate_commit':CANDIDATE,'candidate':candidate,'state':'pending_review','proposed_verdict':'measured','raw_measurement_before_D04':True,'batch':batch,'owner':owner,'r041_sha256':sha(r041),'t20_sha256':sha(t20),'d06_result_sha256':sha(d06),'arms':arms,'s_batch_slot':'pending: use only the separately delivered D16 command'}
  write(raw/'result.json',result);return result
 except BaseException as error:
  if raw is not None:write(raw/'failed_harness.json',{'rid':RID,'batch':batch,'owner':owner,'error':repr(error),'raw_measurement_preserved':True})
  raise
 finally:
  if proc is not None and lifecycle().owned_group_alive(proc.pid):raise RuntimeError('T05 owned service still alive; GPU lock preserved')
  unlock(owner)
  if raw is not None:write(raw/'owned_cleanup.json',{'schema':'ft_t05_owned_cleanup/v1','rid':RID,'batch':batch,'owner':owner,'lock_released':True})
def self_test()->None:
 with tempfile.TemporaryDirectory() as x:
  a=Path(x);c=commands(a,34567);assert len(c)==6 and all('8095' not in z for q in c for z in q);assert ['--kv-reserve-tokens','73728']==serve_argv(34567)[serve_argv(34567).index('--kv-reserve-tokens'):serve_argv(34567).index('--kv-reserve-tokens')+2];assert c[0][c[0].index('--same-prompt')+1]=='0' and c[1][c[1].index('--same-prompt')+1]=='1';assert all('--reps' in q for q in c)
 print('SELFTEST PASS: T05 two-arm 73728 command shape, no 8095')
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--self-test',action='store_true');a=p.parse_args(argv)
 if a.self_test:self_test();return 0
 if not a.run:print(json.dumps({'rid':RID,'candidate_commit':CANDIDATE,'cpu_only':True,'worktree':str(WT),'trace':str(TRACE),'arms':['P1','P2'],'kv_window':73728,'commands_per_arm':6,'raw_only_pending_review':True}));return 0
 print(json.dumps(run()));return 0
if __name__=='__main__':raise SystemExit(main())
