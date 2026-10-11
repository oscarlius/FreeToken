"""Root-admitted D09 T2/T03b three-service replay parent.

CPU ``--filedry`` uses the independent T2 client's fake clock and writes the
same three-service/60-call/judgement topology.  ``--run`` is deliberately
inert until a sealed root admission binds this exact source and all inputs.
"""
from __future__ import annotations

import argparse, copy, hashlib, importlib.util, json, os, signal, socket
import subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE
ROOT = Path('/data2/FreeToken')
RID = 'E2-D09-T2-T03b-parent-night-20261009'
CANDIDATE = 'c17b69a46cd512fbf3d127d3879bce92caae457b'
WORKTREE = ROOT / 'wt/d09-message-boundary-v1'
CLIENT_SHA256 = '9407d83c5b76955592c9524297047ec90f64a2f321b20aee3adc3cd89ee08db6'
T16_PROVENANCE_SHA256 = 'ed58778c314e6d6def818445b0040d173591eb86868d572a6585d18eab4a60f5'
T16_DEV = ROOT / 'development/d09_t16_night_v1'
CLIENT_PATH = ROOT / 'development/d09_gpu_night_20261009/t2_actual_v5.py'
MAX_SERVICES, MAX_CALLS, MAX_TOKENS = 3, 60, 32


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('x', encoding='utf-8') as h: json.dump(value, h, ensure_ascii=False, indent=2); h.write('\n')
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None; spec.loader.exec_module(module); return module


def local_client_path():
    return CLIENT_PATH if CLIENT_PATH.exists() else PACKAGE_ROOT.parent / 'd09_gpu_night_20261009/t2_actual_v5.py'


def bindings(client):
    t16 = T16_DEV / 'd09_native_provenance_v1.json'
    d07 = T16_DEV / 'd07_g3g4_prepare.py'
    assert sha(local_client_path()) == CLIENT_SHA256
    assert sha(t16) == T16_PROVENANCE_SHA256
    return {str(Path(__file__).resolve()): sha(__file__), str(local_client_path()): CLIENT_SHA256,
            str(t16): T16_PROVENANCE_SHA256, str(d07): sha(d07)}


def plan_sets(client):
    module, plan, client_bindings = client.prepare()
    assert len(plan) == 36 and all(x['payload']['max_tokens'] == MAX_TOKENS for x in plan)
    hot = plan
    edit = [copy.deepcopy(x) for x in plan if x['mode'] == 'edit']
    assert len(edit) == 12
    cold_a, cold_b = copy.deepcopy(edit), copy.deepcopy(edit)
    for item in cold_a: item['mode'] = 'edit_cold_A'
    for item in cold_b: item['mode'] = 'edit_cold_B'
    # Physical request order is edited round 11 down to 0 for both cold services.
    return module, hot, (sorted(cold_a, key=lambda x: x['round'], reverse=True),
                         sorted(cold_b, key=lambda x: x['round'], reverse=True)), client_bindings


def output_bytes(record):
    """Bytewise comparator for reasoning/content/tool-argument stream result."""
    value = record['result']
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def compare_cold(hot, cold_a, cold_b, output):
    rows = []
    for round_id in range(12):
        a, b, h = cold_a[round_id], cold_b[round_id], hot[round_id]
        if output_bytes(a) != output_bytes(b):
            row = {'round': round_id, 'classification': 'failed_harness', 'reason': 'cold_A_B_output_unstable'}
            put(output / f'compare_{round_id:02}.json', row); return rows + [row], 'failed_harness'
        if output_bytes(h) != output_bytes(a):
            hb, cb = output_bytes(h), output_bytes(a)
            diff = next(i for i, (x, y) in enumerate(zip(hb, cb)) if x != y) if hb != cb else min(len(hb), len(cb))
            row = {'round': round_id, 'classification': 'not_met', 'first_differing_output_byte': diff,
                   'hot_length': len(hb), 'cold_length': len(cb)}
            put(output / f'compare_{round_id:02}.json', row); return rows + [row], 'not_met'
        row = {'round': round_id, 'classification': 'PASS', 'bytewise_output_equal': True}
        put(output / f'compare_{round_id:02}.json', row); rows.append(row)
    return rows, 'measured_pending_independent_review'


