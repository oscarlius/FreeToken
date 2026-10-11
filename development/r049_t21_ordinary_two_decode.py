"""R049 ordinary-SSE two-stream adapter; no ft_dev or pause endpoint."""
from __future__ import annotations
import hashlib, importlib.util, json, socket, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
ORDINARY=HERE/'r046c_t06_ordinary_client_v2.py'
R058=HERE/'r058_concurrent_request.py'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); assert spec.loader;sys.modules[name]=module;spec.loader.exec_module(module);return module
def token_digest(rows):
 values=[]
 for row in rows:
  value=row.get('next_token')
  if type(value) is not int:raise RuntimeError('ordinary sidecar token id differs')
  values.append(value)
 return hashlib.sha256(b''.join(value.to_bytes(4,'little',signed=True) for value in values)).hexdigest()
def dynamic_private_port():
 with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as guard:
  guard.bind(('127.0.0.1',0));port=guard.getsockname()[1]
 if port==8095:raise RuntimeError('ordinary fixture must not select 8095')
 return port
def _first_real(event):
 for choice in event.get('choices') or []:
  delta=choice.get('delta') or {}
  if any(isinstance(delta.get(key),str) and delta[key] for key in ('content','reasoning_content','reasoning')):return True
  for call in delta.get('tool_calls') or []:
   arguments=((call.get('function') or {}).get('arguments')) if isinstance(call,dict) else None
   if isinstance(arguments,str) and arguments:return True
 return False
def ordinary_stream_request(base_url,input_path,out,timeout=1800):
 """Preserve every normal SSE line and its clocks; chunks are not token clocks."""
 client=load(ORDINARY,'r049_ordinary_client_stream');input_path=Path(input_path);out=Path(out)
 payload=json.loads(input_path.read_text());body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
 raw=out.with_suffix('.sse');events=out.with_suffix('.events.jsonl');out.parent.mkdir(parents=True,exist_ok=True)
 uid=usage=finish=None;done=False;first=None;terminal=None;dispatch=time.monotonic_ns();wall=time.time_ns()
 try:
  with urllib.request.urlopen(urllib.request.Request(base_url.rstrip('/')+'/chat/completions',data=body,headers={'Content-Type':'application/json','Accept':'text/event-stream'}),timeout=timeout) as response:
   with raw.open('xb') as rf,events.open('x',encoding='utf-8') as ef:
    for line in response:
     mono,clock=time.monotonic_ns(),time.time_ns();rf.write(line);text=line.decode('utf-8',errors='strict').strip()
     if not text.startswith('data:'):continue
     part=text[5:].strip()
     if part=='[DONE]':done=True;continue
     event=json.loads(part)
     if 'ft_dev' in event:raise RuntimeError('ordinary stream rejects ft_dev ACK')
     current=client.uid_from_id(event.get('id'))
     if uid is None:uid=current
     elif uid!=current:raise RuntimeError('ordinary stream UID changed')
     ef.write(json.dumps({'monotonic_ns':mono,'time_ns':clock,'event':event},sort_keys=True)+'\n');ef.flush()
     if _first_real(event) and first is None:first={'monotonic_ns':mono,'time_ns':clock}
     if event.get('usage') is not None:
      if usage is not None:raise RuntimeError('ordinary stream has multiple usage records')
      usage=event['usage']
     for choice in event.get('choices') or []:
      if choice.get('finish_reason') is not None:finish=choice['finish_reason'];terminal={'monotonic_ns':mono,'time_ns':clock}
 except urllib.error.HTTPError as error:
  raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(error.read())
  raise RuntimeError('ordinary stream failed; partial raw preserved') from error
 except BaseException as error:
  raise RuntimeError('ordinary stream failed; partial raw preserved') from error
 if uid is None or not isinstance(usage,dict) or finish not in {'stop','length','tool_calls'} or not done:raise RuntimeError('ordinary stream lacks id, usage, finish, or DONE')
 if not isinstance(usage.get('prompt_tokens'),int) or not isinstance(usage.get('completion_tokens'),int) or usage['completion_tokens']<=0:raise RuntimeError('ordinary stream usage differs')
 value={'schema':'ft_r049_ordinary_sse_stream/v1','pause_enabled':False,'ft_dev_ack':False,'input_sha256':sha(input_path),'uid':uid,'usage':usage,'finish_reason':finish,'raw_sse_sha256':sha(raw),'events_sha256':sha(events),'dispatch_monotonic_ns':dispatch,'dispatch_time_ns':wall,'first_output_event':first,'terminal_event':terminal,'chunk_clock_origin':'network_sse_chunk_not_backend_token'}
 out.write_text(json.dumps(value,sort_keys=True)+'\n');return value
