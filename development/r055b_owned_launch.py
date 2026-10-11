"""R055b controller. Its --dry-run executes the same R055b preparation source."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RID = "E2-R055b-gate-D06"
ADAPTER = "r055b_gate_d06_prepare.py"
REVIEW_SCHEMA = "ft_r055b_startup_review/v1"
SOURCE_DEPENDENCIES = (Path(__file__).name, ADAPTER, "r055a_dryrun_base_v1.py", "r055_owned_launch.py",
                       "r055_gate_d06_prepare.py", "d07_g3g4_prepare.py",
                       "t16_private_port_base_runner.py", "t16_full_tail_base_runner.py")


def source_hashes():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in SOURCE_DEPENDENCIES}


def require_retained_cold(legacy):
    """Bind R055a's accepted partial evidence through sealed metadata only."""
    root = Path('/data2/_shared/runs/ft_rounds/E2-R055a-gate-D06')
    pin = legacy.ROOT / 'runs/plan_batches/closed_round_pins/E2-R055a-gate-D06_v2.json'
    checks = {
        pin: 'e785009fe2adecf1116c94b8416bb99093f6d31f14b98bb8df8a3ff3475bd127',
        root / 'round.json': '0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3',
        root / 'MANIFEST.sha256': 'b38e9da3be0781958916fcc5714c8d750645cc10e1ebf4381fe72f5768064ab0',
    }
    for path, wanted in checks.items():
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise RuntimeError('retained R055a metadata is absent or writable')
        if hashlib.sha256(path.read_bytes()).hexdigest() != wanted:
            raise RuntimeError('retained R055a metadata SHA differs')
    binding = json.loads(pin.read_text())
    record = json.loads((root / 'round.json').read_text())
    partial = record.get('supplemental_independent_raw_review', {})
    if (binding.get('verdict') != 'failed_harness' or record.get('verdict') != 'failed_harness'
            or partial.get('partial_cold_verdict') != 'PASS'
            or partial.get('sha256') != '10161a2fe801414c3aa611487ead1d8a64a2e7baf1853d90ad4bca7fa7a08aa4'):
        raise RuntimeError('retained R055a cold verdict binding differs')
    writer = legacy.ROOT / 'scripts/round_json_append.py'
    if hashlib.sha256(writer.read_bytes()).hexdigest() != '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff':
        raise RuntimeError('D04 history checker changed')
    subprocess.run([str(legacy.ROOT / 'venv/bin/python'), str(writer), str(root), 'check'], check=True,
                   stdout=subprocess.DEVNULL)
    return {'rid': root.name, 'pin_path': str(pin), 'pin_sha256': checks[pin],
            'round_sha256': checks[root / 'round.json'], 'manifest_sha256': checks[root / 'MANIFEST.sha256'],
            'partial_cold_verdict': 'PASS', 'cold_arms_replayed': False,
            'independent_raw_review_sha256': partial['sha256']}


