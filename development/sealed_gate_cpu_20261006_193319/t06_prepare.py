#!/usr/bin/env python3
"""E2-R046 actual measured-run runner; GPU only when an R-reviewed --run is invoked."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, shutil, subprocess, sys
from pathlib import Path

RID="E2-R046"; CANDIDATE="0aa23431e5b800797543bdecbf35a01045131d7d"
ROOT=Path("/data2/FreeToken"); WT=ROOT/"wt/e2base1-ordinary-rewind"; VENV=ROOT/"venv"
ROUNDS=Path("/data2/_shared/runs/ft_rounds"); D07_RUNS=ROOT/"runs/dev_D07"; SEED_ROOT=ROOT/"wt/e1r003"
MODEL="Qwen3.8-Flash-Next-NVFP4"; HERE=Path(__file__).resolve().parent
SEED_CLIENT=HERE/"t06_seed_agent_trace.py"; D07_SOURCE=HERE/"d07_g3g4_prepare.py"
SEEDS={"seed12k":"1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153",
       "seed_45k":"499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9",
       "seed_real":"8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3"}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
def load_d07(source=D07_SOURCE):
 if source.is_symlink() or not source.is_file(): raise RuntimeError("T06 requires D07 lifecycle source")
 spec=importlib.util.spec_from_file_location("t06_d07_lifecycle",source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def seed_paths():
 paths={role:SEED_ROOT/f"{role}.txt" for role in SEEDS}
 for role,p in paths.items():
  if p.is_symlink() or not p.is_file() or sha(p)!=SEEDS[role]: raise RuntimeError(f"T06 seed raw bytes differ: {role}")
 return paths
def require_d07():
 hits=[]
 for result in D07_RUNS.glob("E2-R043_*/result.json"):
  cleanup=result.with_name("owned_cleanup.json")
  try: r=json.loads(result.read_text());c=json.loads(cleanup.read_text())
  except (OSError,json.JSONDecodeError): continue
  if (r.get("schema")=="ft_d07_g3g4_result/v1" and r.get("verdict")=="development_selfcheck_pass" and r.get("rid")=="E2-R043" and r.get("candidate_commit")==CANDIDATE and c.get("schema")=="ft_d07_owned_cleanup/v1" and c.get("rid")=="E2-R043" and c.get("candidate_commit")==CANDIDATE and c.get("lock_released") is True and c.get("batch")==r.get("batch") and c.get("gpu_owner")==r.get("gpu_owner")): hits.append((result,cleanup))
 if len(hits)!=1: raise RuntimeError("exactly one complete D07 result plus matching owned cleanup is required")
 return hits[0]
def packet(wt=WT):
 d=load_d07(); candidate=d.checked_worktree(wt); tools=d.verify_d07_tools(wt)
 if SEED_CLIENT.is_symlink() or not SEED_CLIENT.is_file(): raise RuntimeError("T06 seed-aware candidate client unavailable")
 return {"schema":"ft_t06_prepare/v2","rid":RID,"candidate_commit":CANDIDATE,"candidate":candidate,"candidate_tools":tools,
  "d07_lifecycle_source":str(D07_SOURCE),"d07_lifecycle_source_sha256":sha(D07_SOURCE),"seed_client":str(SEED_CLIENT),"seed_client_sha256":sha(SEED_CLIENT),
  "seeds":[{"role":r,"path":str(p),"raw_sha256":SEEDS[r]} for r,p in seed_paths().items()],"fixture_port":d.dynamic_fixture_port(),"cuda_visible_devices_cpu_guard":"",
  "run_requires":["explicit --run","Linux host","R041 D04 kept","T20 E2-R040 D04 kept","D07 result plus owned cleanup","R startup review","atomic owned GPU lock","GPU idle gate"],
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
def manifest(run,g_dirs,d07_receipt,owner):
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
 return {"schema":"ft_t06_route_manifest/v1","rid":RID,"candidate_commit":CANDIDATE,"service":{"independent_arms":["G_seed12k","G_seed_45k","G_seed_real","G_two"],"gpu_owner":owner},"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"],"d07_development_receipt":{"path":str(d07_receipt[0]),"sha256":sha(d07_receipt[0]),"cleanup_path":str(d07_receipt[1]),"cleanup_sha256":sha(d07_receipt[1])},"arms":arms,"files":files,"timing":"excluded; route trace disables CUDA graph"}
def validate_manifest(root):
 m=json.loads((Path(root)/"manifest.json").read_text())
 if m.get("schema")!="ft_t06_route_manifest/v1" or m.get("rid")!=RID or m.get("candidate_commit")!=CANDIDATE: raise ValueError("T06 manifest identity differs")
 arms=m.get("arms")
 if not isinstance(arms,list) or {x.get("role") for x in arms}!=set(SEEDS)|{"two"}: raise ValueError("T06 manifest arms differ")
 for a in arms:
  if a["role"] in SEEDS and (a.get("directory")!=f"G_{a['role']}" or a.get("kind")!="generate" or a.get("rounds")!=12 or a.get("max_tokens")!=2048 or a.get("seed_raw_sha256")!=SEEDS[a["role"]]): raise ValueError("T06 seed arm incomplete")
  if a["role"]=="two" and (a.get("directory")!="G_two" or a.get("kind")!="two-decode" or a.get("same_prompt") is not False): raise ValueError("T06 two-decode must differ")
 if m.get("d15_training_route")!="G_seed12k/route" or set(m.get("heldout_routes",[]))!={"G_seed_45k/route","G_seed_real/route","G_two/route"}: raise ValueError("T06 D15 training/heldout route partition differs")
 return m
def execute(wt=WT,output_root=ROUNDS):
 if sys.platform!="linux": raise RuntimeError("T06 --run requires Linux GPU host")
 d=load_d07(); admission=packet(wt);receipt=require_d07();r041,t20=d.require_r041_kept(ROOT),d.require_t20_kept()
 if (output_root/RID).exists(): raise RuntimeError("T06 round already exists; no overwrite/retry-in-place")
 batch=d.load_owned_lifecycle().verified_module(ROOT/"runs/plan_batches/e2_launch.py",d.ATOMIC_HELPER_SHA,"t06_batch_reader").next_batch(output_root)
 owner=d.take_d07_gpu_lock(RID,batch);run=None;process=None
 try:
  idle=d.require_gpu_idle();run=output_root/RID;run.mkdir(parents=True);g_dirs={}
  for source in (__file__,SEED_CLIENT,D07_SOURCE): shutil.copy2(source,run/Path(source).name)
  d.write_new(run/"preflight.json",{**admission,"batch":batch,"gpu_owner":owner,"gpu_memory_mib":idle,"r041_closure":str(r041),"r041_closure_sha256":sha(r041),"t20_closure":str(t20),"t20_closure_sha256":sha(t20),"d07_receipt":str(receipt[0]),"d07_receipt_sha256":sha(receipt[0])})
  for role,seed in seed_paths().items():
   g=run/f"G_{role}";g.mkdir();route=g/"route";route.mkdir();g_dirs[role]=g;port=d.dynamic_fixture_port();process=d.start_server(g,wt,port,route);trace=g/f"trace_{role}.json";invoke_seed(wt,port,role,seed,trace,g/f"generate_{role}.log");d.load_owned_lifecycle().stop_owned_process(process);process=None;invoke_analysis(wt,g,run/f"route_summary_{role}.json",trace=trace)
  g=run/"G_two";g.mkdir();route=g/"route";route.mkdir();g_dirs["two"]=g;port=d.dynamic_fixture_port();process=d.start_server(g,wt,port,route);two=g/"two_decode.json";invoke_two(wt,port,two,g/"two_decode.log");d.load_owned_lifecycle().stop_owned_process(process);process=None;invoke_analysis(wt,g,run/"route_summary_two.json",two=two)
  write_new(run/"manifest.json",manifest(run,g_dirs,receipt,owner));validate_manifest(run)
  summaries={role:json.loads((run/f"route_summary_{role}.json").read_text()) for role in (*SEEDS,"two")}
  result={"schema":"ft_t06_raw_measurement/v1","round_id":RID,"card":"T06","title":"route trace and real suffix distribution (trace enabled)","epoch":2,"parent":"E2-R040","base":{"code_version":"E2-base.1@0aa23431","commit":CANDIDATE},"candidate_commit":CANDIDATE,"batch":batch,"verdict":"pending_review","proposed_verdict":"measured","raw_measurement_before_D04":True,"manifest":"manifest.json","manifest_sha256":sha(run/"manifest.json"),"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"actual_quality_from_route_summaries":summaries,"timing":"excluded from performance claims","anomalies":[]}
  write_new(run/"result.json",result)
  write_new(run/"metadata/pre_d04.json",{"schema":"ft_t06_pre_d04/v1","round_id":RID,"card":"T06","base":{"code_version":"E2-base.1@0aa23431","commit":CANDIDATE},"verdict":"pending_review","proposed_verdict":"measured","result":"result.json","result_sha256":sha(run/"result.json"),"route_summaries":{role:f"route_summary_{role}.json" for role in summaries},"canonical_round_json_created":False,"canonical_manifest_created":False})
  return result
 except BaseException as e:
  process=getattr(e,'owned_process',process)
  if run is not None: write_new(run/"failed_harness.json",{"rid":RID,"batch":batch,"gpu_owner":owner,"error":repr(e),"raw_measurement_preserved":True})
  raise
 finally:
  if process is not None: d.load_owned_lifecycle().stop_owned_process(process)
  d.release_d07_gpu_lock(owner)
  if run is not None: write_new(run/"owned_cleanup.json",{"schema":"ft_t06_owned_cleanup/v1","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"gpu_owner":owner,"lock_released":True})
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",action="store_true");p.add_argument("--worktree",type=Path,default=WT);p.add_argument("--output-root",type=Path,default=ROUNDS);a=p.parse_args(argv)
 print(json.dumps(execute(a.worktree,a.output_root) if a.run else packet(a.worktree),ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
