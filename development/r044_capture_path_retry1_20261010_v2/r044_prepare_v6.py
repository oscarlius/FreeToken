#!/usr/bin/env python3
"""E2-R044 raw T10 runner v7: two prefill modes, never a D04 closure."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys
from queue_authorization import factual, policy
from pathlib import Path

RID="E2-R044-night-20261010-retry1"; CANDIDATE="0aa23431e5b800797543bdecbf35a01045131d7d"
ROOT=Path("/data2/FreeToken"); WT=ROOT/"wt/e2base1-ordinary-rewind"; VENV=ROOT/"venv"
ROUNDS=Path("/data2/_shared/runs/ft_rounds"); HERE=Path(__file__).resolve().parent
D07_SOURCE=HERE/"d07_g3g4_prepare.py"; OLD=ROUNDS/"E2-R017"/"phase1_manifest.json"
ARGS_READER=HERE/"d04_original"/"serve_args_diff.py"; STRICT_READER=HERE/"t16_full_tail_base_runner.py"
CAPTURE_STARTUP=HERE/"t10_capture_startup_v3.py"; CAPTURE_REQUESTS=24; CAPTURE_MAX_TOKENS=200
LEGACY_CAPTURE=HERE/"t10_capture_startup.py"; REPLAY_SOURCE=HERE/"t10_ordinary_replay_v1.py"
ORDINARY_ADAPTER=HERE/"r049_t21_ordinary_adapter_v2.py"; ORDINARY_CLIENT=HERE/"r046c_t06_ordinary_client_v2.py"
TRACES={"cold":ROUNDS/"E2-R017"/"forward_trace.json","warm":ROUNDS/"E2-R017"/"reverse_trace.json"}
TRACE_SHA={"cold":"055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899",
           "warm":"097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24"}
R017_ROUND_SHA="f3198a83789480c6bf2e4a2d333f036a3a12e3fd055241e6a5e55c91d4660c37"
R017_MANIFEST_SHA="68595988896b31b4f08e545b291396cb9cafb45162b965e0edc48bc296316c38"
OLD_SHA="31f1a9c190f2b529b8e4b2d2bc964af0b5cd5e084d4a16b05db797143c4df98e"
REVIEW_DIR=ROOT/"runs/dev_T10/reviews/E2-R044-night-20261010-retry1"
DEV_D16_CAPTURE_ROOT=ROOT/"runs/dev_D16"/RID
R052A_ACTUAL_RID="E2-R052a-night-20261009-v2"
R052A_ACTUAL_MANIFEST_SHA="e342d1a7557c80936dbf60bd4df6e21fa89ac9b54aeae7e54bbd5b934b294184"
R052A_ACTUAL_ROUND_SHA="a6afa48714be5357c1dc9af157c944541f24768414c94653e1928a8a54d14b8a"
MODEL="Qwen3.8-Flash-Next-NVFP4"; ARMS=("B1","B2","B3"); MODES={"ordinary":False,"layer_major":True}
PAIR_SOURCE=HERE/"ft_batch_port_pair_v1.py"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open("x",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2,sort_keys=True);f.write("\n")
def load_d07(source=D07_SOURCE):
 spec=importlib.util.spec_from_file_location("t10_d07",source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def load_source(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def port_pair():
 m=load_source(PAIR_SOURCE,"t10_port_pair")
 return m.port_receipt(m.dynamic_port())

def copy_runtime_sources(target):
 target.mkdir(parents=True,exist_ok=False)
 rows=[]
 for source in (Path(__file__).resolve(),CAPTURE_STARTUP,LEGACY_CAPTURE,REPLAY_SOURCE,ORDINARY_ADAPTER,ORDINARY_CLIENT,PAIR_SOURCE):
  if source.is_symlink() or not source.is_file():raise RuntimeError("T10 runtime source unavailable")
  copied=target/source.name;shutil.copyfile(source,copied);copied.chmod(0o600)
  with copied.open("ab") as handle:handle.flush();os.fsync(handle.fileno())
  if sha(copied)!=sha(source):raise RuntimeError("T10 runtime copy differs")
  rows.append({"source":str(source),"copy":str(copied),"sha256":sha(copied),"mode":oct(copied.stat().st_mode&0o777)})
 return rows

def file_dry_run(directory):
 """Formal writer rehearsal: no lock, RID, Popen, connection or request."""
 directory=Path(directory)
 if (directory.exists() or any(p.is_symlink() for p in (directory,*directory.parents))
     or directory.parent.resolve()!=ROUNDS.resolve() or not directory.name.startswith('.dryrun_R044_')):
  raise RuntimeError("T10 file-dry output must be a fresh canonical hidden sibling")
 d=load_d07();require_queue(d,check_lock=False);admission=packet(WT);directory.mkdir(parents=True,mode=0o700);copies=copy_runtime_sources(directory/"source");planned=[]
 for mode,layer_major in MODES.items():
  for arm in ARMS:
   path=directory/mode/arm;path.mkdir(parents=True);pair=port_pair()
   write_new(path/'port_pair.json',pair)
   prepared=start_mode(d,path,WT,pair['api'],path/'route',layer_major,directory/'source'/CAPTURE_STARTUP.name,file_dry=True)
   planned.append({"mode":mode,"arm":arm,"port_pair":pair,"service":prepared})
 receipt={"schema":"ft_r044_file_dry_run/v3","rid":RID,"candidate_commit":CANDIDATE,"passed":True,"admission":admission,"source_copies":copies,"services":planned,"source_sha256":startup_source_hashes(),"script":str(Path(__file__).resolve()),"cwd":os.getcwd(),"uid":os.getuid(),"formal_rid_directory_created":False,"service_started":False,"requests_sent":False,"gpu_lock_taken":False,"batch_allocated":False}
 write_new(directory/"dry_run_receipt.json",receipt);(directory/"dry_run_receipt.json").chmod(0o444);return receipt

def retained_registration():
 root=OLD.parent;round_path=root/"round.json";manifest=root/"MANIFEST.sha256"
 for path,wanted in ((round_path,R017_ROUND_SHA),(manifest,R017_MANIFEST_SHA)):
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222 or sha(path)!=wanted:
   raise RuntimeError("T10 R017 sealed metadata binding differs")
 value=json.loads(round_path.read_text())
 if value.get("verdict")!="kept" or not any(x.get("new")=="kept" for x in value.get("verdict_history",[])):
  raise RuntimeError("T10 R017 D04 kept history is missing")
 entries={line.split(maxsplit=1)[1].removeprefix("./"):line.split()[0] for line in manifest.read_text().splitlines() if line.strip()}
 if entries.get(OLD.name)!=OLD_SHA or any(entries.get(path.name)!=TRACE_SHA[name] for name,path in TRACES.items()):
  raise RuntimeError("T10 retained inputs are not registered in R017 MANIFEST")
 return {name:{"path":str(path),"sha256":TRACE_SHA[name],"rounds":12} for name,path in TRACES.items()}


R040G_MEASUREMENT_COMMIT = "effb9969706922ddad9e59b96377e46469ebe97f"
HISTORICAL_T20_COMMIT = "0aa23431e5b800797543bdecbf35a01045131d7d"
def require_r040g_measurement(closure):
    document = json.loads(Path(closure).read_text())
    if (document.get("base", {}).get("commit") != R040G_MEASUREMENT_COMMIT
            or document.get("experimental", {}).get("candidate_commit") != R040G_MEASUREMENT_COMMIT):
        raise RuntimeError("E2-R040g measured closure is not bound to effb996")
    return closure

def require_actual_r052a_not_met():
 """Consume the exact sealed R052a terminal, not an abstract queue label."""
 directory=ROUNDS/R052A_ACTUAL_RID;round_json=directory/"round.json";manifest=directory/"MANIFEST.sha256";history=directory/"round_history";sums=history/"SHA256SUMS"
 required=(directory,round_json,manifest,history,sums,history/"round.v002.json")
 if any(path.is_symlink() or not path.exists() for path in required) or not directory.is_dir() or not history.is_dir():raise RuntimeError("T10 actual R052a sealed terminal is incomplete")
 for path in (directory,*directory.rglob("*")):
  if path.is_symlink() or path.stat().st_mode&0o222:raise RuntimeError("T10 actual R052a sealed terminal has writable or symlinked member")
 if sha(manifest)!=R052A_ACTUAL_MANIFEST_SHA or sha(round_json)!=R052A_ACTUAL_ROUND_SHA:raise RuntimeError("T10 actual R052a manifest or terminal round SHA differs")
 try:document=json.loads(round_json.read_text());history_sums=sums.read_text().splitlines()
 except (OSError,json.JSONDecodeError) as exc:raise RuntimeError("T10 actual R052a terminal is unreadable") from exc
 expected={"round_id":R052A_ACTUAL_RID,"verdict":"not_met","proposed_verdict":"not_met","product_acceptance":False}
 if any(document.get(key)!=value for key,value in expected.items()):raise RuntimeError("T10 actual R052a terminal verdict/facts differ")
 if document.get("base",{}).get("commit")!=CANDIDATE or document.get("experimental",{}).get("candidate_commit")!=CANDIDATE:raise RuntimeError("T10 actual R052a candidate binding differs")
 entries={}
 for line in manifest.read_text().splitlines():
  parts=line.split(maxsplit=1)
  if len(parts)!=2 or len(parts[0])!=64:raise RuntimeError("T10 actual R052a manifest entry differs")
  relative=parts[1].removeprefix("./");target=directory/relative
  if relative in entries or target.is_symlink() or not target.is_file() or sha(target)!=parts[0]:raise RuntimeError("T10 actual R052a manifest payload binding differs")
  entries[relative]=parts[0]
 if entries.get("independent_review.json")!=document.get("independent_review",{}).get("sha256"):raise RuntimeError("T10 actual R052a terminal evidence binding differs")
 history_entries={line.split(maxsplit=1)[1]:line.split()[0] for line in history_sums if line.strip() and len(line.split(maxsplit=1))==2}
 if history_entries.get("round.v002.json")!=R052A_ACTUAL_ROUND_SHA or sha(history/"round.v002.json")!=R052A_ACTUAL_ROUND_SHA or (history/"round.v002.json").read_bytes()!=round_json.read_bytes():raise RuntimeError("T10 actual R052a history binding differs")
 return {"rid":R052A_ACTUAL_RID,"path":str(round_json),"round_sha256":R052A_ACTUAL_ROUND_SHA,"manifest_path":str(manifest),"manifest_sha256":R052A_ACTUAL_MANIFEST_SHA,"facts":expected}

def require_queue(d,check_lock=True):
 if check_lock and (d.LOCK.exists() or d.LOCK.is_symlink()):raise RuntimeError("foreign GPU lock exists; T10 remains queued")
 t20=d.require_t20_failed_harness()
 d.require_closed_round("E2-R052","failed_harness")
 d.require_closed_round("E2-R040f","failed_harness")
 require_actual_r052a_not_met()
 return t20

def require_output_root(output_root):
 output_root=Path(output_root)
 if (not output_root.is_absolute() or '..' in output_root.parts
     or any(p.is_symlink() for p in [output_root,*output_root.parents])
     or output_root.resolve()!=ROUNDS.resolve()):
  raise RuntimeError("T10 output root must be canonical ft_rounds")

def startup_source_hashes():
 paths=[Path(__file__).resolve(),CAPTURE_STARTUP,LEGACY_CAPTURE,REPLAY_SOURCE,ORDINARY_ADAPTER,ORDINARY_CLIENT,STRICT_READER,D07_SOURCE,PAIR_SOURCE,ARGS_READER]
 paths.extend(WT/'scripts/equiv_suite'/name for name in ('__init__.py','service_capture_startup.py','service_capture.py','sampler_capture.py'))
 paths.extend(WT/name for name in ('scripts/_agent_trace_original.py','python/freetoken/server/launch.py','python/freetoken/server/args.py','python/freetoken/server/openai_api.py'))
 return {str(p):sha(p) for p in paths}

def require_file_dry_receipt(path):
 path=Path(path)
 if (any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_mode&0o222
     or path.name!='dry_run_receipt.json' or path.parent.parent.resolve()!=ROUNDS.resolve()
     or not path.parent.name.startswith('.dryrun_R044_')):raise RuntimeError('T10 requires readonly actual file-dry receipt')
 value=json.loads(path.read_text())
 expected={'schema':'ft_r044_file_dry_run/v3','rid':RID,'candidate_commit':CANDIDATE,'passed':True,
           'script':str(Path(__file__).resolve()),'cwd':os.getcwd(),'uid':os.getuid(),'source_sha256':startup_source_hashes()}
 if any(value.get(k)!=v for k,v in expected.items()) or len(value.get('services',[]))!=6:raise RuntimeError('T10 file-dry identity/source/coverage differs')
 if any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')):raise RuntimeError('T10 file-dry has prohibited effects')
 return {'path':str(path),'sha256':sha(path)}

def require_startup_review():
 directory=REVIEW_DIR;review=directory/"review.json";pin=directory/"pin.json"
 if (not directory.is_dir() or directory.stat().st_mode&0o222
     or any(p.is_symlink() for p in [directory,*directory.parents])):
  raise RuntimeError("T10 startup review directory is not sealed")
 for path in (review,pin):
  if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:
   raise RuntimeError("T10 startup review file is absent or writable")
 registered=json.loads(pin.read_text())
 if (registered.get('schema')!='ft_t10_startup_review_pin/v1' or registered.get('rid')!=RID
     or registered.get('review_path')!=str(review) or registered.get('review_sha256')!=sha(review)):
  raise RuntimeError("T10 startup review SHA pin differs")
 value=json.loads(review.read_text());expected={'schema':'ft_t10_startup_review/v3','rid':RID,
     'candidate_commit':CANDIDATE,'approved':True,'verdict':'PASS',
     'output_root':str(ROUNDS),'source_sha256':startup_source_hashes()}
 if any(value.get(k)!=v for k,v in expected.items()):raise RuntimeError("T10 startup review source/output binding differs")
 dry=require_file_dry_receipt(value.get('file_dry_receipt',''))
 if value.get('file_dry_receipt_sha256')!=dry['sha256']:raise RuntimeError('T10 startup review file-dry SHA differs')
 return review

def bind_inputs(run):
 bound={}
 for name,path in TRACES.items():
  payload=path.read_bytes()
  if hashlib.sha256(payload).hexdigest()!=TRACE_SHA[name]:raise RuntimeError("T10 business trace SHA differs")
  target=run/(name+"_trace_input.json")
  with target.open("xb") as stream:stream.write(payload)
  target.chmod(0o444);trace_rows(target);bound[name]=target
 return bound
def trace_rows(path):
 d=json.loads(Path(path).read_text()); rows=d.get("rounds")
 if not isinstance(rows,list) or len(rows)!=12: raise ValueError("T10 requires exact retained 12-round trace")
 out={}
 for r in rows:
  messages=r.get("messages"); rec=r.get("record") or {}; key=rec.get("messages_sha")
  if not isinstance(messages,list) or not isinstance(key,str) or key in out: raise ValueError("retained input messages binding is incomplete")
  if hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]!=key: raise ValueError("retained input messages SHA differs")
  out[key]=r
 return out
def packet(wt=WT):
 d=load_d07(); cand=d.checked_worktree(wt);tools=d.verify_d07_tools(wt)
 retained=retained_registration()
 if not OLD.is_file() or OLD.is_symlink(): raise RuntimeError("T10 requires retained E2-R017 phase1 manifest for the 33/36 comparison")
 capture=CAPTURE_STARTUP
 if capture.is_symlink() or not capture.is_file():raise RuntimeError("T10 actual service-capture startup is unavailable")
 r052a=require_actual_r052a_not_met()
 return {"schema":"ft_t10_e2_r044_prepare/v1","rid":RID,"card":"T10","candidate_commit":CANDIDATE,"candidate":cand,"historical_t20_commit":HISTORICAL_T20_COMMIT,"tools":tools,"retained_inputs":retained,"capture_startup":{"path":str(capture),"sha256":sha(capture),"uid_contract":"fresh HTTP service UIDs 0..23; 12 cold then 12 warm"},"old_33_36_evidence":{"path":str(OLD),"sha256":OLD_SHA,"ordinary_cold_warm_identical":3,"ordinary_cold_warm_total":36},"groups":[{"name":n,"prefill_layer_major":v,"processes":3,"cold_warm_rounds":12} for n,v in MODES.items()],"queue_authorization":{"r040g":factual("E2-R040g"),"r052a":{"actual_terminal":r052a,"authorization":"user_authorized_independent_terminal"},"night_tail_queue":policy("E2-R044")},"run_requires":["explicit --run","Linux","T20 E2-R040 failed_harness per user decision","E2-R052 failed_harness retained",f"actual {R052A_ACTUAL_RID} not_met terminal","factual E2-R040g failed_harness recorded","owned O_EXCL lock","GPU idle","R launch review"],"cuda_visible_devices_cpu_guard":""}
def validate_replay(path,expected):
 d=json.loads(path.read_text());rows=d.get("rounds")
 if not isinstance(rows,list) or len(rows)!=12: raise ValueError("replay lacks 12 real rows")
 found={}
 for r in rows:
  key=r.get("messages_sha")
  if key not in expected or key in found or not isinstance(r.get("text"),str) or r.get("error") is not None or r.get("dry_run") or r.get("finish_reason") not in {"stop","length","tool_calls"}: raise ValueError("T10 replay input/fulltext/terminal binding fails")
  if not isinstance(r.get("completion_tokens"),int) or r["completion_tokens"]<1 or not isinstance(r.get("cached_tokens"),int) or r.get('transport')!='ordinary_sse_no_ft_dev_ack' or type(r.get("uid")) is not int: raise ValueError("T10 replay lacks ordinary UID/cache evidence")
  if 'ack_schema' in r:raise ValueError('T10 ordinary replay rejects dev ACK')
  found[key]=r
 if set(found)!=set(expected): raise ValueError("T10 replay messages differ from retained inputs")
 return found
def invoke_replay(wt,port,phase,trace,out,log,d):
 runtime=out.parent.parent.parent/'source'
 cmd=[str(VENV/"bin/python"),str(runtime/REPLAY_SOURCE.name),"--original",str(wt/'scripts/_agent_trace_original.py'),"--trace",str(trace),"--out",str(out),"--base-url",f"http://127.0.0.1:{port}/v1","--model",MODEL,"--phase",phase]
 env=d.clean_environment(wt);env["FT_REPLAY_MAX_TOKENS"]="200"
 with log.open("x",encoding="utf-8") as f:subprocess.run(cmd,cwd=wt,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 return validate_replay(out,trace_rows(trace))
def capture_expected(arm):
 """The OpenAI API's fresh FrontendManager assigns 0..23 for these serial replays."""
 path=arm/"expected_capture.json"
 rows=[{"uid":uid,"generation_index":generation,"logical_label":f"{RID}:{arm.name}:uid-{uid}"} for uid in range(CAPTURE_REQUESTS) for generation in range(CAPTURE_MAX_TOKENS)]
 write_new(path,rows);return path
