from pathlib import Path
import importlib.util
import json
import signal
import sys
import types
import pytest

HERE=Path(__file__).parents[1]

def load(name):
 spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def test_worker_sigterm_calls_actual_capture_shutdown_seam_once(monkeypatch,tmp_path):
 worker=load('t10_capture_startup_v3');calls=[]
 class Scheduler:
  def run_forever(self):
   calls.append('run');signal.raise_signal(signal.SIGTERM)
  def shutdown(self):calls.append('capture_finalize')
 def original(args,acks):
  instance=Scheduler()
  try:instance.run_forever()
  except KeyboardInterrupt:instance.shutdown()
  acks.append('returned')
 capture=types.ModuleType('equiv_suite.service_capture_startup')
 capture.install_from_env=lambda _:None;capture.run_scheduler=original
 suite=types.ModuleType('equiv_suite');suite.service_capture_startup=capture
 scheduler=types.ModuleType('freetoken.scheduler');scheduler.Scheduler=Scheduler
 monkeypatch.setitem(sys.modules,'equiv_suite',suite)
 monkeypatch.setitem(sys.modules,'equiv_suite.service_capture_startup',capture)
 monkeypatch.setitem(sys.modules,'freetoken.scheduler',scheduler)
 monkeypatch.syspath_prepend(str(HERE))
 for key in ('FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT'):monkeypatch.delenv(key,raising=False)
 output=tmp_path/'shutdown.json';monkeypatch.setenv('FT_T10_WORKER_SHUTDOWN',str(output))
 previous=signal.getsignal(signal.SIGTERM);acks=[]
 worker.worker_run_scheduler(object(),acks)
 assert calls==['run','capture_finalize'] and acks==['returned']
 assert signal.getsignal(signal.SIGTERM)==previous
 doc=json.loads(output.read_text())
 assert doc['status']=='complete' and doc['scheduler_run_started'] is True
 with pytest.raises(RuntimeError,match='exists'):worker.worker_run_scheduler(object(),[])

def test_second_sigterm_during_actual_capture_cleanup_is_absorbed(monkeypatch,tmp_path):
 worker=load('t10_capture_startup_v3');handlers={};calls=[]
 class Scheduler:
  def run_forever(self):handlers['handler'](signal.SIGTERM,None)
  def shutdown(self):calls.append('capture_finalize');handlers['handler'](signal.SIGTERM,None)
 def original(args,acks):
  instance=Scheduler()
  try:instance.run_forever()
  except KeyboardInterrupt:instance.shutdown()
  acks.append('returned')
 capture=types.ModuleType('equiv_suite.service_capture_startup');capture.install_from_env=lambda _:None;capture.run_scheduler=original
 suite=types.ModuleType('equiv_suite');suite.service_capture_startup=capture
 scheduler=types.ModuleType('freetoken.scheduler');scheduler.Scheduler=Scheduler
 legacy=types.ModuleType('t10_capture_startup');legacy.install_terminal_cap=lambda _:None
 monkeypatch.setitem(sys.modules,'equiv_suite',suite);monkeypatch.setitem(sys.modules,'equiv_suite.service_capture_startup',capture)
 monkeypatch.setitem(sys.modules,'freetoken.scheduler',scheduler);monkeypatch.setitem(sys.modules,'t10_capture_startup',legacy)
 monkeypatch.setattr(worker.signal,'getsignal',lambda _:'previous-handler');monkeypatch.setattr(worker.signal,'signal',lambda _,handler:handlers.__setitem__('handler',handler))
 output=tmp_path/'shutdown.json';monkeypatch.setenv('FT_T10_WORKER_SHUTDOWN',str(output));acks=[]
 worker.worker_run_scheduler(object(),acks)
 assert calls==['capture_finalize'] and acks==['returned'] and handlers['handler']=='previous-handler'
 assert json.loads(output.read_text())['status']=='complete'

@pytest.mark.parametrize('key',['FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT'])
def test_worker_rejects_trace_pause_before_outputs(monkeypatch,tmp_path,key):
 worker=load('t10_capture_startup_v3')
 suite=types.ModuleType('equiv_suite');suite.service_capture_startup=types.SimpleNamespace()
 scheduler=types.ModuleType('freetoken.scheduler');scheduler.Scheduler=object
 legacy=types.ModuleType('t10_capture_startup');legacy.install_terminal_cap=lambda _:None
 monkeypatch.setitem(sys.modules,'equiv_suite',suite);monkeypatch.setitem(sys.modules,'freetoken.scheduler',scheduler)
 monkeypatch.setitem(sys.modules,'t10_capture_startup',legacy);monkeypatch.setenv(key,'1')
 with pytest.raises(RuntimeError,match='disabled'):worker.worker_run_scheduler(None,None)
 assert not list(tmp_path.iterdir())

def test_real_frozen_replay_uses_same_messages_and_binds_twelve_api_uids(monkeypatch,tmp_path):
 replay=load('t10_ordinary_replay_v1');checkout=HERE.parent/'e2base1/scripts/_agent_trace_original.py'
 if not checkout.is_file(): checkout=Path('/data2/FreeToken/wt/e2base1-ordinary-rewind/scripts/_agent_trace_original.py')
 original_path=tmp_path/'_agent_trace_original.py'
 original_path.write_bytes(checkout.read_bytes().replace(b'\r\n',b'\n'))
 original=replay.load(original_path,'t10_business_test');rows=[]
 for index in range(12):
  messages=[{'role':'user','content':f'fixed request {index}'}]
  rows.append({'messages':messages,'record':{'messages_sha':original.messages_digest(messages)}})
 trace=tmp_path/'trace.json';trace.write_text(json.dumps({'rounds':rows}))
 observed=[]
 def send(base,payload_path,api_path,timeout):
  payload=json.loads(payload_path.read_text());observed.append(payload)
  uid=len(observed)-1
  raw=api_path.with_suffix('.sse')
  event={'id':f'chatcmpl-{uid}','choices':[{'delta':{'content':'fixed answer'},'finish_reason':'stop'}],
         'usage':{'prompt_tokens':23,'completion_tokens':2}}
  raw.write_text('data: '+json.dumps(event)+'\n\ndata: [DONE]\n')
  api={'uid':uid,'sse':str(raw),'sse_sha256':replay.hashlib.sha256(raw.read_bytes()).hexdigest()}
  api_path.write_text(json.dumps(api));return api
 adapter=types.SimpleNamespace(ordinary_stream_request=send,sha=lambda p:replay.hashlib.sha256(Path(p).read_bytes()).hexdigest())
 real_load=replay.load
 monkeypatch.setattr(replay,'load',lambda p,n:adapter if Path(p).name=='r049_t21_ordinary_adapter_v2.py' else real_load(p,n))
 output=tmp_path/'out.json'
 replay.replay(original_path,trace,output,'http://127.0.0.1:12345/v1','model','cold')
 doc=json.loads(output.read_text())
 assert [row['uid'] for row in doc['rounds']]==list(range(12))
 assert [row['messages'] for row in rows]==[payload['messages'] for payload in observed]
 assert all(payload['max_tokens']==200 and payload['temperature']==0 for payload in observed)
 assert all(row['transport']=='ordinary_sse_no_ft_dev_ack' for row in doc['rounds'])
