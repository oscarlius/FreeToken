"""Prepare E2-R040 failed-harness metadata; default CLI only writes a proposal."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
RID="E2-R040";BATCH=71;CANDIDATE="0aa23431e5b800797543bdecbf35a01045131d7d";REVIEW_SHA="b59ad3d582489bc2bbb14527f1acaaa720145dc6d157030edd1ef475be35befc";RECEIPT_SHA="3e8152aeb10a48cddf498a445cff962679c2673c1236925d8ba25d14b20c0010";FAILED_SHA="de9e81a2a379059726e98fff977503f86a5482686c23abdf3ed7ae5884e5ebf0"
ARMS=("PRODUCTION","OFF_p1","ON_p1","OFF_p2","ON_p2","OFF_p3","ON_p3")
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def rec(root,p):
 q=Path(p);q=q if q.is_absolute() else root/q
 return {"path":str(q) if Path(p).is_absolute() else Path(p).as_posix(),"sha256":sha(q)}
def metadata(root,review,receipt):
 st=root/f"status_batch{BATCH}.json";status=json.loads(st.read_text());rv=json.loads(review.read_text());rc=json.loads(receipt.read_text())
 if (status.get("rid"),status.get("batch"),status.get("state"))!=(RID,BATCH,"failed") or not isinstance(status.get("batch_pid"),int):raise ValueError("failed status required")
 if sha(review)!=REVIEW_SHA or (rv.get("schema"),rv.get("rid"),rv.get("batch"),rv.get("verdict"))!=("ft_t20_r040_partial_observation_review/v1",RID,BATCH,"PARTIAL_MEASUREMENTS_PENDING_USER_DISPOSITION"):raise ValueError("partial review pin differs")
 if rv.get("terminal_failure",{}).get("status_sha256")!=sha(st) or rv.get("terminal_failure",{}).get("failed_harness_sha256")!=FAILED_SHA:raise ValueError("review terminal binding differs")
 if sha(receipt)!=RECEIPT_SHA or (rc.get("schema"),rc.get("state"),rc.get("rid"),rc.get("batch"),rc.get("candidate_commit"))!=("ft_t20_actual_launch/v1","launched",RID,BATCH,CANDIDATE) or rc.get("batch_pid")!=status["batch_pid"]:raise ValueError("receipt differs")
 arms=sorted(p.parent.relative_to(root).as_posix() for p in root.rglob("SERVE_CMD.txt"));archive={"missing_serve_args":[],"missing_environment":[]}
 for arm in arms:
  source=next((x for x in ("source.json","environment.json","compiled_extensions.json") if (root/arm/x).is_file()),None)
  source_record=rec(root,Path(arm)/source) if source else rec(root,"execution_archive.json")
  ev=[source_record,rec(root,Path(arm)/"SERVE_CMD.txt"),rec(root,Path(arm)/"serve.log"),rec(root,st.name),rec(root,receipt)]
  for f,k in (("serve_args.txt","missing_serve_args"),("ENV.txt","missing_environment")):
   if not (root/arm/f).is_file():archive[k].append({"arm":arm,"reason":f"failed harness retained no {f}","evidence":ev})
 failed=root/"failed_harness.json"
 if sha(failed)!=FAILED_SHA:raise ValueError("failed receipt pin differs")
 return {"schema":"ft_round/v2","round_id":RID,"epoch":2,"card":"T20","created_at":datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S CST"),"base":{"commit":CANDIDATE,"code_version":"E2-base.1@0aa23431"},"verdict":"pending_review","proposed_verdict":"failed_harness","verdict_history":[],"retractions":[],"serve":{"arms":{a:{} for a in arms}},"results":{"started_service_arms":float(len(arms)),"partial_review_artifacts":1.0},"failure_archive":archive,"proofs":{"partial_review":rec(root,review),"terminal_status":rec(root,st.name),"launch_receipt":rec(root,receipt),"failed_receipt":rec(root,failed)}}
def main():
 p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--review",type=Path,required=True);p.add_argument("--receipt",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(metadata(a.root,a.review,a.receipt),indent=2)+"\n")
if __name__=="__main__":main()
