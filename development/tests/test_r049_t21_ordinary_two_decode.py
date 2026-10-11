import importlib.util, io, json, urllib.error
from pathlib import Path
import pytest

SOURCE=Path(__file__).parents[1]/'r049_t21_ordinary_two_decode.py'
def load():
 spec=importlib.util.spec_from_file_location('r049_two',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def payload(path):path.write_text(json.dumps({'stream':True,'stream_options':{'include_usage':True}}))
class Response:
 def __init__(self,lines):self.lines=lines
 def __enter__(self):return self
 def __exit__(self,*_):return False
 def __iter__(self):return iter(self.lines)
def test_stream_records_real_events_and_ignores_empty_delta(monkeypatch,tmp_path):
 m=load();inp=tmp_path/'in.json';payload(inp)
 lines=[b'data: {"id":"chatcmpl-7","choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}\n',b'data: {"id":"chatcmpl-7","choices":[{"delta":{"content":""},"finish_reason":null}]}\n',b'data: {"id":"chatcmpl-7","choices":[{"delta":{"content":"x"},"finish_reason":"stop"}]}\n',b'data: {"id":"chatcmpl-7","choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n',b'data: [DONE]\n']
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_a,**_k:Response(lines));row=m.ordinary_stream_request('http://unit/v1',inp,tmp_path/'api.json')
 assert row['uid']==7 and row['first_output_event'] and row['terminal_event'] and (tmp_path/'api.events.jsonl').read_text().count('chatcmpl-7')==4
def test_stream_rejects_missing_usage_and_preserves_partial_raw(monkeypatch,tmp_path):
 m=load();inp=tmp_path/'in.json';payload(inp);monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_a,**_k:Response([b'data: {"id":"chatcmpl-7","choices":[]}\n',b'data: [DONE]\n']))
 with pytest.raises(RuntimeError,match='lacks id, usage'):m.ordinary_stream_request('http://unit',inp,tmp_path/'api.json')
 assert (tmp_path/'api.sse').exists()
def test_stream_preserves_partial_http_error(monkeypatch,tmp_path):
 m=load();inp=tmp_path/'in.json';payload(inp);error=urllib.error.HTTPError('x',500,'x',{},io.BytesIO(b'partial'))
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_a,**_k:(_ for _ in ()).throw(error))
 with pytest.raises(RuntimeError,match='partial raw preserved'):m.ordinary_stream_request('http://unit',inp,tmp_path/'api.json')
 assert (tmp_path/'api.sse').read_bytes()==b'partial'
def test_dynamic_port_never_8095():assert load().dynamic_private_port()!=8095

def test_run_pair_binds_barrier_streams_to_mixed_backend_sidecar(monkeypatch,tmp_path):
 m=load();left,right=tmp_path/'left.json',tmp_path/'right.json'
 for path,value in ((left,'a'*64),(right,'b'*64)):path.write_text(json.dumps({'stream':True,'stream_options':{'include_usage':True},'input_ids_sha256':value}))
 sidecar=tmp_path/'tokens.jsonl';sidecar.write_text('\n'.join(json.dumps({'schema':'ft_t06_ordinary_token/v2','uid':uid,'request_seq':1,'completion_tokens_delta':1,'completion_tokens_cumulative':1,'next_token':uid,'finished':True,'finish_reason':'stop','service_birth':{'pid':1},'worker_birth':{'pid':2}}) for uid in (11,12))+'\n')
 def fake(base,input_path,out,timeout):
  uid=11 if Path(input_path).name=='left.json' else 12;raw=Path(out).with_suffix('.sse');events=Path(out).with_suffix('.events.jsonl');raw.write_bytes(b'raw');events.write_text('{}\n')
  Path(out).write_text(json.dumps({'uid':uid,'usage':{'completion_tokens':1},'finish_reason':'stop','input_sha256':m.sha(input_path),'raw_sse_sha256':m.sha(raw),'events_sha256':m.sha(events)}));return {}
 monkeypatch.setattr(m,'ordinary_stream_request',fake)
 value=m.run_pair('http://unit',left,right,tmp_path/'out',sidecar,timeout=2)
 assert value['bindings']['left']['uid']!=value['bindings']['right']['uid']
 assert {x['input_ids_sha256'] for x in value['bindings'].values()}=={'a'*64,'b'*64}
 assert all(x['backend_token_time_origin']=='model_backend' for x in value['bindings'].values())
