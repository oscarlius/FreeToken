#!/bin/bash
set -euo pipefail
exec /data2/FreeToken/venv/bin/python -u -c 'import os,sys,json,hashlib,importlib.util,subprocess,time,signal,socket,shutil,re,struct,urllib.request
from pathlib import Path
BASE=Path('"'"'/data2/FreeToken/development/r067_d20_short_tail_v1'"'"')
RID='"'"'E2-R067-d20-short-tail'"'"'
PY='"'"'/data2/FreeToken/venv/bin/python'"'"'
RUN=Path('"'"'/data2/FreeToken/runs/dev_R067'"'"')/RID
FD=BASE/'"'"'R067_V2_2_FILEDRY_CONFIG.json'"'"'
ADMIT=BASE/'"'"'R067_ROOT_STARTUP_ADMISSION_20261009_v1.json'"'"'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,name):
 spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def put(p,value):
 with Path(p).open('"'"'x'"'"',encoding='"'"'utf-8'"'"') as h:json.dump(value,h,indent=2,ensure_ascii=False);h.write('"'"'\n'"'"')
def append(p,value):
 with Path(p).open('"'"'a'"'"',encoding='"'"'utf-8'"'"') as h:h.write(json.dumps(value,ensure_ascii=False)+'"'"'\n'"'"');h.flush();os.fsync(h.fileno())
def bindable(ports):
 handles=[]
 try:
  for port in ports:
   s=socket.socket();s.bind(('"'"'0.0.0.0'"'"',port));handles.append(s)
 finally:
  for s in handles:s.close()
assert sha(FD)=='"'"'987f9a8dc10f3bf4a330f63b7ba7570322427c642a09b89f58507bcef22a0ef4'"'"'
assert sha(ADMIT)=='"'"'45b270e15af50b8f28bd9734d2cb0bc91d54e38f614c1a6b23a049bc1f43528d'"'"'
fd=json.loads(FD.read_text());admit=json.loads(ADMIT.read_text())
assert admit['"'"'approved'"'"'] and admit['"'"'config_sha256'"'"']==sha(FD)
proof=Path(admit['"'"'root_preflight_path'"'"']);assert sha(proof)==admit['"'"'root_preflight_sha256'"'"']
for path,digest in json.loads(proof.read_text())['"'"'bindings'"'"'].items():assert sha(path)==digest,path
assert sha(admit['"'"'independent_review_path'"'"'])==admit['"'"'independent_review_sha256'"'"']
d07=load('"'"'/data2/FreeToken/development/d07_g3g4_prepare.py'"'"','"'"'r067_d07_actual'"'"')
d07.CANDIDATE=fd['"'"'worktree_binding'"'"']['"'"'hot'"'"']['"'"'commit'"'"'];d07.RID=RID
owned=d07.load_owned_lifecycle()
batch=int(os.environ['"'"'R067_BATCH'"'"']);receipt=Path(os.environ['"'"'R067_RECEIPT'"'"'])
actual_argv=[x.decode() for x in Path('"'"'/proc/self/cmdline'"'"').read_bytes().rstrip(b'"'"'\0'"'"').split(b'"'"'\0'"'"')]
assert actual_argv[-1]=='"'"'--run'"'"';planned_argv=actual_argv[:-1]
d07.require_child_receipt(receipt,batch,Path(fd['"'"'worktree_binding'"'"']['"'"'hot'"'"']['"'"'path'"'"']),RUN.parent,rid=RID,expected_argv=planned_argv,schema='"'"'ft_r067_owned_launch/v1'"'"')
for w in fd['"'"'worktree_binding'"'"'].values():
 assert subprocess.check_output(['"'"'git'"'"','"'"'-C'"'"',w['"'"'path'"'"'],'"'"'rev-parse'"'"','"'"'HEAD'"'"'],text=True).strip()==w['"'"'commit'"'"']
 assert not subprocess.check_output(['"'"'git'"'"','"'"'-C'"'"',w['"'"'path'"'"'],'"'"'status'"'"','"'"'--porcelain'"'"','"'"'--untracked-files=all'"'"'],text=True)
for path in ('"'"'/data2/FreeToken/run/production.active.json'"'"','"'"'/data2/FreeToken/run/production.cleanup_failed.json'"'"'):
 assert not Path(path).exists(),path
