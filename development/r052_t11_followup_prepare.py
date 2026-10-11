#!/usr/bin/env python3
"""E2-R052 T11 follow-up behavior runner; GPU only with reviewed --run."""
import argparse,json,hashlib,importlib.util,sys,subprocess,urllib.request,os,socket,shutil
from pathlib import Path
RID='E2-R052'; CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'; PARENT=CANDIDATE; ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1-ordinary-rewind'; VENV=ROOT/'venv'; ROUNDS=Path('/data2/_shared/runs/ft_rounds')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes():
 base=Path(__file__).resolve().parent
 d=load_d07()
 paths=tuple(base/name for name in (Path(__file__).name,'r052_t11_replay.py','d07_g3g4_prepare.py','ft_batch_port_pair_v1.py','r052_d0_shutdown_startup_v1.py'))+tuple(WT/name for name in ('scripts/_agent_trace_original.py','python/freetoken/server/launch.py','python/freetoken/server/args.py','python/freetoken/server/api_server.py','python/freetoken/server/openai_api.py','python/freetoken/moe/offload_cache.py','python/freetoken/moe/d0_decode.py','python/freetoken/scheduler/cache.py'))+(d.OWNED_SOURCE/'t17_owned_launch_protocol.py',ROOT/'runs/plan_batches/e2_launch.py')
 return {str(path):sha(path) for path in paths}
def dry_run_directory():return ROUNDS/f'.dryrun_R052_v5_{RID}'
def copy_source(source,target):
 if source.is_symlink() or not source.is_file():raise RuntimeError('R052 runtime source unavailable')
 shutil.copyfile(source,target);target.chmod(0o600)
 return {'source':str(source),'source_sha256':sha(source),'copy':str(target),'copy_sha256':sha(target),'source_md5':hashlib.md5(source.read_bytes()).hexdigest(),'copy_md5':hashlib.md5(target.read_bytes()).hexdigest(),'mode':oct(target.stat().st_mode&0o777)}
