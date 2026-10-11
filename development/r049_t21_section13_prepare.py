"""E2-R049 §13 T21 runner; inert without --run and fail-closed on R046c."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, socket, subprocess, sys, time, urllib.request, threading
from types import SimpleNamespace
from pathlib import Path

RID='E2-R049'; CANDIDATE='988c9e183c8dca4415fd9b5d02318b26664da619'; PARENT='effb9969706922ddad9e59b96377e46469ebe97f'
T06_RID='E2-R046c'; T06_MANIFEST_SCHEMA='ft_r046c_route_manifest/v1'
# The old two-session probe requires ft_dev ACKs, which §13 forbids by
# disabling the pause endpoint.  Do not allocate a batch or take a lock until
# an ordinary-SSE two-session tool is delivered and bound in a new source file.
SECTION13_ORDINARY_TWO_DECODE_AVAILABLE=False
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); WT=ROOT/'wt/e2d15'; VENV=ROOT/'venv'; HERE=Path(__file__).resolve().parent
PROFILE_TOOL=WT/'tools/build_expert_profile.py'; FRONTEND_RENDER=WT/'python/freetoken/tokenizer/tokenize.py'; TRAIN_ROUTE=ROUNDS/'E2-R046c/G_seed12k/route'
HELDOUT={'seed_45k':ROUNDS/'E2-R046c/G_seed_45k/trace_seed_45k.json','seed_real':ROUNDS/'E2-R046c/G_seed_real/trace_seed_real.json'}
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
# This bound qwen4_exp model has text_config.num_experts=512.
MODEL_NUM_EXPERTS=512
WINDOW=98304
SEED_WINDOW_CLIENT=HERE/'r046_seed_agent_trace_v2.py'
D0_HELPER=HERE/'r049_d0_startup.py'
D0_CACHE=WT/'python/freetoken/moe/offload_cache.py'
D0_STARTUP=WT/'scripts/equiv_suite/service_capture_startup.py'
AGENT_TRACE=WT/'scripts/agent_trace.py'; AGENT_TRACE_RAW=WT/'scripts/_agent_trace_original.py'; TWO_DECODE_PROBE=WT/'scripts/multisession_probe.py'
D07_LEAF=HERE/'d07_g3g4_prepare.py'; ACK_GENERATION=WT/'python/freetoken/server/generation.py'; ACK_GRAPH=WT/'python/freetoken/engine/graph.py'; ACK_TOKENIZER=WT/'python/freetoken/tokenizer/server.py'
class T21NotMet(RuntimeError): pass
POLICIES={'L':'lru','P':'profile','PA':'profile+adapt'}; PROCESS_ORDER=('L1','P1','PA1','L2','P2','PA2','L_D0','P_D0','PA_D0')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_new(path, value):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
ENV_RECORD_KEYS=('CUDA_VISIBLE_DEVICES','PYTHONPATH','VIRTUAL_ENV','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','FT_DEV_EXPERT_POLICY','FT_DEV_EXPERT_PROFILE','FT_DEV_EXPERT_ADAPT_EVERY','FT_DEV_EXPERT_ADAPT_SWAPS','FT_DEV_D0','FT_T21_DIAG_JOURNAL')
def file_probe(path,purpose):
 path.parent.mkdir(parents=True,exist_ok=True);write_new(path,{'schema':'ft_r049_cpu_file_probe/v1','kind':'CPU_FILE_PROBE','not_measurement':True,'purpose':purpose});return sha(path)
def service_files(d,directory,port,policy,profile,d0,*,file_dry_run=False):
 env=env_for(d,policy,profile,d0);base_argv=d.serve_argv(port);journal=directory/'d0_journal.jsonl'
 if any(flag in base_argv for flag in ('--route-trace','--enable-route-trace')): raise RuntimeError('T21 §13 must not enable route trace')
 if d0:
  if journal.exists() or journal.is_symlink(): raise RuntimeError('T21 D0 journal path is not fresh')
  env['FT_T21_DIAG_JOURNAL']=str(journal);argv=[str(VENV/'bin/python'),str(D0_HELPER),*base_argv]
 else:
  if 'FT_T21_DIAG_JOURNAL' in env or 'FT_DEV_D0' in env: raise RuntimeError('T21 production must not load D0 hook')
  argv=base_argv
 directory.mkdir(parents=True,exist_ok=True)
 recorded={key:env[key] for key in ENV_RECORD_KEYS if key in env}
 (directory/'ENV.json').write_text(json.dumps(recorded,sort_keys=True)+'\n',encoding='utf-8');(directory/'ENV.txt').write_text(''.join(f'{k}={recorded[k]}\n' for k in sorted(recorded)),encoding='utf-8')
 (directory/'SERVE_CMD.txt').write_text(json.dumps({'argv':argv,'policy':policy,'d0':d0,'journal':str(journal) if d0 else None}),encoding='utf-8')
 write_new(directory/'serve_args_diff.json',arm_difference_declaration(policy,d0))
 (directory/'serve.log').open('x',encoding='utf-8').close()
 if file_dry_run:
  # Service-owned paths are prepared here.  Client writers own their output
  # paths below, so the dry path exercises the same exclusive-create boundary.
  for name in ('owned_process.json','health.json','serve_args.txt') : file_probe(directory/name,'formal T21 service output')
  if d0:file_probe(journal,'formal D0 journal')
 return env,argv,journal
def load_d07():
 p=HERE/'d07_g3g4_prepare.py';spec=importlib.util.spec_from_file_location('r049_d07',p);m=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(m)
 original=m.serve_argv
 def argv(port):
  result=list(original(port))
  for flag,value in (('--memory-ratio','0.88'),('--kv-reserve-tokens',str(WINDOW)),('--max-seq-len-override',str(WINDOW))):result[result.index(flag)+1]=value
  return result
 m.serve_argv=argv;return m
def arms():
 return [{'name':name,'policy':POLICIES[name.removesuffix('_D0').rstrip('12')],'d0':name.endswith('_D0'),'production':not name.endswith('_D0'),'workloads':['cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512']} for name in PROCESS_ORDER]
def assert_plan(rows):
 if [x['name'] for x in rows]!=list(PROCESS_ORDER): raise RuntimeError('T21 process order differs')
 if [x['policy'] for x in rows[:6]]!=['lru','profile','profile+adapt']*2: raise RuntimeError('T21 production policy order differs')
 if any(x['d0'] for x in rows[:6]) or any(not x['d0'] for x in rows[6:]): raise RuntimeError('T21 D0 split differs')
 if any(x['workloads']!=rows[0]['workloads'] for x in rows): raise RuntimeError('T21 workload shape differs')
 return rows
def require_section13_runtime_tooling():
 if not SECTION13_ORDINARY_TWO_DECODE_AVAILABLE: raise RuntimeError('T21 §13 ordinary-SSE two-decode tooling is not delivered; do not allocate a batch or start a service')
def arm_difference_declaration(policy,d0):
 """Declare every variable allowed to differ from the L reference in its stratum."""
 if policy not in POLICIES.values(): raise RuntimeError('T21 unknown policy declaration')
 variables={'FT_DEV_EXPERT_POLICY':policy}
 if policy!='lru': variables['FT_DEV_EXPERT_PROFILE']='seed12k_only.strp'
 if policy=='profile+adapt': variables.update(FT_DEV_EXPERT_ADAPT_EVERY='1',FT_DEV_EXPERT_ADAPT_SWAPS='1')
 if d0: variables['FT_DEV_D0']='1'
 return {'schema':'ft_t21_serve_args_diff/v1','comparison_stratum':'diagnostic_d0' if d0 else 'production','reference_arm':'L_D0' if d0 else 'L1','allowed_difference_keys':sorted(variables),'target_values':variables,'common_contract':{'memory_ratio':'0.88','kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'route_trace_enabled':False,'pause_endpoint_enabled':False},'single_variable_rule':'within a stratum, policy is the only scientific variable; profile and adaptation fields are required consequences of that policy'}
def source_hashes():
 paths=(Path(__file__),SEED_WINDOW_CLIENT,PROFILE_TOOL,FRONTEND_RENDER,D07_LEAF,D0_HELPER,D0_CACHE,D0_STARTUP,AGENT_TRACE,AGENT_TRACE_RAW,TWO_DECODE_PROBE,ACK_GENERATION,ACK_GRAPH,ACK_TOKENIZER)
 return {str(p):sha(p) for p in paths}
def require_review(dry_receipt=None):
 p=ROOT/'runs/dev_T21'/f'{RID}_startup_review_v3.json'
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222: raise RuntimeError('T21 startup review absent or writable')
 d=json.loads(p.read_text()); want={'schema':'ft_t21_startup_review/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'approved':True,'verdict':'PASS','source_sha256':source_hashes()}
 if any(d.get(k)!=v for k,v in want.items()): raise RuntimeError('T21 startup review binding differs')
 if dry_receipt is not None and (d.get('dry_run_receipt')!=dry_receipt['path'] or d.get('dry_run_receipt_sha256')!=dry_receipt['sha256']):raise RuntimeError('T21 review binds a different dry-run receipt')
 return p
def require_t06_metadata():
 manifest=ROUNDS/T06_RID/'manifest.json'
 if manifest.is_symlink() or not manifest.is_file(): raise RuntimeError('R046c T06 route manifest absent')
 d=json.loads(manifest.read_text())
 if d.get('schema')!=T06_MANIFEST_SCHEMA or d.get('rid')!=T06_RID or d.get('candidate_commit')!=PARENT: raise RuntimeError('R046c T06 route manifest identity differs')
 if d.get('memory_ratio')!='0.88': raise RuntimeError('R046c T06 performance ratio differs')
 if d.get('window')!={'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'completion_reserve_tokens':2048,'max_prompt_tokens':WINDOW-2048}:raise RuntimeError('R046c T06 release window differs')
 arms=d.get('arms'); heldout=d.get('heldout_routes')
 if not isinstance(arms,list) or len(arms)!=4 or any(not isinstance(arm,dict) for arm in arms): raise RuntimeError('R046c T06 arm training binding differs')
 roles={arm.get('role'):arm for arm in arms}
 if d.get('d15_training_route')!='G_seed12k/route' or not isinstance(heldout,list) or len(heldout)!=3 or set(heldout)!={'G_seed_45k/route','G_seed_real/route','G_two/route'}: raise RuntimeError('R046c T06 train/heldout partition differs')
 if set(roles)!={'seed12k','seed_45k','seed_real','two'} or any(roles[role].get('directory')!=f'G_{role}' or roles[role].get('d15_training_input') is not (role=='seed12k') for role in roles): raise RuntimeError('R046c T06 arm training binding differs')
 return manifest
def admission(dry_receipt=None):
 d=load_d07()
 if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists; T21 remains queued')
 closures={T06_RID:d.require_closed_round(T06_RID,'measured'),'E2-R050-gate-D15':d.require_closed_round('E2-R050-gate-D15','kept')}
 if subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()!=CANDIDATE or subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True): raise RuntimeError('D15 candidate differs or is dirty')
 if subprocess.run(['git','-C',str(WT),'merge-base','--is-ancestor',PARENT,'HEAD']).returncode: raise RuntimeError('D15 candidate lacks eff measurement ancestry')
 return d,closures,require_t06_metadata(),require_review(dry_receipt)
def child_argv(batch,receipt):
 return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]
def receipt_sha(d,argv): return d.argv_sha256(argv)
def require_receipt(d,batch,path):
 mine=d.process_birth(); expected=receipt_sha(d,child_argv(batch,path)); deadline=time.monotonic()+30
 static={'schema':'ft_t21_owned_launch/v1','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':expected}
 while time.monotonic()<deadline:
  if path.is_symlink(): raise RuntimeError('T21 child receipt is symlinked')
  if not path.is_file(): time.sleep(.05);continue
  try: row=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError) as error: raise RuntimeError('T21 child receipt unreadable') from error
  if any(row.get(k)!=v for k,v in static.items()): raise RuntimeError('T21 child receipt binding differs')
  if row.get('state')=='reserved' or (row.get('state')=='launched' and row.get('child') is None): time.sleep(.05);continue
  if row.get('state')!='launched': raise RuntimeError('T21 child receipt state unknown')
  if row.get('batch_pid')!=mine['pid'] or row.get('child')!=mine: raise RuntimeError('T21 child receipt binding differs')
  return row
 raise RuntimeError('T21 child receipt did not reach launched state')
def controller():
 if sys.platform!='linux': raise RuntimeError('T21 controller requires Linux')
 require_section13_runtime_tooling()
 dry_receipt=require_dry_run_receipt();d,_,_,_=admission(dry_receipt); owned=d.load_owned_lifecycle(); helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r049_atomic')
 batch=helper.next_batch(ROUNDS); receipt=ROOT/'runs/dev_T21'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True); argv=child_argv(batch,receipt)
 reserved={'schema':'ft_t21_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':receipt_sha(d,argv),'controller':d.process_birth()}
 got=owned.reserve_process(helper,batch,RID,argv,receipt,reserved); child=owned.process_identity(got['batch_pid'])
 if child is None or child.get('pid')!=got['batch_pid'] or type(child.get('start_ticks')) is not int: raise RuntimeError('T21 reserved child birth unavailable')
 child={'pid':child['pid'],'start_ticks':child['start_ticks'],'execution_id':f"{child['pid']}:{child['start_ticks']}"}
 return d.publish_child_binding(receipt,got,child,lifecycle=owned)
def start_service(d,directory,port,policy,profile,d0):
 env,argv,journal=service_files(d,directory,port,policy,profile,d0)
 log=(directory/'serve.log').open('a',encoding='utf-8');process=subprocess.Popen(argv,cwd=WT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=d.load_owned_lifecycle().process_identity(process.pid)
  if birth is None or birth.get('pgid')!=process.pid or birth.get('session')!=process.pid:raise RuntimeError('T21 service lacks private PGID/session')
  deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   if process.poll() is not None:raise RuntimeError('T21 service died during startup')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as response:
     if json.load(response).get('status')=='ok':
      write_new(directory/'owned_process.json',{'pid':process.pid,'birth':birth,'port':port,'d0_journal':str(journal) if d0 else None});write_new(directory/'health.json',{'status':'ok'})
      text=(directory/'serve.log').read_text(encoding='utf-8',errors='replace');at=text.find('Parsed arguments')
      if at<0:raise RuntimeError('T21 service did not emit Parsed arguments')
      parsed='\n'.join(text[at:].splitlines()[:2]).strip()
      if not parsed:raise RuntimeError('T21 Parsed arguments are empty')
      (directory/'serve_args.txt').write_text(parsed+'\n',encoding='utf-8');return process
   except (OSError,ValueError):pass
   time.sleep(2)
  raise TimeoutError('T21 service readiness exceeded')
 except BaseException as error:
  try:stop_service(d,process)
  except BaseException as cleanup:cleanup.owned_process=process;cleanup.owned_cleanup_failed=True;raise cleanup from error
  error.owned_process=process;raise
def stop_service(d,process):
 try:d.load_owned_lifecycle().stop_owned_process(process)
 except BaseException as error:error.owned_process=process;error.owned_cleanup_failed=True;raise
def _token_sha256(ids):
 if not isinstance(ids,list) or not ids or any(type(item) is not int or item < 0 for item in ids): raise RuntimeError('T21 tokenizer did not produce request input IDs')
 return hashlib.sha256(b''.join(int(item).to_bytes(4,'little',signed=True) for item in ids)).hexdigest()
def _load_tokenizer(path):
 from transformers import AutoTokenizer
 return AutoTokenizer.from_pretrained(str(path),trust_remote_code=True)
def _frontend_contract():
 if FRONTEND_RENDER.is_symlink() or not FRONTEND_RENDER.is_file(): raise RuntimeError('T21 candidate FrontendManager renderer is unavailable')
 raw=FRONTEND_RENDER.read_text(encoding='utf-8')
 required=('self.tokenizer.apply_chat_template(','tokenize=False,','add_generation_prompt=True,','add_special_tokens=not templated','chat_template_kwargs = {**chat_template_kwargs, "tools": tools}')
 if any(marker not in raw for marker in required): raise RuntimeError('T21 candidate FrontendManager rendering contract differs')
 return {'frontend_renderer_path':str(FRONTEND_RENDER),'frontend_renderer_sha256':sha(FRONTEND_RENDER),'frontend_template_contract':'TokenizeManager._render: tokenize=False, add_generation_prompt=True, tools injected into chat_template_kwargs; TokenizeManager.tokenize: add_special_tokens=False'}
def _frontend_ids(tokenizer,messages,*,tools=None,chat_template_kwargs=None):
 kwargs=dict(chat_template_kwargs or {})
 if tools is not None: kwargs['tools']=tools
 try: rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,**kwargs)
 except Exception as error: raise RuntimeError('T21 could not reconstruct the exact chat-template request') from error
 if not isinstance(rendered,str): raise RuntimeError('T21 chat template did not render request text')
 ids=tokenizer.encode(rendered,add_special_tokens=False)
 if hasattr(ids,'tolist'): ids=ids.tolist()
 _token_sha256(ids)
 return ids
def _usage_prompt_tokens(record):
 usage=record.get('usage') if isinstance(record,dict) else None
 value=usage.get('prompt_tokens') if isinstance(usage,dict) else (record.get('prompt_tokens') if isinstance(record,dict) else None)
 if type(value) is not int or value <= 0: raise RuntimeError('T21 response lacks service prompt_tokens')
 return value
def _client_binding_digest(digest,frontend_token_count,service_prompt_tokens,*,kind):
 if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): raise RuntimeError('T21 request input digest is invalid')
 if type(frontend_token_count) is not int or frontend_token_count<=0: raise RuntimeError('T21 frontend request token count is invalid')
 if service_prompt_tokens!=frontend_token_count: raise RuntimeError('T21 service prompt_tokens differs from reconstructed request IDs; possible truncation/frontend drift')
 return {'schema':'ft_t21_request_input_binding/v1','kind':kind,'input_ids_sha256':digest,'frontend_token_count':frontend_token_count,'service_prompt_tokens':service_prompt_tokens,'service_prompt_tokens_equal_frontend':True,'truncation_check':'service_prompt_tokens_equal_frontend','binding_origin':'client_frontend_reconstruction_not_server_capture','server_capture':False}
def _client_binding(ids,service_prompt_tokens,*,kind): return _client_binding_digest(_token_sha256(ids),len(ids),service_prompt_tokens,kind=kind)
def _frozen_probe(d):
 paths=d.verify_frozen_cold_helpers(); probe=Path(paths['probe_raw'])
 spec=importlib.util.spec_from_file_location('r049_frozen_probe',probe); module=importlib.util.module_from_spec(spec); assert spec.loader;spec.loader.exec_module(module);return module
def _cold_binding(d,tokenizer,cold_id,path):
 probe=_frozen_probe(d); text,built=probe.build_text(tokenizer,32052,cold_id)
 ids=_frontend_ids(tokenizer,[{'role':'user','content':text}],chat_template_kwargs={'enable_thinking':False})
 document=json.loads(Path(path).read_text()); record=document.get('record')
 binding=_client_binding(ids,_usage_prompt_tokens(record),kind='cold_eq')
 binding.update({'cold_id':cold_id,'sealed_cold_eq_raw_sha256':d.COLD_RAW_SHA,'built_text_tokens':built,**_frontend_contract()})
 return binding
def _install_timed_agent_capture(module):
 """Patch only the candidate companion's documented _consume/_write seams."""
 original_consume,module_write=module._consume,module._write;evidence=[]
 def consume(events,t0):
  rows=[];uid=None;prior_seq=prior_cumulative=0
  def tapped():
   nonlocal uid,prior_seq,prior_cumulative
   for event in events:
    if isinstance(event,dict) and isinstance(event.get('ft_dev'),dict):
     dev=event['ft_dev'];current=dev.get('uid');seq=dev.get('request_seq');delta=dev.get('completion_tokens_delta');cumulative=dev.get('completion_tokens_cumulative')
     if dev.get('schema')!='ft_dev_stream/v1' or type(current) is not int or (uid is not None and current!=uid) or type(seq) is not int or type(delta) is not int or delta not in (0,1) or type(cumulative) is not int or seq!=prior_seq+1 or cumulative!=prior_cumulative+delta: raise RuntimeError('T21 replay ft_dev SSE acknowledgement differs')
     uid=current;prior_seq=seq;prior_cumulative=cumulative
     if delta: rows.append({'t_s':time.perf_counter()-t0,'uid':uid,'request_seq':seq,'completion_tokens_delta':delta,'completion_tokens_cumulative':cumulative})
    yield event
  result=original_consume(tapped(),t0)
  if uid is None or not rows or result.get('usage',{}).get('completion_tokens') not in (None,prior_cumulative): raise RuntimeError('T21 replay lacks usable SSE timing')
  evidence.append(rows);return result
 def write(path_,doc):
  rounds=doc.get('rounds') if isinstance(doc,dict) else None
  if not isinstance(rounds,list) or len(rounds)!=len(evidence): raise RuntimeError('T21 replay timing does not bind output rounds')
  for row,events in zip(rounds,evidence):
   target_row=row.get('record') if isinstance(row,dict) and isinstance(row.get('record'),dict) else row
   if not isinstance(target_row,dict): raise RuntimeError('T21 replay output row differs')
   target_row['token_events']=events
  return module_write(path_,doc)
 module._consume=consume;module._write=write
 return evidence
