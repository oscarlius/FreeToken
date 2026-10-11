from __future__ import annotations
import copy, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r067d_cpu_prep as p

R = lambda n,c: f"INFO Prefill batch, #new-seq: 1, #new-token: {n}, #cached-token: {c}, token usage: 0.1\n"
RAW = Path(__file__).resolve().parents[1] / 'raw_windows_v4'
def raw(name): return (RAW / name).read_text(encoding='utf-8')
SAMPLES = [
 ('retry2_seed', raw('retry2_seed.txt'),8193,0,8193),
 ('retry2_t1',raw('retry2_t1.txt'),1,8192,1),
 ('retry2_t64',raw('retry2_t64.txt'),64,8192,64),
 ('smoke481_short',raw('smoke481_short.txt'),512,0,512),
 ('smoke481_long',raw('smoke481_long.txt'),8257,0,8257),
 ('smoke184_short',raw('smoke184_short.txt'),512,0,512),
 ('smoke184_long',raw('smoke184_long.txt'),8257,0,8257),
]
def test_real_window_contracts_and_negative_mutations():
 for name,text,new,cache,budget in SAMPLES:
  assert p.validate_window(text,expected_new=new,expected_cache=cache,token_budget=budget)
  for bad in (text.replace('#new-seq: 1', '#new-seq: 2', 1), text.replace(f'#cached-token: {cache}', f'#cached-token: {cache+1}',1), text + R(1,cache)):
   try: p.validate_window(bad,expected_new=new,expected_cache=cache,token_budget=budget)
   except AssertionError: pass
   else: raise AssertionError(name + ' accepted negative mutation')
def test_services_are_new_round_unique_pairs_and_single_source_digest():
 ss=p.services(); assert len(ss)==10; assert len({x['port_pair']['api'] for x in ss}|{x['port_pair']['tcpstore'] for x in ss})==20
 for s in ss:
  assert p.actual_argv(s)==s['argv']; assert p.argv_sha256(s['argv'])==s['argv_sha256']; assert 'retry2' not in str(s['argv'])
 p.verify_service_bindings(ss)
 stale=copy.deepcopy(ss); stale[0]['argv_sha256']='0'*64
 try: p.verify_service_bindings(stale)
 except AssertionError: pass
 else: raise AssertionError('stale argv digest was accepted')
 reused=copy.deepcopy(ss); reused[1]['port_pair']['api']=reused[0]['port_pair']['api']; reused[1]['argv']=p.actual_argv(reused[1]); reused[1]['argv_sha256']=p.argv_sha256(reused[1])
 try: p.verify_service_bindings(reused)
 except AssertionError: pass
 else: raise AssertionError('reused API port was accepted')
 stale_port=copy.deepcopy(ss); i=stale_port[0]['argv'].index('--port')+1; stale_port[0]['argv'][i]='29999'; stale_port[0]['argv_sha256']=p.argv_sha256(stale_port[0]['argv'])
 try: p.verify_service_bindings(stale_port)
 except AssertionError: pass
 else: raise AssertionError('actual argv stale port was accepted')
def test_filedry_has_no_runtime_side_effects():
 with tempfile.TemporaryDirectory() as t:
  from prepare_runner_packet import main as prepare
  prepare(); out=Path(t)/'fd'; r=p.filedry(out); assert (r['services'],r['calls'],r['unique_ports'])==(10,14,20); assert not r['gpu_started'] and not r['service_started'] and not r['http_generation']; assert len(json.loads((out/'prepared_child_cpu_mode.json').read_text())['would_spawn'])==10
def test_real_184_windows_need_review_and_runner_uses_single_seam():
 import future_runner
 readiness=p.replay_readiness(RAW); assert readiness['replay_sources_complete'] and not readiness['gpu_admitted']; assert 'independent review' in readiness['blocker']
 source=Path(future_runner.__file__).read_text(); assert 'actual_argv(service)' in source and 'actual_environment(service)' in source and 'probe_or_capture' in source
 try: future_runner.require_replay_admission(RAW)
 except AssertionError: pass
 else: raise AssertionError('runner admitted without independent review')