def load_d07():
 p=Path(__file__).with_name('d07_g3g4_prepare.py');s=importlib.util.spec_from_file_location('r052_d07',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def threshold(target):
 counts=[target.get('prompt_tokens'),target.get('completion_tokens')]
 if any(type(x) is not int or x<0 for x in counts) or counts[0]<=0:raise ValueError('target full token length missing')
 full=sum(counts)
 return full//64*64
def classify(target,follow):
 cached=follow.get('cached_tokens')
 if type(cached) is not int or cached<0:raise ValueError('follow-up lacks actual cached_tokens')
 floor=threshold(target)
 if floor<=13376 or 13376<cached<floor:raise RuntimeError('R052 hypothesis bounds do not distinguish observed result')
 return {'target_uid':target.get('uid'),'target_full_tokens':target['prompt_tokens']+target['completion_tokens'],'threshold_64':floor,'followup_cached_tokens':cached,'classification':'H-hook' if cached>=floor else 'H-bug'}
def followup_messages(target,short_user='请继续。'):
 messages=target.get('messages');text=target.get('text')
 assistant=target.get('assistant_message',{'role':'assistant','content':text})
 if not isinstance(messages,list) or not messages or not isinstance(assistant,dict) or assistant.get('role')!='assistant' or not any(assistant.get(k) for k in ('content','reasoning_content','tool_calls')):raise ValueError('target actual prompt/output missing')
 return [*messages,assistant,{'role':'user','content':short_user}]
def execute_followup(target,send,short_user='请继续。'):
 """Send the only permitted continuation after the actual uid=8 response."""
 if target.get('trace_index')!=7 or target.get('history_uid')!=8:raise ValueError('R052 target binding differs')
 messages=followup_messages(target,short_user);response=send(messages)
 if not isinstance(response,dict):raise ValueError('follow-up response is not an object')
 return {'followup_messages':messages,'actual_response':response}
def replay_module():
 p=Path(__file__).with_name('r052_t11_replay.py');spec=importlib.util.spec_from_file_location('r052_replay',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def dry_run():
 """Prepare formal paths in a sibling and return before Popen, HTTP, lock, or batch."""
 d=load_d07();d.checked_worktree(WT);tools=replay_module();target=dry_run_directory()
 if target.exists():raise RuntimeError('R052 dry-run sibling already exists')
 target.mkdir(mode=0o700,parents=True);target.chmod(0o700);trace=tools.bind_trace(target);client=tools.client_module(WT);binding=tools.target_binding(trace,client)
 copies=[copy_source(Path(__file__),target/Path(__file__).name),copy_source(Path(__file__).with_name('r052_t11_replay.py'),target/'r052_t11_replay.py'),copy_source(WT/'scripts/_agent_trace_original.py',target/'_agent_trace_original.py')]
 port,pair=tools.private_port_pair()
 _,argv,service_probes=tools.prepare_service_files(d,target,WT,port,file_dry_run=True);outputs=tools.dry_replay_outputs(target)
 receipt={'schema':'ft_r052_dry_run/v5','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'passed':True,'source_sha256':source_hashes(),'source_copies':copies,'owner':{'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')},'cwd':os.getcwd(),'worktree':{'path':str(WT),'parent':str(WT.parent)},'formal_rid_directory_created':False,'formal_directory':str(ROUNDS/RID),'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'port':port,'port_pair':pair,'trace_sha256':tools.TRACE_SHA,'trace_rounds':len(trace.get('rounds',[])),'trace_source':str(tools.TRACE),'target_binding':binding,'client_prechecked':bool(client),'serve_argv':argv,'cpu_file_probes':[*(service_probes or []),*outputs]}
 d.write_new(target/'dry_run_receipt.json',receipt);path=target/'dry_run_receipt.json';path.chmod(0o444)
 return {**receipt,'dry_run_directory':str(target),'receipt_sha256':sha(path)}
def require_dry_run_receipt():
 path=dry_run_directory()/'dry_run_receipt.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R052 dry-run receipt absent or writable')
 value=json.loads(path.read_text());tools=replay_module();owner={'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')}
 if (value.get('schema')!='ft_r052_dry_run/v5' or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=PARENT or value.get('passed') is not True or value.get('trace_source')!=str(tools.TRACE) or value.get('trace_sha256')!=tools.TRACE_SHA or value.get('target_binding')!={'trace_index':7,'history_uid':8,'messages_sha':tools.TARGET_MESSAGES_SHA} or type(value.get('trace_rounds')) is not int or value['trace_rounds']<=7 or type(value.get('port')) is not int or value.get('port_pair',{}).get('api')!=value.get('port') or value.get('port_pair',{}).get('tcpstore')!=value.get('port')+1 or value.get('source_sha256')!=source_hashes() or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('worktree')!={'path':str(WT),'parent':str(WT.parent)} or any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated'))):raise RuntimeError('R052 dry-run receipt identity differs')
 return {'path':str(path),'sha256':sha(path)}
def require_startup_review(receipt):
 path=ROOT/'runs/dev_R052/reviews'/f'{RID}_startup_review_v5.json'
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R052 startup review absent or writable')
 value=json.loads(path.read_text());want={'schema':'ft_r052_startup_review/v5','rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'approved':True,'verdict':'PASS','source_sha256':source_hashes(),'dry_run_receipt':receipt['path'],'dry_run_receipt_sha256':receipt['sha256']}
 if any(value.get(k)!=v for k,v in want.items()):raise RuntimeError('R052 startup review binding differs')
 return {'path':str(path),'sha256':sha(path)}

def run_owned_body(d,batch,*,replay=None):
 tools=replay or replay_module();owner=d.take_d07_gpu_lock(RID,batch);run=None;proc=None;result=None
 try:
  d.require_gpu_idle();run=ROUNDS/RID;run.mkdir(parents=True)
  trace=tools.bind_trace(run);client=tools.client_module(WT)
  port,pair=tools.private_port_pair();d.write_new(run/'port_pair.json',pair);proc=tools.start_service(d,run,WT,port)
  target=tools.replay_to_target(port,run,trace,client)
  result=execute_followup(target,lambda messages:tools.followup(client,port,messages,target))
  d.write_new(run/'followup_raw.json',result['actual_response'])
  result.update(schema='ft_r052_raw_measurement/v5',round_id=RID,batch=batch,candidate_commit=CANDIDATE,
                verdict='pending_review',proposed_verdict='measured',target=target)
 except BaseException as error:
  proc=getattr(error,'owned_process',proc)
  if run is not None:d.write_new(run/'failed_harness.json',{'rid':RID,'batch':batch,'owner':owner,'error':repr(error)})
  raise
 finally:
  failed=False;cleanup_error=None
  if proc is not None:
   try:d.load_owned_lifecycle().stop_owned_process(proc)
   except BaseException as error:failed=True;cleanup_error=repr(error)
  if failed or (proc is not None and d.load_owned_lifecycle().owned_group_alive(proc.pid)):
   if run is not None:d.write_new(run/'owned_cleanup.json',{'rid':RID,'batch':batch,'owner':owner,'lock_released':False,'error':cleanup_error})
   raise RuntimeError('R052 owned cleanup failed; preserve GPU lock')
  d.release_d07_gpu_lock(owner)
  if run is not None:d.write_new(run/'owned_cleanup.json',{'rid':RID,'batch':batch,'owner':owner,'lock_released':True})
 try:
  result['d0']=tools.d0_evidence(run)
  follow=result['actual_response'];result['cache_evidence']=tools.confirm_cache_evidence(target,follow,result['d0'])
  result.update(classify(target,follow))
  d.write_new(run/'result.json',result)
 except BaseException as error:
  d.write_new(run/'failed_harness.json',{'rid':RID,'batch':batch,'error':repr(error),'service_cleanup_complete':True})
  raise
 return result

def child_argv(batch,receipt):return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]
def dispatch(*,owned_child=False,batch=None,receipt=None,body=None):
 d=load_d07()
 if not owned_child:
  dry_receipt=require_dry_run_receipt();review=require_startup_review(dry_receipt)
  r041=d.require_r041_kept(ROOT);t20=d.require_t20_failed_harness()
  d.require_closed_round('E2-R045','measured');d.checked_worktree(WT)
  if (ROUNDS/RID).exists():raise RuntimeError('R052 round already exists')
  if d.LOCK.exists() or d.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists before batch reservation')
  owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r052_atomic')
  batch=helper.next_batch(ROUNDS);path=ROOT/'runs/dev_R052'/f'launch_{RID}_batch{batch}.json';path.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,path)
  value={'schema':'ft_r052_owned_launch/v5','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'controller':d.process_birth(),'dry_run_receipt':dry_receipt,'startup_review':review,'prerequisites':{'r041':str(r041),'t20':str(t20)}}
  receipt=owned.reserve_process(helper,batch,RID,argv,path,value);birth=owned.process_identity(receipt['batch_pid'])
  if birth is None or birth.get('pid')!=receipt['batch_pid'] or type(birth.get('start_ticks')) is not int:raise RuntimeError('R052 child birth unavailable')
  return d.publish_child_binding(path,receipt,{'pid':birth['pid'],'start_ticks':birth['start_ticks'],'execution_id':f"{birth['pid']}:{birth['start_ticks']}"},lifecycle=owned)
 if batch is None or receipt is None:raise RuntimeError('R052 child requires receipt')
 d.require_child_receipt(receipt,batch,WT,ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt),schema='ft_r052_owned_launch/v5')
 dry_receipt=require_dry_run_receipt();require_startup_review(dry_receipt)
 d.require_r041_kept(ROOT);d.require_t20_failed_harness();d.require_closed_round('E2-R045','measured');d.checked_worktree(WT)
 return body() if body is not None else run_owned_body(d,batch)
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args(argv)
 if a.dry_run:
  if a.run or a.owned_child or a.batch is not None or a.launch_receipt is not None:raise RuntimeError('--dry-run cannot mix run, child, batch, or receipt')
  print(json.dumps(dry_run(),ensure_ascii=False,sort_keys=True));return 0
 if not a.run:
  if a.owned_child or a.batch is not None or a.launch_receipt is not None:raise RuntimeError('owned child arguments require --run')
  print(json.dumps({'rid':RID,'cpu_only':True,'candidate_commit':CANDIDATE}));return 0
 if sys.platform!='linux':p.error('--run requires the Linux GPU host')
 if a.owned_child and (a.batch is None or a.batch<1 or a.launch_receipt is None):p.error('owned child requires positive batch and receipt')
 if not a.owned_child and (a.batch is not None or a.launch_receipt is not None):p.error('controller cannot consume child batch arguments')
 print(json.dumps(dispatch(owned_child=a.owned_child,batch=a.batch,receipt=a.launch_receipt),ensure_ascii=False,sort_keys=True));return 0
if __name__=='__main__':main()
