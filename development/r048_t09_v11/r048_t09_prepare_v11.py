#!/usr/bin/env python3
"""E2-R048b T09 controlled hybrid retry, enabled only through --run."""
import argparse, getpass, hashlib, importlib.util, json, math, os, runpy, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

RID="E2-R048b"; ROOT=Path("/data2/FreeToken"); VENV=ROOT/"venv"; WT=ROOT/"wt/e2d08-capture-trace"; LOCK=Path("/data2/_shared/gpu.lock")
BATCH_ROOT=Path("/data2/_shared/runs/ft_rounds")
CANDIDATE="76af7584d7595d9cc52dcd60deff3aacdae1d9d6"; BASE="effb9969706922ddad9e59b96377e46469ebe97f"
MODEL_CONFIG=ROOT/"models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json"
MODEL_CONFIG_SHA256="deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80"
EXPECTED_HYBRID_LAYERS=tuple(range(48))
GATES=(("E2-R048a","failed_harness"),("E2-R048","failed_harness"),("E2-R040","failed_harness"),("E2-R050-gate-D15","kept"),("E2-R051-gate-D08","kept"),("E2-R051a-gate-D08","kept"))
FAILED_METADATA_GATES=(("E2-R049","failed_harness"),("E2-R049a","failed_harness"))
QUEUE_EXCEPTION={"deferred_round":"E2-R049b","reason":"retry approval pending","no_data_dependency":True,"basis":"CODEX_HANDOFF_20261006.md §8.7"}
BODY_READY=True
ROUNDS=BATCH_ROOT
ROUND=ROUNDS/RID
REVIEW=ROOT/"runs/dev_R048/reviews/E2-R048b_startup_review_98304_v11.json"
DRY_RUN=ROUNDS/f".dryrun_{RID}_98304_v11"
NODE1="1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47"
ARM_PREFIXES={
 "V0":["numactl","--cpunodebind=0,1","--interleave=all"],
 "A":["numactl","--interleave=all","taskset","-c","1,3-23,25,27-47"],
 "B":["numactl","--interleave=all","taskset","-c",NODE1],
 "C":["numactl","--membind=1","taskset","-c",NODE1],
 "S":["numactl","--interleave=all","taskset","-c","1,3-23,25,27-47"],
}
HERE=Path(__file__).resolve().parent
PORT_PAIR=HERE/"ft_batch_port_pair_v1.py"
ARGS_PARSER=HERE/"d04_original"/"serve_args_diff.py"
ORDINARY_STARTUP=HERE/"r046c_t06_ordinary_startup_v4.py"
ORDINARY_CLIENT=HERE/"r048_t09_ordinary_client_v3.py"
ORDINARY_ADAPTER=HERE/"r048_t09_ordinary_adapter_v3.py"
ORDINARY_V3=HERE/"r046c_t06_ordinary_client_v3.py"
ORDINARY_V2=HERE/"r046c_t06_ordinary_client_v2.py"
R049_ORDINARY_CLIENT_V2=HERE/"r049_t21_ordinary_client_v2.py"
R049_ORDINARY_ADAPTER_V2=HERE/"r049_t21_ordinary_adapter_v2.py"
R058_CONCURRENT=HERE/"r058_concurrent_request.py"
ROUTE_ANALYZER=HERE/"r046c_route_analyze_ordinary_v2.py"
HISTORY_CHECKER=HERE/"round_json_append_v1.py"
RUNTIME_SOURCES=(HISTORY_CHECKER,PORT_PAIR,ARGS_PARSER,ORDINARY_STARTUP,ORDINARY_CLIENT,ORDINARY_ADAPTER,ORDINARY_V3,ORDINARY_V2,R049_ORDINARY_CLIENT_V2,R049_ORDINARY_ADAPTER_V2,R058_CONCURRENT,ROUTE_ANALYZER)
def closed_round(rid, verdict):
 p=Path(__file__).with_name("d07_g3g4_prepare.py");s=importlib.util.spec_from_file_location("r048_gate",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m.require_closed_round(rid,verdict)
def git(cmd): return subprocess.check_output(cmd,text=True).strip()
def queue_exception(rounds=ROUNDS):
 deferred=Path(rounds)/QUEUE_EXCEPTION["deferred_round"]
 if deferred.exists() or deferred.is_symlink():
  raise RuntimeError("R048 queue exception refused: E2-R049b formal round directory exists")
 return dict(QUEUE_EXCEPTION)
def require_candidate_gate(path):
 value=json.loads(Path(path).read_text(encoding="utf-8"))
 if value.get("experimental",{}).get("candidate_commit")!=CANDIDATE or value.get("base",{}).get("commit")!=BASE:
  raise RuntimeError("R048 new T16 gate does not bind this exact candidate and parent")
 return {"path":str(path),"candidate_commit":CANDIDATE,"parent_commit":BASE}
def admission(require_round=closed_round, worktree=WT, lock=LOCK):
 if lock.exists() or lock.is_symlink(): raise RuntimeError("foreign GPU lock exists before lifecycle/batch")
 if worktree.is_symlink():raise RuntimeError("R048 candidate worktree cannot be a symlink")
 closures={rid:str(require_round(rid,verdict)) for rid,verdict in GATES}
 candidate_gate=require_candidate_gate(closures["E2-R051a-gate-D08"])
 failed_metadata={rid:str(require_round(rid,verdict)) for rid,verdict in FAILED_METADATA_GATES}
 exception=queue_exception()
 head=git(["git","-C",str(worktree),"rev-parse","HEAD"]); dirty=git(["git","-C",str(worktree),"status","--porcelain","--untracked-files=no"])
 if head!=CANDIDATE or dirty: raise RuntimeError("R048 requires exact clean D08 candidate")
 if subprocess.run(["git","-C",str(worktree),"merge-base","--is-ancestor",BASE,"HEAD"],check=False).returncode!=0: raise RuntimeError("R048 D08 candidate is not descended from E2-base.1 0aa")
 return {"rid":RID,"candidate_commit":head,"base_commit":BASE,"closures":closures,"candidate_gate":candidate_gate,"failed_metadata":failed_metadata,"queue_exception":exception,"arms":["V0","A","B","C","S"],"S":"repeat of A affinity: nativepool has no separate switch","default_prepare_no_request":True}
def child_argv(batch,receipt):return [str(VENV/"bin/python"),str(Path(__file__).resolve()),"--run","--owned-child","--batch",str(batch),"--launch-receipt",str(receipt)]
def load_d07():
 p=Path(__file__).with_name('d07_g3g4_prepare.py');s=importlib.util.spec_from_file_location('r048_d07',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def load_module(path,name):
 s=importlib.util.spec_from_file_location(name,Path(path));m=importlib.util.module_from_spec(s)
 if s.loader is None: raise RuntimeError(f"R048 source has no loader: {path}")
 s.loader.exec_module(m);return m

def allocate_port_pair():
 """Probe, but never listen/connect, one private API/TCPStore pair."""
 helper=load_module(PORT_PAIR,"r048_port_pair")
 port=helper.dynamic_port();receipt=helper.port_receipt(port)
 if receipt.get("api")!=port or receipt.get("tcpstore")!=port+1: raise RuntimeError("R048 private port-pair binding differs")
 return port,receipt

def service_argv(d,port,arm):
 if arm not in ARM_PREFIXES: raise RuntimeError(f"unknown T09 arm: {arm}")
 argv=list(d.serve_argv(port))
 for key in ("--kv-reserve-tokens","--max-seq-len-override"):
  argv[argv.index(key)+1]="98304"
 try: strategy=argv.index("--moe-strategy")
 except ValueError as error: raise RuntimeError("D07 serve argv lacks moe strategy") from error
 if strategy+1==len(argv): raise RuntimeError("D07 serve argv has incomplete moe strategy")
 argv[strategy+1]="hybrid"
 argv=[item for item in argv if item!="--prefill-layer-major"]
 if "--moe-cpu-layers" in argv:
  raise RuntimeError("T09 fixed hybrid layer inventory does not permit CPU-only layer routing")
 if "--prefill-layer-major" in argv or argv[strategy+1]!="hybrid" or "--max-prefill-length" not in argv or argv[argv.index("--max-prefill-length")+1]!="4096":
  raise RuntimeError("T09 hybrid serve argv differs from card")
 return [*ARM_PREFIXES[arm],*argv]

def source_binding(worktree=WT):
 files=("python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp","python/freetoken/moe/cpu_executor.py","python/freetoken/layers/moe.py","python/freetoken/engine/engine.py","python/freetoken/engine/graph.py","python/freetoken/server/args.py","python/freetoken/moe/offload_cache.py")
 bound={}
 for relative in files:
  path=Path(worktree)/relative
  if not path.is_file() or path.is_symlink(): raise RuntimeError(f"R048 source binding unavailable: {relative}")
  bound[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
 script=Path(__file__).resolve()
 native={}
 for pattern in ("python/freetoken/kernel/_cpu_moe*.so","python/freetoken/kernel/_pinned_tensor*.so"):
  matches=list(Path(worktree).glob(pattern))
  if len(matches)!=1 or matches[0].is_symlink(): raise RuntimeError(f"R048 native binding unavailable: {pattern}")
  native[str(matches[0].relative_to(worktree))]=hashlib.sha256(matches[0].read_bytes()).hexdigest()
 config_bytes=MODEL_CONFIG.read_bytes();config=json.loads(config_bytes)
 if hashlib.sha256(config_bytes).hexdigest()!=MODEL_CONFIG_SHA256 or config.get("text_config",{}).get("num_hidden_layers")!=48:
  raise RuntimeError("T09 model config differs from the fixed 48-layer hybrid trace inventory")
 return {"candidate_commit":CANDIDATE,"worktree":str(Path(worktree).resolve()),"sources":bound,"native":native,"model_config":{"path":str(MODEL_CONFIG),"sha256":MODEL_CONFIG_SHA256,"expected_hybrid_layers":list(EXPECTED_HYBRID_LAYERS)},"script":{"path":str(script),"sha256":hashlib.sha256(script.read_bytes()).hexdigest()},"operator":{"uid":getattr(os,"getuid",lambda:-1)(),"user":getpass.getuser()}}

def native_all_zero_timing_semantics(worktree=WT):
 """Bind the candidate's trace implementation before interpreting zero timings.

 The candidate emits three native task clocks for every traced hybrid decode,
 but has no serialised ``not_submitted``/``miss_zero`` state.  A triple-zero
 row is therefore ambiguous; it must remain a fail-closed diagnostic result.
 """
 root=Path(worktree)
 paths={
  "hybrid_callsite":root/"python/freetoken/layers/moe.py",
  "cpu_executor":root/"python/freetoken/moe/cpu_executor.py",
  "engine":root/"python/freetoken/engine/engine.py",
  "native_pool":root/"python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp",
 }
 for name,path in paths.items():
  if path.is_symlink() or not path.is_file(): raise RuntimeError("R048 native timing source is unavailable: "+name)
 text={name:path.read_text(encoding="utf-8") for name,path in paths.items()}
 required={
  "hybrid_callsite":("pending = executor.decode_submit", "executor.register_trace_context(", "copy_event_begin.record()"),
  "cpu_executor":("def observe_trace_completion", 'self._ext.task_timing(context["task"])', '"cpu_task": timing', "external=True", "self._trace_last_observed"),
  "engine":("copy_done_event.record(self.stream)", "self._observe_hybrid_trace_completion(", "completion_event.synchronize()"),
  "native_pool":('out["start_ns"]', 'out["end_ns"]', 'out["barrier_wait_ns_total"]'),
 }
 for name,markers in required.items():
  if any(marker not in text[name] for marker in markers): raise RuntimeError("R048 candidate native timing contract differs: "+name)
 no_submit_markers=("not_submitted", "no_submit", "miss_zero", "cpu_work_submitted")
 present={marker:[name for name,body in text.items() if marker in body] for marker in no_submit_markers}
 present={marker:names for marker,names in present.items() if names}
 return {"candidate_commit":CANDIDATE,"sources":{name:{"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in paths.items()},
         "native_task_timing_fields":["start_ns","end_ns","barrier_wait_ns_total"],
         "explicit_no_submit_markers":present,"all_zero_permitted":False,
         "reason":"candidate trace exposes clocks but no explicit task-not-submitted or zero-miss record; all-zero timing is ambiguous"}

def source_hashes():
 names=(Path(__file__).name,"d07_g3g4_prepare.py",*(str(path.relative_to(HERE)) for path in RUNTIME_SOURCES))
 base=Path(__file__).resolve().parent
 return {name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in names}

def copy_runtime_sources(directory):
 """Freeze only the worker/client/parser closure needed by this R048 run."""
 root=Path(directory)/"runtime_sources";root.mkdir(mode=0o700,parents=True,exist_ok=False);out={}
 for source in RUNTIME_SOURCES:
  relative=source.relative_to(HERE);target=root/relative;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  shutil.copyfile(source,target);os.chmod(target,0o600)
  if hashlib.sha256(source.read_bytes()).hexdigest()!=hashlib.sha256(target.read_bytes()).hexdigest(): raise RuntimeError(f"R048 runtime source copy differs: {relative}")
  out[str(relative)]={"path":str(target),"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"mode":oct(target.stat().st_mode&0o777)}
 return root,out

def require_file_dry_run(path=DRY_RUN/"dry_run_receipt.json"):
 path=Path(path)
 if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222: raise RuntimeError("R048 dry-run receipt is absent or writable")
 try: value=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as error: raise RuntimeError("R048 dry-run receipt is unreadable") from error
 expected={"schema":"ft_r048_real_path_dry_run/v7","rid":RID,"candidate_commit":CANDIDATE,"parent_commit":BASE,"source_sha256":source_hashes(),"owner_path":str(Path(__file__).resolve()),"formal_directory":str(ROUND),"queue_exception":queue_exception(),"service_started":False,"requests_sent":False,"gpu_lock_taken":False,"batch_allocated":False,"formal_rid_directory_created":False,"passed":True}
 if any(value.get(key)!=wanted for key,wanted in expected.items()): raise RuntimeError("R048 dry-run receipt binding differs")
 binding=source_binding()
 if value.get("binding")!=binding or value.get("uid")!=binding["operator"]["uid"] or value.get("user")!=binding["operator"]["user"] or value.get("cwd")!=os.getcwd(): raise RuntimeError("R048 dry-run receipt identity binding differs")
 return path

def require_launch_review(review=REVIEW):
 review=Path(review)
 if review.is_symlink() or not review.is_file() or review.stat().st_mode & 0o222: raise RuntimeError("R048 startup review is absent or writable")
 try: value=json.loads(review.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as error: raise RuntimeError("R048 startup review is unreadable") from error
 dry=require_file_dry_run()
 expected={"schema":"ft_r048_startup_review/v5","rid":RID,"candidate_commit":CANDIDATE,"parent_commit":BASE,"verdict":"PASS","approved":True,"source_sha256":source_hashes(),"queue_exception":queue_exception(),"dry_run_receipt_sha256":hashlib.sha256(dry.read_bytes()).hexdigest()}
 if any(value.get(key)!=wanted for key,wanted in expected.items()): raise RuntimeError("R048 startup review binding differs")
 return review

def write_service_plan(d,arm_dir,arm,worktree,port,*,phase="performance",runtime_root=None,dry_run=False):
 if phase not in {"performance","diagnostic"}: raise RuntimeError("R048 phase differs")
 env=d.clean_environment(worktree)
 # clean_environment is pause-oriented. R048 uses ordinary SSE, never ft_dev ACK.
 env.pop("FT_DEV_PAUSE_ENDPOINT",None)
 for key in ("FT_DEV_D0","FT_DEV_D0_PATH","FT_DEV_HYB_TRACE"): env.pop(key,None)
 if phase=="diagnostic": env.update(FT_DEV_D0="1",FT_DEV_D0_PATH=str(arm_dir/"d0"),FT_DEV_HYB_TRACE="1")
 argv=service_argv(d,port,arm)
 if runtime_root is not None:
  observer=Path(runtime_root)/"r046c_t06_ordinary_startup_v4.py"
  if not observer.is_file(): raise RuntimeError("R048 ordinary worker wrapper copy is absent")
  ft_args=argv[len(ARM_PREFIXES[arm]):]
  if not ft_args or ft_args[0]!=str(VENV/"bin/ft") or len(ft_args)<2 or ft_args[1]!="serve": raise RuntimeError("R048a observer service argv lacks ft serve")
  argv=[*ARM_PREFIXES[arm],str(VENV/"bin/python"),str(observer),"--observer-dir",str(arm_dir/"ordinary"),"--",*ft_args[1:]]
 persisted={key:env[key] for key in ("CUDA_VISIBLE_DEVICES","FT_DEV_D0","FT_DEV_D0_PATH","FT_DEV_HYB_TRACE","FT_DEV_PAUSE_ENDPOINT","PYTHONPATH","VIRTUAL_ENV") if key in env}
 d.write_new(arm_dir/"serve_argv.json",{"arm":arm,"phase":phase,"argv":argv,"server_argv":service_argv(d,port,arm),"port":port,"tcpstore_port":port+1,"dry_run":dry_run,"environment":persisted,"ordinary_worker_observer":runtime_root is not None})
 return env,argv

def write_service_files(d,arm_dir,arm,worktree,port,*,phase="performance",runtime_root=None,dry_run=False):
 env,argv=write_service_plan(d,arm_dir,arm,worktree,port,phase=phase,runtime_root=runtime_root,dry_run=dry_run)
 persisted={key:env[key] for key in ("CUDA_VISIBLE_DEVICES","FT_DEV_D0","FT_DEV_D0_PATH","FT_DEV_HYB_TRACE","FT_DEV_PAUSE_ENDPOINT","PYTHONPATH","VIRTUAL_ENV") if key in env}
 d.write_new(arm_dir/"ENV.txt",{"worktree":str(worktree),"phase":phase,"environment":persisted,"dry_run":dry_run})
 with (arm_dir/"SERVE_CMD.txt").open("x",encoding="utf-8") as stream: stream.write(" ".join(argv)+"\n")
 return env,argv

def write_actual_serve_args(arm_dir):
 text=(arm_dir/"serve.log").read_text(encoding="utf-8")
 position=text.find("Parsed arguments")
 if position<0: raise RuntimeError("R048 service did not publish Parsed arguments")
 with (arm_dir/"serve_args.txt").open("x",encoding="utf-8") as stream:
  stream.write("\n".join(text[position:].splitlines()[:2])+"\n")

def parse_actual_server_args(arm_dir,parser_path=ARGS_PARSER):
 parser=load_module(parser_path,"r048_serve_args_diff")
 try: value=parser.parse(str(Path(arm_dir)/"serve.log"))
 except SystemExit as error: raise RuntimeError("R048 actual Parsed arguments are unreadable") from error
 if not isinstance(value,dict) or not value: raise RuntimeError("R048 actual Parsed arguments are empty")
 return value

def normalized_env(value,arm):
 result=dict(value)
 if "FT_DEV_D0_PATH" in result: result["FT_DEV_D0_PATH"]="<ARM>/d0"
 return result

def actual_args_env_diff(reference,observed,output,*,allowed=("_unique_suffix",)):
 """Compare real parsed ServerArgs and persisted env; no pre-launch echo is trusted."""
 ref=Path(reference);other=Path(observed);out=Path(output)
 left,right=parse_actual_server_args(ref),parse_actual_server_args(other)
 keys=set(left)|set(right);changed=sorted(key for key in keys if left.get(key)!=right.get(key))
 left_env=json.loads((ref/"ENV.txt").read_text(encoding="utf-8"))["environment"]
 right_env=json.loads((other/"ENV.txt").read_text(encoding="utf-8"))["environment"]
 env_changed=sorted(key for key in set(left_env)|set(right_env) if normalized_env(left_env,ref.name).get(key)!=normalized_env(right_env,other.name).get(key))
 value={"schema":"ft_r048_actual_serve_args_env_diff/v1","reference":str(ref),"observed":str(other),"parsed_changed":changed,"environment_changed":env_changed,"allowed":list(allowed),"actual_parsed":{ref.name:left,other.name:right},"actual_environment":{ref.name:left_env,other.name:right_env}}
 with out.open("x",encoding="utf-8") as handle: json.dump(value,handle,sort_keys=True)
 if set(changed)-set(allowed) or env_changed: raise RuntimeError("R048 actual serve args/env differ beyond declared identity field")
 return value

def stop_service(process,d=None):
 d=load_d07() if d is None else d;owned=d.load_owned_lifecycle()
 try: owned.stop_owned_process(process)
 except BaseException as error:
  error.owned_process=process;error.owned_cleanup_failed=True;raise
 if owned.owned_group_alive(process.pid):
  error=RuntimeError("R048 owned service group remains after stop")
  error.owned_process=process;error.owned_cleanup_failed=True;raise error

def _file_probe(d,path):
 path.parent.mkdir(parents=True,exist_ok=True);d.write_new(path,{"file_probe":path.name,"writable":True})
 if not path.is_file() or not path.read_bytes(): raise RuntimeError(f"R048 file probe failed: {path.name}")

def start_service(arm_dir,arm,worktree,port,*,phase="performance",runtime_root=None,file_dry_run=False):
 d=load_d07();env,argv=write_service_files(d,arm_dir,arm,worktree,port,phase=phase,runtime_root=runtime_root,dry_run=file_dry_run)
 if file_dry_run:
  for name in ("serve.log","serve_args.txt","owned_process.json","health.json","d0_decode.json","d0_hyb_trace.jsonl","observer.json","ordinary/inputs.jsonl","ordinary/tokens.jsonl"):
   _file_probe(d,arm_dir/name)
  return None
 log=(arm_dir/"serve.log").open("x",encoding="utf-8")
 process=subprocess.Popen(argv,cwd=worktree,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=d.load_owned_lifecycle().process_identity(process.pid)
  if birth is None or birth.get("pgid")!=process.pid or birth.get("session")!=process.pid: raise RuntimeError("R048 owned service lacks private process group/session")
  d.write_new(arm_dir/"owned_process.json",{"pid":process.pid,"pgid":process.pid,"port":port,"birth":birth})
  deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   if process.poll() is not None: raise RuntimeError(f"R048 owned service exited during startup: {process.returncode}")
   try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=3) as response:
     health=json.load(response)
    if health.get("status")=="ok":
     d.write_new(arm_dir/"health.json",health);write_actual_serve_args(arm_dir);return process
   except (OSError,ValueError): pass
   time.sleep(2)
  raise TimeoutError("R048 owned service did not become healthy")
 except BaseException as startup_error:
  try: stop_service(process,d)
  except BaseException as cleanup_error:
   cleanup_error.owned_process=process;cleanup_error.owned_cleanup_failed=True;raise cleanup_error from startup_error
  startup_error.owned_process=process;raise

def invoke_frozen_cold_eq(d,port,cold_id,output,prompt_tokens,max_tokens):
 """Run the pinned D07 request construction with T09's actual shape arguments."""
 pins=d.verify_frozen_cold_helpers()
 cold=Path(pins["cold_eq_raw"]);probe=Path(pins["probe_raw"])
 if pins.get("cold_eq_raw_sha256")!=d.COLD_RAW_SHA or pins.get("probe_raw_sha256")!=d.PROBE_RAW_SHA: raise RuntimeError("R048 frozen cold helper pin differs")
 spec=importlib.util.spec_from_file_location("probe_ft_cold32k",probe);module=importlib.util.module_from_spec(spec)
 if spec.loader is None: raise RuntimeError("R048 frozen probe has no loader")
 spec.loader.exec_module(module);module.URL=f"http://127.0.0.1:{port}/v1/chat/completions"
 old_module,old_argv=sys.modules.get("probe_ft_cold32k"),sys.argv[:]
 sys.modules["probe_ft_cold32k"]=module;sys.argv=[str(cold),cold_id,str(output),str(prompt_tokens),str(max_tokens)]
 try: runpy.run_path(str(cold),run_name="__main__")
 finally:
  sys.argv=old_argv
  if old_module is None: sys.modules.pop("probe_ft_cold32k",None)
  else: sys.modules["probe_ft_cold32k"]=old_module

def cold_raw_evidence(path,cold_id,prompt_tokens,max_tokens):
 try: raw=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as error: raise RuntimeError(f"R048 cold raw output unreadable: {path}") from error
 record=raw.get("record") if isinstance(raw,dict) else None
 if not isinstance(record,dict) or record.get("cold_id")!=cold_id or record.get("completion_tokens")!=max_tokens or not isinstance(raw.get("text"),str) or not raw["text"]:
  raise RuntimeError(f"R048 cold raw request/response binding is incomplete: {cold_id}")
 for key in ("ttft_s","decode_tps"):
  if type(record.get(key)) not in (int,float) or record[key]<=0: raise RuntimeError(f"R048 cold raw {key} is absent: {cold_id}")
 if type(record.get("built_tokens")) is not int or record["built_tokens"]<=0: raise RuntimeError(f"R048 cold raw frontend-token binding is absent: {cold_id}")
 return {"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"cold_id":cold_id,"requested_prompt_tokens":prompt_tokens,"requested_completion_tokens":max_tokens,"frontend_token_binding":{"built_tokens":record["built_tokens"]},"raw_record":record,"fulltext_path":path.name}

def two_decode_raw_evidence(path):
 try: raw=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as error: raise RuntimeError("R048 two-decode output unreadable") from error
 reps=raw.get("reps") if isinstance(raw,dict) else None
 if raw.get("schema")!="multisession_probe/v1" or raw.get("command")!="two-decode" or raw.get("same_prompt") is not False or not isinstance(reps,list) or len(reps)!=1: raise RuntimeError("R048 two-decode is not one different-content D06 measurement")
 rep=reps[0];records=rep.get("_records") if isinstance(rep,dict) else None
 if not isinstance(records,list) or len(records)!=2 or not isinstance(rep.get("prompt_sha256"),list) or len(rep["prompt_sha256"])!=2 or not isinstance(rep.get("frontend_token_counts"),list) or len(rep["frontend_token_counts"])!=2:
  raise RuntimeError("R048 two-decode lacks per-way frontend binding")
 for row in records:
  if not isinstance(row,dict) or row.get("completion_tokens")!=512 or type(row.get("ttft_s")) not in (int,float) or not isinstance(row.get("token_events"),list) or not row["token_events"]: raise RuntimeError("R048 two-decode lacks raw per-way TTFT/token evidence")
 return {"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"same_prompt":False,"ways":2,"completion_tokens_each":512,"frontend_token_binding":{"prompt_sha256":rep["prompt_sha256"],"frontend_token_counts":rep["frontend_token_counts"]},"raw_repetition":rep}

def candidate_frontend_binding(worktree, tokenizer_path, payload):
 """Bind sorted ordinary wire bytes to the actual candidate API/tokenizer path."""
 if payload.get("ignore_eos") is not True or payload.get("stop") is not None:
  raise RuntimeError("R048 exact-token payload must ignore EOS and carry no custom stop")
 wire=json.loads(json.dumps(payload,ensure_ascii=False,sort_keys=True))
 prior=sys.path[:];sys.path.insert(0,str(Path(worktree)/"python"))
 try:
  from freetoken.tokenizer.tokenize import TokenizeManager
  from freetoken.server.api_models import ChatCompletionRequest
  from freetoken.server.openai_api import chat_request_to_genspec
  from freetoken.message import TokenizeMsg
  from transformers import AutoTokenizer
  manager=TokenizeManager(AutoTokenizer.from_pretrained(str(tokenizer_path),trust_remote_code=True))
  request=ChatCompletionRequest.model_validate(wire);spec=chat_request_to_genspec(request,{})
  sampling=spec.sampling_params
  if request.ignore_eos is not True or request.stop is not None or sampling.ignore_eos is not True or sampling.max_tokens!=wire["max_tokens"] or sampling.stop_strs!=[]:
   raise RuntimeError("R048 candidate API/GenSpec exact-token contract differs")
  message=TokenizeMsg(uid=0,text=spec.messages,tools=spec.template_tools,chat_template_kwargs=spec.chat_template_kwargs,sampling_params=spec.sampling_params,images=None)
  ids=manager.tokenize([message])[0].input_ids
  ids=ids.tolist() if hasattr(ids,"tolist") else ids
 finally: sys.path[:]=prior
 if not isinstance(ids,list) or any(type(item) is not int for item in ids): raise RuntimeError("R048 candidate TokenizeManager produced invalid IDs")
 canonical=json.dumps(ids,separators=(",",":"),ensure_ascii=True).encode("ascii")
 wire_raw=json.dumps(wire,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
 return wire,{"wire_sha256":hashlib.sha256(wire_raw).hexdigest(),"input_ids_sha256":hashlib.sha256(canonical).hexdigest(),"input_tokens":len(ids),"construction":"ChatCompletionRequest->chat_request_to_genspec->TokenizeMsg->TokenizeManager","exact_token_contract":{"ignore_eos":sampling.ignore_eos,"max_tokens":sampling.max_tokens,"stop_strs":sampling.stop_strs}}

def exact_token_payload(model,text,max_tokens):
 """T09-owned wrapper around the frozen text builder for exact-output workloads."""
 if type(max_tokens) is not int or max_tokens<1: raise RuntimeError("R048 exact-token request budget is invalid")
 return {"model":model,"messages":[{"role":"user","content":text}],"max_tokens":max_tokens,"temperature":0,"stream":True,"stream_options":{"include_usage":True},"chat_template_kwargs":{"enable_thinking":False},"ignore_eos":True,"stop":None}

def ordinary_payload(d,cold_id,prompt_tokens,max_tokens,output):
 """Use sorted actual wire bytes and candidate TokenizeManager, never a recreated template."""
 pins=d.verify_frozen_cold_helpers();probe=Path(pins["probe_raw"])
 module=load_module(probe,"r048_pinned_probe")
 from transformers import AutoTokenizer
 tokenizer=AutoTokenizer.from_pretrained(module.MODEL_DIR,trust_remote_code=True)
 text,built=module.build_text(tokenizer,prompt_tokens,cold_id)
 # The sealed helper owns the card's deterministic text builder only; it has no
 # exact-output wire builder.  T09 fixes EOS/stop semantics in its owned wrapper.
 payload=exact_token_payload(d.MODEL,text,max_tokens)
 if payload.get("chat_template_kwargs")!={"enable_thinking":False}: raise RuntimeError("R048 ordinary payload lacks frozen nothink flags")
 wire,frontend=candidate_frontend_binding(WT,module.MODEL_DIR,payload)
 Path(output).write_text(json.dumps(wire,ensure_ascii=False,sort_keys=True,separators=(",",":")),encoding="utf-8")
 if frontend["wire_sha256"]!=hashlib.sha256(Path(output).read_bytes()).hexdigest(): raise RuntimeError("R048 sorted ordinary wire differs from candidate binding")
 return {"path":str(output),"sha256":frontend["wire_sha256"],"cold_id":cold_id,"built_tokens":built,"max_tokens":max_tokens,"candidate_frontend":frontend}

def _ordinary_one(client,adapter,base,payload,api,inputs,tokens,binding,prepared,*,timed):
 client.ordinary_request(base,payload,api)
 value=client.bind(payload,api,None,None,inputs,tokens,binding)
 record=adapter.ordinary_binding(value)
 planned=prepared["candidate_frontend"]
 if record["input_ids_sha256"]!=planned["input_ids_sha256"] or record["input_tokens"]!=planned["input_tokens"]: raise RuntimeError("R048 candidate TokenizeManager IDs differ from actual worker UserMsg")
 record["candidate_frontend"]=planned
 if timed: record["timing"]=adapter.timing_from_sse(api)
 return record

def run_workloads(directory,port,*,phase="performance",runtime_root=None,file_dry_run=False):
 """All traffic is ordinary SSE plus UserMsg/Detokenize evidence; never ft_dev ACK."""
 d=load_d07();directory=Path(directory);pins=d.verify_frozen_cold_helpers()
 cases=(("first_shot",f"{RID}-first-shot",2000,64),("dec32k_s3A","s3A",32052,128),("dec32k_s3B","s3B",32052,128),("short",f"{RID}-short",2000,512))
 if phase not in {"performance","diagnostic"}: raise RuntimeError("R048 workload phase differs")
 if file_dry_run:
  for name,*_ in cases:
   for suffix in ("payload.json","api.json","binding.json","sse","events.jsonl"): _file_probe(d,directory/f"{name}.{suffix}")
  for name in ("two_left.payload.json","two_right.payload.json","two_left.api.json","two_right.api.json","two_decode.json"): _file_probe(d,directory/name)
  return {"file_dry_run":True,"phase":phase,"transport":"ordinary_sse_no_ft_dev_ack","frozen_cold_helpers":{"probe_raw_sha256":pins["probe_raw_sha256"]}}
 if runtime_root is None: raise RuntimeError("R048 ordinary workload requires copied runtime sources")
 client=load_module(Path(runtime_root)/"r048_t09_ordinary_client_v3.py","r048_ordinary_client")
 adapter=load_module(Path(runtime_root)/"r048_t09_ordinary_adapter_v3.py","r048_ordinary_adapter")
 inputs,tokens=directory/"ordinary"/"inputs.jsonl",directory/"ordinary"/"tokens.jsonl"
 base=f"http://127.0.0.1:{port}/v1";cold={}
 for name,cold_id,prompt_tokens,max_tokens in cases:
  payload=directory/f"{name}.payload.json";prepared=ordinary_payload(d,cold_id,prompt_tokens,max_tokens,payload)
  record=_ordinary_one(client,adapter,base,payload,directory/f"{name}.api.json",inputs,tokens,directory/f"{name}.binding.json",prepared,timed=phase=="performance")
  if record["completion_tokens"]!=max_tokens: raise RuntimeError(f"R048 ordinary completion differs: {name}")
  cold[name]={"request":prepared,"ordinary":record}
 # Two real independent ordinary streams start together; their own UID/token sidecars bind each way.
 pair=[];errors=[];barrier=__import__("threading").Barrier(2)
 def request_pair(label,target):
  try:
   payload=directory/f"two_{label}.payload.json";prepared=ordinary_payload(d,f"{RID}-two-{label}",target,512,payload);barrier.wait(timeout=30)
   pair.append((label,_ordinary_one(client,adapter,base,payload,directory/f"two_{label}.api.json",inputs,tokens,directory/f"two_{label}.binding.json",prepared,timed=phase=="performance")))
  except BaseException as error: errors.append(error)
 threads=[__import__("threading").Thread(target=request_pair,args=("left",16000)),__import__("threading").Thread(target=request_pair,args=("right",16001))]
 for thread in threads: thread.start()
 for thread in threads: thread.join()
 if errors: raise RuntimeError("R048 ordinary two-decode failed") from errors[0]
 if len(pair)!=2 or len({row[1]["uid"] for row in pair})!=2 or any(row[1]["completion_tokens"]!=512 for row in pair): raise RuntimeError("R048 ordinary two-decode UID/token binding differs")
 result={"schema":"ft_r048_ordinary_workloads/v1","phase":phase,"transport":"ordinary_sse_no_ft_dev_ack","performance_numbers_included":phase=="performance","frozen_cold_helpers":{"probe_raw_sha256":pins["probe_raw_sha256"]},"cold":cold,"two_decode":{"same_prompt":False,"ways":2,"records":dict(pair)}}
 d.write_new(directory/"two_decode.json",result);return result

def trace_evidence(path):
 """Require complete, fresh per-decode evidence from the post-replay writer."""
 try: rows=[json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
 except (OSError,json.JSONDecodeError) as error: raise RuntimeError("R048 hybrid trace is unreadable") from error
 if not rows: raise RuntimeError("R048 hybrid trace has no completed layer records")
 groups={};last_native={};previous_sequence=0
 for row in rows:
  cpu=row.get("cpu_task");pcie=row.get("pcie_copy")
  if row.get("trace_mode_perturbs_timing") is not True or not isinstance(cpu,dict) or not isinstance(pcie,dict): raise RuntimeError("R048 hybrid trace lacks completion-observation schema")
  timings=tuple(cpu.get(key) for key in ("start_ns","end_ns","barrier_wait_ns_total"))
  native_completed=all(type(value) is int and value>0 for value in timings) and cpu["end_ns"]>=cpu["start_ns"]
  if timings==(0,0,0): raise RuntimeError("R048 hybrid trace has no candidate no-submit field; all-zero CPU task is unverifiable")
  if not native_completed: raise RuntimeError("R048 hybrid trace has invalid native completion state")
  if pcie.get("status")!="measured_cuda_event": raise RuntimeError("R048 hybrid trace completion ordering is invalid")
  elapsed=pcie.get("event_elapsed_ms");completed_at=pcie.get("completion_observed_host_ns")
  if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0 or type(completed_at) is not int or completed_at<=0: raise RuntimeError("R048 hybrid trace lacks PCIe completion event")
  seq,bs,layer=row.get("decode_observation_sequence"),row.get("batch_size"),row.get("layer")
  if row.get("post_replay_completion") is not True or type(row.get("replayed")) is not bool or type(seq) is not int or seq<1 or type(bs) is not int or bs<1 or type(layer) is not int or layer not in EXPECTED_HYBRID_LAYERS:
   raise RuntimeError("R048 hybrid trace lacks bound post-replay sequence/layer evidence")
  if seq<previous_sequence: raise RuntimeError("R048 hybrid trace sequence moved backwards")
  previous_sequence=seq
  group=groups.setdefault(seq,{"batch_size":bs,"replayed":row["replayed"],"layers":set()})
  if group["batch_size"]!=bs or group["replayed"]!=row["replayed"] or layer in group["layers"]:
   raise RuntimeError("R048 hybrid trace duplicates or mixes decode observations")
  group["layers"].add(layer)
  native=(cpu["start_ns"],cpu["end_ns"]);key=(bs,layer)
  if key in last_native and native<=last_native[key]: raise RuntimeError("R048 hybrid trace repeats stale native completion")
  last_native[key]=native
  if row["replayed"] and (row.get("enqueue_timing_not_observed_on_replay") is not True or any(row.get(key) is not None for key in ("cpu_submit_enqueue_ns","pcie_copy_enqueue_ns","cpu_sync_enqueue_ns"))):
   raise RuntimeError("R048 graph replay reports unobserved Python enqueue timing")
 if sorted(groups)!=list(range(1,len(groups)+1)) or any(group["layers"]!=set(EXPECTED_HYBRID_LAYERS) for group in groups.values()):
  raise RuntimeError("R048 hybrid trace has missing decode sequences or hybrid layers")
 replay_count=sum(group["replayed"] for group in groups.values())
 if replay_count<2: raise RuntimeError("R048 hybrid trace lacks two actual graph replays")
 return {"path":Path(path).name,"sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),"rows":len(rows),"trace_mode_perturbs_timing":True,"decode_observations":len(groups),"graph_replay_observations":replay_count,"expected_hybrid_layers":list(EXPECTED_HYBRID_LAYERS),"complete_layer_inventory":True,"fresh_native_completion":True}

def node1_available_kb():
 values={}
 for line in Path("/sys/devices/system/node/node1/meminfo").read_text(encoding="utf-8").splitlines():
  key,_,rest=line.partition(":")
  if key in {"Node 1 MemFree","Node 1 FilePages"}: values[key]=int(rest.strip().split()[0])
 return values.get("Node 1 MemFree",0)+values.get("Node 1 FilePages",0)

def run_measurements(batch,*,file_dry_run=False,directory_override=None):
 d=load_d07();run=Path(directory_override) if directory_override is not None else ROUND/f"batch{batch}"
 if run.is_symlink() or (run.exists() and (not file_dry_run or any(run.iterdir()))): raise RuntimeError("R048 batch output already exists")
 if not run.exists(): run.mkdir(parents=True)
 runtime_root,runtime_binding=copy_runtime_sources(run)
 port,pair=allocate_port_pair()
 d.write_new(run/"measurement_plan.json",{"schema":"ft_r048_t09_plan/v4","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"arms":["V0","A","B","C","S"],"phases":{"performance":{"d0":False,"hyb_trace":False,"pause":False,"transport":"ordinary_sse_no_ft_dev_ack"},"diagnostic":{"d0":True,"hyb_trace":True,"numbers_excluded_from_performance":True}},"port_pair":pair,"max_prefill_length":4096,"comparison_scope":"within_round_hybrid_S_vs_V0","kv_reserve_tokens":98304,"max_seq_len_override":98304,"memory_ratio":0.88,"runtime_sources":runtime_binding,"file_dry_run":file_dry_run})
 results={"schema":"ft_r048_t09_results/v4","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"base_commit":BASE,"arms":{},"port_pair":pair,"performance_phase":{"d0":False,"hyb_trace":False,"pause":False,"transport":"ordinary_sse_no_ft_dev_ack"},"diagnostic_phase":{"d0":True,"hyb_trace":True,"performance_numbers_excluded":True},"comparison_scope":"within_round_hybrid_S_vs_V0","kv_reserve_tokens":98304,"max_seq_len_override":98304,"memory_ratio":0.88,"runtime_sources":runtime_binding,"proposed_verdict":"measured","file_dry_run":file_dry_run}
 for arm in ("V0","A","B","C","S"):
  arm_dir=run/arm;arm_dir.mkdir()
  if not file_dry_run and arm=="C" and node1_available_kb()<120586240:
   results["arms"][arm]={"state":"skipped_insufficient_node1_memory","node1_available_kb":node1_available_kb()};continue
  phases={}
  for phase in ("performance","diagnostic"):
   phase_dir=arm_dir/phase;phase_dir.mkdir();process=None
   try:
    process=start_service(phase_dir,arm,WT,port,phase=phase,runtime_root=runtime_root,file_dry_run=file_dry_run)
    workloads=run_workloads(phase_dir,port,phase=phase,runtime_root=runtime_root,file_dry_run=file_dry_run)
    trace=None if phase=="performance" else ({"file_dry_run":True,"path":"d0_hyb_trace.jsonl"} if file_dry_run else trace_evidence(phase_dir/"d0_hyb_trace.jsonl"))
    phases[phase]={"state":"file_probed" if file_dry_run else "measured","port":port,"tcpstore_port":port+1,"workloads":workloads,"hybrid_trace":trace,"performance_numbers_excluded":phase=="diagnostic"}
   finally:
    if process is not None: stop_service(process,d)
  results["arms"][arm]={"state":"file_probed" if file_dry_run else "measured","port_pair":pair,"phases":phases}
 if not file_dry_run:
  for phase in ("performance","diagnostic"):
   usable=[arm for arm in ("V0","A","B","C","S") if results["arms"].get(arm,{}).get("state")!="skipped_insufficient_node1_memory"]
   if usable:
    reference=run/usable[0]/phase
    for arm in usable[1:]: actual_args_env_diff(reference,run/arm/phase,run/f"args_env_diff_{phase}_{usable[0]}_{arm}.json")
 d.write_new(run/"round.json",results)
 return results
run_measurements.full_implementation=True

def body_implementation_ready():
 return callable(run_measurements) and bool(getattr(run_measurements,"full_implementation",False))

def prepare(dry_run_dir):
 """Run the formal file branch in a non-RID sibling, without service or lock."""
 directory=Path(dry_run_dir)
 if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents) or directory.resolve()==ROUND.resolve() or ROUND.resolve() in directory.resolve().parents:
  raise RuntimeError("R048 dry-run directory may not be the formal round or its child")
 d=load_d07();admitted=admission(d.require_closed_round);binding=source_binding()
 if directory.exists() or directory.is_symlink(): raise RuntimeError("R048 dry-run output already exists")
 results=run_measurements(None,file_dry_run=True,directory_override=directory)
 receipt={"schema":"ft_r048_real_path_dry_run/v7","rid":RID,"candidate_commit":CANDIDATE,"parent_commit":BASE,"source_sha256":source_hashes(),"owner_path":str(Path(__file__).resolve()),"uid":getattr(os,"getuid",lambda:-1)(),"user":getpass.getuser(),"cwd":os.getcwd(),"formal_directory":str(ROUND),"formal_rid_directory_created":False,"passed":True,"admission":admitted,"queue_exception":admitted["queue_exception"],"binding":binding,"results":results,"port_pair":results["port_pair"],"service_started":False,"requests_sent":False,"gpu_lock_taken":False,"batch_allocated":False}
 path=directory/"dry_run_receipt.json";d.write_new(path,receipt);os.chmod(path,0o444)
 return {**receipt,"receipt":{"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"mode":oct(path.stat().st_mode & 0o777)}}

def controller(*, body_ready=BODY_READY):
 if not body_ready or not body_implementation_ready():raise RuntimeError('R048 blocked: T09 business body is not ready; controller will not reserve or start GPU')
 d=load_d07();admission(d.require_closed_round);require_launch_review();owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r048_atomic')
 batch=helper.next_batch(BATCH_ROOT);receipt=ROOT/'runs/dev_R048'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,receipt)
 value={'schema':'ft_r048_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':d.argv_sha256(argv),'controller':d.process_birth()};got=owned.reserve_process(helper,batch,RID,argv,receipt,value);birth=owned.process_identity(got['batch_pid'])
 if birth is None or birth.get('pid')!=got['batch_pid'] or type(birth.get('start_ticks')) is not int:raise RuntimeError('R048 child birth unavailable')
 return d.publish_child_binding(receipt,got,{'pid':birth['pid'],'start_ticks':birth['start_ticks'],'execution_id':f"{birth['pid']}:{birth['start_ticks']}"},lifecycle=owned)

def child(batch,receipt,*,body_ready=BODY_READY):
 if not body_ready or not body_implementation_ready(): raise RuntimeError("R048 blocked: T09 business body is not ready; child will not take GPU lock")
 d=load_d07();admission(d.require_closed_round);require_launch_review()
 # The D07 helper enforces candidate binding from its module constant; this is a
 # private loaded module, so bind it to this R048 candidate before validation.
 d.CANDIDATE=CANDIDATE
 d.require_child_receipt(receipt,batch,WT,ROUND,rid=RID,expected_argv=child_argv(batch,receipt),schema="ft_r048_owned_launch/v1")
 owner=d.take_d07_gpu_lock(RID,batch)
 try:
  result=run_measurements(batch)
 except BaseException as error:
  if getattr(error,"owned_cleanup_failed",False): raise
  d.release_d07_gpu_lock(owner)
  raise
 d.release_d07_gpu_lock(owner)
 return result
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--prepare",action="store_true");p.add_argument("--dry-run-dir",type=Path);p.add_argument("--run",action="store_true");p.add_argument("--owned-child",action="store_true");p.add_argument("--batch",type=int);p.add_argument("--launch-receipt",type=Path);a=p.parse_args(argv)
 if a.prepare:
  if a.run or a.owned_child or a.batch is not None or a.launch_receipt is not None or a.dry_run_dir is None: p.error("--prepare requires only --dry-run-dir")
  print(json.dumps(prepare(a.dry_run_dir),ensure_ascii=False,sort_keys=True));return 0
 if not a.run:
  if a.owned_child or a.batch is not None or a.launch_receipt is not None or a.dry_run_dir is not None: p.error("owned child arguments require --run")
  print(json.dumps({'rid':RID,'state':'queued','default_prepare_no_request':True},sort_keys=True));return 0
 if a.owned_child:
  if a.batch is None or a.launch_receipt is None: p.error("owned child requires --batch and --launch-receipt")
  result=child(a.batch,a.launch_receipt,body_ready=BODY_READY)
 else:
  if a.batch is not None or a.launch_receipt is not None: p.error("controller does not accept child receipt arguments")
  result=controller(body_ready=BODY_READY)
 print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
