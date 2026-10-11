"""Prepare, never seal, the reviewed R018 D03 continuation gate."""
from __future__ import annotations
import argparse, hashlib, json, math, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

RID="E2-R018-gate-D03"; BATCH=46
CANONICAL_ROUND=Path('/data2/_shared/runs/ft_rounds')/RID
PARENT="c30ae0d7003c3bbbf56867ce74da797332fa7ed5"; CANDIDATE="f5067bbe05da51d5f78185213435a8be095a684a"
RAW_SHA="cfdd3a08f4af422178fdd72f058ea67783002fd0a506ca3388acaaae64b9b566"
RECEIPT_SHA="49a2fa4327613d639413e57a0d66115f3c0033c7508f91db8c97b3ffa1dba88b"
REVIEW_SHA="6c2a90d98c028ceaeff90d78a85e6eb75b368982a3114f2b6eed1524ea787243"
RECEIPT_PATH=Path('/data2/FreeToken/runs/dev_D03/launch_E2-R018-gate-D03.json')
RUNNER_SHA="29fa24ed89a3e35ddd0c426c67fa9c481f85d1700a5498a7c0abc8daab01e0c6"; BASE_SHA="51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16"
WRAPPER_SHA="d60333ffb4722d1d29e972129a08eb225cfc81ce0a257e2922379a90cd5746b1"
ARMS=tuple(f"{name}_b46" for name in ("PARENT","NEW","PARENT_P","NEW_P","CHUNK_PARENT","CHUNK_NEW","CHUNK_PARENT_P","CHUNK_NEW_P"))
CONTROL=("round.json","round_history","MANIFEST.sha256")
PID_RE=re.compile(r"['\"]?\.pid=(\d+)['\"]?")

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text(encoding="utf-8"))
 except Exception as e: raise ValueError(f"invalid JSON: {p}") from e
def jb(v): return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()
def require(p):
 p=Path(p)
 if not p.is_file() or p.is_symlink() or not p.stat().st_size: raise ValueError(f"missing or empty artifact: {p}")
 return p
def guarded_path(path):
 # Inspect the spelling before resolve so an ancestor symlink cannot disappear.
 raw=Path(os.path.abspath(path)); current=raw
 while True:
  if current.is_symlink():raise ValueError('symlink path or ancestor rejected: '+str(current))
  if current==current.parent:break
  current=current.parent
 return raw.resolve(strict=True)
def exact_round(path):
 resolved=guarded_path(path)
 if resolved!=CANONICAL_ROUND:raise ValueError('exact canonical R018 round required')
 return resolved
def terminal(pid):
 if type(pid) is not int or pid <= 0:raise ValueError('positive owned PID required')
 p=Path(f"/proc/{pid}/stat")
 if not p.exists():return True
 fields=p.read_text().rpartition(") ")[2].split()
 if len(fields)<4:raise ValueError('malformed process identity')
 return fields[0]=='Z'
def owned(d):
 uid=os.geteuid() if hasattr(os,'geteuid') else None
 for p in [d,*d.rglob("*")]:
  if p.is_symlink() or (uid is not None and p.stat().st_uid!=uid): raise ValueError(f"foreign owner or symlink rejected: {p}")
def finite(v):
 if isinstance(v,bool):return
 if isinstance(v,(int,float)):
  if not math.isfinite(v):raise ValueError("nonfinite metric")
 elif isinstance(v,list):
  for x in v:finite(x)
 elif isinstance(v,dict):
  for x in v.values():finite(x)
def arm(d,name):
 p=d/name
 payloads=("short.json","chunked.json") if name.startswith("CHUNK_") else ("det.json",)
 for f in ("SERVE_CMD.txt","serve.log","serve_args.txt","ENV.txt","tax.json","prefill_seq.txt",*payloads):require(p/f)
 m=PID_RE.findall((p/"serve_args.txt").read_text())
 if len(m)!=1 or not terminal(int(m[0])):raise ValueError(f"live or ambiguous service PID: {name}")
 expected=PARENT if name.startswith(("PARENT","CHUNK_PARENT")) else CANDIDATE
 if expected not in (p/"ENV.txt").read_text():raise ValueError(f"wrong source commit: {name}")
 return {"serve_cmd":f"{name}/SERVE_CMD.txt","serve_args":f"{name}/serve_args.txt","environment_snapshot":f"{name}/ENV.txt","owned_service_pid":int(m[0])}
