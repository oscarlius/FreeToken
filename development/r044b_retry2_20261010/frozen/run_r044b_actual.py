#!/usr/bin/env python3
"""R044b controller for the retained six-service R044 implementation."""
import argparse, ast, hashlib, importlib.util, json, os, shutil, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path

ROOT=Path('/data2/FreeToken'); PACKET=ROOT/'development/r044b_20261010'; OLD=ROOT/'development/r044_capture_path_retry2_20261010'
RETRY=Path('/data2/_shared/runs/ft_rounds/E2-R044-night-20261010-retry2/ordinary/B1/serve.log'); R047=Path('/data2/FreeToken/runs/dev_R047_anchor_diag/E2-R047-ANCHOR-DIAG-night-20261010/serve.log')
READER=OLD/'d04_original/serve_args_diff.py'; LEAF=Path('/data2/_shared/experiment_harness/evidence.py'); RID='E2-R044b-20261010'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
GENERATION_PHASE_LIMIT_S=1500
TOTAL_WALL_LIMIT_S=5400
RETAINED_REPLAY_TIMEOUT_S=1800
CLEANUP_RESERVE_S=150
LEGACY_STARTUP_BOUND_S=905
TELEMETRY_CLEANUP_RESERVE_S=5
NVIDIA_SMI=Path('/usr/bin/nvidia-smi')
VMSTAT=Path('/usr/bin/vmstat')
PROC_DISKSTATS=Path('/proc/diskstats')
TELEMETRY_INTERVAL_S=1