def capture_bindings(arm):
 """Reject a service unless every HTTP reply UID has a physical sampler/delivery chain."""
 root=capture_destination(arm); report=root/"service_delivery.json"
 if not report.is_file() or report.is_symlink():raise ValueError("T10 sampler capture report is missing")
 data=json.loads(report.read_text())
 shutdown=json.loads((arm/'worker_shutdown.json').read_text())
 if shutdown.get('schema')!='ft_t10_worker_shutdown/v3' or shutdown.get('status')!='complete' or shutdown.get('scheduler_run_started') is not True:raise ValueError('T10 worker did not complete capture shutdown')
 identity=data.get('process_identity') or {}
 if any(shutdown.get(k)!=identity.get(k) for k in ('pid','start_ticks')):raise ValueError('T10 shutdown worker birth differs from capture')
 cap=data.get("t10_terminal_cap",{});counts=cap.get("actual_delivery_counts",{})
 if data.get("terminal")!="complete" or data.get("errors") or cap.get("declared_max_tokens")!=CAPTURE_MAX_TOKENS or len(data.get("admission_receipts",[]))!=CAPTURE_REQUESTS:raise ValueError("T10 sampler capture did not complete all declared HTTP UIDs")
 admissions={x["uid"]:x for x in data["admission_receipts"]}
 if set(admissions)!=set(range(CAPTURE_REQUESTS)):raise ValueError("T10 sampler capture UID allocation differs from fresh-service contract")
 tokens={uid:[] for uid in admissions}
 for row in data.get("deliveries",[]):
  uid=row.get("uid");gen=row.get("generation_index");token=row.get("sampled_token_id")
  if uid not in tokens or gen!=len(tokens[uid]) or type(token)is not int:raise ValueError("T10 sampler delivery ordering/binding differs")
  tokens[uid].append(token)
 if any(not values or len(values)>CAPTURE_MAX_TOKENS or counts.get(str(uid))!=len(values) for uid,values in tokens.items()):raise ValueError("T10 sampler capture terminal counts differ from physical deliveries")
 return {"service_delivery_sha256":sha(report),"sampler_root":str(root/"sampler"),"process_identity":data.get("process_identity"),"uids":{str(uid):{"input_ids_sha256":admissions[uid].get("receipt_sha256"),"sampled_token_ids":tokens[uid]} for uid in tokens}}
