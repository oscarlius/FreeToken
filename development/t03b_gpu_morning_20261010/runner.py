"""Morning T03b rolling checkpoint acceptance; CPU and GPU share one lifecycle."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
WT = ROOT / 'wt/t03b-rolling64'
CANDIDATE = 'dc951c6918ae0fab4ef8f6152c6de198f0f7f858'
RID = 'E2-T03b-rolling64-20261010'
RUN = ROOT / 'runs/dev_T03b' / RID
PORTS = [(31601 + i * 2, 31602 + i * 2) for i in range(6)]
WORKLOAD_SECONDS = 2400
CLEANUP_RESERVE_SECONDS = 300
GENERATION_PHASE_SECONDS = 1500

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def put(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True, indent=2); f.write('\n')

def load(p, name):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def gate():
    g = load(ROOT / 'development/d07_g3g4_prepare.py', 't03b_morning_d07')
    g.RID = RID; g.CANDIDATE = CANDIDATE
    return g

def transport():
    return load(HERE / 'frozen_t03b_transport.py', 't03b_frozen_transport')

def sources(g):
    paths = [HERE / name for name in ('runner.py', 'frozen_t03b_transport.py', 'r052_d0_shutdown_startup_v2.py')]
    paths += [ROOT / 'development/d07_g3g4_prepare.py', ROOT / 'runs/plan_batches/e2_launch.py', g.OWNED_SOURCE / 't17_owned_launch_protocol.py']
    return {str(p): sha(p) for p in paths}

def candidate():
    head = subprocess.check_output(['git', '-C', str(WT), 'rev-parse', 'HEAD'], text=True).strip()
    if head != CANDIDATE or subprocess.check_output(['git', '-C', str(WT), 'status', '--porcelain', '--untracked-files=no'], text=True):
        raise RuntimeError('candidate commit or tracked source differs')
    return head

def check_admission(p, g):
    p = Path(p)
    if p.is_symlink() or not p.is_file() or p.stat().st_mode & 0o222:
        raise RuntimeError('sealed root admission required')
    d = json.loads(p.read_text())
    for key, value in {'rid': RID, 'candidate': CANDIDATE, 'root_approved': True, 'services_max': 6, 'calls_max': 24, 'source_sha256': sources(g)}.items():
        if d.get(key) != value: raise RuntimeError('admission differs: ' + key)
    for native, digest in d['native_sha256'].items():
        if sha(Path(native)) != digest: raise RuntimeError('candidate native differs')
    return d

def child_argv(p, batch, receipt):
    return [str(ROOT / 'venv/bin/python'), str(HERE / 'runner.py'), '--run', '--child', '--admission', str(p), '--batch', str(batch), '--receipt', str(receipt)]

def controller(p, g=None):
    g = g or gate(); check_admission(p, g); candidate()
    if g.LOCK.exists() or g.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock')
    owned = g.load_owned_lifecycle()
    helper = owned.verified_module(ROOT / 'runs/plan_batches/e2_launch.py', g.ATOMIC_HELPER_SHA, 't03b_morning_atomic')
    batch = helper.next_batch(g.ROUNDS); receipt = HERE / 'runs' / f'launch_batch{batch}.json'
    receipt.parent.mkdir(parents=True, exist_ok=True); argv = child_argv(p, batch, receipt)
    reserved = {'schema': 'ft_t03b_morning_launch/v1', 'state': 'reserved', 'rid': RID, 'batch': batch, 'candidate_commit': CANDIDATE, 'argv_sha256': g.argv_sha256(argv), 'controller': g.process_birth()}
    launched = owned.reserve_process(helper, batch, RID, argv, receipt, reserved)
    birth = g.process_identity(launched['batch_pid'])
    if birth is None: raise RuntimeError('child exited before birth binding')
    return g.publish_child_binding(receipt, launched, {k: birth[k] for k in ('pid', 'start_ticks', 'execution_id')}, lifecycle=owned)

def bind_ports(ports):
    held = []
    try:
        for port in ports:
            for family, host in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
                s = socket.socket(family, socket.SOCK_STREAM); held.append(s)
                if family == socket.AF_INET6: s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                s.bind((host, port))
    finally:
        for s in held: s.close()

def wait_gpu_idle(g, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try:
            g.require_gpu_idle(); return
        except RuntimeError:
            if time.monotonic() >= deadline: raise
            time.sleep(1)

def require_ports(ports, output, timeout=120):
    deadline = time.monotonic() + timeout
    while True:
        try: bind_ports(ports); return
        except OSError:
            if time.monotonic() >= deadline:
                p = subprocess.run(['ss', '-tanp'], capture_output=True, text=True)
                output.write_text(p.stdout + p.stderr)
                raise RuntimeError('owned API/TCP ports did not become bindable')
            time.sleep(1)

class Effects:
    def __init__(self, g):
        self.g = g; self.owned = g.load_owned_lifecycle(); self.t = transport()
        self.t.urllib.request.urlopen = build_opener(ProxyHandler({})).open

    def prepare(self, arm, index):
        arm.mkdir(); source = arm / 'source'; source.mkdir()
        p = source / 'r052_d0_shutdown_startup_v2.py'
        shutil.copyfile(HERE / p.name, p)
        if sha(p) != sha(HERE / p.name): raise RuntimeError('copied startup differs')
        api, tcp = PORTS[index]; argv = self.t.serve_argv(api)
        argv += ['--enable-toolcall-rolling-ckpt']
        if index % 2: argv += ['--no-prefill-anchor-cut']
        argv = ['taskset', '-c', '1,3-47', str(ROOT / 'venv/bin/python'), '-u', str(p), *argv[1:]]
        env = self.g.clean_environment(WT)
        env.update(PYTHONPATH=str(source) + ':' + str(WT / 'python'), FT_DEV_D0='1', FT_DEV_D0_PATH=str(arm / 'd0'), FT_DEV_D0_TIMELINE='1', FT_DEV_D0_TIMELINE_STEPS='20000', FT_R052_WORKER_SHUTDOWN=str(arm / 'worker_shutdown.json'))
        # The engine derives the TCP store port from the API port. Validate
        # this against the pinned live source before admission.
        put(arm / 'recipe.json', {'argv': argv, 'api': api, 'tcpstore': tcp, 'candidate': CANDIDATE, 'startup_sha256': sha(p)})
        return argv, env

    def start(self, arm, index, argv, env):
        self.g.require_gpu_idle(); require_ports(PORTS[index], arm / 'ports_before_failure.txt')
        with (arm / 'serve.log').open('xb') as f:
            proc = subprocess.Popen(argv, cwd=arm / 'source', env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        put(arm / 'owner.json', {'identity': self.g.process_identity(proc.pid), 'argv_sha256': self.g.argv_sha256(argv)})
        return proc

    def ready(self, proc, index, timeout):
        deadline = time.monotonic() + min(900, timeout)
        while time.monotonic() < deadline:
            if proc.poll() is not None: raise RuntimeError('service exited before ready')
            try:
                with self.t.urllib.request.urlopen(f'http://127.0.0.1:{PORTS[index][0]}/health', timeout=3) as f:
                    if json.load(f).get('status') == 'ok': return
            except (OSError, ValueError): pass
            time.sleep(2)
        raise TimeoutError('health-only readiness timed out')

    def positive(self, index, payload, timeout):
        return self.t.stream_request(PORTS[index][0], payload, timeout=timeout)

    def negative(self, index, timeout):
        return self.t.request_json(PORTS[index][0], self.t.negative_payload(), timeout=timeout)

    def cleanup(self, arm, index, proc, timeout):
        deadline = time.monotonic() + timeout
        stop_budget = min(120, max(0, deadline - time.monotonic())); reap_budget = min(30, max(0, deadline - time.monotonic() - stop_budget))
        self.owned.stop_owned_process(proc, stop_budget, reap_budget)
        if self.owned.owned_group_alive(proc.pid): raise RuntimeError('owned service descendants alive')
        require_ports(PORTS[index], arm / 'ports_after_failure.txt', min(120, max(0, deadline - time.monotonic())))
        wait_gpu_idle(self.g, min(120, max(0, deadline - time.monotonic())))
        put(arm / 'cleanup.json', {'owned_group_absent': True, 'api_tcpstore_dual_stack_bindable': True, 'cleanup_budget_s': timeout})

    def evidence(self, arm, turns):
        shutdown = json.loads((arm / 'worker_shutdown.json').read_text())
        if shutdown.get('schema') != 'ft_r052_worker_shutdown/v1' or shutdown.get('status') != 'complete' or shutdown.get('scheduler_run_started') is not True:
            raise RuntimeError('actual scheduler D0 shutdown incomplete')
        count = self.t.snapshot_count(arm / 'serve.log')
        decode = json.loads((arm / 'd0_decode.json').read_text())
        if decode.get('anchor_snapshots_taken') != count: raise RuntimeError('final snapshot count differs')
        hit = self.t.bind_post_trigger_cache(turns[2], arm / 'd0_prefill.jsonl')
        return {'snapshots': count, 'post_trigger_cache_hit': hit, 'trigger': self.t.classify_positive(turns[0]['response'])}

def run_lifecycle(run, e):
    run.mkdir(parents=True); workload_deadline = time.monotonic() + WORKLOAD_SECONDS; cleanup_deadline = workload_deadline + CLEANUP_RESERVE_SECONDS; names = [f'{kind}_p{p}' for p in range(1, 4) for kind in ('A_cut_on', 'B_cut_off')]
    calls = 0; rows = []; error = None; verdict = 'kept'; safe = True
    for index, name in enumerate(names):
        arm = run / name; proc = None
        try:
            remaining = int(workload_deadline - time.monotonic())
            if remaining <= 0: raise TimeoutError('whole workload budget exhausted before service start')
            argv, env = e.prepare(arm, index); proc = e.start(arm, index, argv, env); e.ready(proc, index, remaining)
            messages = e.t.positive_payload()['messages']; turns = []; phase_deadline = min(workload_deadline, time.monotonic() + GENERATION_PHASE_SECONDS)
            for turn in range(3):
                remaining = int(min(workload_deadline, phase_deadline) - time.monotonic())
                if remaining <= 0: raise TimeoutError('generation phase budget exhausted before request')
                payload = {**e.t.positive_payload(), 'messages': messages}; calls += 1
                response, raw, ttft, wire = e.positive(index, payload, remaining)
                row = {'payload': payload, 'response': response, 'sse_events': raw, 'wire': wire, 'first_token_s': ttft}
                put(arm / f'positive_turn{turn}.json', row); turns.append(row)
                messages = e.t.retained_followup(messages, response)
            remaining = int(min(workload_deadline, phase_deadline) - time.monotonic())
            if remaining <= 0: raise TimeoutError('generation phase budget exhausted before negative control')
            calls += 1; put(arm / 'negative.json', e.negative(index, remaining))
        except BaseException as exc:
            error = repr(exc); verdict = 'failed_harness'
        finally:
            if proc is not None:
                try:
                    # Cleanup must fit the round's reserved tail even after a hung arm.
                    remaining_cleanup = cleanup_deadline - time.monotonic()
                    if remaining_cleanup <= 0: raise TimeoutError('cleanup reserve exhausted')
                    e.cleanup(arm, index, proc, remaining_cleanup)
                except BaseException as exc: error = repr(exc); verdict = 'failed_harness'; safe = False
        if error: break
        try:
            row = e.evidence(arm, turns); row['arm'] = name; rows.append(row); put(arm / 'arm_result.json', row)
            # A triggered path must actually snapshot before a product verdict
            # is meaningful. No fake counters or API 200 substitute for it.
            if row['trigger']['classification'] != 'hit': raise RuntimeError('frozen trigger was not exercised')
            if row['snapshots'] == 0:
                verdict = 'not_met'; break
        except BaseException as exc: error = repr(exc); verdict = 'failed_harness'; break
    put(run / 'terminal.json', {'rid': RID, 'candidate': CANDIDATE, 'verdict': verdict, 'calls': calls, 'services': len(list(run.glob('*_p*'))), 'arms': rows, 'error': error, 'post_cleanup_closed': safe, 'workload_seconds': WORKLOAD_SECONDS, 'cleanup_reserve_seconds': CLEANUP_RESERVE_SECONDS, 'generation_phase_seconds': GENERATION_PHASE_SECONDS, 'independent_review_required': True, 'product_acceptance': False})
    return safe

def child(p, batch, receipt, g=None, e=None, run=None):
    g = g or gate(); check_admission(p, g); candidate()
    g.require_child_receipt(receipt, batch, WT, ROOT / 'runs/dev_T03b', rid=RID, expected_argv=child_argv(p, batch, receipt), schema='ft_t03b_morning_launch/v1')
    owner = g.take_d07_gpu_lock(RID, batch); safe = False; child_deadline = time.monotonic() + WORKLOAD_SECONDS + CLEANUP_RESERVE_SECONDS
    try:
        g.require_gpu_idle(); safe = run_lifecycle(run or RUN, e or Effects(g))
    finally:
        if safe:
            wait_gpu_idle(g, max(0, child_deadline - time.monotonic())); g.release_d07_gpu_lock(owner)
        else: raise RuntimeError('cleanup unproven; preserve owned GPU lock')

def filedry(g=None):
    g = g or gate()
    return {'schema': 'ft_t03b_morning_filedry/v1', 'rid': RID, 'candidate': CANDIDATE, 'source_sha256': sources(g), 'gpu_started': False, 'http_started': False, 'service_started': False, 'compile_started': False}

def main():
    p = argparse.ArgumentParser(); p.add_argument('--filedry', action='store_true'); p.add_argument('--run', action='store_true'); p.add_argument('--child', action='store_true'); p.add_argument('--admission', type=Path); p.add_argument('--batch', type=int); p.add_argument('--receipt', type=Path); a = p.parse_args()
    if a.filedry:
        print(json.dumps(filedry(), sort_keys=True)); return
    if not a.run or not a.admission: p.error('root admission and --run required')
    if a.child:
        if a.batch is None or not a.receipt: p.error('owned child requires batch/receipt')
        child(a.admission, a.batch, a.receipt)
    else: controller(a.admission)

if __name__ == '__main__': main()

