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

def ordinary_binding(binding):
 """Reject ACK-shaped evidence; accept only the v3 worker-bound contract."""
 if not isinstance(binding,dict) or binding.get('schema')!='ft_r049_t21_ordinary_binding/v8' or binding.get('verdict')!='worker_input_uid_token_bound':raise RuntimeError('ordinary T21 v4 binding differs')
 worker,api,tokens=binding.get('worker_input'),binding.get('api'),binding.get('token_sidecar')
 if not isinstance(worker,dict) or not isinstance(api,dict) or not isinstance(tokens,dict):raise RuntimeError('ordinary v4 binding fields differ')
 uid=api.get('uid');usage=api.get('usage')
 if type(uid) is not int or type(worker.get('input_tokens')) is not int or not isinstance(worker.get('input_ids_sha256'),str) or len(worker['input_ids_sha256'])!=64:raise RuntimeError('ordinary UserMsg binding differs')
 if not isinstance(usage,dict) or type(usage.get('prompt_tokens')) is not int or type(usage.get('completion_tokens')) is not int:raise RuntimeError('ordinary API usage differs')
 rows=tokens.get('events')
 if not isinstance(rows,list) or len(rows)!=usage['completion_tokens'] or any(row.get('uid')!=uid or row.get('completion_tokens_delta')!=1 for row in rows):raise RuntimeError('ordinary DetokenizeMsg binding differs')
 if worker['input_tokens']!=usage['prompt_tokens']:raise RuntimeError('ordinary input and API length differ')
 return {'uid':uid,'input_ids_sha256':worker['input_ids_sha256'],'input_tokens':worker['input_tokens'],'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens'],'finish_reason':api.get('finish_reason'),'token_ids_sha256':token_digest(rows),'token_events':rows,'evidence':binding}

def timing_from_sse(api):
 """SSE chunks establish TTFT/terminal only; they are never token evidence."""
 doc=json.loads(Path(api).read_text());first,last=doc.get('first_output_event'),doc.get('terminal_event')
 if not isinstance(first,dict) or not isinstance(last,dict) or type(first.get('monotonic_ns')) is not int or type(last.get('monotonic_ns')) is not int or last['monotonic_ns']<=first['monotonic_ns']:raise RuntimeError('ordinary SSE lacks monotonic first-output/terminal timing')
 usage=doc.get('usage')
 dispatch=doc.get('dispatch_monotonic_ns')
 if type(dispatch) is not int or dispatch>=first['monotonic_ns']:raise RuntimeError('ordinary SSE lacks dispatch-before-output timing')
 if not isinstance(usage,dict) or type(usage.get('completion_tokens')) is not int or usage['completion_tokens']<2:raise RuntimeError('ordinary SSE lacks decode usage token count')
 return {'dispatch_monotonic_ns':dispatch,'first_output_monotonic_ns':first['monotonic_ns'],'terminal_monotonic_ns':last['monotonic_ns'],'completion_tokens':usage['completion_tokens'],'ttft_s':(first['monotonic_ns']-dispatch)/1e9,'decode_tps':(usage['completion_tokens']-1)/((last['monotonic_ns']-first['monotonic_ns'])/1e9),'chunk_clock_origin':'network_sse_chunk_not_backend_token','basis':'ordinary_sse_first_nonempty_to_terminal_with_api_completion_count'}
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
 import os, urllib.parse
 if os.environ.get('FT_DEV_PAUSE_ENDPOINT')=='1' or urllib.parse.urlparse(base_url).port in (8095,8099):raise RuntimeError('T21 ordinary client refuses pause or shared ports')
 payload=json.loads(input_path.read_text())
 if payload.get('stream') is not True or (payload.get('stream_options') or {}).get('include_usage') is not True:raise ValueError('T21 ordinary request requires stream usage')
 body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
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
 value.update(payload_source={'path':str(input_path),'sha256':sha(input_path)},sse=str(raw),sse_sha256=sha(raw),events=str(events))
 with out.open('x',encoding='utf-8') as output:output.write(json.dumps(value,sort_keys=True)+'\n')
 return value