def bind_capture(replay,capture,offset):
 out={}
 for index,(key,row) in enumerate(replay.items()):
  uid=row["uid"];expected=offset+index
  if uid!=expected or str(uid) not in capture["uids"]:raise ValueError("T10 HTTP UID does not bind the declared sampler capture")
  evidence=capture["uids"][str(uid)]
  if len(evidence["sampled_token_ids"])!=row["completion_tokens"]:raise ValueError("T10 completion count differs from captured sampled IDs")
  out[key]={**row,"capture_input_receipt_sha256":evidence["input_ids_sha256"],"sampler_root":capture["sampler_root"],"sampled_token_ids":evidence["sampled_token_ids"]}
 return out
def top2(record,index):
 """Read only the pinned sampler row at the first actual ID fork; no retokenization."""
 root=Path(record["sampler_root"]);manifest=json.loads((root/"manifest.json").read_text())
 if manifest.get("terminal")!="complete":raise ValueError("T10 sampler manifest is not terminal")
 for item in manifest.get("captures",[]):
  directory=root/item["id"];receipt=directory/"receipt.json";raw=receipt.read_bytes()
  if sha(receipt)!=item.get("receipt_sha256"):raise ValueError("T10 sampler receipt is not manifest-bound")
  rows=json.loads(raw).get("rows",[])
  for row in rows:
   if row.get("uid")==record["uid"] and row.get("generation_index")==index:
    import torch
    snapshot=directory/"logits_fp32.pt"
    if sha(snapshot)!=json.loads(raw).get("snapshot",{}).get("sha256"):raise ValueError("T10 sampler receipt does not bind logits bytes")
    logits=torch.load(snapshot,map_location="cpu",weights_only=True)[row["row_index"]].contiguous()
    values,ids=torch.topk(logits,2);return {"capture_id":item["id"],"capture_receipt_sha256":sha(receipt),"top2_ids":[int(x) for x in ids.tolist()],"top2_values":[float(x) for x in values.tolist()],"top2_gap":float(values[0]-values[1]),"tensor_dtype":str(logits.dtype),"tensor_shape":list(logits.shape),"tensor_sha256":hashlib.sha256(logits.numpy().tobytes()).hexdigest()}
 raise ValueError("T10 first divergent sampled ID lacks a sampler-logits row")