def check_service_spec(service):
    argv, env = service['argv'], service['env']
    assert '--enable-message-boundary-ckpt' in argv
    assert '--prefill-layer-major' in argv and '--moe-strategy' in argv and argv[argv.index('--moe-strategy') + 1] == 'offload'
    assert '--ple-backend' in argv and argv[argv.index('--ple-backend') + 1] == 'pinned'
    assert 'FT_DEV_PREFILL_SCHEDULE' not in env and env['PYTHONPATH'] == str(WORKTREE / 'python')
    assert service['worktree'] == str(WORKTREE) and service['candidate_commit'] == CANDIDATE
    assert 1024 <= int(service['api_port']) <= 65535 and 1024 <= int(service['tcpstore_port']) <= 65535


def require_admission(path, source_bindings):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222: raise RuntimeError('root admission absent, symlinked, or writable')
    doc = json.loads(path.read_text())
    expected = {'schema': 'ft_d09_replay_parent_admission/v1', 'root_approved': True, 'rid': RID,
                'candidate_commit': CANDIDATE, 'bindings': source_bindings, 'max_services': MAX_SERVICES,
                'max_generation_calls': MAX_CALLS, 'max_tokens': MAX_TOKENS,
                'required_gates': {'T16': 'passed', 'T17': 'passed'}}
    if any(doc.get(k) != v for k, v in expected.items()): raise RuntimeError('root admission binding differs')
    services = doc.get('services')
    if not isinstance(services, list) or [x.get('name') for x in services] != ['fresh_on', 'edit_cold_A', 'edit_cold_B']:
        raise RuntimeError('root admission service plan differs')
    for service in services: check_service_spec(service)
    return doc


def reserve_port_pair(api_port, tcpstore_port):
    """Reserve both loopback ports together; caller closes immediately before spawn."""
    if int(api_port) and int(api_port) == int(tcpstore_port): raise RuntimeError('API and TCPStore ports must differ')
    held = []
    try:
        for port in (api_port, tcpstore_port):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', int(port))); held.append(sock)
        return held
    except BaseException:
        for sock in held: sock.close()
        raise


def release_port_pair(held):
    for sock in held: sock.close()


