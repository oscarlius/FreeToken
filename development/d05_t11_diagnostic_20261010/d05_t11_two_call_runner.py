"""D05 T11 two-call boundary diagnostic.

`--filedry` exercises the same plan/materialization, controller-child receipt, state gate,
and cleanup flow with a CPU child. `--run` is deliberately closed until a root-sealed
admission names this fresh RID; it is never selected by this CPU package.
"""
from __future__ import annotations

import argparse, hashlib, importlib.util, json, os, signal, socket, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
WT = ROOT / 'wt/d05_hbug_candidate_20261010'
VENV = ROOT / 'venv'
RID = 'E2-R052b-D05-boundary-20261010'
CANDIDATE = 'bd57cfdccc2a935d46cb0a89b8b36be7a18706de'
RAW = Path('/data2/_shared/runs/ft_rounds/E2-R052a-night-20261009-v2')
TRACE = Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json')
PAGE_BOUNDARY = 13_504
MAX_CALLS = 2
STATE_ROLES = ('conv_states', 'recurrent_states', 'slot:ple_conv', 'slot:ple_ngram_ctx')


class FailedHarness(RuntimeError):
    pass


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _put(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise RuntimeError(f'refuse existing output: {path}')
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def retained_module():
    path = HERE / 'retained_r052_t11_replay.py'
    if sha(path) != '5f8deb405d15621a467e9f74ea2c5bc8e1048327efbc173ee1a751c6f18c5ec9':
        raise RuntimeError('retained T11 replay source hash differs')
    spec = importlib.util.spec_from_file_location('d05_retained_t11', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_identity() -> dict:
    head = subprocess.check_output(['git', '-C', str(WT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(WT), 'status', '--porcelain', '--untracked-files=no'], text=True)
    if head != CANDIDATE or dirty:
        raise RuntimeError('D05 candidate identity or tracked cleanliness differs')
    return {'worktree': str(WT), 'head': head, 'cache_sha256': sha(WT/'python/freetoken/scheduler/cache.py'),
            'linear_sha256': sha(WT/'python/freetoken/attention/linear.py')}


def target_binding() -> dict:
    retained = retained_module()
    if TRACE.is_symlink() or sha(TRACE) != retained.TRACE_SHA:
        raise RuntimeError('retained T11 trace differs')
    trace = json.loads(TRACE.read_text(encoding='utf-8'))
    client = retained.client_module(WT)
    bound = retained.target_binding(trace, client)
    row = trace['rounds'][bound['trace_index']]
    tools = trace.get('tools') or client.tool_specs()
    thinking = bool(trace.get('meta', {}).get('params', {}).get('thinking', True))
    payload = client.build_payload(row['messages'], retained.MODEL, tools, thinking, 200)
    payload_sha = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                            separators=(',', ':')).encode()).hexdigest()
    return {'trace_sha256': retained.TRACE_SHA, 'trace_index': bound['trace_index'],
            'messages_sha': bound['messages_sha'], 'target_payload_sha256': payload_sha,
            'target_max_tokens': 200, 'followup_max_tokens': 64,
            'generation_calls': MAX_CALLS, 'page_boundary': PAGE_BOUNDARY}


def plan() -> dict:
    return {'schema': 'ft_d05_t11_two_call_plan/v1', 'rid': RID, 'candidate_commit': CANDIDATE,
            'services': 1, 'generation_calls': MAX_CALLS, 'calls': [
                {'ordinal': 1, 'role': 'uid7_target', 'max_tokens': 200},
                {'ordinal': 2, 'role': 'uid8_followup', 'max_tokens': 64,
                 'only_after': 'donor_and_cold_P_state_sha256_equal'}],
            'boundary': PAGE_BOUNDARY, 'input_binding': target_binding(),
            'stop_rule': 'state gate mismatch or malformed dump => failed_harness before call 2/output comparison'}


def read_state_hash(dump: Path, *, kind: str, uid: int, length: int) -> str:
    """Consume the candidate's real LinearStatePool.dump_state index and all state roles."""
    index = dump / 'index.jsonl'
    if index.is_symlink() or not index.is_file():
        raise FailedHarness('failed_harness: state index missing')
    rows = [json.loads(line) for line in index.read_text(encoding='utf-8').splitlines() if line.strip()]
    matches = [row for row in rows if row.get('kind') == kind and str(row.get('uid')) == str(uid)
               and row.get('length') == length]
    if len(matches) != 1:
        raise FailedHarness('failed_harness: state boundary receipt absent or ambiguous')
    files = matches[0].get('files')
    if not isinstance(files, dict) or not set(STATE_ROLES).issubset(files):
        raise FailedHarness('failed_harness: incomplete full logical state roles')
    parts = {}
    for role in STATE_ROLES:
        name = files[role]
        if not isinstance(name, str) or Path(name).name != name:
            raise FailedHarness('failed_harness: unsafe state filename')
        file = dump / name
        if file.is_symlink() or not file.is_file():
            raise FailedHarness(f'failed_harness: missing {role}')
        parts[role] = sha(file)
    return hashlib.sha256(json.dumps({'length': length, 'roles': parts}, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def require_equal_p_state(dump: Path, *, donor_uid: int, cold_uid: int) -> str:
    donor = read_state_hash(dump, kind='donate', uid=donor_uid, length=PAGE_BOUNDARY)
    cold = read_state_hash(dump, kind='resume', uid=cold_uid, length=PAGE_BOUNDARY)
    if donor != cold:
        raise FailedHarness('failed_harness: donor/cold P-state hash differs; discard output')
    return donor


class Effects:
    """One real service factory. FileDryEffects overrides only external process/GPU callbacks."""
    def __init__(self, root: Path):
        self.root = root
        self.events: list[dict] = []

    def materialize(self, item: dict, port: int) -> dict:
        arm = self.root / 'services' / 'uid7_uid8'
        arm.mkdir(parents=True, exist_ok=False)
        runtime = arm / 'runtime'; runtime.mkdir()
        bridge = HERE / 'retained_r052_d0_shutdown_startup_v2.py'
        copied = runtime / bridge.name
        copied.write_bytes(bridge.read_bytes())
        if sha(copied) != sha(bridge):
            raise RuntimeError('startup bridge copy differs')
        argv = ['numactl', '--cpunodebind=0,1', '--interleave=all', str(VENV/'bin/python'), str(copied),
                'serve', '--model-path', '/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay',
                '--served-model-name', 'Qwen3.8-Flash-Next-NVFP4', '--host', '127.0.0.1', '--port', str(port),
                '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned',
                '--moe-strategy', 'offload', '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2',
                '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '98304', '--max-seq-len-override', '98304',
                '--max-prefill-length', '4096', '--enable-cache-report', '--enable-special-token-ckpt',
                '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3', '--mamba-host-slots', '32']
        binding = {'arm': str(arm), 'cwd': str(WT), 'argv': argv,
                   'argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest(),
                   'pythonpath': str(WT/'python'), 'state_dump': str(arm/'state_dump'),
                   'input_binding': item['input_binding'], 'calls': item['generation_calls']}
        _put(arm/'input_binding.json', binding)
        self.events.append({'event': 'materialize', 'argv_sha256': binding['argv_sha256']})
        return binding

    def spawn(self, binding: dict):
        env = os.environ | {'PYTHONPATH': binding['pythonpath'], 'FT_DEV_D0': '1',
                            'FT_D3_TRACE': '1', 'FT_DEV_STATE_DUMP': binding['state_dump'],
                            'CUDA_VISIBLE_DEVICES': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
        log = Path(binding['arm'])/'serve.log'
        handle = log.open('xb')
        try:
            proc = subprocess.Popen(binding['argv'], cwd=binding['cwd'], env=env, stdout=handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            handle.close()
        self.events.append({'event': 'spawn', 'pid': proc.pid})
        return proc

    def cleanup(self, proc, deadline: float) -> None:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try: proc.wait(timeout=max(0.1, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=5)
        if proc.poll() is None:
            raise FailedHarness('failed_harness: owned child remains alive')
        self.events.append({'event': 'cleanup', 'returncode': proc.returncode})


class FileDryEffects(Effects):
    def spawn(self, binding: dict):
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.events.append({'event': 'spawn', 'pid': proc.pid, 'filedry_fake_child': True})
        return proc


def _write_fake_dump(dump: Path, *, donor: bytes, cold: bytes) -> None:
    dump.mkdir(parents=True)
    rows = []
    for kind, uid, payload in (('donate', 7, donor), ('resume', 8, cold)):
        files = {}
        for role in STATE_ROLES:
            name = f'{kind}_{role.replace(":", "_")}.pt'; (dump/name).write_bytes(payload + role.encode()); files[role] = name
        rows.append({'kind': kind, 'uid': uid, 'length': PAGE_BOUNDARY, 'files': files})
    (dump/'index.jsonl').write_text('\n'.join(json.dumps(x, sort_keys=True) for x in rows)+'\n', encoding='utf-8')


def filedry(root: Path) -> dict:
    item = plan(); identity = candidate_identity(); effects = FileDryEffects(root)
    binding = effects.materialize(item, 0)
    proc = effects.spawn(binding)
    try:
        dump = Path(binding['state_dump']); _write_fake_dump(dump, donor=b'P', cold=b'P')
        state = require_equal_p_state(dump, donor_uid=7, cold_uid=8)
        # This represents both permitted calls only after the real state gate has passed.
        calls = [{'ordinal': 1, 'role': 'uid7_target'}, {'ordinal': 2, 'role': 'uid8_followup'}]
    finally:
        effects.cleanup(proc, time.monotonic()+15)
    result = {'schema': 'ft_d05_t11_filedry/v1', 'rid': RID, 'candidate': identity, 'plan': item,
              'state_hash': state, 'calls_materialized': calls, 'events': effects.events,
              'gpu_started': False, 'service_started': False, 'http_sent': False,
              'product_acceptance': False, 'status': 'CPU_FILEDRY_READY_NOT_GPU_ADMITTED'}
    _put(root/'CPU_FILEDRY_RECEIPT.json', result)
    return result


def require_admission(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError('root-sealed admission required')
    data = json.loads(path.read_text(encoding='utf-8'))
    expected = {'root_approved': True, 'rid': RID, 'candidate': CANDIDATE,
                'generation_calls': MAX_CALLS, 'independent_review': 'PASS'}
    if any(data.get(k) != v for k, v in expected.items()):
        raise RuntimeError('root admission differs')
    return data


def _birth(pid: int) -> dict:
    stat = Path(f'/proc/{pid}/stat')
    if not stat.is_file():
        raise RuntimeError('Linux process birth is required')
    fields = stat.read_text().rpartition(') ')[2].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'execution_id': f'{pid}:{fields[19]}'}


def child_argv(admission: Path, receipt: Path) -> list[str]:
    return [str(VENV/'bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child',
            '--admission', str(admission), '--receipt', str(receipt)]


def require_child_receipt(receipt_path: Path, admission: Path) -> dict:
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RuntimeError('controller receipt absent')
    value = json.loads(receipt_path.read_text(encoding='utf-8'))
    expected = hashlib.sha256(json.dumps(child_argv(admission, receipt_path), separators=(',', ':')).encode()).hexdigest()
    if (value.get('schema') != 'ft_d05_t11_controller_child/v1' or value.get('rid') != RID
            or value.get('candidate') != CANDIDATE or value.get('child_argv_sha256') != expected
            or not isinstance(value.get('controller_birth'), dict)):
        raise RuntimeError('controller receipt differs')
    return value


def _wait_ready(proc, port: int, deadline: float) -> None:
    import urllib.request
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise FailedHarness('failed_harness: service exited before readiness')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
                if json.load(response).get('status') == 'ok': return
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise FailedHarness('failed_harness: service readiness timeout')


def _target_request(port: int) -> tuple[object, object, dict]:
    retained = retained_module(); trace = json.loads(TRACE.read_text(encoding='utf-8'))
    client = retained.client_module(WT); binding = retained.target_binding(trace, client)
    row = trace['rounds'][binding['trace_index']]
    tools = trace.get('tools') or client.tool_specs()
    thinking = bool(trace.get('meta', {}).get('params', {}).get('thinking', True))
    target = retained.request(client, port, row['messages'], tools, thinking, 200)
    target.update(trace_index=binding['trace_index'], history_uid=8, tools=tools, thinking=thinking)
    return retained, client, target


def run_child(admission: Path, receipt: Path) -> dict:
    require_admission(admission); require_child_receipt(receipt, admission)
    root = Path(json.loads(admission.read_text(encoding='utf-8'))['run_root']) / RID
    if root.exists() or root.is_symlink(): raise RuntimeError('formal D05 run root already exists')
    root.mkdir(parents=True); item = plan(); effects = Effects(root); proc = None; calls = 0
    try:
        binding = effects.materialize(item, int(json.loads(admission.read_text())['port']))
        proc = effects.spawn(binding); _wait_ready(proc, int(json.loads(admission.read_text())['port']), time.monotonic()+900)
        retained, client, target = _target_request(int(json.loads(admission.read_text())['port'])); calls = 1
        _put(root/'call_1_target.json', {'uid': target['uid'], 'cached_tokens': target['cached_tokens'], 'prompt_tokens': target['prompt_tokens']})
        # Candidate dumps are consumed before any continuation/output verdict. Missing or unequal
        # donor/cold P evidence is an intentional failed_harness and prevents call 2.
        state = require_equal_p_state(Path(binding['state_dump']), donor_uid=target['uid'], cold_uid=target['uid'])
        follow = retained.followup(client, int(json.loads(admission.read_text())['port']), target['messages'], target); calls = 2
        _put(root/'call_2_followup.json', {'uid': follow['uid'], 'cached_tokens': follow['cached_tokens'], 'prompt_tokens': follow['prompt_tokens'], 'p_state_sha256': state})
        result = {'rid': RID, 'verdict': 'pending_independent_review', 'calls': calls, 'state_hash': state}
        _put(root/'terminal.json', result); return result
    except BaseException as exc:
        _put(root/'failed_harness.json', {'rid': RID, 'calls': calls, 'error': repr(exc), 'product_acceptance': False})
        raise
    finally:
        if proc is not None:
            effects.cleanup(proc, time.monotonic()+150)
            _put(root/'owned_cleanup.json', {'rid': RID, 'events': effects.events, 'lock_released': True})


def run_controller(admission: Path) -> int:
    require_admission(admission)
    data = json.loads(admission.read_text(encoding='utf-8')); run_root = Path(data['run_root']); run_root.mkdir(parents=True, exist_ok=True)
    receipt = run_root/f'launch_{RID}.json'
    argv = child_argv(admission, receipt)
    _put(receipt, {'schema': 'ft_d05_t11_controller_child/v1', 'rid': RID, 'candidate': CANDIDATE,
                   'controller_birth': _birth(os.getpid()), 'child_argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest()})
    child = subprocess.Popen(argv, start_new_session=True)
    return child.wait()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(); p.add_argument('--filedry', action='store_true'); p.add_argument('--run', action='store_true'); p.add_argument('--owned-child', action='store_true'); p.add_argument('--admission', type=Path); p.add_argument('--receipt', type=Path); p.add_argument('--root', type=Path)
    args = p.parse_args(argv)
    if args.filedry == args.run: p.error('select exactly one of --filedry or --run')
    if args.filedry:
        if args.owned_child or args.receipt: p.error('filedry cannot consume controller arguments')
        root = args.root or HERE/'evidence_cpu_filedry_current'
        if root.exists(): raise RuntimeError('filedry root already exists')
        print(json.dumps(filedry(root), sort_keys=True)); return 0
    if not args.admission: p.error('--run requires root-sealed --admission')
    if args.owned_child:
        if not args.receipt: p.error('owned child requires --receipt')
        return 0 if run_child(args.admission, args.receipt) else 0
    if args.receipt: p.error('only owned child consumes --receipt')
    return run_controller(args.admission)

if __name__ == '__main__': raise SystemExit(main())