def test_bind_probe_closes_partially_created_socket_and_capture_precedes_failure(tmp_path):
 class Sock:
  def __init__(self, fail=False): self.fail,self.closed=fail,False
  def bind(self, _):
   if self.fail: raise OSError('occupied')
  def close(self): self.closed=True
 made=[]
 def factory():
  x=Sock(True); made.append(x); return x
 ticks=iter((0,0,1,1,1));
 try: p.probe_or_capture((45671,45672),tmp_path/'diag',1,socket_factory=factory,monotonic=lambda:next(ticks),sleeper=lambda _:None)
 except RuntimeError: pass
 else: raise AssertionError('occupied pair accepted')
 assert all(x.closed for x in made); assert (tmp_path/'diag'/'ss-tanp.txt').exists() and (tmp_path/'diag'/'lsof.txt').exists()

def runtime_helpers():
 import ast, subprocess
 packet=json.loads((p.HERE/'R067D_PREPARED_RUNNER_PACKET.json').read_text())
 nodes=[n for n in ast.parse(packet['child_source']).body if isinstance(n,ast.FunctionDef) and n.name in packet['runtime_helpers']]
 ns={'Path':Path,'r067d_tools':p,'subprocess':subprocess}
 exec(compile(ast.Module(nodes,[]),'<actual-prepared-child-helpers>','exec'),ns)
 return ns

def test_real_child_judge_replays_seven_windows_and_rejects_usage_boundaries():
 import pytest
 judge=runtime_helpers()['judge_prepared_window']
 for name,text,new,cache,budget in SAMPLES:
  prompt=new+cache; service={'kind':'hot' if cache else 'cold'};item={'role':'query','max_tokens':64}
  usage={'prompt_tokens':prompt,'cached_tokens':cache,'completion_tokens':64}
  marker=b'POST /v1/completions HTTP/1.1" 200 OK' if name.startswith('smoke') else b'POST /internal/t17/exact-ids HTTP/1.1" 200 OK'
  def run(window, u): return judge(service,item,range(prompt),window.encode(),{'response':{'usage':u}},cache or prompt-1,new,post_marker=marker)
  assert run(text,usage)[1], name
  for key in usage:
   bad=dict(usage);bad[key]+=1
   assert not run(text,bad)[1], (name,key)
  assert not run(text.replace(marker.decode(),'POST /different'),usage)[1]
  for bad in (text.replace('#new-seq: 1','#new-seq: 2',1),text.replace(f'#cached-token: {cache}',f'#cached-token: {cache+1}',1),text+R(1,cache)):
   assert not run(bad,usage)[1]
  with pytest.raises(AssertionError,match='overbudget'):
   p.validate_runtime_window(text,expected_new=new,expected_cache=cache,token_budget=new-1)

def test_real_launch_helper_checks_digest_and_probes_before_fake_spawn():
 import pytest
 start=runtime_helpers()['start_prepared_service'];s=p.services()[0];events=[]
 def probe(*args): events.append('probe')
 def popen(*args,**kw): events.append('spawn');return object()
 start(s,p.actual_environment(s),None,probe=probe,popen=popen)
 assert events==['probe','spawn']
 bad=copy.deepcopy(s);bad['argv_sha256']='f'*64;events.clear()
 with pytest.raises(AssertionError): start(bad,p.actual_environment(bad),None,probe=probe,popen=popen)
 assert events==[]
 def failed_probe(*args): events.append('probe');raise RuntimeError('failed_harness')
 with pytest.raises(RuntimeError): start(s,p.actual_environment(s),None,probe=failed_probe,popen=popen)
 assert events==['probe']

def test_occupied_ephemeral_port_deadline_and_missing_lsof(tmp_path,monkeypatch):
 import socket,subprocess,pytest
 class Clock:
  value=0
  def now(self): return self.value
  def sleep(self,seconds): self.value+=seconds
 clock=Clock();events=[]
 def diagnostic(argv,**kwargs):
  events.append(argv[0])
  if argv[0]=='lsof': raise FileNotFoundError('lsof unavailable')
  return subprocess.CompletedProcess(argv,0,'occupied-port-evidence','')
 monkeypatch.setattr(p.subprocess,'run',diagnostic)
 with socket.socket() as occupied:
  occupied.bind(('0.0.0.0',0));port=occupied.getsockname()[1]
  with pytest.raises(RuntimeError,match='failed_harness'):
   p.probe_or_capture((port,0),tmp_path/'diag-real',120,monotonic=clock.now,sleeper=clock.sleep)
 assert clock.value==120 and events==['ss','lsof']
 assert (tmp_path/'diag-real'/'ss-tanp.txt').read_text()=='occupied-port-evidence'
 assert 'unavailable' in (tmp_path/'diag-real'/'lsof.txt').read_text()
