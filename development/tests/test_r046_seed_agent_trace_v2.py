"""Actual pinned client loops and candidate frontend methods, with synthetic CPU IDs/SSE."""
import ast, hashlib, importlib.util, json, sys
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('seed_window_v2',ROOT/'r046_seed_agent_trace_v2.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.fixture
def frontend():
 source=ROOT/'e2d15/python/freetoken/tokenizer/tokenize.py'
 tree=ast.parse(source.read_text(encoding='utf-8'));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TokenizeManager')
 namespace={'torch':SimpleNamespace(int32='int32'),'UserMsg':lambda **kw:SimpleNamespace(**kw)}
 unit=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),cls],type_ignores=[])
 exec(compile(ast.fix_missing_locations(unit),str(source),'exec'),namespace)
 class IDs:
  def __init__(self,count):self.count=count
  def view(self,*_):return self
  def to(self,*_):return self
  def tolist(self):return list(range(self.count))
 class Tokenizer:
  calls=[]
  def apply_chat_template(self,messages,**kwargs):
   self.calls.append((messages,kwargs));assert kwargs['tokenize'] is False and kwargs['add_generation_prompt'] is True
   assert len(kwargs['tools'])==3
   return json.dumps(messages,ensure_ascii=False)
  def encode(self,text,**kwargs):
   assert kwargs=={'return_tensors':'pt','add_special_tokens':False}
   size={1:87100,3:96256}.get(len(json.loads(text)),96257)
   return IDs(size)
 instance=namespace['TokenizeManager'].__new__(namespace['TokenizeManager']);instance.tokenizer=Tokenizer();instance._dsv4_encoder=None
 return instance

@pytest.fixture
def client(tmp_path):
 directory=tmp_path/'candidate/scripts';directory.mkdir(parents=True)
 for name in ('agent_trace.py','_agent_trace_original.py'):
  (directory/name).write_bytes((ROOT/'e2d15/scripts'/name).read_bytes().replace(b'\r\n',b'\n'))
 return directory/'agent_trace.py'

def transport(module,frontend):
 calls=[]
 def events(url,payload,timeout):
  calls.append(payload);count={1:87100,3:96256}.get(len(payload['messages']),96257)
  uid=len(calls)
  yield {'ft_dev':{'schema':'ft_dev_stream/v1','uid':uid,'request_seq':1,'completion_tokens_delta':1,'completion_tokens_cumulative':1},'choices':[{'delta':{'content':'ok'},'finish_reason':None}]}
  yield {'usage':{'prompt_tokens':count,'completion_tokens':1},'choices':[{'delta':{},'finish_reason':'stop'}]}
 module._ns['post_events']=events
 return calls

def generate(monkeypatch,tmp_path,client,frontend):
 module=m.load(client);calls=transport(module,frontend)
 seed=tmp_path/'seed_real.txt';raw='原种子\r\n完全保留'.encode('utf-8');seed.write_bytes(raw);seed_sha=hashlib.sha256(raw).hexdigest()
 out=tmp_path/'trace.json';monkeypatch.setattr(m,'load',lambda _:module);monkeypatch.setattr(m,'load_frontend',lambda *_:(frontend,{'renderer_sha256':'a'*64}))
 m.main(['--client',str(client),'--seed-file',str(seed),'--seed-sha256',seed_sha,'--worktree',str(tmp_path),'--tokenizer-path',str(tmp_path),'--out',str(out),'--rounds','12','--max-tokens','2048','--base-url','http://denied.invalid/v1','--model','fixture'])
 return out,calls,raw,seed_sha

def test_actual_client_preserves_seed_and_stops_before_third_request(monkeypatch,tmp_path,client,frontend):
 out,calls,raw,seed_sha=generate(monkeypatch,tmp_path,client,frontend)
 doc=json.loads(out.read_text());window=doc['meta']['window_completion'];binding=json.loads(out.with_suffix('.seed_binding.json').read_text())
 assert len(calls)==len(doc['rounds'])==window['completed_k']==2
 assert window['window_hit']['request_k']==3 and window['window_hit']['actual_prompt_tokens']==96257 and window['window_hit_count']==1 and window['not_failure']
 assert window['completed_input_bindings'][1]['actual_prompt_tokens']==96256
 assert calls[0]['messages'][0]['content'].startswith(raw.decode('utf-8')+'\n\n')
 assert binding['seed_raw_sha256']==seed_sha and binding['window']==98304 and binding['max_tokens']==2048
 assert all(row['record']['actual_input_binding']['actual_input_ids_sha256'] for row in doc['rounds'])
 assert not any(payload['messages']==window['window_hit']['payload']['messages'] for payload in calls)

