import hashlib, importlib.util, json, sys, time
from pathlib import Path

DEV=Path(__file__).parents[1]
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[name]=m;s.loader.exec_module(m);return m

def test_actual_ordinary_sidecar_binding_reads_physical_receipts(tmp_path):
 m=load(DEV/'r061_oom_fault_prepare_v1.py','r061sidecar');client=load(DEV/'r046c_t06_ordinary_client_v3.py','ordinary')
 uid=2;birth={'pid':11,'start_ticks':22,'execution_id':'11:22','pgid':11,'session':11};ids=tmp_path/'absolute-ids.json';ids.write_bytes(b'[10,11]');digest=hashlib.sha256(ids.read_bytes()).hexdigest()
 inp=tmp_path/'payload.json';inp.write_text(json.dumps({'stream':True,'stream_options':{'include_usage':True}}));side=tmp_path/'inputs.jsonl';tok=tmp_path/'tokens.jsonl'
 side.write_text(json.dumps({'schema':'ft_t06_ordinary_input/v3','uid':uid,'input_tokens':2,'canonical_encoding':'utf8-json-int-array-separators=,:','input_ids_sha256':digest,'input_ids_path':str(ids),'input_ids_file_sha256':digest,'source':'Scheduler._process_one_msg(UserMsg)','time_ns':1,'service_birth':birth,'worker_birth':birth})+'\n')
 tok.write_text(json.dumps({'schema':'ft_t06_ordinary_token/v3','uid':uid,'request_seq':1,'next_token':99,'completion_tokens_delta':1,'completion_tokens_cumulative':1,'finished':True,'finish_reason':'stop','time_ns':2,'service_birth':birth,'worker_birth':birth})+'\n')
 raw=tmp_path/'raw.sse';raw.write_text('data: {"id":"chatcmpl-2","choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n'+'data: {"id":"chatcmpl-2","choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n'+'data: [DONE]\n')
 api=tmp_path/'api.json';api.write_text(json.dumps({'schema':'ft_t06_ordinary_sse/v3','pause_enabled':False,'payload_source':{'path':str(inp),'sha256':m.sha(inp)},'sse':str(raw),'sse_sha256':m.sha(raw),'uid':uid,'usage':{'prompt_tokens':2,'completion_tokens':1},'finish_reason':'stop'}))
 value=m.ordinary_sidecar_binding(client,inp,api,side,tok)
 assert value['uid']==uid and value['token_ids_sha256']==hashlib.sha256(b'[99]').hexdigest() and value['fulltext_sha256']