def run_service(client, module, plan, service, output, owner, d07):
    """Start one owned service, execute its bound plan, then clean its group."""
    arm = output / 'services' / service['name']; arm.mkdir(parents=True)
    reservation = reserve_port_pair(service['api_port'], service['tcpstore_port'])
    env = d07.clean_environment(WORKTREE); env.update(service['env']); env['PYTHONDONTWRITEBYTECODE'] = '1'
    put(arm / 'argv.json', service['argv']); put(arm / 'environment.json', service['env'])
    proc = None
    try:
        put(arm / 'port_pair_reservation.json', {'api_port': service['api_port'], 'tcpstore_port': service['tcpstore_port'],
                                                 'both_bound_before_spawn': True})
        release_port_pair(reservation); reservation = []
        with (arm / 'serve.log').open('xb') as log:
            proc = subprocess.Popen(service['argv'], cwd=arm, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        identity = d07.process_identity(proc.pid)
        put(arm / 'owner.json', {'candidate_commit': CANDIDATE, 'pid_identity': identity, 'argv': service['argv'], 'GPU_owner': owner})
        # Health is the only non-generation readiness operation. No generated call is added.
        endpoint = f'http://127.0.0.1:{service["api_port"]}'
        deadline = time.monotonic() + 1800
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while True:
            if proc.poll() is not None: raise RuntimeError('owned service exited before health')
            if time.monotonic() >= deadline: raise TimeoutError('health readiness timeout')
            try:
                with opener.open(endpoint + '/health', timeout=10) as response:
                    health = json.loads(response.read())
                if health.get('status') == 'ok': break
            except (OSError, ValueError): time.sleep(2)
        put(arm / 'ready.json', {'health': health, 'generation_readiness_calls': 0})
        results = client.execute(module, plan, opener, endpoint, arm / 'serve.log', arm / 'client')
        expected_calls = 36 if service['name'] == 'fresh_on' else 12
        if len(results) != expected_calls: raise RuntimeError('unexpected client call count')
        if service['name'] != 'fresh_on' and any(x['cached_tokens'] != 0 for x in results):
            raise RuntimeError('cold edit cache geometry is nonzero')
        return results
    finally:
        if proc is not None:
            d07.load_owned_lifecycle().stop_owned_process(proc, 120, 30)
            if d07.load_owned_lifecycle().owned_group_alive(proc.pid): raise RuntimeError('owned service group remains alive')
            put(arm / 'cleanup.json', {'pid_identity': d07.process_identity(proc.pid), 'group_alive': False})
        release_port_pair(reservation)
        d07.require_gpu_idle()
        post = reserve_port_pair(service['api_port'], service['tcpstore_port']); release_port_pair(post)


def filedry():
    client = load(local_client_path(), 'd09_t2_actual_v5')
    module, hot_plan, (cold_a_plan, cold_b_plan), client_bindings = plan_sets(client)
    root = HERE / 'FILEDRY_v3_sourcefix1';
    if root.exists(): raise RuntimeError('FILEDRY already exists; preserve historical evidence')
    root.mkdir()
    def execute_mock(name, plan):
        arm = root / 'services' / name; arm.mkdir(parents=True)
        held = reserve_port_pair(0, 0)
        ports = [sock.getsockname()[1] for sock in held]
        log = arm / 'serve.log'; log.write_bytes(b'FILEDRY pre-existing log\n')
        now = [0.0]; calls = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self):
                for delay, line in ((.125, b'data: {"choices":[{"delta":{"reasoning_content":"stable"}}]}\n'),
                                    (.625, b'data: {"choices":[{"delta":{"content":" output"},"finish_reason":"length"}],"usage":{"prompt_tokens":100,"completion_tokens":32,"prompt_tokens_details":{"cached_tokens":0}}}\n'),
                                    (.25, b'data: [DONE]\n')):
                    now[0] += delay
                    with log.open('ab') as h: h.write(b'FILEDRY service window\n')
                    yield line
        class Opener:
            def open(self, request, timeout):
                payload = json.loads(request.data); assert payload == plan[len(calls)]['payload']
                calls.append(payload); return Response()
        original_time = module.time
        module.time = SimpleNamespace(perf_counter=lambda: now[0])
        try:
            results = client.execute(module, plan, Opener(), f'http://127.0.0.1:{ports[0]}', log, arm / 'client', lambda: now[0])
        finally:
            module.time = original_time
            release_port_pair(held)
        assert len(calls) == len(plan)
        put(arm / 'port_pair_reservation.json', {'api_port': ports[0], 'tcpstore_port': ports[1],
                                                 'both_bound': True, 'released_after_mock_execute': True})
        return results, len(calls)
    hot_results, hot_calls = execute_mock('fresh_on', hot_plan)
    cold_a_results, cold_a_calls = execute_mock('edit_cold_A', cold_a_plan)
    cold_b_results, cold_b_calls = execute_mock('edit_cold_B', cold_b_plan)
    assert all(x['cached_tokens'] == 0 for x in cold_a_results + cold_b_results)
    hot = {x['round']: x for x in hot_results if x['mode'] == 'edit'}
    cold_a = {x['round']: x for x in cold_a_results}; cold_b = {x['round']: x for x in cold_b_results}
    rows, verdict = compare_cold(hot, cold_a, cold_b, root)
    receipt = {'schema': 'ft_d09_replay_parent_filedry/v3', 'rid': RID, 'runner_sha256': sha(__file__),
               'root_client_sha256': CLIENT_SHA256, 'root_client_bindings': client_bindings,
               'planned_services': 3, 'planned_generation_calls': 60, 'actual_mock_calls': hot_calls + cold_a_calls + cold_b_calls,
               'per_service_actual_mock_calls': {'fresh_on': hot_calls, 'edit_cold_A': cold_a_calls, 'edit_cold_B': cold_b_calls},
               'cold_cached_tokens': 0, 'comparison_verdict': verdict, 'comparison_rows': rows,
               'gpu_started': False, 'http_started': False, 'service_started': False, 'compile_started': False}
    put(root / 'terminal.json', receipt); return receipt