def test_actual_replay_matches_completed_rounds_and_unsent_window_hit(monkeypatch,tmp_path,client,frontend):
 trace,_,_,seed_sha=generate(monkeypatch,tmp_path,client,frontend);expected=json.loads(trace.read_text())['meta']['window_completion']
 # Reload the real ACK companion without the generate test's loader patch.
 spec=importlib.util.spec_from_file_location('window_replay_candidate',client);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 calls=transport(module,frontend);guard=m.WindowGuard(frontend,seed_sha,{},expected=expected);m.install(module,guard)
 out=tmp_path/'replay.json';monkeypatch.setattr(sys,'argv',[str(client),'replay','--trace',str(trace),'--out',str(out),'--base-url','http://denied.invalid/v1','--model','fixture'])
 module.main();result=json.loads(out.read_text())['meta']['window_completion']
 assert len(calls)==result['completed_k']==2 and result['window_hit']['request_k']==3
 assert result['window_hit']['input_binding']['actual_input_ids_sha256']==expected['window_hit']['input_binding']['actual_input_ids_sha256']
 assert result['completed_input_bindings'][0]['max_tokens']==module._ns['REPLAY_MAX_TOKENS']==32

def test_seed_sha_mismatch_fails_before_loading_candidate(monkeypatch,tmp_path):
 seed=tmp_path/'seed.txt';seed.write_bytes(b'original')
 monkeypatch.setattr(m,'load',lambda *_:pytest.fail('changed seed reached candidate'))
 with pytest.raises(RuntimeError,match='original seed raw SHA differs'):
  m.main(['--client','unused','--seed-file',str(seed),'--seed-sha256','0'*64,'--worktree','unused','--tokenizer-path','unused','--out','unused','--rounds','12','--max-tokens','2048'])

def test_actual_r049_replay_uses_same_window_and_keeps_sse_timing(monkeypatch,tmp_path,client,frontend):
 trace,_,_,_=generate(monkeypatch,tmp_path,client,frontend)
 spec=importlib.util.spec_from_file_location('r049_replay_contract',ROOT/'r049_t21_prepare.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
 monkeypatch.setattr(runner,'AGENT_TRACE',client);monkeypatch.setattr(runner,'_load_window_client',lambda:m)
 install=runner._install_timed_agent_capture;calls=[]
 def capture(module):
  sent=transport(module,frontend);calls.append(sent);return install(module)
 monkeypatch.setattr(runner,'_install_timed_agent_capture',capture)
 out=tmp_path/'t21.json';proof=runner._timed_agent_replay(12345,trace,out,{'policy':'profile'},tmp_path/'unused.strp')
 doc=json.loads(out.read_text());result=doc['meta']['window_completion']
 assert len(calls[0])==result['completed_k']==2 and result['window_hit']['request_k']==3
 assert proof['sse_timing_bound'] and doc['rounds'][0]['token_events'][0]['uid']==1
 assert doc['rounds'][0]['actual_input_binding']['actual_prompt_tokens']==87100

def test_replay_rejects_changed_producer_window_ids(monkeypatch,tmp_path,client,frontend):
 trace,_,_,seed_sha=generate(monkeypatch,tmp_path,client,frontend);expected=json.loads(trace.read_text())['meta']['window_completion']
 expected['window_hit']['input_binding']['actual_input_ids_sha256']='0'*64
 guard=m.WindowGuard(frontend,seed_sha,{},expected=expected)
 for index,row in enumerate(json.loads(trace.read_text())['rounds']):
  payload={'messages':row['messages'],'tools':m.load(client)._ns['tool_specs'](),'max_tokens':32}
  guard.check(payload,index)
 rows=[{'prompt_tokens':proof['actual_prompt_tokens']} for proof in guard.checked]
 with pytest.raises(RuntimeError,match='window hit input IDs differ'):guard.finish({'rounds':rows})
