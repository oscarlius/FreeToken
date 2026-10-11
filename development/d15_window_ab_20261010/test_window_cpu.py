import importlib.util,json,sys,time
from pathlib import Path
import pytest
HERE=Path(__file__).parent
def mod(n):
 s=importlib.util.spec_from_file_location(n,HERE/f'{n}.py');m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
startup=mod('window_startup');runner=mod('window_runner')
class Release:
 def environment(self,*x):return {'VIRTUAL_ENV':'/venv'}
 def serve_argv(self,*x):return ['taskset','-c','1,3-47','ft','serve','--host','x','--port','9','--max-running-requests','2','--kv-reserve-tokens','1','--max-seq-len-override','1']
def test_projection_clean_parent():
 a,e=startup.release_projection(Release(),'W128K','observer.py');assert a[a.index('--port')+1]=='32102' and e['MASTER_PORT']=='32202'
 assert e['PATH']=='/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

@pytest.mark.skipif(sys.platform!='linux',reason='actual Linux launcher resolution')
def test_isolated_environment_resolves_taskset():
 import subprocess
 _,env=startup.release_projection(Release(),'W98K','observer.py')
 result=subprocess.run(['taskset','--version'],env=env,capture_output=True,text=True,check=True)
 assert 'taskset' in result.stdout
class D:pass
def test_two_service_budget_and_a_mismatch_suppresses_followups(tmp_path,monkeypatch):
 d=D();d.root=tmp_path;d.now=lambda:0;d.adapter=d.client=d.producer=object();d.lifecycle=object();d.system_uptime=lambda:1;d.gpu_idle=lambda:True;starts=[];calls=[]
 def start(rec,run,*args):run.mkdir();starts.append(rec['arm']);return object(),object(),run/'o',0
 def inv(*args,**kwargs):
  calls.append(args[4].name);arm='W98K' if 'W98K' in str(args[4]) else 'W128K';token='x' if arm=='W98K' else 'y';return ({'native_token_sha256':token,'cached_tokens':0}, {})
 d.start=start;d.frontend=lambda x:[0]*100223;d.sampler=None;d.slot_check=lambda _,expected:{'actual_slots':expected};d.seed_payloads=[tmp_path/f'p{i}' for i in range(8)]
 for p in d.seed_payloads:p.write_text('{}')
 d.window_payload=lambda p:p;d.next_b_payload=lambda *x:x[1];d.cold_payload=lambda p:p
 monkeypatch.setattr(runner,'invoke',inv);monkeypatch.setattr(runner,'cleanup',lambda *x:True)
 packet={'input_sha256':[runner.sha(p) for p in d.seed_payloads],'arms':[{'arm':'W98K','port':1,'window':98304,'expected_auto_slots':2700},{'arm':'W128K','port':2,'window':131072,'expected_auto_slots':2401}]}
 with pytest.raises(RuntimeError,match='suppressed'):runner.run_two(packet,{},d)
 assert starts==['W98K','W128K'] and len(calls)==9
def test_observer_mp_install():
 text=(HERE/'window_observer.py').read_text();assert 'install(Path(target))' in text and 'Event(enable_timing=True)' in text and 'elapsed_time(end)' in text
def test_passing_path_uses_two_services_and_runs_b_and_cold(tmp_path,monkeypatch):
 d=D();d.root=tmp_path;d.now=lambda:0;d.adapter=d.client=d.producer=object();d.lifecycle=object();d.system_uptime=lambda:1;d.gpu_idle=lambda:True;starts=[];calls=[]
 def start(rec,run,*args):run.mkdir();starts.append(rec['arm']);return object(),object(),run/'o',0
 def inv(*args,**kwargs):calls.append(args[4].name);return ({'native_token_sha256':'same','cached_tokens':0,'completion_tokens':2,'decode_elapsed_s':1,'min_free_gpu_mib':1}, {})
 d.start=start;d.frontend=lambda x:[0]*100223;d.sampler=None;d.slot_check=lambda _,expected:{'actual_slots':expected};d.seed_payloads=[tmp_path/f'p{i}' for i in range(8)]
 for p in d.seed_payloads:p.write_text('{}')
 d.window_payload=lambda p:(p.write_text(json.dumps({'max_tokens':2048})),p)[1];d.next_b_payload=lambda old,p,*x:(p.write_text(json.dumps({'max_tokens':2048})),p)[1];d.cold_payload=lambda p:p
 monkeypatch.setattr(runner,'invoke',inv);monkeypatch.setattr(runner,'cleanup',lambda *x:True)
 packet={'input_sha256':[runner.sha(p) for p in d.seed_payloads],'arms':[{'arm':'W98K','port':1,'window':98304,'expected_auto_slots':2700},{'arm':'W128K','port':2,'window':131072,'expected_auto_slots':2401}]}
 out=runner.run_two(packet,{},d)
 assert starts==['W98K','W128K'] and len(calls)==21 and len(out['W128K']['B'])==4