class OwnedTelemetry:
 """Task-owned raw monitor sidecars; they never make inference requests."""
 def __init__(self,run,d,*,clock=time.monotonic,absolute_end=None,sleeper=time.sleep,wall_clock=datetime.now,popen=subprocess.Popen):
  self.run=run;self.d=d;self.clock=clock;self.absolute_end=absolute_end;self.sleeper=sleeper;self.wall_clock=wall_clock;self.popen=popen;self.stop_event=threading.Event();self.samples=[];self.processes=[];self.thread=None;self.stopped=False
  self.raw=run/'telemetry';self.diskstats=self.raw/'proc_diskstats.jsonl';self.bindings=self.raw/'service_bindings.jsonl';self.manifest=self.raw/'telemetry_manifest.json';self.terminal=self.raw/'telemetry_terminal.json'
 def _stamp(self):return self.wall_clock().astimezone().isoformat()
 def _identity(self,process):
  identity=self.d.load_owned_lifecycle().process_identity(process.pid)
  required={'pid','start_ticks','pgid'}
  if not required<=set(identity) or identity['pid']!=process.pid:raise RuntimeError('telemetry sidecar birth identity differs')
  return identity
 def start(self):
  if not NVIDIA_SMI.is_file() or not VMSTAT.is_file() or not PROC_DISKSTATS.is_file():raise RuntimeError('telemetry preflight lacks required nvidia-smi/vmstat/proc diskstats source')
  if shutil.which('iostat') is not None:raise RuntimeError('R044b telemetry contract requires reviewed iostat fallback declaration, not an unpinned tool')
  self.raw.mkdir(parents=True);self._disk_handle=self.diskstats.open('x',encoding='utf-8');self._bindings_handle=self.bindings.open('x',encoding='utf-8')
  specs=(
   ('nvidia_dmon_raw.txt',[str(NVIDIA_SMI),'dmon','-s','umt','-d','1','-i','0','-o','DT']),
   ('vmstat_raw.txt',[str(VMSTAT),'-n','-t','1']),
  )
  try:
   for name,argv in specs:
    handle=(self.raw/name).open('x',encoding='utf-8')
    process=self.popen(argv,stdout=handle,stderr=subprocess.STDOUT,text=True,start_new_session=True)
    self.processes.append({'name':name,'argv':argv,'handle':handle,'process':process,'birth':self._identity(process)})
   self.thread=threading.Thread(target=self._disk_loop,name='r044b-proc-diskstats',daemon=False);self.thread.start()
   self._write_manifest('started')
  except BaseException:
   self.stop();raise
 def bind_service(self,arm,process):
  row={'event':'service_bound','at':self._stamp(),'arm':str(arm),'service_birth':self._identity(process)};self.samples.append(row);self._bindings_handle.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n');self._bindings_handle.flush()
 def _disk_loop(self):
  next_tick=self.clock()
  while not self.stop_event.is_set():
   self._disk_handle.write(json.dumps({'at':self._stamp(),'source':'/proc/diskstats','raw':PROC_DISKSTATS.read_text(encoding='utf-8')},ensure_ascii=False,separators=(',',':'))+'\n');self._disk_handle.flush()
   next_tick+=TELEMETRY_INTERVAL_S;delay=max(0,next_tick-self.clock())
   if self.stop_event.wait(delay):break
 def _write_manifest(self,state):
  if self.manifest.exists():return
  value={'schema':'ft_r044b_owned_telemetry/v1','rid':RID,'state':state,'started_at':self._stamp(),'interval_s':TELEMETRY_INTERVAL_S,'streams':{'nvidia_dmon':{'argv':[str(NVIDIA_SMI),'dmon','-s','umt','-d','1','-i','0','-o','DT'],'raw':'nvidia_dmon_raw.txt','fields':'dmon u,m,t: utilization, FB memory, PCIe RX/TX'},'vmstat':{'argv':[str(VMSTAT),'-n','-t','1'],'raw':'vmstat_raw.txt','fields':'standard CPU/memory/swap/IO/queue table'},'disk':{'iostat':'unavailable (/usr/bin/iostat absent)','fallback':'proc_diskstats_fallback','raw':'proc_diskstats.jsonl'}},'sidecars':[{'name':row['name'],'argv':row['argv'],'birth':row['birth']} for row in self.processes]}
  self.dummy_write(value)
 def dummy_write(self,value):
  with self.manifest.open('x',encoding='utf-8') as handle:json.dump(value,handle,indent=2);handle.write('\n')
 def _remaining_stop(self):
  if self.absolute_end is None:return 2
  remaining=self.absolute_end-self.clock()
  if remaining<=0:raise DeadlineExpired('R044b total wall deadline exceeded during telemetry cleanup')
  return min(2,remaining)
 def stop(self):
  if self.stopped:return
  self.stop_event.set()
  if self.thread is not None:self.thread.join(timeout=self._remaining_stop())
  if self.thread is not None and self.thread.is_alive():raise RuntimeError('telemetry diskstats thread remains after stop')
  failures=[]
  for row in self.processes:
   process=row['process']
   if process.poll() is None:
    process.terminate()
    try:process.wait(timeout=self._remaining_stop())
    except subprocess.TimeoutExpired:
     process.kill();process.wait(timeout=self._remaining_stop())
   if process.poll() is None:failures.append(row['name'])
   row['handle'].close()
  self._disk_handle.close();self._bindings_handle.close()
  if failures:raise RuntimeError(f'telemetry sidecars remain: {failures}')
  for path in [self.diskstats,self.bindings,*[self.raw/row['name'] for row in self.processes]]:path.chmod(0o444)
  if not self.manifest.exists():self._write_manifest('stopped')
  with self.terminal.open('x',encoding='utf-8') as handle:json.dump({'schema':'ft_r044b_owned_telemetry_terminal/v1','rid':RID,'stopped_at':self._stamp(),'sidecars_stopped':True,'diskstats_thread_alive':False},handle,indent=2);handle.write('\n')
  self.manifest.chmod(0o444)
  self.terminal.chmod(0o444)
  self.stopped=True

class DeadlineExpired(RuntimeError):
 pass

def remaining_deadline(clock,work_end,phase_end,stage):
 total=work_end-clock()
 if total<=0:raise DeadlineExpired(f'R044b work deadline exceeded during {stage}; cleanup reserve is protected')
 if phase_end is not None:
  phase=phase_end-clock()
  if phase<=0:raise DeadlineExpired(f'R044b generation phase deadline exceeded during {stage}')
  return min(total,phase)
 return total