def validate(d,review):
 d=exact_round(d); review=guarded_path(review)
 if d.name!=RID or any((d/x).exists() for x in CONTROL):raise ValueError("assigned unsealed round required")
 if review!=d/f"review_batch{BATCH}.json":raise ValueError("exact independent review path required")
 owned(d)
 review_path=require(review)
 if sha(review_path)!=REVIEW_SHA:raise ValueError('frozen independent review bytes mismatch')
 gate=load(require(d/f"gate_batch{BATCH}.json")); status=load(require(d/f"status_batch{BATCH}.json")); review=load(review_path)
 if sha(d/f"gate_batch{BATCH}.json")!=RAW_SHA:raise ValueError("actual gate SHA differs")
 if gate.get("arms")!=list(ARMS) or gate.get("candidate_case")!="D03-continuation" or gate.get("gate")!="D03" or gate.get("parent_commit")!=PARENT or gate.get("new_commit")!=CANDIDATE:raise ValueError("R018 gate identity/arms mismatch")
 for profile,rows in (("layer_major",13),("non_layer_major",23)):
  x=gate.get(profile,{}); pre=x.get("prefill",{})
  if pre.get("parent_rows")!=rows or pre.get("new_rows")!=rows:raise ValueError(f"{profile} prefill rows mismatch")
  if profile=="non_layer_major":
   for side in ("D0","PROD"):
    if set(x.get(side,{})) < {"short","chunked"}:raise ValueError("ordinary profile lacks short/chunked")
 finite(gate)
 if status.get("state")!="complete_measurements_pending_review" or status.get("batch_pid")!=3451139 or status.get("batch")!=BATCH or status.get("rid")!=RID or status.get("candidate_case")!="D03-continuation" or not terminal(3451139):raise ValueError("R018 terminal status mismatch")
 binding=require(d/"candidate_binding.json"); wrapper=require(d/f"batch{BATCH}.sh")
 if sha(wrapper)!=WRAPPER_SHA:raise ValueError("actual wrapper SHA mismatch")
 b=load(binding)
 if b.get("candidate_runner_sha256")!=RUNNER_SHA or b.get("base_runner_sha256")!=BASE_SHA:raise ValueError("archived runner/base mismatch")
 if sha(require(d/'runner_batch46.py'))!=RUNNER_SHA or sha(require(d/'base_runner_batch46.py'))!=BASE_SHA:raise ValueError('archived source bytes mismatch')
 if any(b.get(key)!=value for key,value in {'case':'D03-continuation','card':'D03','parent_commit':PARENT,'new_commit':CANDIDATE,'parent_wt':'e1r003st','new_wt':'e2d03-continuation'}.items()):raise ValueError('candidate binding identity mismatch')
 if b.get('compiled_extensions')!=gate.get('compiled_extensions'):raise ValueError('candidate extension evidence differs')
 receipt=require(RECEIPT_PATH)
 if sha(receipt)!=RECEIPT_SHA:raise ValueError('launch receipt bytes mismatch')
 receipt_doc=load(receipt)
 if any(receipt_doc.get(key)!=value for key,value in {'schema':'ft_candidate_gate_launch/v1','state':'launched','rid':RID,'batch':BATCH,'case':'D03-continuation','card':'D03','candidate_commit':CANDIDATE,'parent_commit':PARENT,'runner_sha256':RUNNER_SHA,'base_runner_sha256':BASE_SHA,'wrapper_sha256':WRAPPER_SHA,'batch_pid':3451139,'batch_pgid':3451139}.items()):raise ValueError('launch receipt identity mismatch')
 expected={"rid":RID,"batch":BATCH,"candidate_commit":CANDIDATE,"parent_commit":PARENT,"runner_sha256":RUNNER_SHA,"base_runner_sha256":BASE_SHA,"wrapper_sha256":WRAPPER_SHA,"batch_pid":3451139}
 if any(review.get(k)!=v for k,v in {**expected,"schema":"ft_independent_raw_review/v1","reviewer":"/root/d06_server_review","scope":"raw measurement replay and source integrity; not formal acceptance","receipt_sha256":RECEIPT_SHA,"formal_verdict":"pending_review","verdict":"PASS","gate_sha256":RAW_SHA,"candidate_binding_sha256":sha(binding)}.items()):raise ValueError("independent review binding mismatch")
 return d,gate,status,review,binding,wrapper
