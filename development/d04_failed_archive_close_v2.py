"""Failed-harness-only adapter around the pinned initial atomic publisher."""
from __future__ import annotations
import hashlib, importlib.util, json, math, os, stat, subprocess, sys
from datetime import datetime
from pathlib import Path

MISSING={"serve_args.txt":"missing_serve_args","ENV.txt":"missing_environment"}
RID="E2-R040";BATCH=71;CANDIDATE="0aa23431e5b800797543bdecbf35a01045131d7d"
REVIEW_SHA="b59ad3d582489bc2bbb14527f1acaaa720145dc6d157030edd1ef475be35befc"
RECEIPT_SHA="3e8152aeb10a48cddf498a445cff962679c2673c1236925d8ba25d14b20c0010"
FAILED_SHA="de9e81a2a379059726e98fff977503f86a5482686c23abdf3ed7ae5884e5ebf0"
GENERIC_SHA="dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835"
WRITER_SHA="67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"
def sha(p):
 h=hashlib.sha256();
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def load_generic(path):
 if sha(path)!=GENERIC_SHA:raise ValueError("initial publisher pin differs")
 s=importlib.util.spec_from_file_location("initial_close",path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def _proof(root,item):
 q=Path(item["path"]);q=q if q.is_absolute() else root/q
 if not q.is_file() or sha(q)!=item["sha256"]:raise ValueError("proof SHA differs")
 return json.loads(q.read_text())
def validate(root,doc):
 if (doc.get("schema"),doc.get("verdict"),doc.get("proposed_verdict"))!=("ft_round/v2","pending_review","failed_harness"):raise ValueError("failed-harness pending close only")
 if (root.name!=RID or doc.get('round_id')!=RID or type(doc.get('epoch')) is not int
     or doc['epoch']!=2 or doc.get('card')!='T20'
     or doc.get('base')!={'commit':CANDIDATE,'code_version':'E2-base.1@0aa23431'}
     or doc.get('verdict_history')!=[] or doc.get('retractions')!=[]):
  raise ValueError('exact R040 round identity and empty initial history required')
 if (root/"round.json").exists() or (root/"round_history").exists() or (root/"MANIFEST.sha256").exists():raise ValueError("open root required")
 if not isinstance(doc.get("created_at"),str) or not doc.get("results") or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in doc["results"].values()):raise ValueError("created_at and finite results required")
 try:datetime.strptime(doc['created_at'],'%Y-%m-%d %H:%M:%S CST')
 except ValueError as error:raise ValueError('created_at CST format differs') from error
 arms=doc.get("serve",{}).get("arms",{});archive=doc.get("failure_archive",{})
 actual={p.parent.relative_to(root).as_posix() for p in root.rglob("SERVE_CMD.txt")}
 if set(arms)!=actual or len(actual)!=24 or doc["results"].get("started_service_arms")!=24.0 or doc["results"].get("partial_review_artifacts")!=1.0:raise ValueError("complete 24-arm inventory and numeric results required")
 proofs=doc.get("proofs")
 if not isinstance(proofs,dict) or set(proofs)!={"partial_review","terminal_status","launch_receipt","failed_receipt"}:raise ValueError("complete proof bindings required")
 parsed={}
 for key,item in proofs.items():
  if not isinstance(item,dict) or not isinstance(item.get("path"),str) or not isinstance(item.get("sha256"),str):raise ValueError("invalid proof")
  parsed[key]=_proof(root,item)
 if proofs["partial_review"]["sha256"]!=REVIEW_SHA or proofs["launch_receipt"]["sha256"]!=RECEIPT_SHA or proofs["failed_receipt"]["sha256"]!=FAILED_SHA:raise ValueError("immutable proof pin differs")
 st,rv,rc,fh=parsed["terminal_status"],parsed["partial_review"],parsed["launch_receipt"],parsed["failed_receipt"]
 if (st.get("rid"),st.get("batch"),st.get("state"))!=(RID,BATCH,"failed") or not isinstance(st.get("batch_pid"),int):raise ValueError("terminal status differs")
 if (rv.get("schema"),rv.get("rid"),rv.get("batch"),rv.get("verdict"))!=("ft_t20_r040_partial_observation_review/v1",RID,BATCH,"PARTIAL_MEASUREMENTS_PENDING_USER_DISPOSITION") or rv.get("terminal_failure",{}).get("status_sha256")!=proofs["terminal_status"]["sha256"]:raise ValueError("partial review differs")
 if (rc.get("schema"),rc.get("state"),rc.get("rid"),rc.get("batch"),rc.get("candidate_commit"))!=("ft_t20_actual_launch/v1","launched",RID,BATCH,CANDIDATE) or rc.get("batch_pid")!=st["batch_pid"]:raise ValueError("launch receipt differs")
 if (fh.get("schema"),fh.get("admitted"))!=("ft_t17_continuation_failure/v1",False):raise ValueError("failed receipt differs")
 if len(archive.get("missing_serve_args",[]))!=7 or len(archive.get("missing_environment",[]))!=7:raise ValueError("exact seven missing-runtime records required")
 for arm in arms:
  for file,key in MISSING.items():
   if (root/arm/file).is_file():continue
   rows=[x for x in archive.get(key,[]) if isinstance(x,dict) and x.get("arm")==arm]
   if len(rows)!=1:raise ValueError(f"missing failed archive {arm}/{file}")
   paths={x.get("path") for x in rows[0].get("evidence",[]) if isinstance(x,dict)}
   source_any={f"{arm}/source.json",f"{arm}/environment.json",f"{arm}/compiled_extensions.json","execution_archive.json"}
   if not ({f"{arm}/SERVE_CMD.txt",f"{arm}/serve.log","status_batch71.json"}<=paths and paths.intersection(source_any)) or not any(Path(x).is_absolute() for x in paths if x):raise ValueError("incomplete failed evidence")
   for x in rows[0]["evidence"]:
    q=Path(x["path"]);q=q if q.is_absolute() else root/q
    if not q.is_file() or x.get("sha256")!=sha(q):raise ValueError("evidence changed")
def initial_publish(root,doc,generic_path,*,inject=None):
 validate(root,doc);g=load_generic(generic_path); mode=stat.S_IMODE(root.stat().st_mode)
 try:
  os.chmod(root,mode|stat.S_IWUSR);g.publish(root,g.build_control(root,doc),inject=inject)
 finally: os.chmod(root,mode)
def append_failed(root,writer,reason,evidence):
 if sha(writer)!=WRITER_SHA:raise ValueError("round writer pin differs")
 return subprocess.run([sys.executable,str(writer),str(root),"verdict","--new","failed_harness","--reason",reason,"--evidence",evidence,"--by","t20-failed-close-v1"],check=True,capture_output=True,text=True)