def remaining_total(clock,absolute_end,stage):
 total=absolute_end-clock()
 if total<0:raise DeadlineExpired(f'R044b total wall deadline exceeded during {stage}')
 return total

def require_startup_budget(clock,work_end):
 required=LEGACY_STARTUP_BOUND_S+CLEANUP_RESERVE_S
 if work_end-clock()<required:raise DeadlineExpired(f'R044b startup budget exhausted; need {required}s for frozen health and owned cleanup')

def stop_owned_with_reserve(d,process,*,clock,absolute_end):
 remaining=remaining_total(clock,absolute_end,'before owned cleanup')
 if remaining<CLEANUP_RESERVE_S:raise RuntimeError('R044b cleanup reserve exhausted; preserve GPU lock for recovery')
 available=max(0,remaining-TELEMETRY_CLEANUP_RESERVE_S)
 kill_timeout=min(30,available)
 term_timeout=min(120,max(0,available-kill_timeout))
 d.load_owned_lifecycle().stop_owned_process(process,term_timeout=term_timeout,kill_timeout=kill_timeout)
 remaining_total(clock,absolute_end,'after owned cleanup')
 return absolute_end-clock()

def invoke_replay_with_deadline(legacy,wt,port,phase,trace,out,log,d,*,clock,work_end,phase_end):
 """Retain the frozen helper and cap its real client subprocess at both deadlines."""
 original_run=legacy.subprocess.run
 def capped_run(*args,**kwargs):
  remaining=remaining_deadline(clock,work_end,phase_end,f'{phase} replay subprocess')
  existing=kwargs.get('timeout',RETAINED_REPLAY_TIMEOUT_S)
  kwargs['timeout']=min(RETAINED_REPLAY_TIMEOUT_S if existing is None else existing,remaining)
  return original_run(*args,**kwargs)
 legacy.subprocess.run=capped_run
 try:
  value=legacy.invoke_replay(wt,port,phase,trace,out,log,d)
 except legacy.subprocess.TimeoutExpired as exc:
  raise DeadlineExpired(f'R044b generation phase client subprocess timed out during {phase}') from exc
 finally:
  legacy.subprocess.run=original_run
 remaining_deadline(clock,work_end,phase_end,f'{phase} replay completion')
 return value

def load_reader():
 s=importlib.util.spec_from_file_location('r044b_reader',READER);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def load_legacy():
 source=OLD/'r044_prepare_v6.py';dependency=OLD/'queue_authorization.py';assert source.is_file() and dependency.is_file() and not source.is_symlink() and not dependency.is_symlink()
 parent=str(OLD);sys.path.insert(0,parent)
 try:
  s=importlib.util.spec_from_file_location('r044b_retained',source);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
 finally:
  assert sys.path[0]==parent;del sys.path[0]
def filedry():
 r=load_reader();a,b=r.parse(RETRY),r.parse(R047);assert a['max_extend_tokens']==b['max_extend_tokens']=='4096'
 for p in (RETRY,R047,READER,LEAF,OLD/'r044_prepare_v6.py',OLD/'queue_authorization.py'):assert p.is_file() and not p.is_symlink()
 return {'schema':'ft_r044b_actual_filedry/v2','rid':RID,'bindings':{str(p):sha(p) for p in (Path(__file__).resolve(),RETRY,R047,READER,LEAF,OLD/'r044_prepare_v6.py',OLD/'queue_authorization.py')},'alias':{'max_prefill_length':'max_extend_tokens','value':a['max_extend_tokens']},'capture_caps':{'physical':5824,'sampler_rows':4800,'bytes':8589934592,'chunked_non_delivery_receipts':19},'retained_protocol':{'services_exact':6,'replay_calls_exact':144,'per_service_replays_exact':24,'actual_serve_log_parser':'d04_original/serve_args_diff.py'},'negative_caps':{'total_wall_s':TOTAL_WALL_LIMIT_S,'generation_phase_s':GENERATION_PHASE_LIMIT_S,'retained_client_timeout_s':RETAINED_REPLAY_TIMEOUT_S,'cleanup_reserve_s':CLEANUP_RESERVE_S,'frozen_startup_bound_s':LEGACY_STARTUP_BOUND_S,'expiry_verdict':'failed_harness'},'old_retry2':'diagnostic only; formal bytes unchanged','side_effects':False}