def first(left,right):
 a,b=left["text"],right["text"];i=next((n for n,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)));same=len(a)==len(b) and i==len(a)
 x,y=left.get("parts",[]),right.get("parts",[]);piece=next((n for n,(u,v) in enumerate(zip(x,y)) if u!=v),min(len(x),len(y)))
 ids_a,ids_b=left.get("sampled_token_ids"),right.get("sampled_token_ids")
 if not isinstance(ids_a,list) or not isinstance(ids_b,list):raise ValueError("T10 comparison lacks physical sampled token IDs")
 token_index=next((n for n,(u,v) in enumerate(zip(ids_a,ids_b)) if u!=v),min(len(ids_a),len(ids_b)));same_ids=len(ids_a)==len(ids_b) and token_index==len(ids_a)
 logits=None if same_ids else {"left":top2(left,token_index),"right":top2(right,token_index)}
 if logits is not None:logits["classification"]="top2_exact" if logits["left"]["tensor_sha256"]==logits["right"]["tensor_sha256"] else ("top1_same_top2_diff" if logits["left"]["top2_ids"][0]==logits["right"]["top2_ids"][0] else "top1_diff")
 return {"same_fulltext":same,"first_text_codepoint":None if same else i,"first_stream_piece_index":None if len(x)==len(y) and piece==len(x) else piece,"same_sampled_token_ids":same_ids,"first_sampled_token_index":None if same_ids else token_index,"first_fork_top2":logits,"left_text_sha256":hashlib.sha256(a.encode()).hexdigest(),"right_text_sha256":hashlib.sha256(b.encode()).hexdigest(),"left_completion_tokens":left["completion_tokens"],"right_completion_tokens":right["completion_tokens"],"left_uid_cached_tokens":{"uid":left["uid"],"cached_tokens":left["cached_tokens"]},"right_uid_cached_tokens":{"uid":right["uid"],"cached_tokens":right["cached_tokens"]},"left_capture_input_receipt_sha256":left["capture_input_receipt_sha256"],"right_capture_input_receipt_sha256":right["capture_input_receipt_sha256"]}
