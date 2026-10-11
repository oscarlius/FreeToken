#!/usr/bin/env python3
"""E2-R046a remaining D07/T06 arms with the sealed R046 OFF arm retained."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path

RID="E2-R046a"; CANDIDATE="effb9969706922ddad9e59b96377e46469ebe97f"
ROOT=Path("/data2/FreeToken"); WT=ROOT/"wt/e2base1-p1"; VENV=ROOT/"venv"
ROUNDS=Path("/data2/_shared/runs/ft_rounds"); D07_RUNS=ROOT/"runs/dev_D07"; SEED_ROOT=ROOT/"wt/e1r003"
MODEL="Qwen3.8-Flash-Next-NVFP4"; HERE=Path(__file__).resolve().parent
SEED_CLIENT=HERE/"r046_seed_agent_trace.py"; D07_SOURCE=HERE/"d07_g3g4_prepare.py"
SEEDS={"seed12k":"1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153",
       "seed_45k":"499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9",
       "seed_real":"8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3"}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
def load_d07(source=D07_SOURCE):
 if source.is_symlink() or not source.is_file(): raise RuntimeError("T06 requires D07 lifecycle source")
 spec=importlib.util.spec_from_file_location("t06_d07_lifecycle",source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.CANDIDATE=CANDIDATE;m.WORKTREE=WT;m.RID=RID;return m
def seed_paths():
 paths={role:SEED_ROOT/f"{role}.txt" for role in SEEDS}
 for role,p in paths.items():
  if p.is_symlink() or not p.is_file() or sha(p)!=SEEDS[role]: raise RuntimeError(f"T06 seed raw bytes differ: {role}")
 return paths
def packet(wt=WT):
 d=load_d07(); candidate=d.checked_worktree(wt); tools=d.verify_d07_tools(wt)
 if SEED_CLIENT.is_symlink() or not SEED_CLIENT.is_file(): raise RuntimeError("T06 seed-aware candidate client unavailable")
 return {"schema":"ft_r046a_d07_t06_prepare/v1","rid":RID,"candidate_commit":CANDIDATE,"candidate":candidate,"candidate_tools":tools,"retained_off":require_retained_off(),
  "d07_lifecycle_source":str(D07_SOURCE),"d07_lifecycle_source_sha256":sha(D07_SOURCE),"seed_client":str(SEED_CLIENT),"seed_client_sha256":sha(SEED_CLIENT),
  "seeds":[{"role":r,"path":str(p),"raw_sha256":SEEDS[r]} for r,p in seed_paths().items()],"fixture_port":d.dynamic_fixture_port(),"cuda_visible_devices_cpu_guard":"",
  "run_requires":["explicit --run","Linux host","R055-gate-D06 kept","R050-gate-D15 kept","R041 D04 kept","R040 and R046 failed_harness preserved","retained G3-off plus new G3-on/G4 before T06 arms","R startup review","atomic owned GPU lock","GPU idle gate"],
  "service_shape":"four independent serial services: G_seed12k, G_seed_45k, G_seed_real, G_two","arms":[{"role":r,"directory":f"G_{r}","kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":h} for r,h in SEEDS.items()]+[{"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256}],"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"],"verdict":"measured","timing":"trace-mode timing excluded from performance claims"}
def invoke_seed(wt,port,role,seed,out,log):
 cmd=[str(VENV/"bin/python"),str(SEED_CLIENT),"--client",str(wt/"scripts/agent_trace.py"),"--seed-file",str(seed),"--out",str(out),"--rounds","12","--max-tokens","2048","--base-url",f"http://127.0.0.1:{port}/v1","--model",MODEL]
 with log.open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=load_d07().clean_environment(wt),stdout=f,stderr=subprocess.STDOUT,check=True)
 binding=out.with_suffix(".seed_binding.json")
 if not out.is_file() or not binding.is_file(): raise RuntimeError(f"T06 {role} lacks trace/actual-wire binding")
 b=json.loads(binding.read_text())
 if b.get("seed_raw_sha256")!=SEEDS[role] or not b.get("actual_wire_first_content_sha256"): raise RuntimeError(f"T06 {role} seed binding incomplete")
def invoke_two(wt,port,out,log):
 cmd=[str(VENV/"bin/python"),str(wt/"scripts/multisession_probe.py"),"two-decode","--base-url",f"http://127.0.0.1:{port}/v1","--model",MODEL,"--ctx","8000","--max-tokens","256","--same-prompt","0","--reps","1","--out",str(out)]
 with log.open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=load_d07().clean_environment(wt),stdout=f,stderr=subprocess.STDOUT,check=True)
 if json.loads(out.read_text()).get("same_prompt") is not False: raise RuntimeError("T06 two-decode is not different-content")
def invoke_analysis(wt,g,summary,*,trace=None,two=None):
 cmd=[str(VENV/"bin/python"),str(wt/"scripts/route_analyze.py"),str(g/"route")]
 if trace is not None: cmd += ["--traces",str(trace)]
 if two is not None: cmd += ["--two-decode",str(two)]
 cmd += ["--serve-log",str(g/"serve.log"),"--out",str(summary)]
 with (g/"route_analyze.log").open("x",encoding="utf-8") as f: subprocess.run(cmd,cwd=wt,env=load_d07().clean_environment(wt),stdout=f,stderr=subprocess.STDOUT,check=True)
 d=json.loads(summary.read_text())
 if trace is not None:
  completions=d.get("completions",{})
  if (d.get("analysis_scope")!="trace_bound_business_requests" or not d.get("suffix_tokens")
      or not isinstance(d.get("business_uids"),list) or len(d["business_uids"])!=12
      or d.get("completion_count")!=12 or len(completions)!=12
      or d.get("missing_business_routes") or any(row.get("max_tokens")!=2048 for row in completions.values())):
   raise RuntimeError("T06 seed analysis lacks 12 UID-bound 2048-token business traces")
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

def run_g3g4(d, wt, run):
 retained=require_retained_off(verify_cold=True)
 root=run/"g3g4";off=ROUNDS/'E2-R046/g3g4/g3_off';on=root/"g3_on";root.mkdir();on.mkdir();cold_id="E2-R046-cold";process=None
 write_new(root/'retained_g3_off.json',retained)
 route=on/"route";route.mkdir();process=None
 try:
  port=d.dynamic_fixture_port();process=d.start_server(on,wt,port,route);d.invoke_cold_eq(wt,port,cold_id,on/"cold.json");trace=on/"trace.json";d.invoke_agent_trace(wt,port,trace)
 except BaseException as error:
  process=getattr(error,'owned_process',process)
  error.owned_process=process
  raise
 finally:
  # A startup cleanup failure already carries its owned process. Never retry
  # it here and erase the failure before the round owner preserves the lock.
  active=sys.exc_info()[1]
  if not getattr(active,'owned_cleanup_failed',False):stop_g3g4_service(d,process)
 serve=on/"serve.log"
 if "CUDA graph disabled for development route trace" not in serve.read_text(encoding="utf-8",errors="replace"):raise RuntimeError("R046 G3/G4 lacks CUDA-graph-disabled marker")
 summary=root/"route_summary.json";d.invoke_analyzer(wt,route,trace,serve,summary);doc=json.loads(summary.read_text())
 return {"schema":"ft_r046a_g3g4_raw/v1","directory":"g3g4","retained_off":retained,"g3":d.g3_compare(off/"cold.json",on/"cold.json"),"g4":{"route_summary":"g3g4/route_summary.json","route_summary_sha256":sha(summary),"business_uids":len(doc.get("business_uids",[])),"suffix_tokens":len(doc.get("suffix_tokens",[]))},"cuda_graph_disabled_marker":True,"timing":"excluded from performance claims"}

def require_retained_off(*,verify_cold=False):
 cold=ROUNDS/'E2-R046/g3g4/g3_off/cold.json'
 review=ROOT/'runs/dev_D17/r046_live_incremental_r_overlap_g3off/review.json'
 cold_sha='0ccee4b9e5a0917b5284a334acc3f0ca3bd5b871d287f674eca907b7f1f47d6d'
 review_sha='e42524eee0ec7ea5e9e971528b2a14f953306d58968712ed7826ba1264779450'
 for path in (cold,review):
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:
   raise RuntimeError('R046a retained OFF evidence must be sealed')
 if sha(review)!=review_sha:raise RuntimeError('R046a retained OFF review differs')
 # Startup uses the registered R receipt and readonly metadata only. The small
 # comparison JSON is read/verified only after this round owns its GPU lock.
 if verify_cold and sha(cold)!=cold_sha:raise RuntimeError('R046a retained OFF cold differs')
 return {'round':'E2-R046','cold':str(cold),'cold_sha256':cold_sha,'review':str(review),
         'review_sha256':review_sha,'off_candidate':'0aa23431e5b800797543bdecbf35a01045131d7d',
         'on_candidate':CANDIDATE,'authorization':'HANDOFF section seven; R055 kept required',
         'off_rerun':False}

def manifest(run,g_dirs,g3g4,owner):
 files={};arms=[]
 for role,digest in SEEDS.items():
  g=g_dirs[role];trace=g/f"trace_{role}.json";binding=trace.with_suffix(".seed_binding.json");summary=run/f"route_summary_{role}.json"
  names={"route":g/"route","serve_log":g/"serve.log","trace":trace,"seed_binding":binding,"route_summary":summary}
  arm={"role":role,"directory":g.relative_to(run).as_posix(),"kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":digest}
  for name,path in names.items():
   if name=="route":
    if not path.is_dir() or not any(path.iterdir()): raise RuntimeError(f"T06 {role} route is empty")
   else: arm[name]=path.relative_to(run).as_posix();arm[name+"_sha256"]=sha(path);files[f"{role}_{name}"]={"path":arm[name],"sha256":arm[name+"_sha256"]}
  arm["d15_training_input"]=(role=="seed12k");arms.append(arm)
 g=g_dirs["two"];two=g/"two_decode.json";summary=run/"route_summary_two.json"
 for name,path in {"serve_log":g/"serve.log","two_decode":two,"route_summary":summary}.items(): files[f"two_{name}"]={"path":path.relative_to(run).as_posix(),"sha256":sha(path)}
 if not (g/"route").is_dir() or not any((g/"route").iterdir()): raise RuntimeError("T06 two route is empty")
 arms.append({"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256,"result":"G_two/two_decode.json","sha256":sha(two),"serve_log":"G_two/serve.log","serve_log_sha256":sha(g/"serve.log"),"route_summary":"route_summary_two.json","route_summary_sha256":sha(summary),"d15_training_input":False})
 return {"schema":"ft_r046_route_manifest/v1","rid":RID,"candidate_commit":CANDIDATE,"service":{"independent_arms":["g3g4","G_seed12k","G_seed_45k","G_seed_real","G_two"],"gpu_owner":owner},"g3g4":g3g4,"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"],"arms":arms,"files":files,"timing":"excluded; route trace disables CUDA graph"}
def validate_manifest(root):
 m=json.loads((Path(root)/"manifest.json").read_text())
 if m.get("schema")!="ft_r046_route_manifest/v1" or m.get("rid")!=RID or m.get("candidate_commit")!=CANDIDATE: raise ValueError("T06 manifest identity differs")
 arms=m.get("arms")
 if not isinstance(arms,list) or {x.get("role") for x in arms}!=set(SEEDS)|{"two"}: raise ValueError("T06 manifest arms differ")
 for a in arms:
  if a["role"] in SEEDS and (a.get("directory")!=f"G_{a['role']}" or a.get("kind")!="generate" or a.get("rounds")!=12 or a.get("max_tokens")!=2048 or a.get("seed_raw_sha256")!=SEEDS[a["role"]]): raise ValueError("T06 seed arm incomplete")
  if a["role"]=="two" and (a.get("directory")!="G_two" or a.get("kind")!="two-decode" or a.get("same_prompt") is not False): raise ValueError("T06 two-decode must differ")
 if m.get("d15_training_route")!="G_seed12k/route" or set(m.get("heldout_routes",[]))!={"G_seed_45k/route","G_seed_real/route","G_two/route"}: raise ValueError("T06 D15 training/heldout route partition differs")
 return m
def child_argv(batch,receipt,wt,out): return [str(VENV/"bin/python"),str(Path(__file__).resolve()),"--run","--owned-child","--batch",str(batch),"--launch-receipt",str(receipt),"--worktree",str(wt),"--output-root",str(out)]
def require_receipt(path,batch,wt,out):
 return load_d07().require_child_receipt(path,batch,wt,out,rid=RID,expected_argv=child_argv(batch,path,wt,out),schema="ft_r046a_owned_launch/v1")
REVIEW_DIR=ROOT/'runs/dev_R046/reviews/E2-R046a-v1'

def require_t20_terminal_decision(receipt=None, rounds=None, expected_sha=None):
 """Apply HANDOFF section six; retain the exact failed round, never grant kept."""
 receipt=receipt or ROOT/'runs/dev_D17/batch71_failed_terminal_observation_20261006.json'
 rounds=rounds or ROUNDS
 expected_sha=expected_sha or '53ceade689dbb6c0a19c4271ac431fe19b4aa46162564bc022a8daadb5b09518'
 if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode&0o222 or sha(receipt)!=expected_sha:
  raise RuntimeError('R040 terminal receipt missing, writable or changed')
 value=json.loads(receipt.read_text())
 if value.get('schema')!='ft_t20_batch71_failed_terminal_observation/v1' or value.get('rid')!='E2-R040' or value.get('batch')!=71 or value.get('state')!='failed_harness_pending_D04' or value.get('round_tree_readonly') is not True or value.get('controller_absent') is not True:
  raise RuntimeError('R040 failed terminal identity differs')
 directory=rounds/'E2-R040'
 if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode&0o222:
  raise RuntimeError('R040 failed original must remain readonly')
 for name in ('status_batch71.json','failed_harness.json'):
  path=directory/name
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222 or sha(path)!=value.get('files_sha256',{}).get(str(path)):
   raise RuntimeError('R040 original terminal evidence changed')
 status=json.loads((directory/'status_batch71.json').read_text())
 if status.get('state')!='failed' or status.get('batch_pid')!=3576643 or status.get('rid')!='E2-R040' or status.get('batch')!=71:
  raise RuntimeError('R040 is not the approved terminal failed batch')
 stat=Path('/proc/3576643/stat')
 if stat.exists():
  fields=stat.read_text().rsplit(')',1)[1].split()
  if int(fields[19])==138313868 and fields[0]!='Z':raise RuntimeError('R040 original controller still live')
 return receipt
def require_startup_review():
 review=REVIEW_DIR/'review.json';pin=REVIEW_DIR/'pin.json'
 for p in (REVIEW_DIR,review,pin):
  if p.is_symlink() or not p.exists() or p.stat().st_mode&0o222:raise RuntimeError('R046 startup review/pin absent, writable or symlinked')
 binding=json.loads(pin.read_text());document=json.loads(review.read_text())
 if binding.get('schema')!='ft_r046a_review_pin/v1' or binding.get('rid')!=RID or binding.get('review_sha256')!=sha(review):raise RuntimeError('R046a review pin differs')
 if document.get('schema')!='ft_r046a_source_startup_review/v1' or document.get('verdict')!='PASS' or document.get('source_execution_ready') is not True or document.get('candidate_commit')!=CANDIDATE or document.get('retained_off')!=require_retained_off():raise RuntimeError('R046a independent review identity differs')
 sources=document.get('sources')
 if not isinstance(sources,dict) or not sources:raise RuntimeError('R046 reviewed runtime sources absent')
 mandatory={str(Path(__file__).resolve()),str(D07_SOURCE),str(SEED_CLIENT),str(ROOT/'runs/plan_batches/e2_launch.py')}
 mandatory.update(str(WT/'scripts'/name) for name in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py'))
 if not mandatory<=set(sources):raise RuntimeError('R046 review lacks actual execution dependencies')
 for name,digest in sources.items():
  source=Path(name)
  if not source.is_absolute() or source.is_symlink() or not source.is_file() or sha(source)!=digest:raise RuntimeError('R046 reviewed runtime source SHA differs: '+name)
 return {'path':str(review),'sha256':sha(review),'pin_sha256':sha(pin)}

def require_output_root(wt,output_root):
 if wt!=WT or output_root!=ROUNDS:raise RuntimeError('R046 requires canonical worktree and output root')
 for p in (wt,output_root):
  if '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)):raise RuntimeError('R046 canonical path is symlinked')

def require_predecessors(d):
 for rid,verdict in (("E2-R055-gate-D06","kept"),("E2-R050-gate-D15","kept"),("E2-R041-gate-D17","kept"),("E2-R040","failed_harness"),("E2-R046","failed_harness")):
  d.require_closed_round(rid,verdict)

def execute(wt=WT,output_root=ROUNDS,*,owned_child=False,batch=None,launch_receipt=None):
 if sys.platform!="linux": raise RuntimeError("T06 --run requires Linux GPU host")
 require_output_root(wt,output_root)
 d=load_d07()
 if not owned_child and (d.LOCK.exists() or d.LOCK.is_symlink()):raise RuntimeError('foreign GPU lock exists; T06 remains queued')
 require_predecessors(d);review=require_startup_review();admission=packet(wt);r041,t20=d.require_r041_kept(ROOT),require_t20_terminal_decision()
 if not owned_child:
  if (output_root/RID).exists(): raise RuntimeError("T06 round already exists; no overwrite/retry-in-place")
  if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists; T06 remains queued")
  owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/"runs/plan_batches/e2_launch.py",d.ATOMIC_HELPER_SHA,"t06_atomic_launcher");batch=helper.next_batch(output_root);path=ROOT/"runs/dev_R046"/f"launch_{RID}_batch{batch}.json";path.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,path,wt,output_root)
  reserved={"schema":"ft_r046a_owned_launch/v1","state":"reserved","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"argv_sha256":d.argv_sha256(argv),"controller":d.process_birth()}
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
  for source in (__file__,SEED_CLIENT,D07_SOURCE): shutil.copy2(source,run/Path(source).name)
  d.write_new(run/"preflight.json",{**admission,"batch":batch,"gpu_owner":owner,"gpu_memory_mib":idle,"startup_review":review,"r041_closure":str(r041),"r041_closure_sha256":sha(r041),"t20_terminal_receipt":str(t20),"t20_terminal_receipt_sha256":sha(t20),"t20_kept_required":False,"authorization":"CODEX_HANDOFF section seven, user decision 10-07 02:50"})
  g3g4=run_g3g4(d,wt,run)
  for role,seed in seed_paths().items():
   g=run/f"G_{role}";g.mkdir();route=g/"route";route.mkdir();g_dirs[role]=g;port=d.dynamic_fixture_port();process=d.start_server(g,wt,port,route);trace=g/f"trace_{role}.json";invoke_seed(wt,port,role,seed,trace,g/f"generate_{role}.log");stop_g3g4_service(d,process);process=None;invoke_analysis(wt,g,run/f"route_summary_{role}.json",trace=trace)
  g=run/"G_two";g.mkdir();route=g/"route";route.mkdir();g_dirs["two"]=g;port=d.dynamic_fixture_port();process=d.start_server(g,wt,port,route);two=g/"two_decode.json";invoke_two(wt,port,two,g/"two_decode.log");stop_g3g4_service(d,process);process=None;invoke_analysis(wt,g,run/"route_summary_two.json",two=two)
  write_new(run/"manifest.json",manifest(run,g_dirs,g3g4,owner));validate_manifest(run)
  summaries={role:json.loads((run/f"route_summary_{role}.json").read_text()) for role in (*SEEDS,"two")}
  result={"schema":"ft_r046_raw_measurement/v1","round_id":RID,"card":"D07-G3G4+T06","title":"combined G3/G4 and route trace measurement (trace enabled)","epoch":2,"parent":"E2-R040","base":{"code_version":"E2-base.1-p1@effb996","commit":CANDIDATE},"candidate_commit":CANDIDATE,"batch":batch,"verdict":"pending_review","proposed_verdict":"measured","raw_measurement_before_D04":True,"manifest":"manifest.json","manifest_sha256":sha(run/"manifest.json"),"g3g4":g3g4,"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"actual_quality_from_route_summaries":summaries,"timing":"excluded from performance claims","anomalies":[]}
  write_new(run/"result.json",result)
  write_new(run/"metadata/pre_d04.json",{"schema":"ft_r046_pre_d04/v1","round_id":RID,"card":"T06","base":{"code_version":"E2-base.1-p1@effb996","commit":CANDIDATE},"verdict":"pending_review","proposed_verdict":"measured","result":"result.json","result_sha256":sha(run/"result.json"),"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"canonical_round_json_created":False,"canonical_manifest_created":False})
  return result
 except BaseException as e:
  process=getattr(e,'owned_process',process)
  cleanup_failed=bool(getattr(e,'owned_cleanup_failed',False))
  if run is not None: write_new(run/"failed_harness.json",{"rid":RID,"batch":batch,"gpu_owner":owner,"error":repr(e),"raw_measurement_preserved":True})
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",action="store_true");p.add_argument("--owned-child",action="store_true",help=argparse.SUPPRESS);p.add_argument("--batch",type=int);p.add_argument("--launch-receipt",type=Path);p.add_argument("--worktree",type=Path,default=WT);p.add_argument("--output-root",type=Path,default=ROUNDS);a=p.parse_args(argv)
 print(json.dumps(execute(a.worktree,a.output_root,owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt) if a.run else packet(a.worktree),ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())