def prepare(directory,review,now=None):
 d,gate,status,review,binding,wrapper=validate(directory,review)
 out=d/"initial_metadata.json"
 if out.exists():raise FileExistsError("initial metadata retained")
 # Validate every original arm and any pre-existing wrapper alias before a write.
 arms={n:arm(d,n) for n in ARMS}
 archive=d/"batch.sh"
 if archive.exists() and archive.read_bytes()!=wrapper.read_bytes():raise ValueError("aliased wrapper mismatch")
 created=(now or datetime.now(timezone(timedelta(hours=8)))).strftime("%F %T CST")
 doc={"schema":"ft_round/v2","round_id":RID,"epoch":2,"card":"T16","title":"D03 continuation default-path gate","created_at":created,"parent":"E2-R002-gate-D03","base":{"repo":"fork/FreeToken","commit":PARENT,"branch":"exp/e1r003-statetools","worktree":"/data2/FreeToken/wt/e1r003st","freetoken_file":"/data2/FreeToken/wt/e1r003st/python/freetoken/__init__.py"},"experimental":{"candidate_commit":CANDIDATE,"branch":"exp/e2d03-continuation","worktree":"/data2/FreeToken/wt/e2d03-continuation","freetoken_file":"/data2/FreeToken/wt/e2d03-continuation/python/freetoken/__init__.py","path_source":f"gate_batch{BATCH}.json"},"design":{"batch":BATCH,"gate":"D03","serve_order":list(ARMS),"first_shot_policy":"preserved individually; no aggregate performance verdict"},"serve":{"arms":arms},"results":{"layer_major":gate["layer_major"],"non_layer_major":gate["non_layer_major"]},"first_shots":[{"profile":p,"side":s,"case":c,"records":v.get("records",[]),"claim":"timing preserved; not a performance claim"} for p in ("layer_major","non_layer_major") for s in ("D0","PROD") for c,v in gate[p][s].items() if isinstance(v,dict) and "records" in v],"diagnostics":{"gate_path":f"gate_batch{BATCH}.json","gate_sha256":RAW_SHA,"status_path":f"status_batch{BATCH}.json","review_sha256":sha(d/f"review_batch{BATCH}.json"),"candidate_binding_sha256":sha(binding),"batch_wrapper_sha256":sha(wrapper)},"sub_conclusions":[{"id":"SC1","status":"pending","text":"D03 continuation gate evidence awaits formal independent review."}],"verdict":"pending_review","proposed_verdict":None,"verdict_history":[],"retractions":[],"histories":[]}
 with out.open("xb") as f:f.write(jb(doc))
 if archive.exists():
  pass
 else:
  with archive.open("xb") as f:f.write(wrapper.read_bytes())
 return {"initial_metadata_sha256":sha(out),"batch_sha256":sha(archive)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--round-dir",type=Path);p.add_argument("--review",type=Path);a=p.parse_args()
 if not a.round_dir or not a.review:p.error("--round-dir and --review required")
 print(json.dumps(prepare(a.round_dir,a.review),sort_keys=True))
if __name__=="__main__":main()