def child_argv(admission_path, batch, receipt):
    return [str(ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child',
            '--admission', str(admission_path), '--batch', str(batch), '--launch-receipt', str(receipt)]


def require_child_receipt(d07, receipt, batch, admission_path):
    deadline = time.monotonic() + 30; expected = d07.argv_sha256(child_argv(admission_path, batch, receipt)); mine = d07.process_birth()
    while time.monotonic() < deadline:
        if receipt.is_file() and not receipt.is_symlink():
            value = json.loads(receipt.read_text())
            if value.get('state') == 'launched' and value.get('child') == mine:
                if (value.get('schema') != 'ft_d09_replay_parent_launch/v1' or value.get('rid') != RID
                        or value.get('batch') != batch or value.get('candidate_commit') != CANDIDATE
                        or value.get('argv_sha256') != expected): raise RuntimeError('child receipt binding differs')
                return value
        time.sleep(.05)
    raise RuntimeError('child receipt did not become bound')


def controller(admission_path):
    client = load(CLIENT_PATH, 'd09_t2_actual_v5'); source_bindings = bindings(client); require_admission(admission_path, source_bindings)
    d07 = load(T16_DEV / 'd07_g3g4_prepare.py', 'd09_parent_d07_controller'); d07.CANDIDATE = CANDIDATE; d07.RID = RID
    if d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists')
    lifecycle = d07.load_owned_lifecycle(); helper = lifecycle.verified_module(ROOT / 'runs/plan_batches/e2_launch.py', d07.ATOMIC_HELPER_SHA, 'd09_parent_atomic')
    batch = helper.next_batch(d07.ROUNDS); receipt = HERE / 'runs' / f'launch_{RID}_batch{batch}.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    argv = child_argv(admission_path, batch, receipt)
    reserved = {'schema': 'ft_d09_replay_parent_launch/v1', 'state': 'reserved', 'rid': RID, 'batch': batch,
                'candidate_commit': CANDIDATE, 'argv_sha256': d07.argv_sha256(argv), 'controller': d07.process_birth(),
                'scope': {'services_max': MAX_SERVICES, 'generation_calls_max': MAX_CALLS}}
    value = lifecycle.reserve_process(helper, batch, RID, argv, receipt, reserved)
    child = d07.process_identity(value['batch_pid'])
    return d07.publish_child_binding(receipt, value, child, lifecycle=lifecycle)


def execute(admission_path, batch, receipt):
    client = load(CLIENT_PATH, 'd09_t2_actual_v5'); module, hot_plan, (cold_a_plan, cold_b_plan), _ = plan_sets(client)
    source_bindings = bindings(client); admission = require_admission(admission_path, source_bindings)
    d07 = load(T16_DEV / 'd07_g3g4_prepare.py', 'd09_parent_d07'); d07.CANDIDATE = CANDIDATE; d07.RID = RID
    output = HERE / 'runs' / f'{RID}_batch{batch}'
    if output.exists() or output.is_symlink(): raise RuntimeError('D09 RID already has output')
    require_child_receipt(d07, receipt, batch, admission_path)
    owner = d07.take_d07_gpu_lock(RID, batch)
    hot_results = cold_a_results = cold_b_results = None
    rows, verdict, error, cleanup_error = [], 'failed_harness', None, None
    try:
        d07.require_gpu_idle(); output.mkdir(parents=True); put(output / 'admission_snapshot.json', admission)
        hot_results = run_service(client, module, hot_plan, admission['services'][0], output, owner, d07)
        cold_a_results = run_service(client, module, cold_a_plan, admission['services'][1], output, owner, d07)
        cold_b_results = run_service(client, module, cold_b_plan, admission['services'][2], output, owner, d07)
        hot = {x['round']: x for x in hot_results if x['mode'] == 'edit'}
        cold_a = {x['round']: x for x in cold_a_results}; cold_b = {x['round']: x for x in cold_b_results}
        rows, verdict = compare_cold(hot, cold_a, cold_b, output)
    except BaseException as exc:
        error = repr(exc)
    finally:
        # A failed idle/release proof intentionally preserves the lock.  The
        # terminal record is written only after successful closure evidence.
        try:
            d07.require_gpu_idle()
            d07.release_d07_gpu_lock(owner)
        except BaseException as exc:
            cleanup_error = repr(exc)
        if output.exists() and cleanup_error is None:
            put(output / 'terminal.json', {'rid': RID, 'verdict': verdict, 'error': error, 'services': 3,
                                            'generation_calls': 60, 'comparisons': rows, 'post_cleanup_closed': True,
                                            'gpu_lock_released': True, 'product_acceptance': False,
                                            'independent_terminal_review_required': True})
    if cleanup_error is not None:
        raise RuntimeError('unsafe cleanup preserves GPU lock: ' + cleanup_error)
    if error is not None:
        raise RuntimeError(error)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--filedry', action='store_true'); parser.add_argument('--run', action='store_true'); parser.add_argument('--owned-child', action='store_true'); parser.add_argument('--admission', type=Path); parser.add_argument('--batch', type=int); parser.add_argument('--launch-receipt', type=Path)
    args = parser.parse_args()
    if args.filedry and not args.run: print(json.dumps(filedry(), ensure_ascii=False, indent=2)); return
    if args.run and args.admission and args.owned_child and args.batch and args.launch_receipt: execute(args.admission, args.batch, args.launch_receipt); return
    if args.run and args.admission and not args.owned_child and args.batch is None and args.launch_receipt is None: controller(args.admission); return
    parser.error('select --filedry or --run --admission ROOT_SEALED_FILE')

if __name__ == '__main__': main()