def comparisons(group):
 out={}
 for kind,pairs in {"cold_cold":[("B1","B2"),("B1","B3"),("B2","B3")],"warm_warm":[("B1","B2"),("B1","B3"),("B2","B3")],"cold_warm":[("B1","B1"),("B2","B2"),("B3","B3")]}.items():
  rows=[]
  for a,b in pairs:
   left=group[a]["cold" if kind!="warm_warm" else "warm"];right=group[b]["cold" if kind=="cold_cold" else "warm"]
   rows += [{"left_arm":a,"right_arm":b,"round":left[k].get("round"),"messages_sha":k,**first(left[k],right[k])} for k in left]
  if len(rows)!=36: raise ValueError("T10 comparison must contain 36 actual pair-rounds")
  out[kind]={"total":36,"identical":sum(x["same_fulltext"] for x in rows),"rows":rows}
 return out
def capture_destination(directory):
 """Keep capture bytes out of formal ft_rounds while retaining mode/arm identity."""
 directory=Path(directory)
 return DEV_D16_CAPTURE_ROOT/directory.parent.name/directory.name/"capture"

def service_files(d,directory,wt,port,layer_major,capture_startup):
 expected=capture_expected(directory);value=d.serve_argv(port)
 for key in ("--kv-reserve-tokens","--max-seq-len-override"):value[value.index(key)+1]='98304'
 if not layer_major:value.remove('--prefill-layer-major')
 argv=[str(VENV/'bin/python'),'-u',str(capture_startup),*value[1:]]
 env=d.clean_environment(wt,trace_dir=None)
 env.update(FT_D16_SERVICE_CAPTURE_DIR=str(capture_destination(directory)),FT_D16_EXECUTION_ID=f'{RID}:{directory.parent.name}:{directory.name}',FT_D16_SERVICE_CAPTURE_EXPECTED_JSON=str(expected),FT_D16_SERVICE_CAPTURE_MAX_CAPTURES=str(CAPTURE_REQUESTS*CAPTURE_MAX_TOKENS+1024),FT_D16_SERVICE_CAPTURE_MAX_BYTES=str(8*1024**3),FT_T10_CAPTURE_MAX_TOKENS=str(CAPTURE_MAX_TOKENS),FT_T10_WORKER_SHUTDOWN=str(directory/'worker_shutdown.json'))
 env['PYTHONPATH']=str(Path(capture_startup).parent)+':'+str(wt/'python')+':'+str(wt/'scripts')
 write_new(directory/'service_plan.json',{'argv':argv,'environment':{k:v for k,v in env.items() if k.startswith('FT_') or k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES','VIRTUAL_ENV')},'route_trace':False,'pause':False,'layer_major':layer_major})
 return argv,env

def start_mode(d,directory,wt,port,route,layer_major,capture_startup=CAPTURE_STARTUP,*,file_dry=False):
 import shlex,time,urllib.request
 directory.mkdir(parents=True,exist_ok=True)
 argv,env=service_files(d,directory,wt,port,layer_major,capture_startup)
 with (directory/'SERVE_CMD.txt').open('x',encoding='utf-8') as stream:stream.write(shlex.join(argv)+'\n')
 log=(directory/'serve.log').open('x',encoding='utf-8')
 if file_dry:
  log.close()
  for name in ('worker_shutdown.json','owned_process.json','health.json','cold.json','warm.json'):
   probe=directory/(name+'.write_probe')
   with probe.open('x',encoding='utf-8') as stream:stream.write('{}\n');stream.flush();os.fsync(stream.fileno())
  return {'argv':argv,'file_dry':True,'service_started':False,'service_plan_sha256':sha(directory/'service_plan.json')}
 try:process=subprocess.Popen(argv,cwd=wt,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 finally:log.close()
 lifecycle=d.load_owned_lifecycle()
 try:
  birth=lifecycle.process_identity(process.pid)
  if birth is None or birth.get('pgid')!=process.pid or birth.get('session')!=process.pid:raise RuntimeError('T10 service process identity differs')
  write_new(directory/'owned_process.json',{'pid':process.pid,'pgid':process.pid,'port':port,'birth':birth})
  deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   if process.poll() is not None:raise RuntimeError('T10 service exited during startup')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as response:health=json.load(response)
    if health.get('status')=='ok':write_new(directory/'health.json',health);return process
   except (OSError,ValueError):pass
   time.sleep(2)
  raise TimeoutError('T10 service did not become healthy')
 except BaseException:
  try:lifecycle.stop_owned_process(process)
  except BaseException as error:error.owned_process=process;error.owned_cleanup_failed=True;raise
  raise
def serve_identity(arm,layer_major):
 owned=json.loads((arm/"owned_process.json").read_text());parsed=load_source(ARGS_READER,"t10_args_reader").parse(arm/"serve.log")
 required={"model_path","server_port","prefill_layer_major","max_prefill_length","max_extend_tokens","mamba_host_slots","enable_cache_report","special_token_ckpt","_unique_suffix"}
 if required-set(parsed):raise ValueError("actual serve.log lacks strict parsed arguments")
 if str(parsed["server_port"])!=str(owned["port"]) or str(parsed["prefill_layer_major"])!=str(layer_major):raise ValueError("actual serve.log port/layer-major differs from declared service")
 if parsed["_unique_suffix"]!=f".pid={owned['pid']}":raise ValueError("actual serve.log PID suffix differs from owned process")
 normalized=dict(parsed);normalized["server_port"]="<dynamic-port>"
 return {"parsed":parsed,"normalized":normalized,"serve_log_sha256":sha(arm/"serve.log"),"owned_process":owned}
def child_argv(batch,receipt,wt,output_root):return [str(VENV/"bin/python"),str(Path(__file__).resolve()),"--run","--owned-child","--batch",str(batch),"--launch-receipt",str(receipt),"--worktree",str(wt),"--output-root",str(output_root)]
def execute(wt=WT,output_root=ROUNDS,*,owned_child=False,batch=None,launch_receipt=None):
 if sys.platform!="linux":raise RuntimeError("T10 --run requires Linux")
 d=load_d07()
 if not owned_child:
  require_output_root(output_root)
  t20=require_queue(d);admission=packet(wt)
  review=require_startup_review()
  if (output_root/RID).exists():raise RuntimeError("T10 E2-R044 exists; no overwrite")
  owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/"runs/plan_batches/e2_launch.py",d.ATOMIC_HELPER_SHA,"t10_atomic_launcher")
  if d.LOCK.exists() or d.LOCK.is_symlink():raise RuntimeError("foreign GPU lock exists; T10 remains queued")
  batch=helper.next_batch(ROUNDS);output_root.mkdir(parents=True,exist_ok=True);receipt_path=output_root/f"launch_{RID}_batch{batch}.json";argv=child_argv(batch,receipt_path,wt,output_root)
  reserved={"schema":"ft_t10_owned_launch/v3","state":"reserved","rid":RID,"batch":batch,"candidate_commit":CANDIDATE,"argv_sha256":d.argv_sha256(argv),"owned_protocol_sha256":d.OWNED_PROTOCOL_SHA,"atomic_helper_sha256":d.ATOMIC_HELPER_SHA,"controller":d.process_birth(),"t20_round_sha256":sha(t20),"startup_review_sha256":sha(review),"packet_sha256":hashlib.sha256(json.dumps(admission,sort_keys=True).encode()).hexdigest()}
  receipt=owned.reserve_process(helper,batch,RID,argv,receipt_path,reserved);identity=owned.process_identity(receipt["batch_pid"])
  if identity is None or identity.get("pid")!=receipt["batch_pid"] or type(identity.get("start_ticks")) is not int:raise RuntimeError("T10 reserved child birth is unavailable")
  return d.publish_child_binding(receipt_path,receipt,{"pid":identity["pid"],"start_ticks":identity["start_ticks"],"execution_id":f"{identity['pid']}:{identity['start_ticks']}"},lifecycle=owned)
 if batch is None or launch_receipt is None:raise RuntimeError("T10 owned child requires controller receipt and reserved batch")
 d.require_child_receipt(launch_receipt,batch,wt,output_root,rid=RID,expected_argv=child_argv(batch,launch_receipt,wt,output_root),schema="ft_t10_owned_launch/v3")
 require_output_root(output_root)
 t20=require_queue(d);admission=packet(wt)
 review=require_startup_review()
 if (output_root/RID).exists():raise RuntimeError("T10 E2-R044 exists; no overwrite")
 owner=d.take_d07_gpu_lock(RID,batch);run=None;process=None;cleanup_failed=False
 try:
  idle=d.require_gpu_idle();run=output_root/RID;run.mkdir(parents=True);copies=copy_runtime_sources(run/"source");write_new(run/"preflight.json",{**admission,"batch":batch,"gpu_owner":owner,"gpu_memory_mib":idle,"t20_closure":str(t20),"t20_closure_sha256":sha(t20),"source_copies":copies})
  traces=bind_inputs(run);groups={}
  for mode,layer_major in MODES.items():
   group={};mode_dir=run/mode;mode_dir.mkdir()
   identities=[]
   for arm in ARMS:
    arm_dir=mode_dir/arm;arm_dir.mkdir();route=arm_dir/"route";route.mkdir();pair=port_pair();port=pair["api"];write_new(arm_dir/"port_pair.json",pair)
    try:process=start_mode(d,arm_dir,wt,port,route,layer_major,run/'source'/CAPTURE_STARTUP.name)
    except BaseException as exc:
     process=getattr(exc,"owned_process",process);cleanup_failed=bool(getattr(exc,"owned_cleanup_failed",False));raise
    try:
     cold=invoke_replay(wt,port,"cold",traces["cold"],arm_dir/"cold.json",arm_dir/"cold.log",d);warm=invoke_replay(wt,port,"warm",traces["warm"],arm_dir/"warm.json",arm_dir/"warm.log",d)
    finally:
     try:d.load_owned_lifecycle().stop_owned_process(process)
     except BaseException:cleanup_failed=True;raise
     process=None
    capture=capture_bindings(arm_dir);group[arm]={"cold":bind_capture(cold,capture,0),"warm":bind_capture(warm,capture,12),"sampler_capture":capture}
    identities.append(serve_identity(arm_dir,layer_major))
   strict=load_source(STRICT_READER,"t10_strict_args").strict_args
   for identity in identities[1:]:strict(identities[0]["normalized"],identity["normalized"],{})
   groups[mode]={"prefill_layer_major":layer_major,"arms":group,"serve_identities":identities,"comparisons":comparisons(group)}
  ordinary=dict(groups["ordinary"]["serve_identities"][0]["normalized"]);layer=dict(groups["layer_major"]["serve_identities"][0]["normalized"]);layer["prefill_layer_major"]=ordinary["prefill_layer_major"];strict(ordinary,layer,{})
  phase2={"status":"physical_sampled_ids_and_first_fork_top2_recorded","scope":"every accepted replay UID binds UserMsg input IDs, sampler sampled IDs, DetokenizeMsg delivery, and retained sampler-input FP32 snapshots","top2":"each actual sampled-ID fork records the manifest-bound sampler row's top-2 IDs, FP32 values, gap, tensor SHA and R013-style top1/top2 classification","budget":{"max_tokens_per_request":CAPTURE_MAX_TOKENS,"max_sampler_rows_per_service":CAPTURE_REQUESTS*CAPTURE_MAX_TOKENS,"max_bytes":8*1024**3},"failure_contract":"200 is a cap: each UID must terminate once at an actual length in [1,200]; missing, extra, reordered or nonterminal sampler/Detokenize delivery is rejected"}
  result={"schema":"ft_t10_raw_measurement/v1","round_id":RID,"card":"T10","base":{"code_version":"E2-base.1@0aa23431","commit":CANDIDATE},"batch":batch,"verdict":"pending_review","proposed_verdict":"measured","old_33_36_retained":admission["old_33_36_evidence"],"groups":groups,"phase2_logits":phase2,"timing":"not a performance result","raw_measurement_before_D04":True};write_new(run/"result.json",result);return result
 except BaseException as e:
  if run is not None:write_new(run/"failed_harness.json",{"rid":RID,"batch":batch,"gpu_owner":owner,"error":repr(e),"raw_measurement_preserved":True})
  raise
 finally:
  if cleanup_failed:raise RuntimeError("T10 owned cleanup failed; preserve GPU lock for recovery")
  if process is not None:
   try:d.load_owned_lifecycle().stop_owned_process(process)
   except BaseException:cleanup_failed=True;raise
  if process is not None and d.load_owned_lifecycle().owned_group_alive(process.pid):raise RuntimeError("T10 owned service remains; preserve GPU lock for recovery")
  d.release_d07_gpu_lock(owner)
  if run is not None:write_new(run/"owned_cleanup.json",{"schema":"ft_t10_owned_cleanup/v1","rid":RID,"batch":batch,"gpu_owner":owner,"lock_released":True})
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--run",action="store_true");p.add_argument("--file-dry-run",type=Path);p.add_argument("--owned-child",action="store_true",help=argparse.SUPPRESS);p.add_argument("--batch",type=int,help=argparse.SUPPRESS);p.add_argument("--launch-receipt",type=Path,help=argparse.SUPPRESS);p.add_argument("--worktree",type=Path,default=WT);p.add_argument("--output-root",type=Path,default=ROUNDS);a=p.parse_args(argv)
 if a.file_dry_run:
  if a.run or a.owned_child or a.batch is not None or a.launch_receipt is not None:p.error("--file-dry-run cannot mix launch arguments")
  print(json.dumps(file_dry_run(a.file_dry_run),ensure_ascii=False,sort_keys=True));return
 print(json.dumps(execute(a.worktree,a.output_root,owned_child=a.owned_child,batch=a.batch,launch_receipt=a.launch_receipt) if a.run else packet(a.worktree),ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
