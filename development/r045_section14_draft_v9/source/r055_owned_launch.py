"""Atomic owned launch for E2-R055-gate-D06; default invocation is inert."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from types import SimpleNamespace
ROOT=Path("/data2/FreeToken"); DEV=Path(__file__).resolve().parent
PARENT_COMMIT="0aa23431e5b800797543bdecbf35a01045131d7d"
CANDIDATE_COMMIT="effb9969706922ddad9e59b96377e46469ebe97f"
RID="E2-R055-gate-D06"; CARD="D06"; ADAPTER="r055_gate_d06_prepare.py"; RECEIPT_SCHEMA="ft_r055_owned_launch/v1"; RECEIPT_WAIT_SECONDS=30
NATIVE_REUSE=ROOT/"runs/dev_D07/effb996_native_reuse_20261007.json"
NATIVE_REUSE_SHA="092d6f64c14a6c27f918cfc6f33336496909de09a02d950e153399107c1fa767"
PARENT_NATIVE=ROOT/"runs/dev_T16/r051_eff_parent_native_provenance_20261007.json"
PARENT_NATIVE_SHA="adeb2ccd8378f4b6ac78313a4ec23f3104381fb533939f18b36dc5ba6ef27bfc"

def d07():
 p=DEV/"d07_g3g4_prepare.py"; s=importlib.util.spec_from_file_location("r055_d07",p); m=importlib.util.module_from_spec(s); assert s.loader; s.loader.exec_module(m); return m

SOURCE_DEPENDENCIES=(Path(__file__).name,ADAPTER,"d07_g3g4_prepare.py","t16_private_port_base_runner.py","t17_d14_runner.py","t17_d14_observe.py","t16_full_tail_base_runner.py")
def source_hashes():
 return {n:hashlib.sha256((DEV/n).read_bytes()).hexdigest() for n in SOURCE_DEPENDENCIES}
def review_path(): return ROOT/"runs/dev_R055/reviews"/f"{RID}_startup_review_v2.json"
def require_leaf_review():
 p=review_path()
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222: raise RuntimeError("R055 startup review is absent or writable")
 try: doc=json.loads(p.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as e: raise RuntimeError("R055 startup review is unreadable") from e
 expected={"schema":"ft_r055_startup_review/v1","rid":RID,"card":CARD,"candidate_commit":CANDIDATE_COMMIT,"parent_commit":PARENT_COMMIT,"verdict":"PASS","approved":True,"source_sha256":source_hashes()}
 if any(doc.get(k)!=v for k,v in expected.items()): raise RuntimeError("R055 startup review binding differs")
 return p

def require_candidate():
 wt=ROOT/"wt/e2base1-p1"
 if wt.is_symlink(): raise RuntimeError("R055 candidate worktree is symlinked")
 try:
  head=subprocess.check_output(["git","-C",str(wt),"rev-parse","HEAD"],text=True).strip(); dirty=subprocess.check_output(["git","-C",str(wt),"status","--porcelain","--untracked-files=no"],text=True); ancestor=subprocess.run(["git","-C",str(wt),"merge-base","--is-ancestor",PARENT_COMMIT,"HEAD"],check=False).returncode
 except (OSError,subprocess.CalledProcessError) as e: raise RuntimeError("R055 candidate worktree is unavailable") from e
 if head!=CANDIDATE_COMMIT or dirty or ancestor: raise RuntimeError("R055 candidate worktree identity, cleanliness, or ancestry differs")
 return wt

def require_native_reuse():
    """Bind only the two sealed native-import receipts; never rebuild or scan modules here."""
    for path, expected in ((NATIVE_REUSE,NATIVE_REUSE_SHA),(PARENT_NATIVE,PARENT_NATIVE_SHA)):
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise RuntimeError("R055 native provenance receipt is absent or writable")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError("R055 native provenance receipt binding differs")
    return {"eff_native_reuse":str(NATIVE_REUSE),"eff_native_reuse_sha256":NATIVE_REUSE_SHA,"parent_native_provenance":str(PARENT_NATIVE),"parent_native_provenance_sha256":PARENT_NATIVE_SHA}

def admission(g):
 if g.LOCK.exists() or g.LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists; R055 remains queued")
 g.require_r041_kept(ROOT); require_candidate(); require_native_reuse(); require_leaf_review()
def argv(batch,receipt): return [str(ROOT/"venv/bin/python"),str(Path(__file__).resolve()),"--run","--owned-child","--batch",str(batch),"--launch-receipt",str(receipt)]
def publish_binding(owned,path,receipt,child):
 if path.is_symlink() or not path.is_file() or receipt.get("state")!="launched": raise RuntimeError("R055 launch receipt is not publishable")
 raw,stat=path.read_bytes(),path.stat()
 if json.loads(raw)!=receipt: raise RuntimeError("R055 receipt changed before child binding")
 value={**receipt,"child":child}; owned.publish_receipt(path,(stat.st_dev,stat.st_ino),value); return value

def controller():
 if sys.platform!="linux": raise RuntimeError("R055 requires the Linux GPU host")
 g=d07(); admission(g); owned=g.load_owned_lifecycle(); helper=owned.verified_module(ROOT/"runs/plan_batches/e2_launch.py",g.ATOMIC_HELPER_SHA,"r055_atomic")
 batch=helper.next_batch(g.ROUNDS); receipt=ROOT/"runs/dev_R055"/f"launch_{RID}_batch{batch}.json"; receipt.parent.mkdir(parents=True,exist_ok=True); child_argv=argv(batch,receipt)
 reserved={"schema":RECEIPT_SCHEMA,"state":"reserved","rid":RID,"batch":batch,"candidate_commit":CANDIDATE_COMMIT,"argv_sha256":g.argv_sha256(child_argv),"controller":g.process_birth()}
 got=owned.reserve_process(helper,batch,RID,child_argv,receipt,reserved); birth=owned.process_identity(got["batch_pid"])
 if birth is None: raise RuntimeError("R055 reserved child birth is unavailable")
 child={"pid":birth["pid"],"start_ticks":birth["start_ticks"],"execution_id":f"{birth['pid']}:{birth['start_ticks']}"}; return publish_binding(owned,receipt,got,child)

def require_receipt(g,batch,path):
 mine,expect=g.process_birth(),g.argv_sha256(argv(batch,path)); static={"schema":RECEIPT_SCHEMA,"rid":RID,"batch":batch,"candidate_commit":CANDIDATE_COMMIT,"argv_sha256":expect}; deadline=time.monotonic()+RECEIPT_WAIT_SECONDS
 while time.monotonic()<deadline:
  if path.is_symlink(): raise RuntimeError("R055 child receipt is symlinked")
  if not path.is_file(): time.sleep(.05); continue
  try: doc=json.loads(path.read_text(encoding="utf-8"))
  except (OSError,json.JSONDecodeError) as e: raise RuntimeError("R055 child receipt is unreadable") from e
  if any(doc.get(k)!=v for k,v in static.items()): raise RuntimeError("R055 child launch receipt binding differs")
  if doc.get("state")=="reserved": time.sleep(.05); continue
  if doc.get("state")!="launched" or doc.get("child")!=mine or doc.get("batch_pid")!=mine["pid"]: raise RuntimeError("R055 child launch receipt binding differs")
  return doc
 raise RuntimeError("R055 child lacks its controller-bound launch receipt")

def pause_request(port, seconds, timeout):
    request=urllib.request.Request(f"http://127.0.0.1:{port}/dev/pause", data=json.dumps({"seconds":seconds,"timeout":timeout}).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=timeout+2) as response:
        return json.load(response)


PAUSE_OBSERVER = '''import json,os,time
from pathlib import Path
def _emit(kind, **fields):
    row={"kind":kind,"time_ns":time.time_ns(),"pid":os.getpid(),"service_pid":int(os.environ["R055_SERVICE_PID"]),"service_birth":json.loads(os.environ["R055_SERVICE_BIRTH"]),**fields}
    with Path(os.environ["R055_PAUSE_OBSERVATIONS"]).open("a",encoding="utf-8") as stream: stream.write(json.dumps(row,sort_keys=True)+"\\n")
def install():
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    process,reply=Scheduler._process_one_msg,SchedulerIOMixin._reply_tokenizer_rank0
    def seen(self,msg):
        name=type(msg).__name__
        if name in ("DevPauseBackendMsg","DevPauseCancelBackendMsg"):_emit("backend",message=name,request_id=str(msg.request_id))
        elif name=="UserMsg":_emit("input",uid=str(msg.uid))
        return process(self,msg)
    def delivered(self,messages):
        for msg in messages:
            name=type(msg).__name__
            if name=="DevPauseResultMsg":_emit("pause_result",request_id=str(msg.request_id),status=str(msg.status))
            elif name=="DetokenizeMsg" and bool(msg.finished):_emit("delivery",uid=str(msg.uid),token=int(msg.next_token))
        return reply(self,messages)
    Scheduler._process_one_msg=seen; SchedulerIOMixin._reply_tokenizer_rank0=delivered
'''

PAUSE_STARTUP = '''import json,os,sys
from pathlib import Path
if "R055_SERVICE_PID" not in os.environ:
    fields=(Path("/proc")/str(os.getpid())/"stat").read_text().rpartition(") ")[2].split()
    birth={"pid":os.getpid(),"start_ticks":int(fields[19]),"execution_id":f"{os.getpid()}:{int(fields[19])}","pgid":int(fields[2]),"session":int(fields[3]),"state":fields[0]}
    os.environ["R055_SERVICE_PID"]=str(os.getpid())
    os.environ["R055_SERVICE_BIRTH"]=json.dumps(birth,sort_keys=True)
import r055_pause_observer
r055_pause_observer.install()
from freetoken.cli import main
sys.argv=["ft",*sys.argv[1:]]
if __name__ == "__main__": main()
'''

def _freeze_pause_observer(run):
    observer, startup=run/"r055_pause_observer.py",run/"r055_pause_startup.py"
    for path,content in ((observer,PAUSE_OBSERVER),(startup,PAUSE_STARTUP)):
        with path.open("x",encoding="utf-8",newline="\n") as handle: handle.write(content)
        path.chmod(0o444)
    return startup


def _trace_pause_backend(run, normal_id, cancel_id):
    path=run/"pause_observations.jsonl"
    if path.is_symlink() or not path.is_file(): raise RuntimeError("R055 pause observer evidence is absent")
    rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows: raise RuntimeError("R055 pause observer produced no backend evidence")
    owned=json.loads((run/"owned_process.json").read_text(encoding="utf-8"))
    birth=owned.get("birth")
    if not isinstance(birth,dict): raise RuntimeError("R055 pause owned process birth is absent")
    identity={key:birth.get(key) for key in ("pid","start_ticks","execution_id","pgid","session")}
    if any(row.get("service_pid") != owned.get("pid") or {key:row.get("service_birth",{}).get(key) for key in identity} != identity for row in rows):
        raise RuntimeError("R055 pause observer service PID/birth differs")
    def one(kind, request_id, message=None):
        hits=[row for row in rows if row.get("kind")==kind and row.get("request_id")==request_id and (message is None or row.get("message")==message)]
        if len(hits)!=1: raise RuntimeError("R055 pause backend evidence is missing or ambiguous")
        return hits[0]
    accepted=one("backend",normal_id,"DevPauseBackendMsg")
    result=one("pause_result",normal_id)
    if result.get("status") != "accepted": raise RuntimeError("R055 pause backend did not accept the real request")
    cancelled=one("backend",cancel_id,"DevPauseCancelBackendMsg")
    after_inputs=[row for row in rows if row.get("kind")=="input" and row["time_ns"] > cancelled["time_ns"]]
    if len(after_inputs)!=1: raise RuntimeError("R055 post-cancel ordinary input is missing or ambiguous")
    delivered=[row for row in rows if row.get("kind")=="delivery" and row.get("uid")==after_inputs[0].get("uid")]
    if len(delivered)!=1 or delivered[0].get("pid") != after_inputs[0].get("pid"):
        raise RuntimeError("R055 post-cancel ordinary delivery did not use the same backend process")
    return {"observer":str(path),"service":birth,"accepted_backend":accepted,"accepted_result":result,"cancel_backend":cancelled,"post_cancel":{"input":after_inputs[0],"delivery":delivered[0]}}


def pause_smoke(gate, batch, run=None):
    """A real, dynamically-port-bound service check; no CPU test calls this function."""
    run=ROOT/"runs/dev_R055"/f"{RID}_batch{batch}_pause_smoke" if run is None else Path(run)
    run.mkdir(parents=True,exist_ok=False); port=gate.dynamic_fixture_port(); proc=None; prior_argv=None
    previous_observer=os.environ.get("R055_PAUSE_OBSERVATIONS")
    try:
        # Keep D07 immutable: temporarily supply an arm-local startup command
        # which observes real scheduler backend/control messages in its owned PGID.
        if callable(getattr(gate,"serve_argv",None)):
            startup=_freeze_pause_observer(run); prior_argv=gate.serve_argv
            gate.serve_argv=lambda _port:[str(gate.VENV/"bin/python"),str(startup)] + prior_argv(_port)[1:]
            os.environ["R055_PAUSE_OBSERVATIONS"]=str(run/"pause_observations.jsonl")
        worktree=require_candidate()
        if prior_argv is not None:
            env=gate.clean_environment(worktree,trace_dir=run/"route")
            selected={key:env.get(key) for key in ("CUDA_VISIBLE_DEVICES","FT_DEV_PAUSE_ENDPOINT","FT_DEV_ROUTE_TRACE","PYTHONPATH","VIRTUAL_ENV","PATH")}
            (run/"ENV.txt").write_text(json.dumps({"worktree":str(worktree),"candidate_commit":CANDIDATE_COMMIT,"environment":selected},sort_keys=True,indent=2)+"\n",encoding="utf-8")
        proc=gate.start_server(run, worktree, port, run/"route")
        if prior_argv is not None:
            text=(run/"serve.log").read_text(encoding="utf-8")
            position=text.find("Parsed arguments")
            if position < 0: raise RuntimeError("R055 pause service did not publish parsed arguments")
            (run/"serve_args.txt").write_text("\n".join(text[position:].splitlines()[:2])+"\n",encoding="utf-8")
        gate.invoke_cold_eq(require_candidate(),port,f"{RID}-pause-before",run/"before.json")
        # The first request is accepted at its safe point but remains active for
        # a full second.  The second request is therefore pending in the real
        # backend when its own API deadline expires and emits its cancel message.
        normal=pause_request(port,1.0,5.0); (run/"pause_completed.json").write_text(json.dumps(normal,indent=2)+"\n")
        cancel=pause_request(port,30.0,0.05)
        (run/"pause_cancel.json").write_text(json.dumps(cancel,indent=2)+"\n")
        gate.invoke_cold_eq(require_candidate(),port,f"{RID}-pause-after-cancel",run/"after_cancel.json")
        if not isinstance(normal,dict) or normal.get("status") != "accepted" or not isinstance(normal.get("request_id"),str) or not normal["request_id"]:
            raise RuntimeError("R055 pause endpoint lacks an accepted request identity")
        if (not isinstance(cancel,dict) or cancel.get("status") != "timeout" or not isinstance(cancel.get("request_id"),str)
                or not cancel["request_id"] or cancel.get("request_id") == normal.get("request_id")
                or "cancel enqueue" in str(cancel.get("error", ""))):
            raise RuntimeError("R055 pause cancel lacks a verified API cancellation receipt")
        evidence=_trace_pause_backend(run,normal["request_id"],cancel["request_id"]) if prior_argv is not None else {"test_double":True}
        return {"run":str(run),"port":port,"owned_process":str(run/"owned_process.json"),"before":str(run/"before.json"),"pause":str(run/"pause_completed.json"),"cancel":str(run/"pause_cancel.json"),"after_cancel":str(run/"after_cancel.json"),"backend_evidence":evidence}
    finally:
        if prior_argv is not None: gate.serve_argv=prior_argv
        if previous_observer is None: os.environ.pop("R055_PAUSE_OBSERVATIONS",None)
        else: os.environ["R055_PAUSE_OBSERVATIONS"]=previous_observer
        if proc is not None:
            try: gate.load_owned_lifecycle().stop_owned_process(proc)
            except BaseException as cleanup_error:
                cleanup_error.owned_process=proc; cleanup_error.owned_cleanup_failed=True; raise


def adapter_module():
 p=DEV/ADAPTER; s=importlib.util.spec_from_file_location("r055_leaf",p);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m

def _pause_manifest(evidence):
    paths=[]
    def collect(value):
        if isinstance(value,str) and Path(value).is_file(): paths.append(Path(value))
        elif isinstance(value,dict):
            for item in value.values(): collect(item)
        elif isinstance(value,list):
            for item in value: collect(item)
    collect(evidence)
    return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(set(paths))}

def child(batch,receipt):
 if sys.platform!="linux": raise RuntimeError("R055 requires the Linux GPU host")
 g=d07(); admission(g); require_receipt(g,batch,receipt); owner=g.take_d07_gpu_lock(RID,batch); runner=None; release=True
 try:
  g.require_gpu_idle()
  module=adapter_module()
  class OwnedRunner(module.CandidateRunner):
   def lock_take(self): return None
   def lock_release(self): return None
   def stop(self):
    try: return super().stop()
    except BaseException: self._owned_cleanup_failed=True; raise
  runner=OwnedRunner(SimpleNamespace(case=CARD,rid=RID,batch=batch,candidate_commit=CANDIDATE_COMMIT,run=True,gate=None))
  # Base gate() must recognize the child-owned lock without releasing it itself.
  runner.token=owner["lock_token"]; runner.lock_inode=owner["lock_inode"]
  runner.execute()
  pause_evidence=pause_smoke(g,batch,runner.directory/"PAUSE_ON")
  module.write_new(runner.directory/"pause_gate.json",{"schema":"ft_r055_pause_on/v1","rid":RID,"batch":batch,"candidate_commit":CANDIDATE_COMMIT,"evidence":pause_evidence,"sha256":_pause_manifest(pause_evidence),"proposed_verdict":"pending_review"})
  return {"rid":RID,"batch":batch,"candidate_commit":CANDIDATE_COMMIT,"verdict":"pending_review","proposed_verdict":"pending_review","source_execution_ready":False,"pause_smoke":pause_evidence}
 except BaseException as exc:
  if getattr(exc,"owned_cleanup_failed",False): release=False
  if runner is not None and runner.directory.is_dir() and not (runner.directory/"failed_harness.json").exists():
   module.write_new(runner.directory/"failed_harness.json",{"schema":"ft_r055_failed_harness/v1","rid":RID,"batch":batch,"error":repr(exc),"owned_cleanup_failed":not release})
  raise
 finally:
  if runner is not None and getattr(runner,"_owned_cleanup_failed",False): release=False
  elif runner is not None and runner.proc is not None and g.load_owned_lifecycle().owned_group_alive(runner.proc.pid): release=False
  if release: g.release_d07_gpu_lock(owner)

def main(argv_in=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",action="store_true");p.add_argument("--owned-child",action="store_true");p.add_argument("--batch",type=int);p.add_argument("--launch-receipt",type=Path);a=p.parse_args(argv_in)
 if not a.run:
  if a.owned_child or a.batch is not None or a.launch_receipt is not None:p.error("--run required for launch arguments")
  print(json.dumps({"schema":"ft_r055_gate_prepare/v1","rid":RID,"requests_sent":False,"gpu_lock_taken":False,"source_execution_ready":False}));return 0
 if a.owned_child:
  if a.batch is None or a.launch_receipt is None:p.error("child requires batch and receipt")
  child(a.batch,a.launch_receipt);return 0
 if a.batch is not None or a.launch_receipt is not None:p.error("controller does not accept child arguments")
 controller();return 0
if __name__=="__main__": raise SystemExit(main())
