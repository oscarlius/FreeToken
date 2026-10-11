"""Read-only E2-R046 failed-harness D04 metadata proposal; never publishes controls."""
from __future__ import annotations
import argparse, hashlib, json, os, stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

RID="E2-R046"; BATCH=73; COMMIT="0aa23431e5b800797543bdecbf35a01045131d7d"
TERMINAL_SHA="0edd19926ef45f56887f6889572f9d2524dd1958d992ce40730ae8da5310aa24"
FAILED_SHA="9204350666f98063ca3992bb675f8a0e4fc5492f34f64c64e4980905857862aa"
CLEANUP_SHA="16793f27ba8b45acd7063f5c26d99bc1885c17057d14d3bc40f58314c840be7d"
COLD_SHA="0ccee4b9e5a0917b5284a334acc3f0ca3bd5b871d287f674eca907b7f1f47d6d"
REVIEW_SHA="e42524eee0ec7ea5e9e971528b2a14f953306d58968712ed7826ba1264779450"
ARMS=("g3g4/g3_off","g3g4/g3_on")

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def record(root,p):
 p=Path(p); q=p if p.is_absolute() else root/p
 return {"path":str(p) if p.is_absolute() else p.as_posix(),"sha256":sha(q),"size_bytes":q.stat().st_size}
def read(p): return json.loads(Path(p).read_text())

def prepare(root,terminal,review):
 root=Path(root); terminal=Path(terminal); review=Path(review)
 if root.name!=RID or root.is_symlink() or stat.S_IMODE(root.stat().st_mode)&0o222: raise ValueError("readonly non-symlink R046 root required")
 if any((root/x).exists() for x in ("round.json","round_history","MANIFEST.sha256")): raise ValueError("open failed round required")
 if sha(terminal)!=TERMINAL_SHA: raise ValueError("terminal receipt pin differs")
 if sha(review)!=REVIEW_SHA: raise ValueError("G3-off review pin differs")
 term=read(terminal); failure=read(root/"failed_harness.json"); cleanup=read(root/"owned_cleanup.json"); rv=read(review)
 if (term.get("rid"),term.get("batch"),term.get("state"))!=(RID,BATCH,"failed_harness_pending_D04") or not all(term.get(k) is True for k in ("controller_absent","service_absent","lock_released","round_tree_readonly")): raise ValueError("terminal observation identity differs")
 if term.get("files_sha256",{}).get("failed_harness.json")!=FAILED_SHA or term["files_sha256"].get("owned_cleanup.json")!=CLEANUP_SHA or term["files_sha256"].get("g3g4/g3_off/cold.json")!=COLD_SHA or term.get("full_raw_hash_performed") is not False: raise ValueError("terminal evidence binding differs")
 if not (root/"preflight.json").is_file() or term["files_sha256"].get("preflight.json")!=sha(root/"preflight.json"): raise ValueError("preflight evidence differs")
 if sha(root/"failed_harness.json")!=FAILED_SHA or (failure.get("rid"),failure.get("batch"))!=(RID,BATCH) or "TimeoutError" not in failure.get("error",""): raise ValueError("failure evidence differs")
 owner=failure.get("gpu_owner",{}); clean_owner=cleanup.get("gpu_owner",{})
 if sha(root/"owned_cleanup.json")!=CLEANUP_SHA or (cleanup.get("rid"),cleanup.get("batch"),cleanup.get("candidate_commit"))!=(RID,BATCH,COMMIT) or cleanup.get("lock_released") is not True or clean_owner.get("execution_id")!=owner.get("execution_id") or clean_owner.get("pid")!=owner.get("pid") or clean_owner.get("start_ticks")!=owner.get("start_ticks"): raise ValueError("cleanup/birth binding differs")
 if (rv.get("schema"),rv.get("rid"),rv.get("batch"),rv.get("verdict"))!=("ft_r046_live_incremental_g3off_review/v1",RID,BATCH,"G3_OFF_PASS_PENDING_ON_COMPARISON") or rv.get("candidate_commit",COMMIT)!=COMMIT or rv.get("cold",{}).get("sha256")!=COLD_SHA: raise ValueError("G3-off review identity differs")
 arms=sorted(p.parent.relative_to(root).as_posix() for p in root.rglob("SERVE_CMD.txt"))
 if tuple(arms)!=ARMS: raise ValueError("expected exactly G3 off/on started arms")
 off=root/ARMS[0]; on=root/ARMS[1]
 if sha(off/"cold.json")!=COLD_SHA or (on/"cold.json").exists(): raise ValueError("G3 output presence differs")
 missing={"missing_environment":[],"missing_serve_args":[]}
 for arm in arms:
  if not all((root/arm/name).is_file() for name in ("SERVE_CMD.txt","serve.log","owned_process.json")): raise ValueError(f"missing retained source proof for {arm}")
  evidence=[record(root,f"{arm}/SERVE_CMD.txt"),record(root,f"{arm}/serve.log"),record(root,f"{arm}/owned_process.json"),record(root,"preflight.json"),record(root,terminal)]
  for filename,key in (("ENV.txt","missing_environment"),("serve_args.txt","missing_serve_args")):
   if (root/arm/filename).exists(): raise ValueError(f"unexpected retained {arm}/{filename}")
   missing[key].append({"arm":arm,"reason":f"batch73 failed before retained {filename}","evidence":evidence})
 created=datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST")
 proofs={"terminal_observation":record(root,terminal),"failed_harness":record(root,"failed_harness.json"),"owned_cleanup":record(root,"owned_cleanup.json"),"preflight":record(root,"preflight.json"),"g3_off_review":record(root,review),"g3_off_cold":record(root,f"{ARMS[0]}/cold.json")}
 metadata={"schema":"ft_round/v2","round_id":RID,"epoch":2,"card":"D07_G3G4_T06","created_at":created,"base":{"commit":COMMIT,"code_version":"E2-base.1@0aa23431"},"verdict":"pending_review","proposed_verdict":"failed_harness","verdict_history":[],"retractions":[],"results":{"started_service_arms":2.0,"completed_cold_arms":1.0,"failed_harness_events":1.0},"serve":{"arms":{a:{} for a in arms}},"failure_archive":missing,"proofs":proofs,"missing_outputs":[{"arm":ARMS[1],"path":f"{ARMS[1]}/cold.json","reason":"timeout before first SSE event; no output fabricated"}]}
 return {"schema":"ft_r046_failed_harness_proposal/v2","mode":"readonly_proposal","round_id":RID,"batch":BATCH,"candidate_commit":COMMIT,"created_at":created,"proposed_metadata":metadata,"proofs":proofs,"formal_close_recipe":{"source_precedent":"development/p0_failed_harness_close.py","initial_control_builder":"development/initial_measurement_close.py:build_control/publish","verdict_appender":"scripts/round_json_append.py verdict --new failed_harness","requires":"root-coordinated one-time raw manifest hash and D04 independent review; this tool never publishes"}}
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--terminal',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(prepare(a.root,a.terminal,a.review),indent=2)+'\n')
if __name__=='__main__':main()