def _binding(client,api,input_path,sidecar):
 doc=json.loads(Path(api).read_text());uid=doc.get('uid');usage=doc.get('usage') or {}
 if type(uid) is not int or type(usage.get('completion_tokens')) is not int:raise RuntimeError('ordinary two-decode API UID/usage differs')
 rows=client.token_sidecar(sidecar,uid,usage['completion_tokens'],doc.get('finish_reason'))
 if doc.get('input_sha256')!=sha(input_path):raise RuntimeError('ordinary two-decode input SHA differs')
 raw=Path(str(api).replace('.api.json','.api.sse'));events=Path(str(api).replace('.api.json','.api.events.jsonl'))
 if not raw.is_file() or not events.is_file() or doc.get('raw_sse_sha256')!=sha(raw) or doc.get('events_sha256')!=sha(events):raise RuntimeError('ordinary two-decode raw/event binding differs')
 ids=json.loads(Path(input_path).read_text()).get('input_ids_sha256')
 if not isinstance(ids,str) or len(ids)!=64:raise RuntimeError('ordinary two-decode lacks actual input token SHA')
 return {'uid':uid,'input_sha256':sha(input_path),'input_ids_sha256':ids,'raw_sse_sha256':sha(raw),'events_sha256':sha(events),'completion_tokens':usage['completion_tokens'],'token_ids_sha256':token_digest(rows),'sidecar_sha256':sha(sidecar),'backend_token_time_origin':'model_backend','token_events':rows}
def run_pair(base_url,left_input,right_input,out,sidecar,timeout=1800):
 """Launch exactly two ordinary SSE requests from an R058 barrier and bind mixed sidecar UIDs."""
 client=load(ORDINARY,'r049_ordinary_client');concurrent=load(R058,'r049_concurrent')
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 specs=[concurrent.RequestSpec('left',0,{'input':str(left_input)}),concurrent.RequestSpec('right',0,{'input':str(right_input)})]
 def send(spec):
  api=out/f'{spec.name}.api.json';ordinary_stream_request(base_url,Path(spec.payload['input']),api,timeout);return {'api':str(api)}
 rows=concurrent.simultaneous(specs[0],specs[1],send,timeout=timeout)
 bindings={row['name']:_binding(client,Path(row['value']['api']),Path(next(item.payload['input'] for item in specs if item.name==row['name'])),Path(sidecar)) for row in rows}
 if bindings['left']['uid']==bindings['right']['uid']:raise RuntimeError('ordinary two-decode streams reused one UID')
 if any(not isinstance(value['input_ids_sha256'],str) or len(value['input_ids_sha256'])!=64 for value in bindings.values()):raise RuntimeError('ordinary two-decode lacks actual input token SHA')
 value={'schema':'ft_r049_ordinary_two_decode/v1','pause_enabled':False,'ft_dev_ack':False,'simultaneous_barrier':True,'bindings':bindings,'adapter_sha256':sha(__file__),'ordinary_client_sha256':sha(ORDINARY),'r058_concurrent_sha256':sha(R058)}
 (out/'result.json').write_text(json.dumps(value,sort_keys=True)+'\n');return value
