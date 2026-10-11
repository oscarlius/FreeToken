import hashlib, importlib.util, json
from pathlib import Path
import httpx, pytest

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('sdk',ROOT/'r061d_sdk_transport_v1.py'); sdk=importlib.util.module_from_spec(spec); spec.loader.exec_module(sdk)
PAYLOAD={'model':'fixture','messages':[{'role':'user','content':'x'}],'stream':True,'stream_options':{'include_usage':True},'max_tokens':128,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
def sse(uid=7):
 rows=[{'id':f'chatcmpl-{uid}','choices':[{'delta':{'content':'ok'},'finish_reason':None}]},{'id':f'chatcmpl-{uid}','choices':[{'delta':{},'finish_reason':'length'}],'usage':{'prompt_tokens':1,'completion_tokens':128,'total_tokens':129}}]
 return b''.join(b'data: '+json.dumps(x).encode()+b'\n\n' for x in rows)+b'data: [DONE]\n\n'
def test_sdk_wire_equals_frozen_payload_and_preserves_raw(tmp_path,monkeypatch):
 source=tmp_path/'queued.json';source.write_text(json.dumps(PAYLOAD)); seen=[]
 def reply(request):
  seen.append(json.loads(request.content));return httpx.Response(200,headers={'content-type':'text/event-stream'},content=sse())
 monkeypatch.setattr(sdk,'HTTP_CLIENT',lambda **kw:httpx.Client(transport=httpx.MockTransport(reply),**kw))
 value=sdk.ordinary_request('http://fixture/v1',source,tmp_path/'queued.api.json')
 assert seen==[PAYLOAD] and value['uid']==7 and value['usage']['completion_tokens']==128
 assert (tmp_path/'queued.api.sse').read_bytes()==sse() and value['sse_sha256']==hashlib.sha256(sse()).hexdigest()
def test_sdk_503_preserves_raw_error(tmp_path,monkeypatch):
 source=tmp_path/'queued.json';source.write_text(json.dumps(PAYLOAD))
 monkeypatch.setattr(sdk,'HTTP_CLIENT',lambda **kw:httpx.Client(transport=httpx.MockTransport(lambda _r:httpx.Response(503,content=b'offline')),**kw))
 with pytest.raises(RuntimeError,match='HTTP error'):sdk.ordinary_request('http://fixture/v1',source,tmp_path/'queued.api.json')
 assert (tmp_path/'queued.api.sse').read_bytes()==b'offline'
