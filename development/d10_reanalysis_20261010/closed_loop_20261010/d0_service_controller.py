"""Default-inert, root-admitted one-service D0 controller."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, socket, subprocess, sys, time, urllib.request
from pathlib import Path

HERE=Path(__file__).parent; WINDOW=HERE.parents[1]/"d15_window_ab_20261010"
TOTAL_S,CLEANUP_S,MEASUREMENT_S,PORT,MASTER=480,60,180,32103,32203
def load(path,name):
 path=Path(path); parent=str(path.parent); inserted=parent not in sys.path
 if inserted:sys.path.insert(0,parent)
 try:
  spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
 finally:
  if inserted:sys.path.remove(parent)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def put(path,value):
 with Path(path).open("x",encoding="utf8") as f:json.dump(value,f,indent=2,sort_keys=True);f.write("\n")
def remaining(deadline):
 value=deadline-time.monotonic()
 if value<=0:raise TimeoutError("eight-minute absolute controller deadline expired")
 return value
def sealed(path):
 path=Path(path)
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError("read-only root admission required")
 return json.loads(path.read_text())
def replace(argv,flag,value):
 if argv.count(flag)!=1:raise RuntimeError(f"expected one {flag}")
 argv[argv.index(flag)+1]=str(value)
def ports_free():
 for port in (PORT,MASTER):
  try:
   with socket.socket() as sock:sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(("127.0.0.1",port))
  except OSError:return False
 return True
def prepare(admission):
 runner=load(WINDOW/"window_runner.py","d10_window_runner")
 record=next(x for x in runner.prepare()["arms"] if x["arm"]=="W98K")
 record={**record,"argv":list(record["argv"]),"environment":dict(record["environment"]),"port":PORT,"master_port":MASTER,"cwd":str(runner.WT)}
 replace(record["argv"],"--port",PORT);record["environment"].update(MASTER_PORT=str(MASTER),FT_DEV_D0="1",FT_DEV_D0_PATH=str(admission["d0_path"]))
 return record
def require(admission,record):
 if admission.get("schema")!="d10_closed_loop_d0_admission/v1" or admission.get("admit") is not True:raise RuntimeError("sealed D0 admission differs")
 if admission.get("service_budget")!=1 or admission.get("window")!=98304 or admission.get("port")!=PORT or admission.get("master_port")!=MASTER:raise RuntimeError("one-service 98K/private-port scope differs")
 if admission.get("controller_sha256")!=sha(__file__):raise RuntimeError("controller source pin differs")
 for path,digest in admission.get("source_pins",{}).items():
  if sha(path)!=digest:raise RuntimeError("source pin differs: "+path)
 template=Path(admission["allxy_admission"])
 if sha(template)!=admission.get("allxy_admission_sha256"):raise RuntimeError("allxy template pin differs")
 sealed(template)
 if record["environment"].get("FT_DEV_D0")!="1" or record["environment"].get("FT_DEV_D0_PATH")!=admission["d0_path"]:raise RuntimeError("D0 environment differs")
def derive_actual(template_path,record,proc,birth,deadline,root):
 doc=sealed(template_path);usable=min(MEASUREMENT_S,remaining(deadline)-CLEANUP_S)
 if usable<=0:raise TimeoutError("no D0 runtime remains after cleanup reserve")
 phase=dict(doc["phases"]["d0"]);phase.update(endpoint=f"http://127.0.0.1:{record['port']}",service_pid=proc.pid,service_start_ticks=birth["start_ticks"],deadline_epoch_s=time.time()+usable,d0_path=record["environment"]["FT_DEV_D0_PATH"])
 doc={**doc,"phases":{**doc["phases"],"d0":phase}};target=root/"d0_actual_admission.json";put(target,doc);target.chmod(0o444)
 put(root/"template_binding.json",{"template":str(template_path),"template_sha256":sha(template_path),"actual_admission":str(target),"service_pid":proc.pid,"service_start_ticks":birth["start_ticks"],"runtime_budget_s":usable})
 return sealed(target)
def bounded_cleanup(proc,log,lifecycle,gpu_idle):
 try:
  if log:log.close()
  lifecycle.stop_owned_process(proc,term_timeout=30,kill_timeout=10)
 except BaseException:return False
 end=time.monotonic()+20
 try:
  while lifecycle.owned_group_alive(proc.pid) and time.monotonic()<end:time.sleep(.2)
  if lifecycle.owned_group_alive(proc.pid) or not ports_free():return False
  while time.monotonic()<end:
   if gpu_idle():return True
   time.sleep(.2)
 except BaseException:return False
 return False
def startup_proof(service,lifecycle,gpu_idle):
 try:
  pid=int(json.loads((service/"owned_process.json").read_text())["pid"])
  return not lifecycle.owned_group_alive(pid) and ports_free() and gpu_idle()
 except BaseException:return False
def start_owned(record,service,lifecycle):
 service.mkdir(parents=True,exist_ok=False);obs=service/"observer";obs.mkdir(mode=0o700)
 env=dict(record["environment"]);env.update(R046C_T06_OBSERVER_DIR=str(obs),OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
 log=(service/"serve.log").open("x");proc=subprocess.Popen([x.replace("__RUN_DIR__",str(service)) for x in record["argv"]],cwd=record["cwd"],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:birth=lifecycle.process_identity(proc.pid)
 except BaseException:birth=None
 put(service/"owned_process.json",{"pid":proc.pid,"pgid":proc.pid,"birth":birth})
 return proc,log,obs,birth
def wait_ready(record,proc,deadline):
 while True:
  if proc.poll() is not None:raise RuntimeError("service exited before health")
  timeout=min(3,remaining(deadline))
  try:
   with urllib.request.urlopen(f"http://127.0.0.1:{record['port']}/health",timeout=timeout) as response:
    health=json.load(response)
    if health.get("status")=="ok" and health.get("maintenance")=="serving":return
  except (OSError,ValueError,json.JSONDecodeError):pass
  time.sleep(1)
def terminal_status(error):return "not_met" if "anomaly" in str(error).lower() or "not_met" in str(error).lower() else "failed_harness"
def execute(admission,deps):
 record=prepare(admission);require(admission,record);deadline=deps.now()+TOTAL_S;root=Path(admission["output_root"]);root.mkdir(parents=True,exist_ok=False)
 put(root/"startup_record.json",{"argv":record["argv"],"environment":record["environment"],"source_sha256":sha(__file__),"window_runner_sha256":sha(WINDOW/"window_runner.py"),"window_startup_sha256":sha(WINDOW/"window_startup.py"),"native_source_pins":admission.get("source_pins",{})})
 owner=deps.take_lock(admission["rid"],admission["batch"]);proc=log=None;service=root/"service";start_attempted=False;error=None
 try:
  deps.require_gpu_idle();start_attempted=True;proc,log,obs,birth=deps.start_owned(record,service,deps.lifecycle)
  deps.wait_ready(record,proc,deadline-CLEANUP_S)
  if not birth or birth.get("pgid")!=proc.pid or birth.get("session")!=proc.pid:raise RuntimeError("private PID/PGID/session missing")
  put(root/"service_birth.json",{"pid":proc.pid,"birth":birth,"started_monotonic_ns":time.monotonic_ns()})
  actual=derive_actual(admission["allxy_admission"],record,proc,birth,deadline,root);load(HERE/"allxy_runner.py","d10_allxy_runner").run(actual,"d0")
 except BaseException as exc:error=exc
 safe=bounded_cleanup(proc,log,deps.lifecycle,deps.gpu_idle) if proc is not None else (startup_proof(service,deps.lifecycle,deps.gpu_idle) if start_attempted else False)
 if safe:deps.release_lock(owner);put(root/"cleanup_proof.json",{"owned_group_dead":True,"ports_reusable":[PORT,MASTER],"gpu_idle":True,"bounded_cleanup_s":CLEANUP_S})
 if error is None and not safe:error=RuntimeError("owned cleanup proof failed")
 if error is None:
  remaining(deadline);put(root/"terminal.json",{"status":"complete","cleanup_proved":True})
 else:put(root/"terminal.json",{"status":terminal_status(error),"error":repr(error),"lock_retained":not safe})
 if error is not None:raise error
class Deps:pass
def actual_deps():
 d=Deps();d.now=time.monotonic;d.d07=load("/data2/FreeToken/development/d07_g3g4_prepare.py","d10_d07");d.lifecycle=d.d07.load_owned_lifecycle();d.take_lock=d.d07.take_d07_gpu_lock;d.release_lock=d.d07.release_d07_gpu_lock;d.start_owned=start_owned;d.wait_ready=wait_ready;d.require_gpu_idle=d.d07.require_gpu_idle
 def gpu_idle():d.require_gpu_idle();return not subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip()
 d.gpu_idle=gpu_idle;return d
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--prepare",action="store_true");p.add_argument("--run",action="store_true");p.add_argument("--admission",type=Path);a=p.parse_args(argv)
 if a.prepare==a.run:p.error("select exactly one")
 if a.prepare:print(json.dumps({"default_inert":True,"service_budget":1,"window":98304,"port":PORT,"master_port":MASTER,"absolute_timeout_s":TOTAL_S,"cleanup_bound_s":CLEANUP_S,"measurement_max_s":MEASUREMENT_S}));return
 if not a.admission:p.error("--run requires --admission")
 execute(sealed(a.admission),actual_deps())
if __name__=="__main__":main()
