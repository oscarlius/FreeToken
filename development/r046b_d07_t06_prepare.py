#!/usr/bin/env python3
"""E2-R046b same-configuration D07 OFF/ON and T06 at memory ratio 0.80."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, socket, subprocess, sys, time, shlex
from pathlib import Path
from types import SimpleNamespace

RID="E2-R046b"; CANDIDATE="effb9969706922ddad9e59b96377e46469ebe97f"
ROOT=Path("/data2/FreeToken"); WT=ROOT/"wt/e2base1-p1"; VENV=ROOT/"venv"
ROUNDS=Path("/data2/_shared/runs/ft_rounds"); D07_RUNS=ROOT/"runs/dev_D07"; SEED_ROOT=ROOT/"wt/e1r003"
MODEL="Qwen3.8-Flash-Next-NVFP4"; HERE=Path(__file__).resolve().parent
SEED_CLIENT=HERE/"r046_seed_agent_trace_v2.py"; D07_SOURCE=HERE/"d07_g3g4_prepare.py"
FILE_PREP_SOURCE=HERE/"d07_r046a_file_prepare_v1.py"
R055B_OBSERVER_SOURCE=HERE/'r055b_owned_launch.py'
PAUSE_HARNESS_SOURCE=HERE/'r055b_pause_harness_v2.py'
R055B_PIN=ROOT/'runs/plan_batches/closed_round_pins/E2-R055b-gate-D06.json'
R055A_V2_PIN=ROOT/'runs/plan_batches/closed_round_pins/E2-R055a-gate-D06_v2.json'
R055B_REVIEW=ROOT/'runs/dev_R055/reviews/E2-R055b-gate-D06_failed_independent_raw_review_v1.json'
R055B_REVIEW_SHA='eada9f216bfc91a90a82b891eb83358f7d6e4d3a0027ba5cc03216f90923e7f5'
MIN_FREE_BYTES=int(1.5*1024**3)
R055A_ROUND_SHA='0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3'
MEMORY_RATIO='0.80'
WINDOW=98304; COMPLETION_RESERVE=2048
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
R046A_ROUND_SHA='01c9dd48367878b9ec742de0c43608bebe2b897638e9bc6e428520b616cea356'
ROUND_WRITER=ROOT/'scripts/round_json_append.py'
ROUND_WRITER_SHA='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
SEEDS={"seed12k":"1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153",
       "seed_45k":"499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9",
       "seed_real":"8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3"}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def memory_plan(pin=R055B_PIN):
 """Use failed-round metadata and its small R review; do not reopen raw arms."""
 r056=require_r056()
 if pin.is_symlink() or not pin.is_file() or pin.stat().st_mode&0o222:raise RuntimeError('R055b sealed pin absent or writable')
 binding=json.loads(pin.read_text());round_path=ROUNDS/'E2-R055b-gate-D06'/'round.json';manifest=round_path.parent/'MANIFEST.sha256'
 for path in (round_path,manifest,R055B_REVIEW):
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R055b sealed metadata/review absent or writable')
 if (binding.get('rid')!='E2-R055b-gate-D06' or binding.get('candidate_commit')!=CANDIDATE or binding.get('verdict')!='failed_harness' or binding.get('round_sha256')!=sha(round_path) or binding.get('manifest_sha256')!=sha(manifest) or binding.get('review_sha256')!=R055B_REVIEW_SHA or sha(R055B_REVIEW)!=R055B_REVIEW_SHA or json.loads(round_path.read_text()).get('verdict')!='failed_harness'):raise RuntimeError('R055b sealed pin binding differs')
 review=json.loads(R055B_REVIEW.read_text());summary=review.get('cuda_memory_summary',{});birth=summary.get('service_birth',{});worker=summary.get('worker_birth',{});events=summary.get('events');observer_hash=hashlib.sha256(load_pause_observer().PAUSE_OBSERVER.encode()).hexdigest()
 retained=review.get('retained_R055a_metadata',{})
 if (review.get('round_id')!='E2-R055b-gate-D06' or review.get('candidate_commit')!=CANDIDATE or review.get('verdict')!='failed_harness' or retained.get('old_verdict_unchanged')!='failed_harness' or retained.get('partial_cold_verdict')!='PASS' or retained.get('independent_raw_review_sha256')!='10161a2fe801414c3aa611487ead1d8a64a2e7baf1853d90ad4bca7fa7a08aa4' or retained.get('history_check_returncode')!=0):raise RuntimeError('R055b review lacks retained six-cold evidence')
 if (summary.get('schema')!='ft_r055b_cuda_memory_summary/v1' or summary.get('device')!=0 or type(birth.get('pid')) is not int or type(birth.get('start_ticks')) is not int or type(worker.get('pid')) is not int or type(worker.get('start_ticks')) is not int or not isinstance(events,list) or not events):raise RuntimeError('R055b model/device identity differs')
 loaded=[];samples=[]
 for event in events:
  if not isinstance(event,dict) or event.get('service_birth')!=birth or event.get('worker_birth')!=worker or event.get('device')!=0 or 'error' in event or 'error' in str(event.get('event','')).lower():raise RuntimeError('R055b observer event binding differs')
  if event.get('event')=='model_loaded':loaded.append(event)
  if type(event.get('free_bytes')) is not int or type(event.get('total_bytes')) is not int or event['free_bytes']<0 or event['total_bytes']<=0 or event['free_bytes']>event['total_bytes']:raise RuntimeError('R055b observer memory sample incomplete')
  samples.append(event)
 if len(loaded)!=1:raise RuntimeError('R055b observer lacks load evidence')
 minimum,total=summary.get('min_free_bytes'),summary.get('total_bytes')
 if type(minimum) is not int or type(total) is not int or minimum<0 or total<=0 or minimum>total:raise RuntimeError('R055b pause memory record incomplete')
 if min(row['free_bytes'] for row in samples)!=minimum or any(row['total_bytes']!=total for row in samples):raise RuntimeError('R055b memory summary differs from events')
 r055a_round=ROUNDS/'E2-R055a-gate-D06'/'round.json'
 if r055a_round.is_symlink() or not r055a_round.is_file() or r055a_round.stat().st_mode&0o222 or sha(r055a_round)!=R055A_ROUND_SHA:raise RuntimeError('R055a sealed OOM metadata differs')
 r055a=json.loads(r055a_round.read_text());reasons=[row.get('reason','') for row in r055a.get('verdict_history',[]) if isinstance(row,dict)]
 if r055a.get('verdict')!='failed_harness' or not any('628 MiB request / 625.69 MiB free' in reason for reason in reasons):raise RuntimeError('R055a historical OOM allocation/free evidence differs')
 return {'schema':'ft_r046b_memory_plan/v2','authorization':'CODEX_HANDOFF section twelve','source_pin':str(pin),'source_pin_sha256':sha(pin),'round_json':str(round_path),'round_sha256':sha(round_path),'independent_review_sha256':R055B_REVIEW_SHA,'r055b_verdict':'failed_harness','model_birth':birth,'worker_birth':worker,'device':0,'observer_source_sha256':observer_hash,'minimum_free_bytes':minimum,'total_bytes':total,'required_free_bytes':MIN_FREE_BYTES,'baseline_memory_ratio':'0.88','memory_ratio':MEMORY_RATIO,'minimum_memory_ratio':'0.80','r055a_round_sha256':R055A_ROUND_SHA,'r056_measured':str(r056),'r056_round_sha256':sha(r056),'window':window_contract(),'estimated_route_overhead_bytes':None,'predicted_free_bytes':None,'prediction_not_gpu_proof':True,'calculation':'no GPU route-growth estimate; require same-window measured R056, loaded >=1.5GiB and actual request-before/after samples','route_snapshot_location':'CPU pinned'}

def window_contract():
 return {'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'completion_reserve_tokens':COMPLETION_RESERVE,'max_prompt_tokens':WINDOW-COMPLETION_RESERVE}
def require_r056(d=None):
 # Canonical measured+D04 is signed only after all eleven requests and raw review.
 return (d or load_d07()).require_closed_round('E2-R056','measured')
def apply_t06_memory_plan(d,plan):
 if plan.get('memory_ratio')!=MEMORY_RATIO:raise RuntimeError('R046b requires 0.80 for every D07/T06 arm')
 original=d.serve_argv
 def t06_argv(port):
  argv=list(original(port))
  for flag,value in (('--memory-ratio',MEMORY_RATIO),('--kv-reserve-tokens',str(WINDOW)),('--max-seq-len-override',str(WINDOW))):
   if flag in argv:argv[argv.index(flag)+1]=value
   else:argv.extend([flag,value])
  return argv
 d.serve_argv=t06_argv
def write_memory_diff(directory,plan):
 write_new(directory/'serve_args_diff.json',{'schema':'ft_r046b_serve_args_diff/v1','target_keys':{'memory_ratio':MEMORY_RATIO,'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW},'baseline_memory_ratio':plan['baseline_memory_ratio'],'all_d07_t06_arms':True,'scientific_arguments_unchanged':True,'trace_required':directory.name!='g3_off','pause_required':directory.name.startswith('G_'),'prediction_not_gpu_proof':plan['prediction_not_gpu_proof'],'startup_memory_basis':{key:plan[key] for key in ('independent_review_sha256','r055a_round_sha256','minimum_free_bytes','total_bytes','required_free_bytes','estimated_route_overhead_bytes','predicted_free_bytes','calculation')},'window':window_contract(),'r056_measured':plan.get('r056_measured')})
def require_t06_loaded_memory(directory,plan,process):
 """Read the model-process observer output; never create a second CUDA context."""
 path=directory/'model_process_cuda.jsonl';observer=directory/'r055b_pause_observer.py'
 if path.is_symlink() or not path.is_file():raise RuntimeError('T06 model-process memory observer missing; do not send requests')
 if observer.is_symlink() or not observer.is_file() or sha(observer)!=plan['observer_source_sha256']:raise RuntimeError('T06 observer source differs')
 rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
 loaded=[row for row in rows if isinstance(row,dict) and row.get('schema')=='ft_r055b_model_process_cuda/v1' and row.get('event')=='model_loaded' and row.get('device')==0]
 if len(loaded)!=1:raise RuntimeError('T06 model-process observer load sample differs')
 row=loaded[0];birth=row.get('service_birth',{});worker=row.get('worker_birth',{})
 owned=directory/'owned_process.json'
 if owned.is_symlink() or not owned.is_file():raise RuntimeError('T06 owned service birth missing')
 owner=json.loads(owned.read_text()).get('birth',{})
 stable_keys=('pid','start_ticks','execution_id','pgid','session')
 if (any(type(birth.get(key)) is not int or birth[key]<=0 for key in ('pid','start_ticks','pgid','session')) or birth.get('execution_id')!=f"{birth.get('pid')}:{birth.get('start_ticks')}" or any(birth.get(key)!=owner.get(key) for key in stable_keys) or birth.get('pid')!=getattr(process,'pid',None) or birth.get('pgid')!=birth['pid'] or birth.get('session')!=birth['pid']):raise RuntimeError('T06 owned service parent birth differs')
 if (any(type(worker.get(key)) is not int or worker[key]<=0 for key in ('pid','start_ticks','pgid','session')) or worker.get('execution_id')!=f"{worker.get('pid')}:{worker.get('start_ticks')}" or any(worker.get(key)!=birth.get(key) for key in ('pgid','session'))):raise RuntimeError('T06 GPU worker birth differs')
 if type(row.get('free_bytes')) is not int or type(row.get('total_bytes')) is not int or row['total_bytes']<=0 or row['free_bytes']<MIN_FREE_BYTES or row['free_bytes']>row['total_bytes'] or ('total_bytes' in plan and row['total_bytes']!=plan['total_bytes']):raise RuntimeError('T06 post-load free memory below 1.5GiB or total differs; do not send requests')
 return row
def invoke_t06_pause(port,directory,*,file_dry_run=False):
 path=directory/'pause_completed.json'
 if file_dry_run:return file_output(path,'formal repaired pause acknowledgement',file_dry_run=True)
 receipt=load_pause_harness().pause_request(port,1.0,5.0)
 write_new(path,receipt)
 if not isinstance(receipt,dict) or receipt.get('status')!='accepted' or not isinstance(receipt.get('request_id'),str) or not receipt['request_id']:
  error=RuntimeError('T06 pause_chain_failure: normal pause was not accepted; stop and ask user')
  error.pause_chain_failure=True
  raise error
 return receipt
def summarize_t06_memory(directory,plan,process,expected_requests,*,pause_required=True):
 loaded=require_t06_loaded_memory(directory,plan,process);path=directory/'model_process_cuda.jsonl'
 rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
 before={};after={}
 for row in rows:
  if (not isinstance(row,dict) or row.get('schema')!='ft_r055b_model_process_cuda/v1' or row.get('device')!=0 or row.get('service_birth')!=loaded['service_birth'] or row.get('worker_birth')!=loaded['worker_birth'] or 'error' in row or 'error' in str(row.get('event','')).lower() or type(row.get('time_ns')) is not int or type(row.get('free_bytes')) is not int or type(row.get('total_bytes')) is not int or row['total_bytes']!=loaded['total_bytes'] or not 0<=row['free_bytes']<=row['total_bytes']):raise RuntimeError('T06 model-process memory sample binding differs')
  kind=row.get('event')
  if kind in ('request_before','request_after'):
   target=before if kind=='request_before' else after;uid=row.get('uid')
   if not isinstance(uid,str) or not uid or uid in target:raise RuntimeError('T06 business memory UID boundary differs')
   target[uid]=row
 if len(before)<expected_requests or set(before)!=set(after) or any(before[uid]['time_ns']>=after[uid]['time_ns'] for uid in before):raise RuntimeError('T06 lacks every business request-before/after sample')
 request_id=None
 if pause_required:
  receipt=json.loads((directory/'pause_completed.json').read_text());request_id=receipt['request_id']
  if not any(row.get('event')=='pause_after' and row.get('request_id')==request_id for row in rows):raise RuntimeError('T06 accepted pause lacks model-process receipt binding')
 summary={'schema':'ft_r046b_model_memory_summary/v1','complete':True,'service_birth':loaded['service_birth'],'worker_birth':loaded['worker_birth'],'device':0,'min_free_bytes':min(row['free_bytes'] for row in rows),'total_bytes':loaded['total_bytes'],'events':rows,'business_requests':[{'uid':uid,'before_time_ns':before[uid]['time_ns'],'after_time_ns':after[uid]['time_ns']} for uid in before],'observer_source_sha256':plan['observer_source_sha256'],'model_memory_jsonl_sha256':sha(path),'normal_pause_request_id':request_id}
 write_new(directory/'cuda_memory_summary.json',summary)
 return summary
def write_new(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
def load_d07(source=D07_SOURCE):
 if source.is_symlink() or not source.is_file(): raise RuntimeError("T06 requires D07 lifecycle source")
 spec=importlib.util.spec_from_file_location("t06_d07_lifecycle",source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.CANDIDATE=CANDIDATE;m.WORKTREE=WT;m.RID=RID;apply_t06_memory_plan(m,{'memory_ratio':MEMORY_RATIO});return m
def load_file_prepare(source=FILE_PREP_SOURCE):
 if source.is_symlink() or not source.is_file(): raise RuntimeError("R046a file preparation source unavailable")
 spec=importlib.util.spec_from_file_location("r046a_file_prepare",source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def load_pause_observer():
 spec=importlib.util.spec_from_file_location('r046a_r055b_observer',R055B_OBSERVER_SOURCE);module=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(module)
 load_pause_harness().install(module)
 return module
def load_pause_harness():
 spec=importlib.util.spec_from_file_location('r046a_pause_harness_v2',PAUSE_HARNESS_SOURCE);module=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(module);return module
def prepare_service(d, directory, wt, port, route, *, start, pause_observer=False):
 directory.mkdir(parents=True,exist_ok=True)
 if route is not None:route_output(route)
 prepared=load_file_prepare().prepare_server_files(d,directory,wt,port,route)
 if pause_observer:
  if directory.name.startswith('G_') and (prepared['env'].get('FT_DEV_PAUSE_ENDPOINT')!='1' or prepared['env'].get('FT_DEV_ROUTE_TRACE')!=str(route)):raise RuntimeError('T06 requires route trace and pause switch throughout')
  if route is None and 'FT_DEV_ROUTE_TRACE' in prepared['env']:raise RuntimeError('D07 OFF must keep route trace disabled')
  source=load_pause_observer();startup=source._freeze_pause_observer(directory)
  prepared['env'].update(R055_PAUSE_OBSERVATIONS=str(directory/'pause_observations.jsonl'),R055B_MODEL_MEMORY=str(directory/'model_process_cuda.jsonl'))
  prepared['argv']=[str(VENV/'bin/python'),str(startup),*prepared['argv'][1:]]
  recorded=json.loads((directory/'ENV.json').read_text());recorded.update({key:prepared['env'][key] for key in ('R055_PAUSE_OBSERVATIONS','R055B_MODEL_MEMORY')})
  (directory/'ENV.json').write_text(json.dumps(recorded,sort_keys=True)+'\n');(directory/'ENV.txt').write_text(''.join(f'{key}={recorded[key]}\n' for key in sorted(recorded)))
  (directory/'SERVE_CMD.txt').write_text('env '+' '.join(f'{key}={shlex.quote(prepared["env"][key])}' for key in ('CUDA_VISIBLE_DEVICES','FT_DEV_PAUSE_ENDPOINT','FT_DEV_ROUTE_TRACE','PYTHONPATH','VIRTUAL_ENV','R055_PAUSE_OBSERVATIONS','R055B_MODEL_MEMORY') if key in prepared['env'])+' '+shlex.join(prepared['argv'])+'\n')
  prepared['observer_source']=str(directory/'r055b_pause_observer.py');prepared['observer_source_sha256']=sha(directory/'r055b_pause_observer.py')
 if not start:return prepared
 return load_file_prepare().start_prepared_server(d,directory,wt,port,prepared)
def seed_paths():
 paths={role:SEED_ROOT/f"{role}.txt" for role in SEEDS}
 for role,p in paths.items():
  if p.is_symlink() or not p.is_file() or sha(p)!=SEEDS[role]: raise RuntimeError(f"T06 seed raw bytes differ: {role}")
 return paths
def packet(wt=WT):
 r056=require_r056()
 d=load_d07(); candidate=d.checked_worktree(wt); tools=d.verify_d07_tools(wt)
 if SEED_CLIENT.is_symlink() or not SEED_CLIENT.is_file(): raise RuntimeError("T06 seed-aware candidate client unavailable")
 return {"schema":"ft_r046b_d07_t06_prepare/v1","rid":RID,"candidate_commit":CANDIDATE,"candidate":candidate,"candidate_tools":tools,"historical_r046":require_historical_r046(),"r056_measured":str(r056),"r056_round_sha256":sha(r056),"window":window_contract(),"memory_ratio":MEMORY_RATIO,
  "model_config_source":model_config_binding(),
  "d07_lifecycle_source":str(D07_SOURCE),"d07_lifecycle_source_sha256":sha(D07_SOURCE),"seed_client":str(SEED_CLIENT),"seed_client_sha256":sha(SEED_CLIENT),
  "seeds":[{"role":r,"path":str(p),"raw_sha256":SEEDS[r]} for r,p in seed_paths().items()],"fixture_port":d.dynamic_fixture_port(),"cuda_visible_devices_cpu_guard":"",
  "run_requires":["R056 complete eleven-request measured+D04 and independent raw review at 98304/.88","explicit --run","Linux host","R055a/R055b failed_harness sealed metadata; R055 gate ended by section ten","R055a-gate-D06 failed_harness with independently PASS retained six cold arms","R050-gate-D15 kept","R041 D04 kept","R040 and R046 failed_harness preserved","new 0.80 G3-off/G3-on same-input comparison and G4 before T06 arms","T06 route trace and pause switch remain enabled throughout","T06 repaired normal pause accepted; complete cancel/recovery belongs to R045","R startup review","foreign GPU lock deny","atomic owned GPU lock","GPU idle gate"],
  "service_shape":"six independent serial services: g3_off, g3_on, G_seed12k, G_seed_45k, G_seed_real, G_two","arms":[{"role":r,"directory":f"G_{r}","kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":h} for r,h in SEEDS.items()]+[{"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256}],"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"],"verdict":"measured","timing":"trace-mode timing excluded from performance claims"}
def file_output(path,purpose,*,file_dry_run=False):
 """The formal producer owns this path; dry-run writes its exact path as a probe."""
 if not file_dry_run:return path
 if path.exists():
  with path.open("a",encoding="utf-8") as f: json.dump({"schema":"ft_r046b_cpu_file_probe/v1","kind":"CPU_FILE_PROBE","not_measurement":True,"purpose":purpose},f,sort_keys=True);f.write("\n")
  return {"path":str(path),"sha256":sha(path),"purpose":purpose}
 return _probe(path,purpose)
def route_output(route,*,file_dry_run=False):
 route.mkdir(parents=True,exist_ok=True)
 if file_dry_run:_probe(route/"CPU_FILE_PROBE.json","formal route output directory")
 return route
def service_lifecycle_outputs(directory,*,file_dry_run=False):
 if file_dry_run:
  for name,purpose in (("owned_process.json","formal owned-process record"),("health.json","formal health record"),("serve_args.txt","formal parsed-arguments record")):file_output(directory/name,purpose,file_dry_run=True)
def validate_seed_completion(binding,role=None):
 if binding.get('schema')!='ft_t06_seed_trace_binding/v2' or binding.get('window')!=WINDOW or binding.get('completion_reserve_tokens')!=COMPLETION_RESERVE or binding.get('max_prompt_tokens')!=WINDOW-COMPLETION_RESERVE or binding.get('max_tokens')!=2048:raise RuntimeError('T06 new-window seed completion identity differs')
 if role is not None and binding.get('seed_raw_sha256')!=SEEDS[role]:raise RuntimeError('T06 original seed SHA differs')
 completed=binding.get('completed_k');hit=binding.get('window_hit')
 if type(completed) is not int or not 1<=completed<=12:raise RuntimeError('T06 completed_k differs')
 if hit is None:
  if completed!=12 or binding.get('window_hit_count')!=0:raise RuntimeError('T06 incomplete trace has no natural window hit')
 else:
  if not isinstance(hit,dict) or hit.get('request_k')!=completed+1 or completed>=12 or hit.get('actual_prompt_tokens',0)<=WINDOW-COMPLETION_RESERVE or binding.get('window_hit_count')!=1 or not hit.get('input_binding',{}).get('actual_input_ids_sha256'):raise RuntimeError('T06 natural window hit differs')
 return completed
def invoke_seed(wt,port,role,seed,out,log,*,file_dry_run=False):
 if file_dry_run:
  file_output(log,"formal seed client log",file_dry_run=True);file_output(out,"formal seed trace",file_dry_run=True);file_output(out.with_suffix(".seed_binding.json"),"formal seed binding",file_dry_run=True);return
 cmd=[str(VENV/"bin/python"),str(SEED_CLIENT),"--client",str(wt/"scripts/agent_trace.py"),"--seed-file",str(seed),"--seed-sha256",SEEDS[role],"--worktree",str(wt),"--tokenizer-path",str(MODEL_PATH),"--out",str(out),"--rounds","12","--max-tokens","2048","--base-url",f"http://127.0.0.1:{port}/v1","--model",MODEL]
 client_env=load_d07().clean_environment(wt);client_env['CUDA_VISIBLE_DEVICES']=''
 with log.open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=client_env,stdout=f,stderr=subprocess.STDOUT,check=True)
 binding=out.with_suffix(".seed_binding.json")
 if not out.is_file() or not binding.is_file(): raise RuntimeError(f"T06 {role} lacks trace/actual-wire binding")
 b=json.loads(binding.read_text());validate_seed_completion(b,role)
 if not b.get("actual_wire_first_content_sha256"): raise RuntimeError(f"T06 {role} seed binding incomplete")
def invoke_two(wt,port,out,log,*,file_dry_run=False):
 if file_dry_run:
  file_output(log,"formal two-decode client log",file_dry_run=True);file_output(out,"formal two-decode output",file_dry_run=True);return
 cmd=[str(VENV/"bin/python"),str(wt/"scripts/multisession_probe.py"),"two-decode","--base-url",f"http://127.0.0.1:{port}/v1","--model",MODEL,"--ctx","8000","--max-tokens","256","--same-prompt","0","--reps","1","--out",str(out)]
 with log.open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=load_d07().clean_environment(wt),stdout=f,stderr=subprocess.STDOUT,check=True)
 if json.loads(out.read_text()).get("same_prompt") is not False: raise RuntimeError("T06 two-decode is not different-content")
def invoke_analysis(wt,g,summary,*,trace=None,two=None,file_dry_run=False):
 if file_dry_run:
  file_output(g/"route_analyze.log","formal analyzer log",file_dry_run=True);file_output(summary,"formal analyzer output",file_dry_run=True);return
 cmd=[str(VENV/"bin/python"),str(wt/"scripts/route_analyze.py"),str(g/"route")]
 if trace is not None: cmd += ["--traces",str(trace)]
 if two is not None: cmd += ["--two-decode",str(two)]
 cmd += ["--serve-log",str(g/"serve.log"),"--out",str(summary)]
 with (g/"route_analyze.log").open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=load_d07().clean_environment(wt),stdout=f,stderr=subprocess.STDOUT,check=True)
 d=json.loads(summary.read_text())
 if trace is not None:
  binding=json.loads(Path(trace).with_suffix(".seed_binding.json").read_text());completed=validate_seed_completion(binding)
  completions=d.get("completions",{})
  if (d.get("analysis_scope")!="trace_bound_business_requests" or not d.get("suffix_tokens")
      or not isinstance(d.get("business_uids"),list) or len(d["business_uids"])!=completed
      or d.get("completion_count")!=completed or len(completions)!=completed
      or d.get("missing_business_routes") or any(row.get("max_tokens")!=2048 for row in completions.values())):
   raise RuntimeError("T06 seed analysis lacks completed_k UID-bound 2048-token business traces")
 else:
  pairs=d.get("two_decode_pairs");pending=d.get("R_B_pending")
  if (d.get("analysis_scope")!="all_prefill_requests" or not isinstance(d.get("raw_suffix_tokens"),dict) or not d["raw_suffix_tokens"]
      or not isinstance(pairs,list) or not pairs or any(not isinstance(row.get("uids"),list) or len(row["uids"])!=2 for row in pairs)
      or type(pending) is not bool or not isinstance(d.get("two_decode_pair_steps"),dict)):
   raise RuntimeError("T06 two-decode analysis lacks pair/route evidence")
  if pending:
   if d.get("R_B") or not d.get("R_B_nullreason"): raise RuntimeError("T06 pending R_B must retain its real null reason")
  elif not d.get("R_B") or not isinstance(d.get("decode_B2_steps"),int) or d["decode_B2_steps"]<=0:
   raise RuntimeError("T06 measured R_B lacks overlapping decode routes")
def stop_g3g4_service(d, process):
 if process is None:return
 try:d.load_owned_lifecycle().stop_owned_process(process)
 except BaseException as error:
  error.owned_process=process
  error.owned_cleanup_failed=True
  raise

def run_g3g4(d, wt, run, plan, *, file_dry_run=False):
 apply_t06_memory_plan(d,plan)
 history=require_historical_r046()
 root=run/"g3g4";root.mkdir();off=root/"g3_off";on=root/"g3_on";cold_id="E2-R046-cold"
 write_new(root/'historical_r046.json',history)
 for directory,route,requests in ((off,None,1),(on,on/"route",3)):
  process=None;port=d.dynamic_fixture_port()
  if file_dry_run:
   prepare_service(d,directory,wt,port,route,start=False,pause_observer=True);write_memory_diff(directory,plan)
   file_output(directory/"serve.log","formal D07 service log",file_dry_run=True);service_lifecycle_outputs(directory,file_dry_run=True)
   for name,purpose in (("model_process_cuda.jsonl","formal D07 model-process observer"),("pause_observations.jsonl","formal D07 observer"),("cuda_memory_summary.json","formal D07 complete model-memory summary"),("cold.json","formal D07 same-configuration cold output")):
    file_output(directory/name,purpose,file_dry_run=True)
   if route is not None:
    route_output(route,file_dry_run=True);file_output(directory/"trace.json","formal G4 business trace",file_dry_run=True)
   continue
  try:
   process=prepare_service(d,directory,wt,port,route,start=True,pause_observer=True);write_memory_diff(directory,plan)
   require_t06_loaded_memory(directory,plan,process)
   d.invoke_cold_eq(wt,port,cold_id,directory/"cold.json")
   if route is not None:d.invoke_agent_trace(wt,port,directory/"trace.json")
  except BaseException as error:
   process=getattr(error,'owned_process',process);error.owned_process=process;raise
  finally:
   active=sys.exc_info()[1]
   if not getattr(active,'owned_cleanup_failed',False):stop_g3g4_service(d,process)
  summarize_t06_memory(directory,plan,process,requests,pause_required=False)
 summary=root/"route_summary.json"
 if file_dry_run:
  file_output(summary,"formal D07 analyzer output",file_dry_run=True)
  return {"schema":"ft_r046b_g3g4_cpu_file_probe/v1","directory":"g3g4","historical_r046":history,"off_rerun":True,"memory_ratio":MEMORY_RATIO,"not_measurement":True}
 serve=on/"serve.log"
 if "CUDA graph disabled for development route trace" not in serve.read_text(encoding="utf-8",errors="replace"):raise RuntimeError("R046b G3/G4 lacks CUDA-graph-disabled marker")
 d.invoke_analyzer(wt,on/"route",on/"trace.json",serve,summary);doc=json.loads(summary.read_text())
 return {"schema":"ft_r046b_g3g4_raw/v1","directory":"g3g4","historical_r046":history,"off_rerun":True,"memory_ratio":MEMORY_RATIO,"g3":d.g3_compare(off/"cold.json",on/"cold.json"),"g4":{"route_summary":"g3g4/route_summary.json","route_summary_sha256":sha(summary),"business_uids":len(doc.get("business_uids",[])),"suffix_tokens":len(doc.get("suffix_tokens",[]))},"cuda_memory_summaries":{"off":"g3g4/g3_off/cuda_memory_summary.json","on":"g3g4/g3_on/cuda_memory_summary.json"},"cuda_graph_disabled_marker":True,"timing":"excluded from performance claims"}

def require_historical_r046():
 """Record sealed predecessor metadata; its 0.88 OFF payload is never reopened."""
 directory=ROUNDS/'E2-R046';round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256'
 for path in (round_json,manifest):
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('R046 historical metadata must be sealed')
 value=json.loads(round_json.read_text())
 if value.get('round_id')!='E2-R046' or value.get('verdict')!='failed_harness':raise RuntimeError('R046 historical verdict differs')
 old_off_path='g3g4/g3_off/cold.json';old_off_sha='0ccee4b9e5a0917b5284a334acc3f0ca3bd5b871d287f674eca907b7f1f47d6d'
 entries=[line.split(None,1) for line in manifest.read_text().splitlines() if line.strip()]
 if any(len(entry)!=2 for entry in entries):raise RuntimeError('R046 historical manifest format differs')
 matches=[digest for digest,path in entries if path.removeprefix('./')==old_off_path]
 if matches!=[old_off_sha]:raise RuntimeError('R046 historical OFF manifest registration differs')
 return {'round':'E2-R046','round_json':str(round_json),'round_sha256':sha(round_json),'manifest':str(manifest),'manifest_sha256':sha(manifest),'old_off_metadata_path':old_off_path,'old_off_declared_sha256':old_off_sha,'old_memory_ratio':'0.88','used_for_comparison':False,'off_rerun':True,'comparison_memory_ratio':MEMORY_RATIO,'authorization':'CODEX_HANDOFF section eleven, 10-07 09:55'}


def manifest(run,g_dirs,g3g4,owner):
 files={};arms=[]
 for arm in ('g3_off','g3_on'):
  directory=run/'g3g4'/arm
  for name in ('cold.json','model_process_cuda.jsonl','cuda_memory_summary.json','serve_args_diff.json','serve.log'):
   path=directory/name;files[f'{arm}_{name}']={'path':path.relative_to(run).as_posix(),'sha256':sha(path)}
 for role,digest in SEEDS.items():
  g=g_dirs[role];trace=g/f"trace_{role}.json";binding=trace.with_suffix(".seed_binding.json");summary=run/f"route_summary_{role}.json"
  names={"route":g/"route","serve_log":g/"serve.log","trace":trace,"seed_binding":binding,"route_summary":summary,"model_memory":g/"model_process_cuda.jsonl","memory_summary":g/"cuda_memory_summary.json","pause_receipt":g/"pause_completed.json","serve_args_diff":g/"serve_args_diff.json"}
  arm={"role":role,"directory":g.relative_to(run).as_posix(),"kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":digest}
  for name,path in names.items():
   if name=="route":
    if not path.is_dir() or not any(path.iterdir()): raise RuntimeError(f"T06 {role} route is empty")
   else: arm[name]=path.relative_to(run).as_posix();arm[name+"_sha256"]=sha(path);files[f"{role}_{name}"]={"path":arm[name],"sha256":arm[name+"_sha256"]}
  completion=json.loads(binding.read_text());validate_seed_completion(completion,role)
  arm["completed_k"]=completion["completed_k"];arm["window_hit"]=completion["window_hit"];arm["d15_training_input"]=(role=="seed12k");arms.append(arm)
 g=g_dirs["two"];two=g/"two_decode.json";summary=run/"route_summary_two.json"
 for name,path in {"serve_log":g/"serve.log","two_decode":two,"route_summary":summary,"model_memory":g/"model_process_cuda.jsonl","memory_summary":g/"cuda_memory_summary.json","pause_receipt":g/"pause_completed.json","serve_args_diff":g/"serve_args_diff.json"}.items(): files[f"two_{name}"]={"path":path.relative_to(run).as_posix(),"sha256":sha(path)}
 if not (g/"route").is_dir() or not any((g/"route").iterdir()): raise RuntimeError("T06 two route is empty")
 arms.append({"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256,"result":"G_two/two_decode.json","sha256":sha(two),"serve_log":"G_two/serve.log","serve_log_sha256":sha(g/"serve.log"),"route_summary":"route_summary_two.json","route_summary_sha256":sha(summary),"d15_training_input":False})
 return {"schema":"ft_r046b_route_manifest/v1","rid":RID,"candidate_commit":CANDIDATE,"memory_ratio":MEMORY_RATIO,"window":window_contract(),"service":{"independent_arms":["g3g4/g3_off","g3g4/g3_on","G_seed12k","G_seed_45k","G_seed_real","G_two"],"gpu_owner":owner},"g3g4":g3g4,"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"],"arms":arms,"files":files,"timing":"excluded; route trace disables CUDA graph"}
def validate_manifest(root):
 m=json.loads((Path(root)/"manifest.json").read_text())
 if m.get("schema")!="ft_r046b_route_manifest/v1" or m.get("rid")!=RID or m.get("candidate_commit")!=CANDIDATE or m.get('memory_ratio')!=MEMORY_RATIO or m.get('window')!=window_contract(): raise ValueError("R046b manifest identity differs")
 arms=m.get("arms")
 if not isinstance(arms,list) or {x.get("role") for x in arms}!=set(SEEDS)|{"two"}: raise ValueError("T06 manifest arms differ")
 for a in arms:
  if a["role"] in SEEDS and (a.get("directory")!=f"G_{a['role']}" or a.get("kind")!="generate" or a.get("rounds")!=12 or a.get("max_tokens")!=2048 or a.get("seed_raw_sha256")!=SEEDS[a["role"]]): raise ValueError("T06 seed arm incomplete")
  if a["role"]=="two" and (a.get("directory")!="G_two" or a.get("kind")!="two-decode" or a.get("same_prompt") is not False): raise ValueError("T06 two-decode must differ")
 if m.get("d15_training_route")!="G_seed12k/route" or set(m.get("heldout_routes",[]))!={"G_seed_45k/route","G_seed_real/route","G_two/route"}: raise ValueError("T06 D15 training/heldout route partition differs")
 return m
def child_argv(batch,receipt,wt,out): return [str(VENV/"bin/python"),str(Path(__file__).resolve()),"--run","--owned-child","--batch",str(batch),"--launch-receipt",str(receipt),"--worktree",str(wt),"--output-root",str(out)]
def require_receipt(path,batch,wt,out):
 return load_d07().require_child_receipt(path,batch,wt,out,rid=RID,expected_argv=child_argv(batch,path,wt,out),schema="ft_r046b_owned_launch/v1")
REVIEW_DIR=ROOT/'runs/dev_R046/reviews/E2-R046b-v4'

def require_t20_terminal_decision(d=None,receipt=None,expected_sha=None):
 """Require the authorized failed T20 closure without reopening its raw files."""
 d=d or load_d07()
 receipt=receipt or ROOT/'runs/dev_D17/batch71_failed_terminal_observation_20261006.json'
 expected_sha=expected_sha or '53ceade689dbb6c0a19c4271ac431fe19b4aa46162564bc022a8daadb5b09518'
 if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode&0o222 or sha(receipt)!=expected_sha:
  raise RuntimeError('R040 terminal receipt missing, writable or changed')
 value=json.loads(receipt.read_text())
 if value.get('schema')!='ft_t20_batch71_failed_terminal_observation/v1' or value.get('rid')!='E2-R040' or value.get('batch')!=71 or value.get('state')!='failed_harness_pending_D04' or value.get('round_tree_readonly') is not True or value.get('controller_absent') is not True:
  raise RuntimeError('R040 failed terminal identity differs')
 d.require_closed_round('E2-R040','failed_harness')
 return receipt
def require_startup_review(dry_receipt):
 review=REVIEW_DIR/'review.json';pin=REVIEW_DIR/'pin.json'
 for p in (REVIEW_DIR,review,pin):
  if p.is_symlink() or not p.exists() or p.stat().st_mode&0o222:raise RuntimeError('R046 startup review/pin absent, writable or symlinked')
 binding=json.loads(pin.read_text());document=json.loads(review.read_text())
 if binding.get('schema')!='ft_r046b_review_pin/v4' or binding.get('rid')!=RID or binding.get('review_sha256')!=sha(review):raise RuntimeError('R046b review pin differs')
 if document.get('schema')!='ft_r046b_source_startup_review/v4' or document.get('rid')!=RID or document.get('verdict')!='PASS' or document.get('source_execution_ready') is not True or document.get('candidate_commit')!=CANDIDATE or document.get('historical_r046')!=require_historical_r046():raise RuntimeError('R046b independent review identity differs')
 if document.get('model_config_source')!=model_config_binding():raise RuntimeError('R046b review config source binding differs')
 sources=document.get('sources')
 if not isinstance(sources,dict) or not sources:raise RuntimeError('R046 reviewed runtime sources absent')
 mandatory={str(path) for path in runtime_sources()}|{str(ROOT/'runs/plan_batches/e2_launch.py')}
 mandatory.update(str(WT/'scripts'/name) for name in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py'))
 if not mandatory<=set(sources):raise RuntimeError('R046 review lacks actual execution dependencies')
 for name,digest in sources.items():
  source=Path(name)
  if not source.is_absolute() or source.is_symlink() or not source.is_file() or sha(source)!=digest:raise RuntimeError('R046 reviewed runtime source SHA differs: '+name)
 receipt=Path(document.get('dry_run_receipt',''))
 if (receipt!=Path(dry_receipt['path']) or document.get('dry_run_receipt_sha256')!=dry_receipt['sha256']):raise RuntimeError('R046a review binds a different dry-run receipt')
 return {'path':str(review),'sha256':sha(review),'pin_sha256':sha(pin)}

def require_output_root(wt,output_root):
 if wt!=WT or output_root!=ROUNDS:raise RuntimeError('R046 requires canonical worktree and output root')
 for p in (wt,output_root):
  if '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)):raise RuntimeError('R046 canonical path is symlinked')

def require_predecessors(d):
 retained=load_pause_observer().require_retained_cold(SimpleNamespace(ROOT=ROOT))
 for rid,verdict in (("E2-R055b-gate-D06","failed_harness"),("E2-R050-gate-D15","kept"),("E2-R041-gate-D17","kept"),("E2-R040","failed_harness"),("E2-R046","failed_harness")):
  d.require_closed_round(rid,verdict)
 require_failed_r046a()
 return retained

def require_failed_r046a():
 """Check the sealed failed predecessor using the bound external D04 writer."""
 directory=ROUNDS/'E2-R046a';pin=ROOT/'runs/plan_batches/closed_round_pins/E2-R046a.json'
 round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256'
 for path in (directory,pin,round_json,manifest):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222 or any(parent.is_symlink() for parent in path.parents):raise RuntimeError('R046a sealed failed metadata differs')
 if not directory.is_dir() or any(not path.is_file() for path in (pin,round_json,manifest)):raise RuntimeError('R046a closed-round metadata types differ')
 if ROUND_WRITER.is_symlink() or not ROUND_WRITER.is_file() or any(parent.is_symlink() for parent in ROUND_WRITER.parents):raise RuntimeError('R046a external canonical D04 writer type or path differs')
 if sha(ROUND_WRITER)!=ROUND_WRITER_SHA:raise RuntimeError('R046a external canonical D04 writer SHA differs')
 registered=json.loads(pin.read_text());document=json.loads(round_json.read_text());base=document.get('base')
 if (sha(round_json)!=R046A_ROUND_SHA or registered.get('schema')!='ft_closed_round_pin/v1' or registered.get('rid')!='E2-R046a' or registered.get('candidate_commit')!=CANDIDATE or registered.get('verdict')!='failed_harness' or registered.get('round_sha256')!=R046A_ROUND_SHA or registered.get('manifest_sha256')!=sha(manifest) or document.get('schema')!='ft_round/v2' or document.get('round_id')!='E2-R046a' or not isinstance(base,dict) or base.get('commit')!=CANDIDATE or document.get('verdict')!='failed_harness'):raise RuntimeError('R046a failed-harness closure binding differs')
 for path in directory.rglob('*'):
  if path.is_symlink() or path.stat().st_mode&0o222:raise RuntimeError('R046a sealed failed tree contains writable member')
 checked=subprocess.run([str(VENV/'bin/python'),str(ROUND_WRITER),str(directory),'check'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if checked.returncode:raise RuntimeError('R046a external D04 history check failed')
 return {'rid':'E2-R046a','round_json':str(round_json),'round_sha256':R046A_ROUND_SHA,'manifest_sha256':sha(manifest),'verdict':'failed_harness','external_history_checker':str(ROUND_WRITER),'external_history_checker_sha256':ROUND_WRITER_SHA}

def _probe(path, purpose):
 write_new(path,{"schema":"ft_r046b_cpu_file_probe/v1","kind":"CPU_FILE_PROBE","not_measurement":True,"purpose":purpose})
 if path.stat().st_mode&0o222==0: raise RuntimeError("R046b dry-run output is not writable: "+str(path))
 return {"path":str(path),"sha256":sha(path),"purpose":purpose}
def _copy_runtime_source(source, target):
 if source.is_symlink() or not source.is_file(): raise RuntimeError("R046b runtime source unavailable: "+str(source))
 shutil.copyfile(source,target);target.chmod(0o600)
 if target.stat().st_mode&0o222==0: raise RuntimeError("R046b copied runtime source remains readonly")
 return {"source":str(source),"source_sha256":sha(source),"copy":str(target),"copy_sha256":sha(target),"copy_mode":oct(target.stat().st_mode&0o777)}
def archive_runtime_sources(root):
 return [_copy_runtime_source(Path(source),root/Path(source).name) for source in runtime_sources()]

def model_config_binding():
 requested=MODEL_PATH/'config.json'
 try:resolved=requested.resolve(strict=True)
 except (OSError,RuntimeError) as error:raise RuntimeError('R046b model config source unavailable') from error
 if resolved.is_symlink() or not resolved.is_file():raise RuntimeError('R046b resolved model config is not a regular source')
 return {'requested_path':str(requested),'resolved_path':str(resolved),'sha256':sha(resolved)}

def runtime_sources():
 return (Path(__file__).resolve(),SEED_CLIENT,D07_SOURCE,FILE_PREP_SOURCE,R055B_OBSERVER_SOURCE,PAUSE_HARNESS_SOURCE,ROUND_WRITER,WT/'python/freetoken/tokenizer/tokenize.py',Path(model_config_binding()['resolved_path']))
def dry_run(wt=WT,output_root=ROUNDS):
 """Perform formal file setup in a sibling, then return before Popen/requests/lock/batch."""
 if sys.platform!="linux": raise RuntimeError("R046b --dry-run requires Linux host")
 require_output_root(wt,output_root);admission=packet(wt);d=load_d07();require_predecessors(d)
 retained=require_historical_r046() # Deliberately does not read old cold.json.
 target=dry_run_directory(output_root)
 if target.exists(): raise RuntimeError("R046b dry-run sibling already exists")
 target.mkdir(mode=0o700);target.chmod(0o700)
 if target.parent!=output_root or not target.name.startswith(".dryrun_R046b_"): raise RuntimeError("R046b dry-run target differs")
 sources=[]
 try:
  sources=archive_runtime_sources(target)
  plan=memory_plan();write_new(target/'memory_plan.json',plan)
  with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
   sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
  if port==8095: raise RuntimeError("R046b dry-run allocated forbidden port")
  probes=[];arms=[]
  g3g4=run_g3g4(d,wt,target,plan,file_dry_run=True)
  apply_t06_memory_plan(d,plan)
  for role,seed in seed_paths().items():
   g=target/f"G_{role}";route=g/"route";prepared=prepare_service(d,g,wt,port,route,start=False,pause_observer=True);write_memory_diff(g,plan);file_output(g/"model_process_cuda.jsonl","formal model-process observer",file_dry_run=True);file_output(g/"pause_observations.jsonl","formal pause observer",file_dry_run=True);invoke_t06_pause(port,g,file_dry_run=True);file_output(g/"cuda_memory_summary.json","formal complete model-memory summary",file_dry_run=True);file_output(g/"serve.log","formal service log",file_dry_run=True);service_lifecycle_outputs(g,file_dry_run=True);route_output(route,file_dry_run=True);trace=g/f"trace_{role}.json";invoke_seed(wt,port,role,seed,trace,g/f"generate_{role}.log",file_dry_run=True);invoke_analysis(wt,g,target/f"route_summary_{role}.json",trace=trace,file_dry_run=True);arms.append({"directory":str(g),"port":port,"env_sha256":sha(g/"ENV.json"),"env_txt_sha256":sha(g/"ENV.txt"),"serve_cmd_sha256":sha(g/"SERVE_CMD.txt"),"log_sha256":sha(g/"serve.log"),"argv":prepared["argv"]})
  g=target/"G_two";route=g/"route";prepared=prepare_service(d,g,wt,port,route,start=False,pause_observer=True);write_memory_diff(g,plan);file_output(g/"model_process_cuda.jsonl","formal model-process observer",file_dry_run=True);file_output(g/"pause_observations.jsonl","formal pause observer",file_dry_run=True);invoke_t06_pause(port,g,file_dry_run=True);file_output(g/"cuda_memory_summary.json","formal complete model-memory summary",file_dry_run=True);file_output(g/"serve.log","formal service log",file_dry_run=True);service_lifecycle_outputs(g,file_dry_run=True);route_output(route,file_dry_run=True);two=g/"two_decode.json";invoke_two(wt,port,two,g/"two_decode.log",file_dry_run=True);invoke_analysis(wt,g,target/"route_summary_two.json",two=two,file_dry_run=True);arms.append({"directory":str(g),"port":port,"env_sha256":sha(g/"ENV.json"),"env_txt_sha256":sha(g/"ENV.txt"),"serve_cmd_sha256":sha(g/"SERVE_CMD.txt"),"log_sha256":sha(g/"serve.log"),"argv":prepared["argv"]})
  for path,purpose in ((target/"manifest.json","formal manifest"),(target/"result.json","formal result"),(target/"metadata/pre_d04.json","formal pre-D04 metadata")):probes.append(file_output(path,purpose,file_dry_run=True))
  receipt={"schema":"ft_r046b_dry_run/v4","rid":RID,"candidate_commit":CANDIDATE,"passed":True,"model_config_source":model_config_binding(),"source_sha256":{row["source"]:row["source_sha256"] for row in sources},"source_copies":sources,"owner":{"path":str(Path(__file__).resolve()),"uid":getattr(os,"getuid",lambda:None)(),"user":os.environ.get("USER") or os.environ.get("LOGNAME")},"cwd":os.getcwd(),"worktree":{"path":str(wt),"parent":str(wt.parent)},"formal_rid_directory_created":False,"formal_directory":str(output_root/RID),"service_started":False,"requests_sent":False,"gpu_lock_taken":False,"batch_allocated":False,"port":port,"historical_r046":retained,"g3g4":g3g4,"packet_sha256":hashlib.sha256(json.dumps(admission,sort_keys=True).encode()).hexdigest(),"arms":arms,"cpu_file_probes":probes}
  write_new(target/"dry_run_receipt.json",receipt);receipt_path=target/"dry_run_receipt.json";receipt_path.chmod(0o444)
  return {**receipt,"dry_run_directory":str(target),"receipt_sha256":sha(receipt_path)}
 except BaseException: raise
def dry_run_directory(output_root=ROUNDS): return output_root/f".dryrun_R046b_v4_{RID}"
def require_dry_run_receipt(output_root=ROUNDS):
 target=dry_run_directory(output_root);receipt=target/"dry_run_receipt.json"
 if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode&0o222:raise RuntimeError("R046b dry-run receipt absent or writable")
 value=json.loads(receipt.read_text())
 expected_user=os.environ.get("USER") or os.environ.get("LOGNAME")
 expected_owner={"path":str(Path(__file__).resolve()),"uid":getattr(os,"getuid",lambda:None)(),"user":expected_user}
 if (value.get("schema")!="ft_r046b_dry_run/v4" or value.get("rid")!=RID or value.get("candidate_commit")!=CANDIDATE or value.get("passed") is not True
     or value.get("owner")!=expected_owner or value.get("cwd")!=str(ROOT) or value.get("worktree")!={"path":str(WT),"parent":str(WT.parent)}
     or any(value.get(flag) is not False for flag in ("formal_rid_directory_created","service_started","requests_sent","gpu_lock_taken","batch_allocated"))):raise RuntimeError("R046b dry-run receipt identity differs")
 if value.get('model_config_source')!=model_config_binding():raise RuntimeError('R046b dry-run config source binding differs')
 expected={str(Path(p).resolve()):sha(p) for p in runtime_sources()}
 if value.get("source_sha256")!=expected:raise RuntimeError("R046b dry-run receipt source SHA differs")
 return {"path":str(receipt),"sha256":sha(receipt)}

def execute(wt=WT,output_root=ROUNDS,*,owned_child=False,batch=None,launch_receipt=None):
 if sys.platform!="linux": raise RuntimeError("T06 --run requires Linux GPU host")
 require_output_root(wt,output_root)
 d=load_d07()
 if not owned_child and (d.LOCK.exists() or d.LOCK.is_symlink()):raise RuntimeError('foreign GPU lock exists; T06 remains queued')
 admission=packet(wt);require_predecessors(d);dry_receipt=require_dry_run_receipt(output_root);review=require_startup_review(dry_receipt);r041,t20=d.require_r041_kept(ROOT),require_t20_terminal_decision(d)
 if not owned_child:
  if (output_root/RID).exists(): raise RuntimeError("T06 round already exists; no overwrite/retry-in-place")
  if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists; T06 remains queued")
  owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/"runs/plan_batches/e2_launch.py",d.ATOMIC_HELPER_SHA,"t06_atomic_launcher");batch=helper.next_batch(output_root);path=ROOT/"runs/dev_R046"/f"launch_{RID}_batch{batch}.json";path.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,path,wt,output_root)
  reserved={"schema":"ft_r046b_owned_launch/v1","state":"reserved","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"argv_sha256":d.argv_sha256(argv),"controller":d.process_birth()}
  value=owned.reserve_process(helper,batch,RID,argv,path,reserved);child=owned.process_identity(value["batch_pid"])
  if child is None or child.get("pid")!=value["batch_pid"] or type(child.get("start_ticks")) is not int: raise RuntimeError("T06 reserved child birth is unavailable")
  child={"pid":child["pid"],"start_ticks":child["start_ticks"],"execution_id":f"{child['pid']}:{child['start_ticks']}"}
  return d.publish_child_binding(path,value,child,lifecycle=owned)
 if batch is None or launch_receipt is None: raise RuntimeError("T06 owned child requires controller receipt and reserved batch")
 require_receipt(launch_receipt,batch,wt,output_root)
 if (output_root/RID).exists(): raise RuntimeError("T06 round already exists; no overwrite/retry-in-place")
 owner=d.take_d07_gpu_lock(RID,batch);run=None;process=None;cleanup_failed=False
 try:
  idle=d.require_gpu_idle();run=output_root/RID;run.mkdir(parents=True);g_dirs={}
  archive_runtime_sources(run)
  plan=memory_plan();write_new(run/'memory_plan.json',plan)
  d.write_new(run/"preflight.json",{**admission,"batch":batch,"gpu_owner":owner,"gpu_memory_mib":idle,"startup_review":review,"dry_run_receipt":dry_receipt,"r041_closure":str(r041),"r041_closure_sha256":sha(r041),"t20_terminal_receipt":str(t20),"t20_terminal_receipt_sha256":sha(t20),"t20_kept_required":False,"authorization":"CODEX_HANDOFF section twelve, latest user decision","r055_kept_required":False,"pause_chain_complete_gate_required":False,"r045_complete_pause_chain_pending":True})
  g3g4=run_g3g4(d,wt,run,plan)
  apply_t06_memory_plan(d,plan)
  for role,seed in seed_paths().items():
   g=run/f"G_{role}";route=g/"route";g_dirs[role]=g;port=d.dynamic_fixture_port();process=prepare_service(d,g,wt,port,route,start=True,pause_observer=True);write_memory_diff(g,plan);require_t06_loaded_memory(g,plan,process);invoke_t06_pause(port,g);trace=g/f"trace_{role}.json";invoke_seed(wt,port,role,seed,trace,g/f"generate_{role}.log");stop_g3g4_service(d,process);completed_process=process;process=None;summarize_t06_memory(g,plan,completed_process,validate_seed_completion(json.loads(trace.with_suffix(".seed_binding.json").read_text()),role));invoke_analysis(wt,g,run/f"route_summary_{role}.json",trace=trace)
  g=run/"G_two";route=g/"route";g_dirs["two"]=g;port=d.dynamic_fixture_port();process=prepare_service(d,g,wt,port,route,start=True,pause_observer=True);write_memory_diff(g,plan);require_t06_loaded_memory(g,plan,process);invoke_t06_pause(port,g);two=g/"two_decode.json";invoke_two(wt,port,two,g/"two_decode.log");stop_g3g4_service(d,process);completed_process=process;process=None;summarize_t06_memory(g,plan,completed_process,2);invoke_analysis(wt,g,run/"route_summary_two.json",two=two)
  write_new(run/"manifest.json",manifest(run,g_dirs,g3g4,owner));validate_manifest(run)
  summaries={role:json.loads((run/f"route_summary_{role}.json").read_text()) for role in (*SEEDS,"two")}
  result={"schema":"ft_r046b_raw_measurement/v1","round_id":RID,"card":"D07-G3G4+T06","title":"combined G3/G4 and route trace measurement (trace enabled)","epoch":2,"parent":"E2-R040","base":{"code_version":"E2-base.1-p1@effb996","commit":CANDIDATE},"candidate_commit":CANDIDATE,"batch":batch,"verdict":"pending_review","proposed_verdict":"measured","raw_measurement_before_D04":True,"manifest":"manifest.json","manifest_sha256":sha(run/"manifest.json"),"g3g4":g3g4,"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"actual_quality_from_route_summaries":summaries,"timing":"excluded from performance claims","authorization":"CODEX_HANDOFF section twelve, latest user decision","r055_verdict_preserved":"failed_harness","retained_six_cold_verdict":"PASS","complete_pause_cancel_recovery_validation":"R045 D06 G3/G4","memory_plan":"memory_plan.json","cuda_memory_summaries":{**{role:f"G_{role}/cuda_memory_summary.json" for role in (*SEEDS,"two")},"g3_off":"g3g4/g3_off/cuda_memory_summary.json","g3_on":"g3g4/g3_on/cuda_memory_summary.json"},"anomalies":[]}
  write_new(run/"result.json",result)
  write_new(run/"metadata/pre_d04.json",{"schema":"ft_r046b_pre_d04/v1","round_id":RID,"card":"T06","base":{"code_version":"E2-base.1-p1@effb996","commit":CANDIDATE},"verdict":"pending_review","proposed_verdict":"measured","result":"result.json","result_sha256":sha(run/"result.json"),"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"canonical_round_json_created":False,"canonical_manifest_created":False})
  return result
 except BaseException as e:
  process=getattr(e,'owned_process',process)
  cleanup_failed=bool(getattr(e,'owned_cleanup_failed',False))
  if run is not None: write_new(run/"failed_harness.json",{"rid":RID,"batch":batch,"gpu_owner":owner,"error":repr(e),"pause_chain_failure":bool(getattr(e,"pause_chain_failure",False)),"user_disposition_required":True,"raw_measurement_preserved":True})
  raise
 finally:
  if cleanup_failed:
   if run is not None:
    birth=None
    if process is not None:birth=d.load_owned_lifecycle().process_identity(process.pid)
    write_new(run/"owned_cleanup.json",{"schema":"ft_r046_owned_cleanup/v1","rid":RID,"batch":batch,"gpu_owner":owner,"lock_released":False,"cleanup_failed":True,"service_pid":getattr(process,'pid',None),"service_birth":birth})
   raise RuntimeError("R046 G3/G4 cleanup failed; preserve GPU lock for recovery")
  if process is not None:
   try:d.load_owned_lifecycle().stop_owned_process(process)
   except BaseException as cleanup_error:
    if run is not None:write_new(run/"owned_cleanup.json",{"schema":"ft_r046_owned_cleanup/v1","rid":RID,"batch":batch,"gpu_owner":owner,"lock_released":False,"cleanup_error":repr(cleanup_error)})
    raise
   if d.load_owned_lifecycle().owned_group_alive(process.pid):
    if run is not None:write_new(run/"owned_cleanup.json",{"schema":"ft_r046_owned_cleanup/v1","rid":RID,"batch":batch,"gpu_owner":owner,"lock_released":False,"owned_group_alive":True})
    raise RuntimeError("R046 owned service remains; preserve GPU lock for recovery")
  d.release_d07_gpu_lock(owner)
  if run is not None: write_new(run/"owned_cleanup.json",{"schema":"ft_r046_owned_cleanup/v1","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"gpu_owner":owner,"lock_released":True})
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",action="store_true");p.add_argument("--dry-run",action="store_true");p.add_argument("--owned-child",action="store_true",help=argparse.SUPPRESS);p.add_argument("--batch",type=int);p.add_argument("--launch-receipt",type=Path);p.add_argument("--worktree",type=Path,default=WT);p.add_argument("--output-root",type=Path,default=ROUNDS);a=p.parse_args(argv)
 if a.run and a.dry_run: p.error("--run and --dry-run are mutually exclusive")
 value=dry_run(a.worktree,a.output_root) if a.dry_run else (execute(a.worktree,a.output_root,owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt) if a.run else packet(a.worktree))
 print(json.dumps(value,ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())