def _load_window_client():
 loader=importlib.util.spec_from_file_location('r049_window_client',SEED_WINDOW_CLIENT);module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module);return module
def _timed_agent_replay(port,trace,target,spec,profile):
 """Run the candidate replay unchanged while preserving actual ft_dev SSE times."""
 path=AGENT_TRACE;module_name='r049_timed_agent_trace';loader=importlib.util.spec_from_file_location(module_name,path);module=importlib.util.module_from_spec(loader);assert loader.loader;loader.loader.exec_module(module)
 _install_timed_agent_capture(module)
 wrapper=_load_window_client()
 source=json.loads(Path(trace).read_text());expected=(source.get('meta') or {}).get('window_completion')
 if not isinstance(expected,dict) or expected.get('schema')!='ft_t06_window_completion/v2' or expected.get('window')!=WINDOW or expected.get('max_prompt_tokens')!=WINDOW-2048:raise RuntimeError('T21 heldout source lacks approved actual-window completion binding')
 frontend,frontend_binding=wrapper.load_frontend(WT,MODEL_PATH)
 wrapper.install(module,wrapper.WindowGuard(frontend,expected['seed_raw_sha256'],frontend_binding,expected=expected))
 old=sys.argv[:];sys.argv=[str(path),'replay','--trace',str(trace),'--out',str(target),'--base-url',f'http://127.0.0.1:{port}/v1','--model','Qwen3.8-Flash-Next-NVFP4','--fresh-note','T21-heldout']
 try: module.main()
 finally: sys.argv=old
 return {'agent_trace_sha256':sha(path),'agent_trace_original_sha256':sha(path.with_name('_agent_trace_original.py')),'window_client_sha256':sha(SEED_WINDOW_CLIENT),'sse_timing_bound':True}

