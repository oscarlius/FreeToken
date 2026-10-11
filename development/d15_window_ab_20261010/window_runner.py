"""D15 sealed two-service runner.  ``--prepare`` has no runtime effects."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,platform,subprocess,time,urllib.request, threading, socket, sys
from pathlib import Path
from window_startup import projected_record
HERE=Path(__file__).parent; WT=Path('/data2/FreeToken/wt/release-e2'); RELEASE=Path('/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2/release_config.py'); ROOT=Path('/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real'); TRACE=ROOT/'trace_seed_real.json'
T17='E2-D09-T17-reapply-bd57-20261010'; R067E='E2-R067e-20261010-retry2'
class UnsafeCleanupError(RuntimeError): pass
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,n):s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[n]=m;s.loader.exec_module(m);return m
def put(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf8') as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
def remaining(deadline):
 n=deadline-time.monotonic()
 if n<=0:raise TimeoutError('global 1800-second D15 budget expired')
 return max(1,int(n))
def sealed(p):
 p=Path(p)
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222:raise RuntimeError('sealed artifact unsafe')
 return p
def inputs():
 ps=[ROOT/f'round-{i:02d}.payload.json' for i in range(8)]
 if any(not p.is_file() or p.is_symlink() for p in [*ps,TRACE]):raise RuntimeError('immutable R046g inputs absent')
 hit=json.loads(TRACE.read_text())['meta']['window_hit']
 if hit.get('request_k')!=9 or hit.get('actual_prompt_tokens')!=100223 or not isinstance(hit.get('payload'),dict):raise RuntimeError('window_hit differs')
 return ps,hit
def prepare(config=RELEASE):
 release=load(config,'release');ps,hit=inputs()
 return {'schema':'d15_window_ab_prepare/v4','default_inert':True,'release_config_sha256':sha(config),'arms':[projected_record(release,x,str(HERE/'window_observer.py')) for x in ('W98K','W128K')],'input_sha256':[sha(x) for x in ps],'trace_sha256':sha(TRACE),'window_hit':{'request_k':9,'actual_prompt_tokens':100223,'payload_sha256':hashlib.sha256(json.dumps(hit['payload'],sort_keys=True,separators=(',',':')).encode()).hexdigest()},'global_timeout_s':1800,'service_budget':2,'prefill_interval_scope':'async Engine.forward_batch stream interval through original forward return; not a kernel sum or TTFT'}
def require_seal(path,packet):
 d=json.loads(sealed(path).read_text())
 if d.get('schema')!='d15_window_ab_root_approval/v2' or d.get('verdict')!='sealed_root_approved':raise RuntimeError('sealed root admission required')
 for k,rid in (('T17',T17),('R067e',R067E)):
  b=d.get('predecessors',{}).get(k)
  if not isinstance(b,dict) or b.get('rid')!=rid or not isinstance(b.get('terminal_verdict'),str):raise RuntimeError(f'{k} terminal binding differs')
  for field in ('terminal','manifest'):
   q=sealed(b.get(field+'_path',''))
   if sha(q)!=b.get(field+'_sha256'):raise RuntimeError(f'{k} {field} SHA differs')
  if json.loads(sealed(b['terminal_path']).read_text()).get('verdict')!=b['terminal_verdict']:raise RuntimeError(f'{k} terminal state differs')
 t=d.get('formal_T16',{});
 if t.get('verdict')!='kept' or sha(sealed(t.get('path','')))!=t.get('sha256'):raise RuntimeError('formal T16 kept binding differs')
 if d.get('prepare_sha256')!=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest():raise RuntimeError('approval does not bind prepared packet')
 pins=d.get('source_pins',{})
 for n in ('adapter','client','producer','runner','observer','native_engine','runtime','startup','observer_source','d07','frontend'):
  x=pins.get(n,{});p=Path(x.get('path',''))
  if p.is_symlink() or not p.is_file():raise RuntimeError(f'{n} source is not a regular file')
  if sha(p)!=x.get('sha256'):raise RuntimeError(f'{n} source pin differs')
 for name,digest in d.get('runtime_files',{}).items():
  p=Path(name)
  if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise RuntimeError('runtime dependency pin differs: '+name)
 if subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()!='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9':raise RuntimeError('candidate commit changed')
 if subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True).strip():raise RuntimeError('candidate tracked source dirty')
 return d
def metric(bound,sse,start,proc_start,system_uptime):
 rows=bound['token_events']
 if len(rows)<2:raise RuntimeError('native token identity evidence invalid')
 # Network monotonic clock is the only reviewed monotonic clock. Native IDs prove equality, not timing.
 dec=(sse['terminal_monotonic_ns']-sse['first_output_monotonic_ns'])/1e9;elapsed=(time.monotonic_ns()-start)/1e9
 return {'process_uptime_s':(time.monotonic_ns()-proc_start)/1e9,'system_uptime_s':system_uptime(),'ttft_upper_bound_s':sse['ttft_s'],'prefill_compute_ms':None,'prefill_evidence':'missing_async_cuda_event_receipt','decode_tps_network':(sse['completion_tokens']-1)/dec,'native_token_ids_only':True,'round_elapsed_s':elapsed,'decoding_fraction':dec/elapsed}
def invoke(adapter,client,base,payload,out,observer,deadline,proc_start,system_uptime,*,frontend=None,sampler=None,window=131072,deadline_abort=None):
 body=json.loads(payload.read_text())
 if frontend is None:raise RuntimeError('actual candidate frontend required')
 ids=frontend(body);input_digest=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
 if len(ids)+body['max_tokens']>window:raise RuntimeError('planned prompt and completion exceed window')
 environment={'uptime':subprocess.check_output(['uptime'],text=True).strip(),'r_threads':sum(x.strip().startswith('R') for x in subprocess.check_output(['ps','-eLo','stat='],text=True).splitlines()),'system_uptime_s':system_uptime()}
 start=time.monotonic_ns();wall_start=time.time_ns();state={}
 def stream():
  try:state['value']=adapter.ordinary_stream_request(base,payload,out,timeout=remaining(deadline))
  except BaseException as exc:state['error']=exc
 worker=threading.Thread(target=stream,daemon=True);worker.start();worker.join(timeout=max(0,deadline-time.monotonic()))
 if worker.is_alive():
  if deadline_abort:deadline_abort()
  worker.join(timeout=2)
  if worker.is_alive():raise UnsafeCleanupError('SSE worker did not exit after owned deadline abort')
  raise TimeoutError('global measurement deadline expired during SSE stream; owned service stopped, bounded shutdown allowance follows')
 if 'error' in state:
  if isinstance(state['error'],TimeoutError) and deadline_abort:deadline_abort()
  raise state['error']
 remaining(deadline);wall_end=time.time_ns();raw=client.bind(payload,out,None,None,observer/'inputs.jsonl',observer/'tokens.jsonl',out.with_suffix('.binding.json'));b=adapter.ordinary_binding(raw);s=adapter.timing_from_sse(out)
 if b['input_ids_sha256']!=input_digest or b['prompt_tokens']!=len(ids):raise RuntimeError('candidate frontend / Worker / API input identity differs')
 event_path=observer/'prefill_events.jsonl';end=min(deadline,time.monotonic()+2);events=[]
 while time.monotonic()<end:
  events=[r for line in event_path.read_text().splitlines() if line.strip() for r in [json.loads(line)] if b['uid'] in r['uids']] if event_path.exists() else []
  if events or raw.get('cached_tokens')==len(ids):break
  time.sleep(.02)
 remaining(deadline)
 if not events and raw.get('cached_tokens')!=len(ids):raise RuntimeError('missing completed prefill stream interval receipts')
 if any(len(r['uids'])!=1 for r in events):raise RuntimeError('serial request observed shared prefill interval')
 row={'input_sha256':sha(payload),'input_ids_sha256':b['input_ids_sha256'],'planned_input_tokens':len(ids),'uid':b['uid'],'native_token_sha256':b['token_ids_sha256'],'completion_tokens':b['completion_tokens'],'cached_tokens':raw.get('cached_tokens'),**metric(b,s,start,proc_start,system_uptime)}
 row.update(environment=environment,round_elapsed_s=(s['terminal_monotonic_ns']-s['dispatch_monotonic_ns'])/1e9,decode_elapsed_s=(s['terminal_monotonic_ns']-s['first_output_monotonic_ns'])/1e9,prefill_compute_ms=sum(r['elapsed_ms'] for r in events),prefill_evidence='async Engine.forward_batch stream intervals including sampling/copy enqueue and CPU waits',prefill_receipts=events,min_free_gpu_mib=sampler.interval_min_free(wall_start,wall_end) if sampler else None)
 row['decoding_fraction']=row['decode_elapsed_s']/row['round_elapsed_s'];put(out.with_suffix('.metrics.json'),row)
 return row,b
def start(record,run,lifecycle,deadline):
 run.mkdir(parents=True,exist_ok=False);obs=run/'observer';obs.mkdir(mode=0o700);env=dict(record['environment']);env.update(R046C_T06_OBSERVER_DIR=str(obs),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1');log=(run/'serve.log').open('x');p=subprocess.Popen([x.replace('__RUN_DIR__',str(run)) for x in record['argv']],cwd=WT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  ident=lifecycle.process_identity(p.pid)
  if not ident or ident.get('pgid')!=p.pid or ident.get('session')!=p.pid:raise RuntimeError('private PID/PGID/session missing')
  put(run/'owned_process.json',{'pid':p.pid,'pgid':p.pid,'birth':ident})
  while True:
   if p.poll() is not None:raise RuntimeError('service exited before health')
   timeout=min(3,remaining(deadline))
   try:
    with urllib.request.urlopen(f"http://127.0.0.1:{record['port']}/health",timeout=timeout) as r:
     health=json.load(r)
     if health.get('status')=='ok' and health.get('maintenance')=='serving':return p,log,obs,time.monotonic_ns()
   except (OSError,ValueError,json.JSONDecodeError):pass
   time.sleep(1)
 except BaseException as original:
  try:
   log.close();lifecycle.stop_owned_process(p);end=time.monotonic()+120
   while lifecycle.owned_group_alive(p.pid) and time.monotonic()<end:time.sleep(1)
   if lifecycle.owned_group_alive(p.pid):raise UnsafeCleanupError('owned group remains after startup failure')
  except BaseException as cleanup_error:
   raise UnsafeCleanupError(f'unsafe startup cleanup: {cleanup_error!r}') from original
  raise
def cleanup(p,log,port,master_port,lifecycle,gpu_idle):
 try:log.close();lifecycle.stop_owned_process(p,term_timeout=90,kill_timeout=30)
 except BaseException:return False
 end=time.monotonic()+120
 try:
  while lifecycle.owned_group_alive(p.pid) and time.monotonic()<end:time.sleep(1)
 except BaseException:return False
 if lifecycle.owned_group_alive(p.pid):return False
 for candidate in (port,master_port):
  try:
   with socket.socket() as sock:sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',candidate))
  except OSError:return False
 while time.monotonic()<end:
  try:
   if gpu_idle():return True
  except BaseException:return False
  time.sleep(.2)
 return False
def slot_check(log_path,expected):
 text=Path(log_path).read_text(errors='replace');import re
 rows=re.findall(r'--moe-cache-auto resolved moe_cache_size=(\d+) num_pages=(\d+) \(prefill_overlap=(True|False)\)',text)
 if len(rows)!=1:raise RuntimeError('exact moe-cache-auto resolution receipt missing or ambiguous')
 actual,pages,_=rows[0];return {'expected_slots':expected,'actual_slots':int(actual),'num_pages':int(pages)}
def run_two(packet,admission,deps):
 """Exactly two starts: W98 A then W128 A+B+cold; all share one deadline."""
 deadline=deps.now()+1800;arms=packet['arms'];adapter,client,producer=deps.adapter, deps.client, deps.producer;out={};started=0
 def measured_call(record,path,out,obs,deadline,born):
  return invoke(adapter,client,f"http://127.0.0.1:{record['port']}/v1",path,out,obs,deadline,born,deps.system_uptime,frontend=deps.frontend,sampler=deps.sampler,window=record['window'],deadline_abort=lambda:deps.lifecycle.stop_owned_process(deps.active_process,term_timeout=90,kill_timeout=30))
 for idx,record in enumerate(arms):
  started+=1;p=log=obs=None;run=deps.root/record['arm']
  try:
   p,log,obs,born=deps.start(record,run,deps.lifecycle,deadline);deps.active_process=p;base=f"http://127.0.0.1:{record['port']}/v1";rows=[]
   for i,path in enumerate(deps.seed_payloads):
    if sha(path)!=packet['input_sha256'][i]:raise RuntimeError('frozen payload changed')
    row,_=measured_call(record,path,run/f'A{i}.api.json',obs,deadline,born);rows.append(row)
    if idx==1 and row['native_token_sha256']!=out['W98K']['A'][i]['native_token_sha256']:raise RuntimeError(f'not_met A token mismatch {i+1}; B/cold suppressed')
   slots=deps.slot_check(run/'serve.log',record['expected_auto_slots'])
   if record['arm']=='W98K' and slots['actual_slots']!=2700:raise RuntimeError('W98K actual auto slots differ from required 2700')
   out[record['arm']]={'A':rows,'slots':slots}
   if idx==0:continue
   for i,(a,b) in enumerate(zip(out['W98K']['A'],rows),1):
    if a['native_token_sha256']!=b['native_token_sha256']:raise RuntimeError(f'not_met A token mismatch {i}; B/cold suppressed')
   payload=deps.window_payload(run/'B09.payload.json');brows=[]
   for k in range(9,13):
    planned=deps.frontend(json.loads(payload.read_text()))
    if k==9 and len(planned)!=100223:raise RuntimeError('B09 canonical frontend input must be 100223 tokens')
    reserve=json.loads(payload.read_text()).get('max_tokens',2048)
    if len(planned)+reserve>record['window']:
     out['W128K']['B_boundary']={'request':k,'reason':'capacity_limit_before_dispatch','planned_input_tokens':len(planned),'max_tokens':reserve,'window':record['window']};break
    row,_=measured_call(record,payload,run/f'B{k:02d}.api.json',obs,deadline,born);brows.append(row)
    if k<12:payload=deps.next_b_payload(payload,run/f'B{k+1:02d}.payload.json',producer,k-1)
   cold=deps.cold_payload(run/'cold.payload.json')
   crow,_=measured_call(record,cold,run/'cold.api.json',obs,deadline,born)
   if crow['cached_tokens']!=0 or crow['min_free_gpu_mib'] is None:raise RuntimeError('cold requires cached_tokens=0 and non-null min_free_gpu_mib')
   out['W128K'].update(B=brows,cold=crow)
  except BaseException as exc:
   if isinstance(exc,UnsafeCleanupError) or 'unsafe startup cleanup' in repr(exc):
    deps.cleanup_safe=False;put(deps.root/'unsafe_cleanup.json',{'error':repr(exc),'phase':record['arm']})
   raise
  finally:
   if p is not None:
    try:clean=cleanup(p,log,record['port'],record.get('master_port',record['port']+100),deps.lifecycle,deps.gpu_idle)
    except BaseException as exc:clean=False
    if not clean:
     deps.cleanup_safe=False;put(deps.root/'unsafe_cleanup.json',{'error':'cleanup did not prove owned process, HTTP/master port, and GPU idle','phase':record['arm']});raise UnsafeCleanupError('unsafe cleanup; retain lock')
 if started!=2:raise RuntimeError('service budget differs')
 rates={arm:sum(r['completion_tokens']-1 for r in value['A'])/sum(r['decode_elapsed_s'] for r in value['A']) for arm,value in out.items()}
 decline=(1-rates['W128K']/rates['W98K'])*100
 out['comparison']={'aggregation':'pooled completion_tokens_minus_one / sum network first-output-to-terminal time, same native outputs','decode_tok_s':rates,'decode_decline_pct':decline,'model_prediction_decline_pct':4.0,'decision':'128K release configuration candidate' if decline<=6 else ('128K feasible; revise slope and pair with replacement strategy' if decline<=12 else '128K temporarily not feasible')}
 return out
class Deps:
 pass
def actual_deps(admission,root):
 d=Deps();pins=admission['source_pins'];d.adapter=load(pins['adapter']['path'],'d15_adapter');d.client=load(pins['client']['path'],'d15_client');d.producer=load(pins['producer']['path'],'d15_producer');d.root=root;d.now=time.monotonic;d.d07=load('/data2/FreeToken/development/d07_g3g4_prepare.py','d07');d.lifecycle=d.d07.load_owned_lifecycle();d.start=start;d.cleanup_safe=True;d.system_uptime=lambda:float(Path('/proc/uptime').read_text().split()[0]);d.slot_check=slot_check
 def idle():
  d.d07.require_gpu_idle()
  return not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
 d.gpu_idle=idle
 driver=load(HERE/'source_bundle/r046c_ordinary_seed_driver_v3.py','d15_frontend');d.frontend=driver.candidate_frontend(WT,Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'))
 from window_runtime import Sampler
 d.sampler=Sampler(root/'telemetry_1hz.jsonl')
 ps,hit=inputs();d.seed_payloads=ps
 def wp(path):put(path,hit['payload']);return path
 def nxt(prior,path,producer,index):
  # Exact old assistant/result is reconstructed from normal SSE; only producer's readonly executor and FOLLOW_UPS may extend it.
  old=json.loads(prior.read_text());api=prior.with_name(prior.stem.replace('payload','api')+'.json');res=d.adapter.full_response(api,producer);msgs=list(old['messages'])+[producer.assistant_message(res)]
  for call in res['tool_calls']:msgs.append({'role':'tool','tool_call_id':call['id'],'content':producer.exec_tool_call(str(pins['producer_root']),call)})
  if not res['tool_calls']:msgs.append({'role':'user','content':producer.FOLLOW_UPS[index%len(producer.FOLLOW_UPS)]})
  put(path,{**old,'messages':msgs});return path
 def cold(path):
  probe=load('/data2/FreeToken/development/d09_gpu_reapplication_20261010/protocol_t16/t16_frozen_helpers_v1/probe_ft_cold32k.py','d15cold');from transformers import AutoTokenizer
  text,_=probe.build_text(AutoTokenizer.from_pretrained('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay',trust_remote_code=True),129012,'D15-W128K-cold');put(path,{'model':'Qwen3.8-Flash-Next-NVFP4','messages':[{'role':'user','content':text}],'temperature':0,'max_tokens':256,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}});return path
 d.window_payload=wp;d.next_b_payload=nxt;d.cold_payload=cold
 # Construction above must succeed before telemetry starts; sampler has no runtime authority before this point.
 d.sampler.start();return d
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--approval',type=Path);a=p.parse_args(argv)
 if a.prepare==a.run:p.error('select exactly one')
 packet=prepare()
 if a.prepare:print(json.dumps(packet,sort_keys=True));return 0
 if platform.system()!='Linux':raise RuntimeError('Linux GPU host only; nothing started')
 admission=require_seal(a.approval,packet);d07=load('/data2/FreeToken/development/d07_g3g4_prepare.py','d07lock');owner=d07.take_d07_gpu_lock('D15-window-ab',0);root=Path('/data2/FreeToken/runs/d15_window_ab')/time.strftime('%Y%m%d_%H%M%S');root.mkdir(parents=True);safe=False;deps=None
 try:
  d07.require_gpu_idle();deps=actual_deps(admission,root);result=run_two(packet,admission,deps);put(root/'result.json',{'verdict':'completed','result':result});safe=True;return 0
 except Exception as e:
  text=repr(e);logs=[]
  for p in root.glob('*/serve.log'):
   value=p.read_text(errors='replace');
   if any(x in value.lower() for x in ('out of memory','cuda oom','cuda error: out of memory')):logs.append({'path':str(p),'sha256':sha(p),'oom_marker':True})
  put(root/'failure.json',{'verdict':'not_met' if logs or 'not_met' in text or 'out of memory' in text.lower() else 'failed_harness','error':text,'oom_source_evidence':logs,'product_acceptance':False});raise
 finally:
  if deps is not None:
   sampler_safe=deps.sampler.close()
   if not sampler_safe:deps.cleanup_safe=False
  if (safe or deps is None or deps.cleanup_safe) and not (root/'unsafe_cleanup.json').exists():d07.release_d07_gpu_lock(owner)
if __name__=='__main__':raise SystemExit(main())