def write_new(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def write_filedry_correction(value):
 """Keep prior file-dry bytes immutable and append the source-bound replacement."""
 target=PACKET/f"FILE_DRY_R044B_CORRECTION_{sha(Path(__file__).resolve())[:12]}.json"
 write_new(target,value)
 with (PACKET/'FILE_DRY_R044B_CORRECTIONS.jsonl').open('a',encoding='utf-8') as stream:
  stream.write(json.dumps({'schema':'ft_r044b_filedry_correction/v1','rid':RID,'receipt':str(target),'receipt_sha256':sha(target),'runner_sha256':sha(Path(__file__).resolve()),'preserved_prior':'FILE_DRY_R044B_CURRENT.json'},sort_keys=True)+'\n')
 return target
def child_argv(legacy,batch,receipt,wt,output_root):
 return [str(legacy.VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--worktree',str(wt),'--output-root',str(output_root)]
def serve_identity(legacy,arm,layer_major):
 """Keep the quoted ServerArgs suffix for strict comparison, compare its value to PID."""
 owned=json.loads((arm/'owned_process.json').read_text());parsed=legacy.load_source(legacy.ARGS_READER,'r044b_args_reader').parse(arm/'serve.log')
 required={'model_path','server_port','prefill_layer_major','max_prefill_length','max_extend_tokens','mamba_host_slots','enable_cache_report','special_token_ckpt','_unique_suffix'}
 if required-set(parsed):raise ValueError('actual serve.log lacks strict parsed arguments')
 if str(parsed['server_port'])!=str(owned['port']) or str(parsed['prefill_layer_major'])!=str(layer_major):raise ValueError('actual serve.log port/layer-major differs from declared service')
 try:suffix=ast.literal_eval(parsed['_unique_suffix'])
 except (SyntaxError,ValueError) as exc:raise ValueError('actual serve.log PID suffix is not a ServerArgs string literal') from exc
 if suffix!=f".pid={owned['pid']}":raise ValueError('actual serve.log PID suffix differs from owned process')
 normalized=dict(parsed);normalized['server_port']='<dynamic-port>'
 return {'parsed':parsed,'normalized':normalized,'serve_log_sha256':sha(arm/'serve.log'),'owned_process':owned}
def configure(legacy):
 legacy.RID=RID;legacy.REVIEW_DIR=ROOT/'runs/dev_T10/reviews'/RID;legacy.DEV_D16_CAPTURE_ROOT=ROOT/'runs/dev_D16'/RID
 legacy.child_argv=lambda batch,receipt,wt,output_root:child_argv(legacy,batch,receipt,wt,output_root)
 legacy.serve_identity=lambda arm,layer_major:serve_identity(legacy,arm,layer_major)
 assert tuple(legacy.MODES)==('ordinary','layer_major') and tuple(legacy.ARMS)==('B1','B2','B3')
 assert legacy.CAPTURE_REQUESTS==24 and legacy.CAPTURE_MAX_TOKENS==200
 return legacy
def validate_controller_receipt(receipt):
 child=receipt.get('child',{});required=('pid','start_ticks','execution_id')
 if receipt.get('schema')!='ft_t10_owned_launch/v3' or receipt.get('state')!='launched' or receipt.get('rid')!=RID:raise RuntimeError('R044b controller receipt identity differs')
 if set(child)!=set(required) or not isinstance(child['pid'],int) or not isinstance(child['start_ticks'],int) or child['execution_id']!=f"{child['pid']}:{child['start_ticks']}":raise RuntimeError('R044b controller child birth receipt differs')
 if not isinstance(receipt.get('argv_sha256'),str) or len(receipt['argv_sha256'])!=64:raise RuntimeError('R044b controller argv hash absent')
 if not isinstance(receipt.get('packet_sha256'),str) or len(receipt['packet_sha256'])!=64:raise RuntimeError('R044b controller admission hash absent')
 return {'controller_child':child,'batch':receipt['batch'],'argv_sha256':receipt['argv_sha256'],'admission_sha256':receipt['packet_sha256'],'retained_services_exact':6,'retained_replay_calls_exact':144}
def evaluate_raw_measurement(result):
 """Classify the first retained comparison mismatch without changing raw bytes."""
 if result.get('stopped_early',{}).get('first_failure') is not None:
  return {'verdict':'not_met','product_acceptance':False,'first_failure':result['stopped_early']['first_failure']}
 for mode,group in result.get('groups',{}).items():
  for kind,comparison in group.get('comparisons',{}).items():
   for row in comparison.get('rows',[]):
    if not row.get('same_fulltext') or not row.get('same_sampled_token_ids'):
     return {'verdict':'not_met','product_acceptance':False,'first_failure':{'mode':mode,'comparison':kind,'left_arm':row['left_arm'],'right_arm':row['right_arm'],'round':row['round'],'messages_sha':row['messages_sha'],'same_fulltext':row['same_fulltext'],'same_sampled_token_ids':row['same_sampled_token_ids']}}
 return {'verdict':'measured_pending_independent_review','product_acceptance':False,'first_failure':None}
def early_stability_rows(legacy,group):
 """Use the retained first-fork comparator before B3/layer-major are admitted."""
 rows=[]
 for kind,left_arm,right_arm,left_phase,right_phase in (('cold_cold','B1','B2','cold','cold'),('warm_warm','B1','B2','warm','warm'),('cold_warm','B1','B1','cold','warm'),('cold_warm','B2','B2','cold','warm')):
  for key,left in group[left_arm][left_phase].items():
   right=group[right_arm][right_phase][key]
   rows.append({'comparison':kind,'left_arm':left_arm,'right_arm':right_arm,'round':left.get('round'),'messages_sha':key,**legacy.first(left,right)})
 return rows
def execute_owned_child(legacy,wt,output_root,batch,launch_receipt,*,clock=time.monotonic,telemetry_factory=OwnedTelemetry):
 """Retained child lifecycle with an early B1/B2 gate and bounded work window."""
 if batch is None or launch_receipt is None:raise RuntimeError('T10 owned child requires controller receipt and reserved batch')
 started=clock();absolute_end=started+TOTAL_WALL_LIMIT_S;work_end=absolute_end-CLEANUP_RESERVE_S;d=legacy.load_d07()
 d.require_child_receipt(launch_receipt,batch,wt,output_root,rid=legacy.RID,expected_argv=legacy.child_argv(batch,launch_receipt,wt,output_root),schema='ft_t10_owned_launch/v3')
 legacy.require_output_root(output_root);t20=legacy.require_queue(d);admission=legacy.packet(wt);review=legacy.require_startup_review()
 if (output_root/legacy.RID).exists():raise RuntimeError('T10 E2-R044 exists; no overwrite')
 owner=d.take_d07_gpu_lock(legacy.RID,batch);run=None;process=None;telemetry=None;cleanup_failed=False
 try:
  run=output_root/legacy.RID;run.mkdir(parents=True)
  remaining_deadline(clock,work_end,None,'before GPU-idle check');idle=d.require_gpu_idle();remaining_deadline(clock,work_end,None,'after GPU-idle check')
  copies=legacy.copy_runtime_sources(run/'source');legacy.write_new(run/'preflight.json',{**admission,'batch':batch,'gpu_owner':owner,'gpu_memory_mib':idle,'t20_closure':str(t20),'t20_closure_sha256':legacy.sha(t20),'source_copies':copies,'negative_caps':{'total_wall_s':TOTAL_WALL_LIMIT_S,'generation_phase_s':GENERATION_PHASE_LIMIT_S,'retained_client_timeout_s':RETAINED_REPLAY_TIMEOUT_S,'cleanup_reserve_s':CLEANUP_RESERVE_S,'frozen_startup_bound_s':LEGACY_STARTUP_BOUND_S}})
  traces=legacy.bind_inputs(run);groups={}
  telemetry=telemetry_factory(run,d,clock=clock,absolute_end=absolute_end);telemetry.start()
  for mode,layer_major in legacy.MODES.items():
   group={};mode_dir=run/mode;mode_dir.mkdir();identities=[]
   for arm in legacy.ARMS:
    arm_dir=mode_dir/arm;arm_dir.mkdir();route=arm_dir/'route';route.mkdir();pair=legacy.port_pair();port=pair['api'];legacy.write_new(arm_dir/'port_pair.json',pair)
    require_startup_budget(clock,work_end)
    try:process=legacy.start_mode(d,arm_dir,wt,port,route,layer_major,run/'source'/legacy.CAPTURE_STARTUP.name)
    except BaseException as exc:
     process=getattr(exc,'owned_process',process);cleanup_failed=bool(getattr(exc,'owned_cleanup_failed',False));raise
    telemetry.bind_service(arm_dir,process)
    remaining_deadline(clock,work_end,None,'after service health');phase_end=min(clock()+GENERATION_PHASE_LIMIT_S,work_end)
    try:
     cold=invoke_replay_with_deadline(legacy,wt,port,'cold',traces['cold'],arm_dir/'cold.json',arm_dir/'cold.log',d,clock=clock,work_end=work_end,phase_end=phase_end);warm=invoke_replay_with_deadline(legacy,wt,port,'warm',traces['warm'],arm_dir/'warm.json',arm_dir/'warm.log',d,clock=clock,work_end=work_end,phase_end=phase_end)
    finally:
     try:cleanup_remaining=stop_owned_with_reserve(d,process,clock=clock,absolute_end=absolute_end);cleaned=process;process=None
     except BaseException:cleanup_failed=True;raise
     if d.load_owned_lifecycle().owned_group_alive(cleaned.pid):cleanup_failed=True;raise RuntimeError('T10 owned service remains; preserve GPU lock for recovery')
    remaining_total(clock,absolute_end,'after service cleanup')
    capture=legacy.capture_bindings(arm_dir);group[arm]={'cold':legacy.bind_capture(cold,capture,0),'warm':legacy.bind_capture(warm,capture,12),'sampler_capture':capture};identities.append(legacy.serve_identity(arm_dir,layer_major))
    if arm=='B2':
     strict=legacy.load_source(legacy.STRICT_READER,'r044b_strict_args').strict_args;strict(identities[0]['normalized'],identities[1]['normalized'],{})
     early=[{'mode':mode,**row} for row in early_stability_rows(legacy,group)];failure=next((row for row in early if not row['same_fulltext'] or not row['same_sampled_token_ids']),None)
     if failure is not None:
      result={'schema':'ft_t10_raw_measurement/v1','round_id':legacy.RID,'card':'T10','base':{'code_version':'E2-base.1@0aa23431','commit':legacy.CANDIDATE},'batch':batch,'verdict':'pending_review','proposed_verdict':'not_met','product_acceptance':False,'stopped_early':{'reason':'stable B1/B2 product mismatch before B3/layer_major','services_started':2,'replay_calls':48,'first_failure':failure},'groups':{mode:{'prefill_layer_major':layer_major,'arms':group,'serve_identities':identities,'early_stability_rows':early},'layer_major':{'not_started':'ordinary B1/B2 product mismatch'}},'raw_measurement_before_D04':True};legacy.write_new(run/'result.json',result);return result
   strict=legacy.load_source(legacy.STRICT_READER,'r044b_strict_args').strict_args
   for identity in identities[1:]:strict(identities[0]['normalized'],identity['normalized'],{})
   groups[mode]={'prefill_layer_major':layer_major,'arms':group,'serve_identities':identities,'comparisons':legacy.comparisons(group)}
  ordinary=dict(groups['ordinary']['serve_identities'][0]['normalized']);layer=dict(groups['layer_major']['serve_identities'][0]['normalized']);layer['prefill_layer_major']=ordinary['prefill_layer_major'];strict(ordinary,layer,{})
  result={'schema':'ft_t10_raw_measurement/v1','round_id':legacy.RID,'card':'T10','base':{'code_version':'E2-base.1@0aa23431','commit':legacy.CANDIDATE},'batch':batch,'verdict':'pending_review','proposed_verdict':'measured','groups':groups,'timing':'not a performance result','raw_measurement_before_D04':True};legacy.write_new(run/'result.json',result);return result
 except BaseException as e:
  if run is not None:legacy.write_new(run/'failed_harness.json',{'rid':legacy.RID,'batch':batch,'gpu_owner':owner,'error':repr(e),'raw_measurement_preserved':True})
  raise
 finally:
  if process is not None:
   try:
    cleanup_remaining=stop_owned_with_reserve(d,process,clock=clock,absolute_end=absolute_end);cleaned=process;process=None
    if d.load_owned_lifecycle().owned_group_alive(cleaned.pid):raise RuntimeError('T10 owned service remains')
   except BaseException:cleanup_failed=True
  if telemetry is not None:
   try:telemetry.stop()
   except BaseException:cleanup_failed=True
  if cleanup_failed:raise RuntimeError('T10 owned cleanup failed; preserve GPU lock for recovery')
  d.release_d07_gpu_lock(owner)
  if run is not None:legacy.write_new(run/'owned_cleanup.json',{'schema':'ft_t10_owned_cleanup/v1','rid':legacy.RID,'batch':batch,'gpu_owner':owner,'lock_released':True})
def run(*,owned_child=False,batch=None,launch_receipt=None,worktree=None,output_root=None,legacy_loader=load_legacy,clock=time.monotonic,telemetry_factory=None):
 if os.environ.get('R044B_ROOT_AUTHORIZED')!='1':raise RuntimeError('root must set R044B_ROOT_AUTHORIZED=1 for --run')
 dry=filedry();admission=json.loads((PACKET/'ROOT_ADMISSION_R044B.json').read_text());assert admission['bindings']==dry['bindings']
 legacy=configure(legacy_loader());kwargs={'owned_child':owned_child,'batch':batch,'launch_receipt':launch_receipt}
 if worktree is not None:kwargs['wt']=worktree
 if output_root is not None:kwargs['output_root']=output_root
 result=execute_owned_child(legacy,kwargs.get('wt',legacy.WT),kwargs.get('output_root',legacy.ROUNDS),batch,launch_receipt,clock=clock,telemetry_factory=OwnedTelemetry if telemetry_factory is None else telemetry_factory) if owned_child else legacy.execute(**kwargs)
 if not owned_child:return validate_controller_receipt(result)
 gate=evaluate_raw_measurement(result);result['r044b_product_gate']=gate
 run=Path(output_root if output_root is not None else legacy.ROUNDS)/RID
 write_new(run/'r044b_product_gate.json',{'schema':'ft_r044b_product_gate/v1','rid':RID,'raw_result_sha256':sha(run/'result.json'),**gate})
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--worktree',type=Path);p.add_argument('--output-root',type=Path);a=p.parse_args();assert a.file_dry_run!=a.run
 if a.file_dry_run:
  v=filedry();receipt=write_filedry_correction(v);print(json.dumps({**v,'receipt':str(receipt),'receipt_sha256':sha(receipt)},indent=2))
 else:
  if a.owned_child and (a.batch is None or a.launch_receipt is None):p.error('owned child requires batch and launch receipt')
  print(json.dumps(run(owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt,worktree=a.worktree,output_root=a.output_root),indent=2))