def _agent_bindings(tokenizer,trace_path,replay_path):
 trace=json.loads(Path(trace_path).read_text()); meta=trace.get('meta') or {}; tools=trace.get('tools'); thinking=bool((meta.get('params') or {}).get('thinking',True)); chat_template_kwargs={} if thinking else {'enable_thinking':False}; source=trace.get('rounds') or []
 replay=json.loads(Path(replay_path).read_text()); bound=[]
 for row in replay.get('rounds') or []:
  index=row.get('round')
  if type(index) is not int or not 0<=index<len(source): raise RuntimeError('T21 replay round does not bind heldout trace')
  messages=source[index].get('messages') if isinstance(source[index],dict) else None
  if not isinstance(messages,list) or not messages: raise RuntimeError('T21 heldout trace lacks replay messages')
  entry=_client_binding(_frontend_ids(tokenizer,messages,tools=tools,chat_template_kwargs=chat_template_kwargs),row.get('prompt_tokens'),kind='heldout_agent_replay')
  events=row.get('token_events') or [];uids=sorted({event.get('uid') for event in events if isinstance(event,dict) and type(event.get('uid')) is int})
  if len(uids)!=1 or not events or any(not isinstance(event,dict) or type(event.get('completion_tokens_delta')) is not int or event['completion_tokens_delta']<=0 for event in events): raise RuntimeError('T21 heldout replay lacks positive single-UID ACK binding')
  cumulative=events[-1].get('completion_tokens_cumulative');completion=row.get('completion_tokens')
  if type(cumulative) is not int or type(completion) is not int or cumulative!=completion: raise RuntimeError('T21 heldout ACK cumulative differs from completion tokens')
  entry.update({'round':index,'ack_uids':uids,'ack_completion_tokens':completion,'trace_sha256':sha(trace_path),'messages_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),**_frontend_contract()})
  bound.append(entry)
 if not bound: raise RuntimeError('T21 replay produced no request binding')
 return bound
def _load_probe_module():
 path=TWO_DECODE_PROBE;spec=importlib.util.spec_from_file_location('r049_two_decode_probe',path);module=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(module);return module
def _two_decode_with_sse(probe,args):
 original=probe._sse_events; traces={}; lock=threading.Lock()
 def tapped(response):
  parts=[]; uid=None
  for event in original(response):
   if isinstance(event,dict):
    dev=event.get('ft_dev') or {}; uid=dev.get('uid',uid)
    for choice in event.get('choices') or []:
     delta=(choice.get('delta') or {}) if isinstance(choice,dict) else {}
     parts.append({'content':delta.get('content',''),'reasoning_content':delta.get('reasoning_content',''),'tool_calls':delta.get('tool_calls',[])})
   yield event
  if type(uid) is not int: raise RuntimeError('T21 two-decode SSE lacks ACK UID')
  with lock:
   if uid in traces: raise RuntimeError('T21 two-decode duplicate ACK UID')
   traces[uid]=parts
 probe._sse_events=tapped
 try: raw=probe.run_two_decode(args)
 finally: probe._sse_events=original
 return raw,traces

def _sse_response(parts):
 """Canonical actual SSE response; never inferred from token timestamps."""
 response={'content':'','reasoning_content':'','tool_calls':[]}
 for part in parts:
  response['content']+=str(part.get('content') or '')
  response['reasoning_content']+=str(part.get('reasoning_content') or '')
  response['tool_calls'].extend(part.get('tool_calls') or [])
 return response

def _run_two_decode_bound(directory,base,policy,profile,d0):
 probe=_load_probe_module(); target=directory/'two_decode.json'; args=SimpleNamespace(base_url=base,model='Qwen3.8-Flash-Next-NVFP4',timeout=1800.0,tokenizer_path=str(MODEL_PATH),ctx=32000,max_tokens=512,same_prompt=0,reps=1,out=target,command='two-decode')
 raw,traces=_two_decode_with_sse(probe,args); public={'schema':raw.get('schema'),'command':'two-decode','same_prompt':False,'reps':[]}; bindings=[]
 for rep in raw.get('reps') or []:
  records=rep.get('_records'); hashes=rep.get('prompt_sha256'); counts=rep.get('frontend_token_counts')
  if not isinstance(records,list) or len(records)!=2 or not isinstance(hashes,list) or len(hashes)!=2 or not isinstance(counts,list) or len(counts)!=2: raise RuntimeError('T21 two-decode lacks exact two request records')
  copy={key:value for key,value in rep.items() if key!='_records'}; ways=[]
  for index,record in enumerate(records):
   expected=hashes[index]
   if not isinstance(expected,str) or len(expected)!=64 or type(counts[index]) is not int or counts[index]<=0: raise RuntimeError('T21 two-decode lacks frontend request binding')
   parts=traces.get(record.get('uid'))
   if not parts or record.get('completion_tokens')!=512 or record.get('error'): raise RuntimeError('T21 two-decode lacks exact 512-token SSE content')
   response=_sse_response(parts); full_text=json.dumps(response,ensure_ascii=False,sort_keys=True,separators=(',',':'))
   sidecar=target.with_name(f'{target.stem}.rep{rep.get("rep")}.way{index}.sse.json')
   sidecar_doc={'schema':'ft_t21_two_decode_sse/v1','uid':record['uid'],'parts':parts,'full_response':response,'full_text':full_text}
   probe.write_exclusive(sidecar,sidecar_doc)
   content_sha=hashlib.sha256(json.dumps(parts,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
   binding=_client_binding_digest(expected,counts[index],_usage_prompt_tokens(record),kind='two_decode')
   binding.update({'response_sse_sha256':content_sha,'full_response_sha256':hashlib.sha256(full_text.encode()).hexdigest(),'candidate_probe_prompt_sha256':expected,'candidate_probe_sha256':sha(WT/'scripts/multisession_probe.py'),'rep':rep.get('rep'),'way':index,**_frontend_contract()})
   bindings.append(binding)
   tokens=target.with_name(f'{target.stem}.rep{rep.get("rep")}.way{index}.tokens.json');probe.write_exclusive(tokens,{'uid':record['uid'],'token_events':record['token_events']})
   way=probe._per_way(record,tokens);way.update({'sse_sidecar':sidecar.name,'sse_sidecar_sha256':sha(sidecar),'full_text':full_text});ways.append(way)
  copy['per_way']=ways;public['reps'].append(copy)
 probe.write_exclusive(target,public)
 if not bindings: raise RuntimeError('T21 two-decode produced no input binding')
 return target,bindings

def _request_binding_only(value):
 if isinstance(value,list): return [_request_binding_only(item) for item in value]
 if isinstance(value,dict): return {key:_request_binding_only(item) for key,item in value.items() if key not in {'response_sse_sha256','full_response_sha256','sse_sidecar','sse_sidecar_sha256','full_text'}}
 return value
def _checked_output(directory,name,path,binding,baseline,texts,bindings):
 text=_full_text_sha256(json.loads(path.read_text())); texts[name]=text;bindings[name]=binding
 comparable=_request_binding_only(binding)
 if baseline is not None and (text!=baseline['texts'].get(name) or comparable!=_request_binding_only(baseline['request_input_bindings'].get(name))):
  evidence={'schema':'ft_t21_not_met/v1','kind':'not_met','arm':directory.name,'workload':name,'text_sha256':text,'baseline_text_sha256':baseline['texts'].get(name),'request_input_binding':comparable,'baseline_request_input_binding':_request_binding_only(baseline['request_input_bindings'].get(name))}
  write_new(directory/'not_met.json',evidence);raise T21NotMet('T21 first workload text/input binding differs')

def run_workloads(directory,port,spec,baseline=None,*,file_dry_run=False):
 if file_dry_run:
  outputs={}
  for name in ('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512'):
   path=directory/({'seed_45k':'seed_45k_replay.json','seed_real':'seed_real_replay.json','two_decode_diff512':'two_decode.json'}.get(name,name+'.json'));file_probe(path,'formal workload output');outputs[name]=path
  return {'d0_enabled':spec['d0'],'outputs':{k:v.name for k,v in outputs.items()},'cpu_file_probe':True}
 d=load_d07(); base=f'http://127.0.0.1:{port}/v1'; outputs={}; texts={}; bindings={};tokenizer=_load_tokenizer(MODEL_PATH)
 for index in (1,2):
  name=f'cold32k_{index}';cold_id=f'{RID}-cold{index}';target=directory/f'{name}.json';d.invoke_cold_eq(WT,port,cold_id,target);binding=_cold_binding(d,tokenizer,cold_id,target);outputs[name]=target;_checked_output(directory,name,target,binding,baseline,texts,bindings)
 for role,trace in HELDOUT.items():
  target=directory/f'{role}_replay.json';timed=_timed_agent_replay(port,trace,target,spec,directory.parent/'seed12k_only.strp');binding=[{**entry,**timed} for entry in _agent_bindings(tokenizer,trace,target)];outputs[role]=target;_checked_output(directory,role,target,binding,baseline,texts,bindings)
 name='two_decode_diff512';two,binding=_run_two_decode_bound(directory,base,spec['policy'],directory.parent/'seed12k_only.strp',spec['d0']);outputs[name]=two;_checked_output(directory,name,two,binding,baseline,texts,bindings)
 outputs_named={k:str(v.name) for k,v in outputs.items()}
 journal_path=str((directory/'d0_journal.jsonl').name) if spec['d0'] else None
 timing=_timing_metrics(outputs)
 return {'timing':timing,'d0_enabled':spec['d0'],'texts':texts,'request_input_bindings':bindings,'outputs':outputs_named,'d0_journal_path':journal_path,'generated_tokens':_output_tokens(outputs)}
def _input_ids_sha256(document):
 # Legacy reader retained only for old raw evidence; R049 writes explicit request bindings above.
 found=[]
 def visit(value):
  if isinstance(value,dict):
   for key,item in value.items():
    if key in {'input_ids_sha256','prompt_sha256'} and isinstance(item,str) and len(item)==64:found.append(item)
    else:visit(item)
  elif isinstance(value,list):
   for item in value:visit(item)
 visit(document)
 if not found:raise RuntimeError('T21 client result lacks actual input_ids SHA binding')
 return sorted(set(found))
def _full_text_sha256(document):
 values=[]
 def visit(value):
  if isinstance(value,dict):
   for key,item in value.items():
    if key in {'text','content','full_text'} and isinstance(item,str):values.append(item)
    else:visit(item)
  elif isinstance(value,list):
   for item in value:visit(item)
 visit(document)
 if not values:raise RuntimeError('T21 client result lacks full text')
 return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def _finite_metric(value,name):
 if not isinstance(value,(int,float)) or isinstance(value,bool) or value<=0: raise RuntimeError(f'T21 lacks actual {name}')
 return float(value)
def _row_decode_tps(row):
 rate=row.get('decode_tps') if isinstance(row,dict) else None
 if isinstance(rate,(int,float)) and not isinstance(rate,bool) and rate>0:return float(rate)
 events=row.get('token_events') if isinstance(row,dict) else None
 if not isinstance(events,list) or len(events)<2: raise RuntimeError('T21 lacks actual SSE token timestamps')
 first,last=events[0].get('t_s'),events[-1].get('t_s');tokens=sum(item.get('completion_tokens_delta',0) for item in events if isinstance(item,dict))
 if not isinstance(first,(int,float)) or not isinstance(last,(int,float)) or last<=first or type(tokens) is not int or tokens<2: raise RuntimeError('T21 invalid actual SSE token timestamps')
 return (tokens-1)/(last-first)
def _timing_from_document(path,name):
 doc=json.loads(Path(path).read_text()); rows=[]
 if name.startswith('cold32k_'):
  record=doc.get('record') or {};rows=[record]
 elif name in HELDOUT:
  rows=[(item.get('record') if isinstance(item,dict) and isinstance(item.get('record'),dict) else item) for item in doc.get('rounds') or []]
 elif name=='two_decode_diff512':
  rows=[way for rep in doc.get('reps') or [] for way in rep.get('per_way') or []]
 if not rows: return None
 ttft=[]; tps=[];tokens=0
 for row in rows:
  if not isinstance(row,dict): return None
  try:
   ttft.append(_finite_metric(row.get('ttft_s'),'TTFT'))
   rate=_finite_metric(_row_decode_tps(row),'decode tok/s')
   count=row.get('completion_tokens')
   if type(count) is not int or count<=0: raise RuntimeError('T21 lacks actual completion token count')
  except RuntimeError:
   return None
  tps.append((rate,count));tokens+=count
 return {'samples':len(rows),'completion_tokens':tokens,'ttft_s':sum(ttft)/len(ttft),'decode_tps':sum(rate*count for rate,count in tps)/tokens,'basis':'stream_first_token_and_first_to_last_ack_timestamps'}
def _timing_metrics(outputs):
 return {name:metric for name,path in outputs.items() if (metric:=_timing_from_document(path,name)) is not None}
def _require_production_timing(metrics):
 missing=set(('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512'))-set(metrics)
 if missing: raise RuntimeError('T21 production lacks actual stream timing: '+','.join(sorted(missing)))
 return metrics

def _d0_rows(directory):
 path=directory/'d0_journal.jsonl'
 if path.is_symlink() or not path.is_file(): raise RuntimeError('T21 D0 journal absent')
 rows=[]
 for line in path.read_text().splitlines():
  try: rows.append(json.loads(line))
  except json.JSONDecodeError as error: raise RuntimeError('T21 D0 journal invalid JSON') from error
 if not rows or [row.get('seq') for row in rows]!=list(range(1,len(rows)+1)): raise RuntimeError('T21 D0 journal sequence differs')
 births={json.dumps(row.get('worker_birth'),sort_keys=True) for row in rows}
 if len(births)!=1 or not isinstance(rows[0].get('worker_birth'),dict) or type(rows[0]['worker_birth'].get('pid')) is not int: raise RuntimeError('T21 D0 worker birth differs')
 if rows[0].get('kind')!='install' or rows[-1].get('kind')!='terminal' or rows[-1].get('status')!='complete': raise RuntimeError('T21 D0 journal lacks complete install/terminal')
 decode=[row for row in rows if row.get('kind')=='decode'];adapt=[row for row in rows if row.get('kind')=='adapt']
 if not decode: raise RuntimeError('T21 D0 journal lacks decode rows')
 for row in decode:
  rids=row.get('rids')
  if any(type(row.get(key)) is not int or row[key]<0 for key in ('active','missing','fetched','hits','h2d_bytes','expert_row_bytes','step')) or not isinstance(rids,list) or not rids or any(type(uid) is not int for uid in rids) or row['active']<row['missing'] or row['hits']!=row['active']-row['missing'] or row['h2d_bytes']!=row['fetched']*row['expert_row_bytes']: raise RuntimeError('T21 D0 decode counter evidence differs')
 for row in adapt:
  rids=row.get('rids')
  if type(row.get('policy_swap_bytes_delta')) is not int or row['policy_swap_bytes_delta']<0 or type(row.get('step')) is not int or not isinstance(rids,list) or not rids or any(type(uid) is not int for uid in rids): raise RuntimeError('T21 D0 adaptation evidence differs')
 return {'path':str(path.name),'sha256':sha(path),'worker_birth':rows[0]['worker_birth'],'decode':decode,'adapt':adapt}
def _output_tokens(outputs):
 total=0
 for path in outputs.values():
  doc=json.loads(path.read_text())
  def visit(value):
   nonlocal total
   if isinstance(value,dict):
    if type(value.get('completion_tokens')) is int: total+=value['completion_tokens'];return
    for item in value.values():visit(item)
   elif isinstance(value,list):
    for item in value:visit(item)
  visit(doc)
 if total<=0: raise RuntimeError('T21 diagnostic outputs lack actual generated token count')
 return total
def run_measurements(batch=None,*,file_dry_run=False,output_root=None):
 output_root=ROUNDS if output_root is None else output_root
 d=load_d07();run=output_root/f'.dryrun_{RID}' if file_dry_run else output_root/RID
 if run.exists() and not file_dry_run:raise RuntimeError('T21 round already exists; no overwrite')
 rows=assert_plan(arms());run.mkdir(parents=True,exist_ok=file_dry_run);profile=None;process=None
 try:
  profile,build_cmd=build_profile(run,file_dry_run=True) if file_dry_run else build_profile(run);write_new(run/'profile_binding.json',{'training_route':'E2-R046c/G_seed12k/route','profile_derived_from_seed12k':True,'heldout_tuning_forbidden':['seed_45k','seed_real','two_decode_diff512'],'profile':'seed12k_only.strp','profile_sha256':sha(profile),'build_argv':build_cmd,'adapt_parameters':{'every':1,'swaps':1,'status':'configured_default_not_tuned'}})
  production={};diagnostic={}
  for spec in rows:
   directory=run/spec['name'];port=d.dynamic_fixture_port();diagnostic_value=None
   if file_dry_run:
    service_files(d,directory,port,spec['policy'],profile,spec['d0'],file_dry_run=True);run_workloads(directory,port,spec,file_dry_run=True);continue
   directory.mkdir();process=start_service(d,directory,port,spec['policy'],profile,spec['d0'])
   try:
    value=run_workloads(directory,port,spec,production.get('L1') if production else None)
    if spec['production']:
     if value.get('d0_enabled') is not False:raise RuntimeError('T21 production arm leaked D0')
     _require_production_timing(value.get('timing') or {})
     production[spec['name']]=value
    else:
     if value.get('d0_enabled') is not True:raise RuntimeError('T21 diagnostic arm lacks D0')
     diagnostic_value=value
   finally:
    owned_process=process;process=None
    try:stop_service(d,owned_process)
    except BaseException as cleanup:cleanup.owned_process=owned_process;cleanup.owned_cleanup_failed=True;raise
   if diagnostic_value is not None:
    # Read terminal journal only after the owned service group has exited.
    role_uids={role:sorted({uid for binding in diagnostic_value['request_input_bindings'][role] for uid in binding['ack_uids']}) for role in HELDOUT}
    role_tokens={role:diagnostic_value['timing'][role]['completion_tokens'] for role in HELDOUT}
    diagnostic[spec['name']]=diagnostic_metrics(_d0_rows(directory),role_tokens,role_uids)
  if file_dry_run:
   file_probe(run/'measurement_journal.json','formal measurement journal');file_probe(run/'result.json','formal result');return {'schema':'ft_r049_cpu_file_dry_run/v1','rid':RID,'run':str(run),'arms':[row['name'] for row in rows],'profile':str(profile),'build_argv':build_cmd}
  assert_bitwise(production);benefit=benefit_gate(production,diagnostic);result={'schema':'ft_t21_raw_measurement/v1','round_id':RID,'card':'T21','batch':batch,'candidate_commit':CANDIDATE,'verdict':'pending_review','proposed_verdict':'measured','production':production,'diagnostic_only':diagnostic,'production_speed_excludes_d0':True,'benefit_claimed':True,'heldout_benefit':benefit};write_new(run/'result.json',result);return result
 except T21NotMet as error:
  if not (run/'not_met.json').exists(): write_new(run/'not_met.json',{'schema':'ft_t21_not_met/v1','kind':'not_met','round_id':RID,'candidate_commit':CANDIDATE,'reason':str(error)})
  raise
 except BaseException as error:
  if process is not None:
   try:stop_service(d,process)
   except BaseException as cleanup:cleanup.owned_process=process;cleanup.owned_cleanup_failed=True;raise cleanup from error
  raise
def child(batch,receipt):
 if sys.platform!='linux': raise RuntimeError('T21 child requires Linux')
 require_section13_runtime_tooling()
 dry_receipt=require_dry_run_receipt();d=load_d07(); admission(dry_receipt); require_receipt(d,batch,receipt); owner=d.take_d07_gpu_lock(RID,batch); release=True
 try: return run_measurements(batch)
 except BaseException as error:
  if getattr(error,'owned_cleanup_failed',False):release=False
  raise
 finally:
  if release: d.release_d07_gpu_lock(owner)
def build_profile(run,*,file_dry_run=False):
 out=run/'seed12k_only.strp'; cmd=[str(VENV/'bin/python'),str(PROFILE_TOOL),str(TRAIN_ROUTE),str(out),'--num-experts',str(MODEL_NUM_EXPERTS)]
 subprocess.run(cmd,cwd=WT,check=True)
 # The builder's exit status is insufficient: make the candidate's STRP
 # reader parse the bytes and require the cache's expert geometry.
 verify=[str(VENV/'bin/python'),'-c',f"import sys; sys.path.insert(0, sys.argv[2]); from freetoken.moe.expert_profile import read_profile; p=read_profile(sys.argv[1], num_experts={MODEL_NUM_EXPERTS}); assert p.ranked",str(out),str(WT/'python')]
 subprocess.run(verify,cwd=WT,check=True)
 return out,cmd
def env_for(d,policy,profile,d0):
 env=d.clean_environment(WT);env['FT_DEV_EXPERT_POLICY']=policy
 if policy!='lru': env['FT_DEV_EXPERT_PROFILE']=str(profile)
 if policy=='profile+adapt': env.update(FT_DEV_EXPERT_ADAPT_EVERY='1',FT_DEV_EXPERT_ADAPT_SWAPS='1')
 if d0: env.update(FT_DEV_D0='1')
 if 'FT_DEV_ROUTE_TRACE' in env or 'FT_DEV_PAUSE_ENDPOINT' in env: raise RuntimeError('T21 §13 requires route trace and pause endpoint disabled')
 return env
def assert_bitwise(production):
 baseline=production['L1']['texts']
 for arm in ('P1','PA1','L2','P2','PA2'):
  if production[arm]['texts']!=baseline: raise RuntimeError('T21 policy changed full text; stop')
 return True
def diagnostic_metrics(journal,role_tokens,role_uids):
 if set(role_tokens)!={'seed_45k','seed_real'} or any(type(value) is not int or value<=0 for value in role_tokens.values()) or set(role_uids)!={'seed_45k','seed_real'}: raise RuntimeError('invalid D0 generated token/role binding')
 decode=journal['decode'];adapt=journal['adapt'];report={'role_completion_tokens':role_tokens,'journal_sha256':journal['sha256'],'worker_birth':journal['worker_birth'],'roles':{}}
 used=set()
 for role,uids in role_uids.items():
  expected=set(uids)
  if not expected: raise RuntimeError('T21 heldout role lacks ACK UID')
  own=[]
  for index,row in enumerate(decode):
   actual=set(row.get('rids') or [])
   if actual & expected:
    if not actual<=expected: raise RuntimeError('T21 D0 decode mixes heldout role UIDs')
    own.append((index,row));used.add(index)
  if not own: raise RuntimeError('T21 D0 decode lacks heldout UID evidence for '+role)
  boundaries={row['step'] for _,row in own};swaps=[]
  for row in adapt:
   actual=set(row.get('rids') or [])
   if actual & expected:
    if not actual<=expected or row.get('step') not in boundaries: raise RuntimeError('T21 D0 swap lacks unique heldout UID/boundary binding')
    swaps.append(row)
  active=sum(row['active'] for _,row in own);missing=sum(row['missing'] for _,row in own);h2d=sum(row['h2d_bytes'] for _,row in own);swap=sum(row['policy_swap_bytes_delta'] for row in swaps)
  if active<=0 or missing>active: raise RuntimeError('invalid D0 counters')
  report['roles'][role]={'active':active,'missing':missing,'hits':sum(row['hits'] for _,row in own),'common_miss_rate':missing/active,'h2d_bytes':h2d,'swap_bytes':swap,'h2d_plus_swap_bytes':h2d+swap,'decode_steps':len(own),'swap_steps':len(swaps),'uids':sorted(expected),'completion_tokens':role_tokens[role],'h2d_plus_swap_bytes_per_token':(h2d+swap)/role_tokens[role]}
 return report
def _mean(values):
 if not values: raise RuntimeError('T21 missing replicate metrics')
 return sum(values)/len(values)
def benefit_gate(production,diagnostic):
 if set(production)!={'L1','P1','PA1','L2','P2','PA2'} or set(diagnostic)!={'L_D0','P_D0','PA_D0'}: raise RuntimeError('T21 missing required production/diagnostic replicates')
 report={'replicates':2,'heldout':{}}
 for policy in ('P','PA'):
  base=[production['L1'],production['L2']];trial=[production[policy+'1'],production[policy+'2']];by_role={}
  for role in HELDOUT:
   base_speed=_mean([arm['timing'][role]['decode_tps'] for arm in base]);trial_speed=_mean([arm['timing'][role]['decode_tps'] for arm in trial]);ldiag=diagnostic['L_D0']['roles'][role];pdiag=diagnostic[policy+'_D0']['roles'][role]
   outcome={'baseline_decode_tps':base_speed,'candidate_decode_tps':trial_speed,'baseline_common_miss_rate':ldiag['common_miss_rate'],'candidate_common_miss_rate':pdiag['common_miss_rate'],'baseline_h2d_plus_swap_bytes_per_token':ldiag['h2d_plus_swap_bytes_per_token'],'candidate_h2d_plus_swap_bytes_per_token':pdiag['h2d_plus_swap_bytes_per_token'],'production_completion_tokens':[arm['timing'][role]['completion_tokens'] for arm in base+trial],'baseline_d0_completion_tokens':ldiag['completion_tokens'],'candidate_d0_completion_tokens':pdiag['completion_tokens']}
   outcome['met']=trial_speed>base_speed and pdiag['common_miss_rate']<ldiag['common_miss_rate'] and pdiag['h2d_plus_swap_bytes_per_token']<ldiag['h2d_plus_swap_bytes_per_token'];by_role[role]=outcome
  report['heldout'][policy]=by_role
 if not all(row['met'] for policies in report['heldout'].values() for row in policies.values()): raise T21NotMet('T21 heldout cache benefit criterion not met')
 return report

def packet():
 return {'schema':'ft_t21_r049_prepare/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'window':{'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'completion_reserve_tokens':2048,'max_prompt_tokens':WINDOW-2048},'memory_ratio':'0.88','assigned':True,'requests_sent':False,'gpu_lock_taken':False,'training_route':'E2-R046c/G_seed12k/route','heldout_routes':['E2-R046c/G_seed_45k','E2-R046c/G_seed_real','E2-R046c/G_two'],'arms':assert_plan(arms()),'cuda_visible_devices_cpu_guard':'','run_requires':['explicit --run','R046c measured','R050 kept','R startup review','foreign GPU lock deny','owned controller receipt','GPU idle']}
def dry_run():
 """Nine-arm file path rehearsal; no Popen, request, lock, or batch."""
 if sys.platform!='linux':raise RuntimeError('T21 dry-run requires Linux')
 d=load_d07();d.require_closed_round('E2-R046c','measured');d.require_closed_round('E2-R050-gate-D15','kept');require_t06_metadata()
 target=dry_run_directory()
 if target.exists():raise RuntimeError('T21 dry-run sibling already exists')
 target.mkdir(mode=0o700);target.chmod(0o700);rows=assert_plan(arms())
 with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
  sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 if port==8095:raise RuntimeError('T21 dry-run allocated forbidden port')
 dry=run_measurements(file_dry_run=True,output_root=ROUNDS)
 receipt={'schema':'ft_r049_dry_run/v1','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'passed':True,'owner':{'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')},'cwd':os.getcwd(),'source_sha256':source_hashes(),'formal_directory':str(ROUNDS/RID),'formal_rid_directory_created':False,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'port':port,'arms':[x['name'] for x in rows],'file_dry_run':dry}
 write_new(target/'dry_run_receipt.json',receipt);(target/'dry_run_receipt.json').chmod(0o444);return receipt
def dry_run_directory(): return ROUNDS/f'.dryrun_{RID}'
def require_dry_run_receipt():
 receipt=dry_run_directory()/'dry_run_receipt.json'
 if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode&0o222:raise RuntimeError('T21 dry-run receipt absent or writable')
 value=json.loads(receipt.read_text());owner={'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')}
 if (value.get('schema')!='ft_r049_dry_run/v1' or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=PARENT or value.get('passed') is not True or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('source_sha256')!=source_hashes() or any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated'))):raise RuntimeError('T21 dry-run receipt binding differs')
 return {'path':str(receipt),'sha256':sha(receipt)}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args(argv)
 if a.run and a.dry_run:p.error('--run and --dry-run are mutually exclusive')
 if a.dry_run and (a.owned_child or a.batch is not None or a.launch_receipt is not None):p.error('--dry-run does not accept controller or child arguments')
 if a.dry_run:print(json.dumps(dry_run(),ensure_ascii=False,sort_keys=True));return 0
 if not a.run: print(json.dumps(packet(),ensure_ascii=False,sort_keys=True));return 0
 if a.owned_child:
  if a.batch is None or a.launch_receipt is None:p.error('owned child requires batch and receipt')
  child(a.batch,a.launch_receipt);return 0
 if a.batch is not None or a.launch_receipt is not None:p.error('controller does not accept child arguments')
 controller();return 0
if __name__=='__main__': raise SystemExit(main())