def full_response(api,original):
 doc=json.loads(Path(api).read_text());raw=Path(doc['sse'])
 if sha(raw)!=doc.get('sse_sha256'):raise RuntimeError('ordinary response raw SHA differs')
 events=(json.loads(line[5:].strip()) for line in raw.read_text(encoding='utf-8').splitlines() if line.startswith('data:') and line[5:].strip()!='[DONE]')
 parsed=original.consume_stream(events,0.0)
 return {key:parsed[key] for key in ('content_text','reasoning_text','tool_calls')}

def model_output(response):
 """Tool-call IDs are API-generated UUIDs; preserve them in the raw response."""
 return {'content_text':response['content_text'],'reasoning_text':response['reasoning_text'],
         'tool_calls':[{'type':call['type'],'function':call['function']} for call in response['tool_calls']]}

def _require_two_decode_sampling(payload):
 if (payload.get('max_tokens') != 512 or payload.get('ignore_eos') is not True or payload.get('stop') is not None):
  raise RuntimeError('ordinary two-decode requires max_tokens=512, ignore_eos=true, and no custom stop')

def run_pair(base_url,left_input,right_input,out,inputs,tokens,expected_ids,original,timeout=1800):
 """Launch exactly two ordinary SSE requests from an R058 barrier and bind mixed sidecar UIDs."""
 client=load(HERE/'r049_t21_ordinary_client_v8.py','r049_pair_client');concurrent=load(R058,'r049_concurrent')
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 specs=[concurrent.RequestSpec('left',0,{'input':str(left_input)}),concurrent.RequestSpec('right',0,{'input':str(right_input)})]
 def send(spec):
  api=out/f'{spec.name}.api.json';ordinary_stream_request(base_url,Path(spec.payload['input']),api,timeout);return {'api':str(api)}
 rows=concurrent.simultaneous(specs[0],specs[1],send,timeout=timeout)
 records=[]
 for row in rows:
  name=row['name'];api=Path(row['value']['api']);payload=Path(next(item.payload['input'] for item in specs if item.name==name))
  _require_two_decode_sampling(json.loads(payload.read_text(encoding='utf-8')))
  bound=client.bind(payload,api,None,None,inputs,tokens,out/f'{name}.binding.json');record=ordinary_binding(bound)
  want=hashlib.sha256(json.dumps(expected_ids[name],separators=(',',':')).encode()).hexdigest()
  if record['input_ids_sha256']!=want or record['prompt_tokens']!=len(expected_ids[name]):raise RuntimeError('ordinary two-decode differs from planned frontend IDs')
  if record['completion_tokens']!=512:raise RuntimeError('ordinary two-decode requires exactly 512 tokens per stream')
  if record['finish_reason']!='length':raise RuntimeError('ordinary two-decode must exhaust its length budget')
  record.update(name=name,response=full_response(api,original),**timing_from_sse(api));records.append(record)
 if len({record['uid'] for record in records})!=2:raise RuntimeError('ordinary two-decode streams reused one UID')
 first=max(record['first_output_monotonic_ns'] for record in records);last=min(record['terminal_monotonic_ns'] for record in records)
 if first>=last:raise RuntimeError('ordinary two-decode did not overlap during live output')
 value={'schema':'ft_r049_ordinary_two_decode/v8','pause_enabled':False,'ft_dev_ack':False,'simultaneous_barrier':True,'records':records,'live_output_overlap_s':(last-first)/1e9,'overlap_token_rate':None,'overlap_basis':'network_first_nonempty_and_terminal_only','adapter_sha256':sha(__file__),'ordinary_client_sha256':sha(HERE/'r049_t21_ordinary_client_v8.py'),'r058_concurrent_sha256':sha(R058)}
 with (out/'result.json').open('x',encoding='utf-8') as output:json.dump(value,output,ensure_ascii=False,sort_keys=True)
 return value