def _dry_base():
    path = HERE / "r055a_dryrun_base_v1.py"
    spec = importlib.util.spec_from_file_location("R055b_owned_dry_base", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module


def adapter_module():
    path = HERE / ADAPTER
    spec = importlib.util.spec_from_file_location("R055b_prepare", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _legacy():
    path = HERE / "r055_owned_launch.py"
    spec = importlib.util.spec_from_file_location("R055b_legacy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    module.RID = RID
    module.ADAPTER = ADAPTER
    module.SOURCE_DEPENDENCIES = SOURCE_DEPENDENCIES
    module.source_hashes = source_hashes
    module.review_path = lambda: module.ROOT / "runs/dev_R055/reviews" / f"{RID}_startup_review_v3.json"
    def require_review():
        receipt = adapter_module().ROUNDS / f".dryrun_R055b_{RID}" / "dry_run_receipt.json"
        review = module.review_path()
        if review.is_symlink() or not review.is_file() or review.stat().st_mode & 0o222:
            raise RuntimeError("R055b startup review is absent or writable")
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode & 0o222:
            raise RuntimeError("R055b dry-run receipt is absent or writable")
        dry = json.loads(receipt.read_text(encoding="utf-8"))
        if dry.get("schema") != "ft_R055b_dry_run/v2" or any(dry.get(key) is not False for key in
                ("service_started", "requests_sent", "gpu_lock_taken", "batch_allocated", "formal_rid_directory_created")):
            raise RuntimeError("R055b dry-run receipt has side effects or wrong schema")
        if dry.get("source_sha256") != source_hashes():
            raise RuntimeError("R055b dry-run source inventory differs")
        expected_dry = {"rid": RID, "cwd": str(module.ROOT), "owner_path": str(Path(__file__).resolve()),
                        "adapter_path": str((HERE / ADAPTER).resolve()), "formal_directory": str(adapter_module().ROUNDS / RID),
                        "passed": True}
        if any(dry.get(key) != value for key, value in expected_dry.items()):
            raise RuntimeError("R055b dry-run identity binding differs")
        if dry.get("user", {}).get("uid") != os.getuid() or dry.get("worktrees", {}).get("parent", {}).get("head") != module.PARENT_COMMIT or dry.get("worktrees", {}).get("candidate", {}).get("head") != module.CANDIDATE_COMMIT:
            raise RuntimeError("R055b dry-run user or worktree binding differs")
        if os.getcwd() != str(module.ROOT) or dry.get("user", {}).get("user") != os.environ.get("USER"):
            raise RuntimeError("R055b launch user/cwd differs from the actual dry-run")
        document = json.loads(review.read_text(encoding="utf-8"))
        expected = {"schema": REVIEW_SCHEMA, "rid": RID, "card": module.CARD,
                    "candidate_commit": module.CANDIDATE_COMMIT, "parent_commit": module.PARENT_COMMIT,
                    "verdict": "PASS", "approved": True, "source_sha256": source_hashes(),
                    "dry_run_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                    "dry_run_source_sha256": source_hashes()}
        if any(document.get(key) != value for key, value in expected.items()):
            raise RuntimeError("R055b startup review binding differs")
        return review
    module.require_leaf_review = require_review
    def admission(g):
        if g.LOCK.exists() or g.LOCK.is_symlink():
            raise RuntimeError("foreign GPU lock exists; R055b remains queued")
        g.require_r041_kept(module.ROOT)
        g.require_closed_round("E2-R050-gate-D15", "kept")
        require_retained_cold(module)
        module.require_candidate(); module.require_native_reuse(); require_review()
    module.admission = admission
    def child_argv(batch, receipt):
        return [str(module.ROOT / "venv/bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child",
                "--batch", str(batch), "--launch-receipt", str(receipt)]
    module.argv = child_argv
    original_d07 = module.d07
    def candidate_d07():
        gate = original_d07()
        gate.CANDIDATE = module.CANDIDATE_COMMIT
        gate.WORKTREE = module.ROOT / 'wt/e2base1-p1'
        return gate
    module.d07 = candidate_d07
    module.pause_smoke = lambda gate, batch, run=None: pause_smoke(module, gate, batch, run)
    original_child = module.child
    def completed_child(batch, receipt):
        value = original_child(batch, receipt)
        root = module.d07().ROUNDS / RID
        gate = {'rid': RID, 'batch': batch, 'candidate_commit': module.CANDIDATE_COMMIT,
                'parent_commit': module.PARENT_COMMIT, 'arms': ['PAUSE_ON'],
                'retained_cold': require_retained_cold(module), 'cold_arms_replayed': False,
                'pause_gate_sha256': hashlib.sha256((root / 'pause_gate.json').read_bytes()).hexdigest(),
                'proposed_verdict': 'pending_review'}
        module.adapter_module().write_new(root / f'gate_batch{batch}.json', gate)
        status = root / f'status_batch{batch}.json'
        document = json.loads(status.read_text())
        document.update(state='complete_measurements_pending_review', pause_chain_complete=True)
        temporary = status.with_suffix('.tmp')
        temporary.write_text(json.dumps(document, indent=2) + '\n')
        os.replace(temporary, status)
        return value
    module.child = completed_child
    return module


def _prepare_pause_command(gate, run, worktree, port):
    """The formal and file-only smoke share the actual command writer."""
    env = gate.clean_environment(worktree, trace_dir=None)
    env.pop('FT_DEV_ROUTE_TRACE', None)
    keys = {'CUDA_VISIBLE_DEVICES', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_ROUTE_TRACE', 'PYTHONPATH', 'VIRTUAL_ENV'}
    command = 'env ' + ' '.join(f'{key}={shlex.quote(env[key])}' for key in sorted(env) if key in keys)
    (run / 'SERVE_CMD.txt').write_text(command + ' ' + shlex.join(gate.serve_argv(port)) + '\n', encoding='utf-8')

PAUSE_OBSERVER = r'''import json,os,time
from pathlib import Path
def _birth():
 f=(Path("/proc")/str(os.getpid())/"stat").read_text().rpartition(") ")[2].split()
 return {"pid":os.getpid(),"start_ticks":int(f[19]),"execution_id":f"{os.getpid()}:{int(f[19])}","pgid":int(f[2]),"session":int(f[3])}
def _emit(kind, **fields):
 worker=_birth();service=json.loads(os.environ.get("R055_SERVICE_BIRTH",json.dumps(worker)))
 row={"kind":kind,"time_ns":time.time_ns(),"pid":os.getpid(),"service_pid":service["pid"],"service_birth":service,"worker_birth":worker,**fields}
 with Path(os.environ["R055_PAUSE_OBSERVATIONS"]).open("a",encoding="utf-8") as out:out.write(json.dumps(row,sort_keys=True)+"\n")
def _memory(event, uid=None, request_id=None, error=None):
 worker=_birth();service=json.loads(os.environ.get("R055_SERVICE_BIRTH",json.dumps(worker)))
 row={"schema":"ft_r055b_model_process_cuda/v1","event":event,"uid":str(uid) if uid is not None else None,"request_id":str(request_id) if request_id is not None else None,"time_ns":time.time_ns(),"device":0,"pid":worker["pid"],"start_ticks":worker["start_ticks"],"service_pid":service["pid"],"service_birth":service,"worker_birth":worker}
 if error is not None:row["error"]=repr(error)
 try:
  import torch
  free,total=torch.cuda.mem_get_info(0);row.update(free_bytes=int(free),total_bytes=int(total),driver_used_bytes=int(total-free),current_allocated_bytes=int(torch.cuda.memory_allocated(0)),current_reserved_bytes=int(torch.cuda.memory_reserved(0)),cumulative_allocated_peak_bytes=int(torch.cuda.max_memory_allocated(0)),cumulative_reserved_peak_bytes=int(torch.cuda.max_memory_reserved(0)))
 except BaseException as exc:row.update(event="error",requested_event=event,error=repr(error or exc))
 with Path(os.environ["R055B_MODEL_MEMORY"]).open("a",encoding="utf-8") as out:out.write(json.dumps(row,sort_keys=True)+"\n")
def install():
 from freetoken.scheduler.scheduler import Scheduler
 from freetoken.scheduler.io import SchedulerIOMixin
 from freetoken.engine.engine import Engine
 process,reply,engine_init=Scheduler._process_one_msg,SchedulerIOMixin._reply_tokenizer_rank0,Engine.__init__
 def seen(self,msg):
  name=type(msg).__name__
  if name in ("DevPauseBackendMsg","DevPauseCancelBackendMsg"):_emit("backend",message=name,request_id=str(msg.request_id));_memory("cancel_before" if name=="DevPauseCancelBackendMsg" else "pause_before",request_id=str(msg.request_id))
  elif name=="InputTokenizedMsg":_emit("input",uid=str(msg.uid));_memory("request_before",msg.uid)
  result=process(self,msg)
  if name=="DevPauseCancelBackendMsg":_memory("cancel_after",request_id=str(msg.request_id))
  return result
 def delivered(self,messages):
  for msg in messages:
   if type(msg).__name__=="DevPauseResultMsg":_emit("pause_result",request_id=str(msg.request_id),status=str(msg.status));_memory("pause_after",request_id=str(msg.request_id))
   elif type(msg).__name__=="DetokenizeMsg" and bool(msg.finished):_emit("delivery",uid=str(msg.uid),token=int(msg.next_token));_memory("request_after",msg.uid)
  return reply(self,messages)
 def loaded(self,*args,**kwargs):
  try:result=engine_init(self,*args,**kwargs)
  except BaseException as exc:_memory("model_load_error",error=exc);raise
  _memory("model_loaded");return result
 Scheduler._process_one_msg=seen;SchedulerIOMixin._reply_tokenizer_rank0=delivered;Engine.__init__=loaded
 if hasattr(Scheduler,"_forward"):
  forward=Scheduler._forward
  def observed_forward(self,value):
   try:return forward(self,value)
   except BaseException as exc:
    for req in getattr(getattr(value,"batch",None),"reqs",[]):_memory("request_error",getattr(req,"uid",None),error=exc)
    raise
  Scheduler._forward=observed_forward
'''
PAUSE_STARTUP = '''import json,os,sys
from pathlib import Path
if "R055_SERVICE_BIRTH" not in os.environ:
 f=(Path("/proc")/str(os.getpid())/"stat").read_text().rpartition(") ")[2].split()
 os.environ["R055_SERVICE_BIRTH"]=json.dumps({"pid":os.getpid(),"start_ticks":int(f[19]),"execution_id":f"{os.getpid()}:{int(f[19])}","pgid":int(f[2]),"session":int(f[3])})
import r055b_pause_observer
r055b_pause_observer.install()
from freetoken.cli import main
sys.argv=["ft",*sys.argv[1:]]
if __name__ == "__main__":main()
'''
def _freeze_pause_observer(run):
 observer,startup=run/'r055b_pause_observer.py',run/'r055b_pause_startup.py'
 for path,content in ((observer,PAUSE_OBSERVER),(startup,PAUSE_STARTUP)):
  with path.open('x',encoding='utf-8',newline='\n') as out:out.write(content)
  path.chmod(0o444)
 return startup


def summarize_memory(run, normal_id, cancel_id):
    path = run / 'model_process_cuda.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    owned = json.loads((run / 'owned_process.json').read_text())
    birth = {key: owned['birth'][key] for key in ('pid', 'start_ticks', 'execution_id', 'pgid', 'session')}
    loaded = [row for row in rows if row.get('event') == 'model_loaded']
    if len(loaded) != 1:
        raise RuntimeError('model-loaded CUDA sample missing or ambiguous')
    worker = loaded[0]['worker_birth']
    totals = set()
    for row in rows:
        if (row.get('schema') != 'ft_r055b_model_process_cuda/v1' or row.get('device') != 0
                or row.get('service_birth') != birth or row.get('worker_birth') != worker
                or row.get('error') is not None or 'error' in str(row.get('event'))):
            raise RuntimeError('model-process CUDA identity or error sample differs')
        for key in ('free_bytes', 'total_bytes', 'driver_used_bytes', 'current_allocated_bytes',
                    'current_reserved_bytes', 'cumulative_allocated_peak_bytes', 'cumulative_reserved_peak_bytes'):
            if type(row.get(key)) is not int or row[key] < 0:
                raise RuntimeError('model-process CUDA sample is incomplete')
        if row['free_bytes'] > row['total_bytes'] or row['driver_used_bytes'] != row['total_bytes'] - row['free_bytes']:
            raise RuntimeError('model-process CUDA byte accounting differs')
        totals.add(row['total_bytes'])
    if len(totals) != 1:
        raise RuntimeError('CUDA device total changed during the pause chain')
    before = [row for row in rows if row['event'] == 'request_before']
    after = [row for row in rows if row['event'] == 'request_after']
    if len(before) != 2 or len(after) != 2 or {row['uid'] for row in before} != {row['uid'] for row in after}:
        raise RuntimeError('CUDA request-before/after boundaries are incomplete')
    business = []
    for prefix, sample in zip(('before', 'after_cancel'), before):
        case = json.loads((run / (prefix + '.json')).read_text())
        record = case.get('record', {})
        wanted_id = RID + ('-pause-before' if prefix == 'before' else '-pause-after-cancel')
        if (record.get('cold_id') != wanted_id or record.get('built_tokens') != 32052
                or record.get('prompt_tokens') != 32064 or record.get('completion_tokens') != 128
                or record.get('cached_tokens') != 0 or record.get('finish_reason') != 'length'
                or case.get('events') != 128 or not case.get('text')):
            raise RuntimeError('pause-chain cold request did not complete the original 32K/128 protocol')
        end = next(row for row in after if row['uid'] == sample['uid'])
        if sample['time_ns'] >= end['time_ns']:
            raise RuntimeError('CUDA business-request timestamps are reversed')
        business.append({'uid': int(sample['uid']), 'request_id': wanted_id,
                         'before_time_ns': sample['time_ns'], 'after_time_ns': end['time_ns'],
                         'case_path': str(run / (prefix + '.json')),
                         'case_sha256': hashlib.sha256((run / (prefix + '.json')).read_bytes()).hexdigest()})
    for event, request_id in (('pause_before', normal_id), ('pause_after', normal_id),
                              ('cancel_before', cancel_id), ('cancel_after', cancel_id)):
        if len([row for row in rows if row['event'] == event and row.get('request_id') == request_id]) != 1:
            raise RuntimeError('CUDA control-request boundaries are incomplete: ' + event)
    observer = run / 'r055b_pause_observer.py'
    return {'schema': 'ft_r055b_cuda_memory_summary/v1', 'complete': True,
            'service_birth': birth, 'worker_birth': worker, 'device': 0,
            'observer_source': str(observer), 'observer_source_sha256': hashlib.sha256(observer.read_bytes()).hexdigest(),
            'memory_jsonl': str(path), 'memory_jsonl_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'events': rows, 'business_requests': business,
            'min_free_bytes': min(row['free_bytes'] for row in rows),
            'total_bytes': next(iter(totals)),
            'maximum_sampled_driver_used_bytes': max(row['driver_used_bytes'] for row in rows),
            'cumulative_allocated_peak_bytes': max(row['cumulative_allocated_peak_bytes'] for row in rows),
            'cumulative_reserved_peak_bytes': max(row['cumulative_reserved_peak_bytes'] for row in rows),
            'control_request_ids': {'pause': normal_id, 'cancel': cancel_id},
            'peak_scope': 'Torch cumulative allocator peaks; driver peak is the maximum sampled total-free.'}


def pause_smoke(legacy, gate, batch, run=None, *, file_dry_run=False, worktree_override=None):
    """A real, dynamically-port-bound service check; no CPU test calls this function."""
    run = legacy.ROOT / 'runs/dev_R055' / f'{legacy.RID}_batch{batch}_pause_smoke' if run is None else Path(run)
    run.mkdir(parents=True, exist_ok=False)
    port = gate.dynamic_fixture_port()
    proc = None
    prior_argv = None
    prior_environment = gate.clean_environment
    previous_observer = os.environ.get('R055_PAUSE_OBSERVATIONS')
    previous_memory = os.environ.get('R055B_MODEL_MEMORY')
    try:
        def pause_environment(worktree, *, trace_dir=None):
            env = prior_environment(worktree, trace_dir=None)
            env.pop('FT_DEV_ROUTE_TRACE', None)
            env['FT_DEV_PAUSE_ENDPOINT'] = '1'
            env['R055_PAUSE_OBSERVATIONS'] = str(run / 'pause_observations.jsonl')
            env['R055B_MODEL_MEMORY'] = str(run / 'model_process_cuda.jsonl')
            env.pop('R055_SERVICE_BIRTH', None)
            return env
        gate.clean_environment = pause_environment
        if callable(getattr(gate, 'serve_argv', None)):
            startup = _freeze_pause_observer(run)
            prior_argv = gate.serve_argv
            gate.serve_argv = lambda _port: [str(gate.VENV / 'bin/python'), str(startup)] + prior_argv(_port)[1:]
            os.environ['R055_PAUSE_OBSERVATIONS'] = str(run / 'pause_observations.jsonl')
            os.environ['R055B_MODEL_MEMORY'] = str(run / 'model_process_cuda.jsonl')
        worktree = Path(worktree_override) if file_dry_run and worktree_override is not None else legacy.require_candidate()
        if prior_argv is not None:
            env = gate.clean_environment(worktree, trace_dir=None);env.pop('FT_DEV_ROUTE_TRACE',None)
            selected = {key: env.get(key) for key in ('CUDA_VISIBLE_DEVICES', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_ROUTE_TRACE', 'PYTHONPATH', 'VIRTUAL_ENV', 'PATH')}
            (run / 'ENV.txt').write_text(json.dumps({'worktree': str(worktree), 'candidate_commit': legacy.CANDIDATE_COMMIT, 'environment': selected}, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        _prepare_pause_command(gate, run, worktree, port)
        if file_dry_run:
            files = {}
            for name in ('serve.log', 'owned_process.json', 'health.json', 'serve_args.txt',
                         'before.json', 'pause_completed.json', 'pause_cancel.json', 'model_process_cuda.jsonl',
                         'after_cancel.json', 'pause_observations.jsonl', 'cuda_memory_summary.json'):
                path = run / name
                path.parent.mkdir(parents=True, exist_ok=True)
                files[name] = _dry_base().write_probe(path, 'CPU FILE PROBE ONLY; no measurement\n')
            files.update({name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                          for name in ('ENV.txt', 'SERVE_CMD.txt', 'r055b_pause_startup.py', 'r055b_pause_observer.py')})
            return {'directory': str(run), 'port': port, 'files': files,
                    'service_started': False, 'requests_sent': False}
        proc = gate.start_server(run, worktree, port, None)
        if prior_argv is not None:
            text = (run / 'serve.log').read_text(encoding='utf-8')
            position = text.find('Parsed arguments')
            if position < 0:
                raise RuntimeError('R055 pause service did not publish parsed arguments')
            (run / 'serve_args.txt').write_text('\n'.join(text[position:].splitlines()[:2]) + '\n', encoding='utf-8')
        gate.invoke_cold_eq(legacy.require_candidate(), port, f'{legacy.RID}-pause-before', run / 'before.json')
        normal = legacy.pause_request(port, 1.0, 5.0)
        (run / 'pause_completed.json').write_text(json.dumps(normal, indent=2) + '\n')
        cancel = legacy.pause_request(port, 30.0, 0.05)
        (run / 'pause_cancel.json').write_text(json.dumps(cancel, indent=2) + '\n')
        gate.invoke_cold_eq(legacy.require_candidate(), port, f'{legacy.RID}-pause-after-cancel', run / 'after_cancel.json')
        if not isinstance(normal, dict) or normal.get('status') != 'accepted' or (not isinstance(normal.get('request_id'), str)) or (not normal['request_id']):
            raise RuntimeError('R055 pause endpoint lacks an accepted request identity')
        if not isinstance(cancel, dict) or cancel.get('status') != 'timeout' or (not isinstance(cancel.get('request_id'), str)) or (not cancel['request_id']) or (cancel.get('request_id') == normal.get('request_id')) or ('cancel enqueue' in str(cancel.get('error', ''))):
            raise RuntimeError('R055 pause cancel lacks a verified API cancellation receipt')
        evidence = legacy._trace_pause_backend(run, normal['request_id'], cancel['request_id']) if prior_argv is not None else {'test_double': True}
        summary = summarize_memory(run, normal['request_id'], cancel['request_id'])
        (run / 'cuda_memory_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        return {'run': str(run), 'port': port, 'owned_process': str(run / 'owned_process.json'), 'before': str(run / 'before.json'), 'pause': str(run / 'pause_completed.json'), 'cancel': str(run / 'pause_cancel.json'), 'after_cancel': str(run / 'after_cancel.json'), 'backend_evidence': evidence, 'cuda_memory_summary': summary}
    finally:
        if prior_argv is not None:
            gate.serve_argv = prior_argv
        gate.clean_environment = prior_environment
        if previous_observer is None:
            os.environ.pop('R055_PAUSE_OBSERVATIONS', None)
        else:
            os.environ['R055_PAUSE_OBSERVATIONS'] = previous_observer
        if previous_memory is None:
            os.environ.pop('R055B_MODEL_MEMORY', None)
        else:
            os.environ['R055B_MODEL_MEMORY'] = previous_memory
        if proc is not None:
            try:
                gate.load_owned_lifecycle().stop_owned_process(proc)
            except BaseException as cleanup_error:
                cleanup_error.owned_process = proc
                cleanup_error.owned_cleanup_failed = True
                raise

def pause_file_dry_run(run: Path, port: int, worktree: Path) -> dict:
    legacy = _legacy()
    gate = legacy.d07()
    # The same pause_smoke writes the observer/env/argv files before its Popen boundary.
    return pause_smoke(legacy, gate, 1, run, file_dry_run=True, worktree_override=worktree)


def main(argv_in=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--launch-receipt", type=Path)
    options = parser.parse_args(argv_in)
    if options.dry_run:
        if options.run or options.owned_child or options.batch is not None or options.launch_receipt is not None:
            parser.error("--dry-run does not accept launch arguments")
        result = adapter_module().dry_run()
        print(json.dumps(result, sort_keys=True))
        return 0
    if options.run:
        legacy = _legacy()
        args = ["--run"]
        if options.owned_child:
            if options.batch is None or options.launch_receipt is None:
                parser.error("child requires batch and receipt")
            args += ["--owned-child", "--batch", str(options.batch), "--launch-receipt", str(options.launch_receipt)]
        elif options.batch is not None or options.launch_receipt is not None:
            parser.error("controller does not accept child arguments")
        return legacy.main(args)
    if options.owned_child or options.batch is not None or options.launch_receipt is not None:
        parser.error("--run required for launch arguments")
    print(json.dumps({"schema": "ft_R055b_owned_launch/v1", "rid": RID, "requests_sent": False,
                      "gpu_lock_taken": False, "source_execution_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