def test_metric_uses_native_times():
 r=runner.metric({'token_events':[{},{}]},{'ttft_s':2,'terminal_monotonic_ns':1000000001,'first_output_monotonic_ns':1,'completion_tokens':2},0,0,lambda:3);assert r['decode_tps_network']==1 and r['process_uptime_s']>=0

def test_actual_v9_binding_and_invoke(tmp_path,monkeypatch):
 fixtures=runner.load(HERE/'test_binding_fixtures.py','window_actual_fixtures')
 payload,api,inputs,tokens,ids,raw=fixtures.request_receipts(tmp_path)
 body=json.loads(payload.read_text());body['max_tokens']=2;payload.write_text(json.dumps(body))
 doc=json.loads(api.read_text());doc['payload_source']['sha256']=runner.sha(payload);api.write_text(json.dumps(doc))
 adapter=runner.load(HERE/'source_bundle/r049_t21_ordinary_adapter_v9.py','window_actual_adapter')
 client=runner.load(HERE/'source_bundle/r049_t21_ordinary_client_v9.py','window_actual_client')
 monkeypatch.setattr(adapter,'ordinary_stream_request',lambda *a,**k:doc)
 monkeypatch.setattr(runner.subprocess,'check_output',lambda *a,**k:'R\nS\n' if a[0][0]=='ps' else 'CPU uptime fixture')
 (tmp_path/'prefill_events.jsonl').write_text(json.dumps({'uids':[7],'elapsed_ms':10})+'\n')
 row,binding=runner.invoke(adapter,client,'http://127.0.0.1:32101/v1',payload,api,tmp_path,runner.time.monotonic()+30,0,lambda:1,frontend=lambda p:[10,11])
 assert binding['input_tokens']==2 and row['completion_tokens']==2 and row['prefill_compute_ms']==10
 assert row['environment']['r_threads']==1 and row['native_token_sha256']==adapter.token_digest(binding['token_events'])

def test_slots_parse_actual_production_log(tmp_path):
 path=tmp_path/'serve.log';path.write_text('--moe-cache-auto resolved moe_cache_size=2401 num_pages=2048 (prefill_overlap=True)\n')
 assert runner.slot_check(path,2401)['actual_slots']==2401

def test_cleanup_stop_exception_is_unsafe_and_checks_master_port(tmp_path):
 class Life:
  def stop_owned_process(self,*a,**k):raise RuntimeError('stop failed')
 assert runner.cleanup(object(),open(tmp_path/'log','w'),32101,32201,Life(),lambda:True) is False

def test_cleanup_rejects_busy_master_port(tmp_path):
 class Life:
  def stop_owned_process(self,*a,**k):pass
  def owned_group_alive(self,*a):return False
 hold=runner.socket.socket();hold.bind(('127.0.0.1',0));master=hold.getsockname()[1]
 try:assert runner.cleanup(object(),open(tmp_path/'log','w'),master+1,master,Life(),lambda:True) is False
 finally:hold.close()

def test_start_stop_throw_is_unsafe_cleanup(tmp_path,monkeypatch):
 class Proc: pid=7
 class Life:
  def process_identity(self,pid):return None
  def stop_owned_process(self,*a,**k):raise RuntimeError('stop throws')
  def owned_group_alive(self,*a):return True
 monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:Proc())
 record={'environment':{},'argv':['x'],'port':32101}
 with pytest.raises(runner.UnsafeCleanupError):runner.start(record,tmp_path/'run',Life(),runner.time.monotonic()+2)

def test_stream_deadline_calls_owned_abort(tmp_path,monkeypatch):
 payload=tmp_path/'payload.json';payload.write_text(json.dumps({'max_tokens':1,'stream':True,'stream_options':{'include_usage':True}}));called=[];stream_started=[]
 class Adapter:
  def ordinary_stream_request(self,*a,**k):stream_started.append(True);time.sleep(1.1)
 monkeypatch.setattr(runner.subprocess,'check_output',lambda *a,**k:'')
 with pytest.raises(TimeoutError):runner.invoke(Adapter(),None,'http://127.0.0.1:1',payload,tmp_path/'api.json',tmp_path,time.monotonic()+1,0,lambda:1,frontend=lambda _:[],deadline_abort=lambda:called.append(True))
 assert called==[True] and stream_started==[True]