assert not RUN.exists()
owner=None;process=None;count_services=0;count_calls=0;results={};hot={};cold={};cells=[];verdict='"'"'pending'"'"';error=None;cleanup_errors=[]
def interrupted(sig,frame):raise InterruptedError('"'"'owned R067 signal '"'"'+str(sig))
for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupted)
try:
 owner=d07.take_d07_gpu_lock(RID,batch);d07.require_gpu_idle()
 RUN.mkdir();(RUN/'"'"'services'"'"').mkdir()
 put(RUN/'"'"'admission_snapshot.json'"'"',admit);put(RUN/'"'"'filedry_snapshot.json'"'"',fd)
 put(RUN/'"'"'launch_binding.json'"'"',{'"'"'batch'"'"':batch,'"'"'receipt'"'"':str(receipt),'"'"'child'"'"':d07.process_identity(os.getpid()),'"'"'argv_sha256'"'"':d07.argv_sha256(planned_argv),'"'"'actual_argv_sha256'"'"':d07.argv_sha256(actual_argv),'"'"'config_sha256'"'"':sha(FD)})
 tool=BASE/'"'"'t17_existing'"'"';sys.path.insert(0,str(tool))
 t17=load(tool/'"'"'t17_d14_runner.py'"'"','"'"'r067_t17_transport'"'"');art=load(tool/'"'"'t17_d14_artifacts.py'"'"','"'"'r067_t17_artifacts'"'"')
 inputs=json.loads(Path(fd['"'"'input_binding'"'"']['"'"'path'"'"']).read_text())
 cases={(x['"'"'prefix'"'"'],x['"'"'tail'"'"']):x for x in inputs['"'"'cases'"'"']}
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for service in fd['"'"'services'"'"']:
  name=service['"'"'name'"'"'];arm=Path(service['"'"'service_dir'"'"']);assert arm.parent==RUN/'"'"'services'"'"'
  for path,digest in json.loads(proof.read_text())['"'"'bindings'"'"'].items():assert sha(path)==digest,path
  bindable([service['"'"'port_pair'"'"']['"'"'api'"'"'],service['"'"'port_pair'"'"']['"'"'tcpstore'"'"']])
  arm.mkdir();(arm/'"'"'input_receipts'"'"').mkdir();(arm/'"'"'state_dump'"'"').mkdir()
  wrapper=t17.freeze_startup_wrapper(arm);shutil.copyfile(tool/'"'"'t17_d14_observe.py'"'"',arm/'"'"'t17_d14_observe.py'"'"');(arm/'"'"'t17_d14_observe.py'"'"').chmod(0o444)
  spawn=fd['"'"'cpu_file_dry_proof'"'"']['"'"'startup_spawn'"'"']
  assert sha(wrapper)==spawn['"'"'startup_sha256'"'"'] and sha(arm/'"'"'t17_d14_exact_ids.py'"'"')==spawn['"'"'exact_ids_sha256'"'"'] and sha(arm/'"'"'t17_d14_observe.py'"'"')==spawn['"'"'observer_sha256'"'"']
  env=d07.clean_environment(Path(service['"'"'worktree'"'"']));env.update(service['"'"'env'"'"'])
  assert '"'"'$'"'"' not in env['"'"'PATH'"'"']
  if service['"'"'kind'"'"']=='"'"'hot'"'"':assert '"'"'FT_DEV_PREFILL_SCHEDULE'"'"' not in env
  put(arm/'"'"'environment.json'"'"',{k:env[k] for k in service['"'"'env'"'"']})
  put(arm/'"'"'argv.json'"'"',service['"'"'argv'"'"']);assert d07.argv_sha256(service['"'"'argv'"'"'])==service['"'"'argv_sha256'"'"']
  assert count_services<10
  append(RUN/'"'"'budget.jsonl'"'"',{'"'"'event'"'"':'"'"'service_start_attempt'"'"','"'"'service'"'"':name,'"'"'index'"'"':count_services+1,'"'"'at'"'"':time.time()})
  count_services+=1
  with (arm/'"'"'serve.log'"'"').open('"'"'xb'"'"') as log:
   process=subprocess.Popen(service['"'"'argv'"'"'],cwd=arm,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  put(arm/'"'"'owner.json'"'"',{'"'"'pid_identity'"'"':d07.process_identity(process.pid),'"'"'argv'"'"':service['"'"'argv'"'"'],'"'"'service'"'"':name,'"'"'batch'"'"':batch,'"'"'GPU_owner'"'"':owner})
  append(RUN/'"'"'progress.jsonl'"'"',{'"'"'event'"'"':'"'"'loading'"'"','"'"'service'"'"':name,'"'"'pid'"'"':process.pid,'"'"'services'"'"':count_services,'"'"'calls'"'"':count_calls,'"'"'at'"'"':time.time()})
  print(json.dumps({'"'"'event'"'"':'"'"'loading'"'"','"'"'service'"'"':name,'"'"'pid'"'"':process.pid,'"'"'services'"'"':count_services,'"'"'calls'"'"':count_calls}),flush=True)
  base='"'"'http://127.0.0.1:'"'"'+str(service['"'"'port_pair'"'"']['"'"'api'"'"']);deadline=time.monotonic()+1800
  try:
   while True:
    if process.poll() is not None:raise RuntimeError('"'"'service exited before readiness: '"'"'+str(process.returncode))
    if time.monotonic()>deadline:raise TimeoutError('"'"'health-only readiness exceeded 1800s'"'"')
    try:
     with opener.open(base+'"'"'/health'"'"',timeout=10) as response:health=json.loads(response.read())
     if health.get('"'"'status'"'"')=='"'"'ok'"'"' and health.get('"'"'maintenance'"'"')=='"'"'serving'"'"':break
    except (OSError,ValueError):pass
    time.sleep(5)
   put(arm/'"'"'ready.json'"'"',{'"'"'health'"'"':health,'"'"'at'"'"':time.time(),'"'"'generation_readiness_calls'"'"':0})
   prefix=int(re.search(r'"'"'_p(\d+)'"'"',name).group(1));requests=service['"'"'requests'"'"'] if service['"'"'kind'"'"']=='"'"'hot'"'"' else [service['"'"'request'"'"']]
   for item in requests:
    tail=item.get('"'"'tail'"'"',int(re.search(r'"'"'_t(\d+)'"'"',name).group(1)) if service['"'"'kind'"'"']=='"'"'cold'"'"' else None)
    case=cases[(prefix,tail if tail is not None else 1)]
    ids=case['"'"'donor_ids'"'"'] if item['"'"'role'"'"']=='"'"'seed'"'"' else case['"'"'input_ids'"'"']
    assert hashlib.sha256(struct.pack('"'"'<%di'"'"'%len(ids),*ids)).hexdigest()==item['"'"'input_ids_sha256'"'"']
    label='"'"'seed'"'"' if item['"'"'role'"'"']=='"'"'seed'"'"' else '"'"'query_t'"'"'+str(tail)
    assert count_calls<14;count_calls+=1
    append(RUN/'"'"'budget.jsonl'"'"',{'"'"'event'"'"':'"'"'generation_call'"'"','"'"'service'"'"':name,'"'"'label'"'"':label,'"'"'index'"'"':count_calls,'"'"'input_sha256'"'"':item['"'"'input_ids_sha256'"'"'],'"'"'at'"'"':time.time()})
    offset=(arm/'"'"'serve.log'"'"').stat().st_size
    raw=t17.exact_id_request(base,ids,item['"'"'max_tokens'"'"'],output_path=arm/(label+'"'"'.json'"'"'),observations_path=arm/'"'"'observations.jsonl'"'"')
    with (arm/'"'"'serve.log'"'"').open('"'"'rb'"'"') as h:h.seek(offset);window=h.read()
    (arm/(label+'"'"'.serve-window.txt'"'"')).write_bytes(window)
    rows=[{'"'"'new_sequences'"'"':int(a),'"'"'new_tokens'"'"':int(b),'"'"'cached_tokens'"'"':int(c)} for a,b,c in re.findall(r'"'"'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)'"'"',window.decode(errors='"'"'strict'"'"'))]
    expected=prefix if service['"'"'kind'"'"']=='"'"'hot'"'"' and item['"'"'role'"'"']!='"'"'seed'"'"' else 0
    valid_geometry=bool(rows) and raw['"'"'response'"'"']['"'"'usage'"'"']['"'"'cached_tokens'"'"']==expected and all(r['"'"'cached_tokens'"'"']==expected for r in rows)
    valid_geometry=valid_geometry and sum(r['"'"'new_tokens'"'"'] for r in rows)==(tail if expected else len(ids)) and sum(r['"'"'new_sequences'"'"'] for r in rows)==1
    if not valid_geometry and service['"'"'kind'"'"']=='"'"'hot'"'"' and item['"'"'role'"'"']!='"'"'seed'"'"':
     evidence={'"'"'classification'"'"':'"'"'probe_invalid'"'"','"'"'raw'"'"':raw,'"'"'backend_rows'"'"':rows,'"'"'expected_cached'"'"':prefix,'"'"'expected_new'"'"':tail}
     put(arm/(label+'"'"'.evidence.json'"'"'),evidence);hot[(prefix,tail)]=evidence
    else:
     if not valid_geometry:raise RuntimeError('"'"'cold/seed cache geometry missing or invalid'"'"')
     evidence=art.request_evidence(arm,label,expected,item['"'"'max_tokens'"'"'])
     assert len(evidence['"'"'sampled_token_ids'"'"'])==item['"'"'max_tokens'"'"'] and evidence['"'"'response'"'"']['"'"'usage'"'"']['"'"'completion_tokens'"'"']==item['"'"'max_tokens'"'"']
     if service['"'"'kind'"'"']=='"'"'cold'"'"':
      observed=[r for r in evidence['"'"'observations'"'"'] if r['"'"'kind'"'"']=='"'"'layer-children'"'"']
      assert len(observed)==1 and observed[0]['"'"'outer_cached_tokens'"'"']==0
      children=observed[0]['"'"'children'"'"'];starts=[0,4096,8192];ends=[4096,8192,prefix+1]
      assert [(r['"'"'cached_tokens'"'"'],r['"'"'device_tokens'"'"']) for r in children]==list(zip(starts,ends))
      assert children[0]['"'"'has_initial_state'"'"'] is False and all(r['"'"'has_initial_state'"'"'] is True for r in children[1:])
      assert len(evidence['"'"'forwards'"'"'])==1 and evidence['"'"'forwards'"'"'][0]['"'"'device_length'"'"']==prefix+tail
      assert sha(service['"'"'schedule'"'"']['"'"'path'"'"'])==service['"'"'schedule'"'"']['"'"'sha256'"'"']
      evidence['"'"'cold_schedule_geometry'"'"']={'"'"'donor_children'"'"':observed,'"'"'outer_prefill'"'"':evidence['"'"'forwards'"'"'],'"'"'schedule'"'"':service['"'"'schedule'"'"'],'"'"'ordinary_tail_and_rewind_proof'"'"':'"'"'frozen one-shot schedule plus source-bound D20 guards and successful single request'"'"'}
     evidence.update(classification='"'"'valid'"'"',backend_rows=rows,service=name,role=item['"'"'role'"'"'],prefix=prefix,tail=tail)
     put(arm/(label+'"'"'.evidence.json'"'"'),evidence)
     if service['"'"'kind'"'"']=='"'"'hot'"'"' and item['"'"'role'"'"']!='"'"'seed'"'"':hot[(prefix,tail)]=evidence
     if service['"'"'kind'"'"']=='"'"'cold'"'"':cold[(prefix,tail,name.split('"'"'_'"'"')[1])]=evidence
    results[name+'"'"'/'"'"'+label]={'"'"'classification'"'"':evidence['"'"'classification'"'"'],'"'"'input_sha256'"'"':item['"'"'input_ids_sha256'"'"'],'"'"'response_sha256'"'"':raw['"'"'response_sha256'"'"'],'"'"'backend_rows'"'"':rows}
    append(RUN/'"'"'progress.jsonl'"'"',{'"'"'event'"'"':'"'"'request_complete'"'"','"'"'service'"'"':name,'"'"'label'"'"':label,'"'"'classification'"'"':evidence['"'"'classification'"'"'],'"'"'services'"'"':count_services,'"'"'calls'"'"':count_calls,'"'"'at'"'"':time.time()})
    print(json.dumps({'"'"'event'"'"':'"'"'request_complete'"'"','"'"'service'"'"':name,'"'"'label'"'"':label,'"'"'classification'"'"':evidence['"'"'classification'"'"'],'"'"'services'"'"':count_services,'"'"'calls'"'"':count_calls}),flush=True)
    if service['"'"'kind'"'"']=='"'"'cold'"'"' and name.split('"'"'_'"'"')[1]=='"'"'B'"'"':
     a=cold[(prefix,tail,'"'"'A'"'"')];b=cold[(prefix,tail,'"'"'B'"'"')]
     same_ab=a['"'"'sampled_token_ids'"'"']==b['"'"'sampled_token_ids'"'"'] and a['"'"'raw_text'"'"']==b['"'"'raw_text'"'"']
     row={'"'"'prefix'"'"':prefix,'"'"'tail'"'"':tail,'"'"'cold_A_equals_B'"'"':same_ab}
     if not same_ab:
      row['"'"'classification'"'"']='"'"'failed_harness'"'"';cells.append(row);verdict='"'"'failed_harness'"'"';raise RuntimeError('"'"'cold A/B unstable'"'"')
     h=hot[(prefix,tail)]
     if h['"'"'classification'"'"']=='"'"'probe_invalid'"'"':row['"'"'classification'"'"']='"'"'probe_invalid'"'"';cells.append(row);continue
     same_hot=h['"'"'sampled_token_ids'"'"']==a['"'"'sampled_token_ids'"'"'] and h['"'"'raw_text'"'"']==a['"'"'raw_text'"'"']
     row.update(hot_equals_cold=same_hot,classification='"'"'PASS'"'"' if same_hot else '"'"'not_met'"'"')
     if not same_hot:
      row['"'"'first_differing_token'"'"']=next((i for i,(x,y) in enumerate(zip(h['"'"'sampled_token_ids'"'"'],a['"'"'sampled_token_ids'"'"'])) if x!=y),None)
      row['"'"'hot_token'"'"']=h['"'"'sampled_token_ids'"'"'][row['"'"'first_differing_token'"'"']] if row['"'"'first_differing_token'"'"'] is not None else None
      row['"'"'cold_token'"'"']=a['"'"'sampled_token_ids'"'"'][row['"'"'first_differing_token'"'"']] if row['"'"'first_differing_token'"'"'] is not None else None
      row['"'"'first_differing_character'"'"']=next((i for i,(x,y) in enumerate(zip(h['"'"'raw_text'"'"'],a['"'"'raw_text'"'"'])) if x!=y),None)
     cells.append(row);put(RUN/('"'"'cell_p'"'"'+str(prefix)+'"'"'_t'"'"'+str(tail)+'"'"'.json'"'"'),row)
     if not same_hot:verdict='"'"'not_met'"'"';raise RuntimeError('"'"'stable cold A/B differs from hot; stop at first differing token'"'"')
  finally:
   if process is not None:
    owned.stop_owned_process(process,120,30)
    put(arm/'"'"'cleanup.json'"'"',{'"'"'group_alive'"'"':owned.owned_group_alive(process.pid),'"'"'pid'"'"':process.pid,'"'"'at'"'"':time.time()})
    assert not owned.owned_group_alive(process.pid);process=None
  d07.require_gpu_idle();bindable([service['"'"'port_pair'"'"']['"'"'api'"'"'],service['"'"'port_pair'"'"']['"'"'tcpstore'"'"']])
 verdict='"'"'PASS'"'"' if count_services==10 and count_calls==14 and len(cells)==4 and all(r['"'"'classification'"'"']=='"'"'PASS'"'"' for r in cells) else '"'"'probe_invalid'"'"'
except BaseException as exc:
 error=repr(exc)
 if verdict=='"'"'pending'"'"':verdict='"'"'failed_harness'"'"'
 print(json.dumps({'"'"'event'"'"':'"'"'terminal_exception'"'"','"'"'verdict'"'"':verdict,'"'"'error'"'"':error}),flush=True)
finally:
 try:
  if process is not None:
   owned.stop_owned_process(process,120,30)
   if owned.owned_group_alive(process.pid):raise RuntimeError('"'"'owned group remains'"'"')
   process=None
  d07.require_gpu_idle()
  if owner is not None:d07.release_d07_gpu_lock(owner);owner=None
 except BaseException as exc:cleanup_errors.append(repr(exc))
 if RUN.exists():
  terminal={'"'"'schema'"'"':'"'"'ft_r067_actual_terminal/v1'"'"','"'"'rid'"'"':RID,'"'"'batch'"'"':batch,'"'"'verdict'"'"':verdict,'"'"'error'"'"':error,'"'"'actual_services'"'"':count_services,'"'"'actual_generation_calls'"'"':count_calls,'"'"'planned_services_max'"'"':10,'"'"'planned_generation_calls_max'"'"':14,'"'"'cells'"'"':cells,'"'"'requests'"'"':results,'"'"'cleanup_errors'"'"':cleanup_errors,'"'"'GPU_lock_released'"'"':owner is None,'"'"'at'"'"':time.time(),'"'"'planned_complete'"'"':count_services==10 and count_calls==14,'"'"'failed_harness_retry_policy'"'"':{'"'"'controller'"'"':'"'"'root'"'"','"'"'maximum_retries'"'"':2,'"'"'new_round_required'"'"':True},'"'"'independent_terminal_review_required'"'"':True,'"'"'product_acceptance'"'"':False}
  put(RUN/'"'"'terminal.json'"'"',terminal);print(json.dumps(terminal),flush=True)
 if cleanup_errors:raise RuntimeError('"'"'owned cleanup failed: '"'"'+repr(cleanup_errors))
' --run
