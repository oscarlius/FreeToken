"""Service runner for the 2026-10-11 hybrid verification window.

Starts one approved service (offload reference or hybrid) behind the exact argv gate,
proves readiness, runs the admission's measurement matrix (AIPerf phases and, where
admitted, quality60), then proves cleanup. The argv gate: offload services carry the
production argv with only --host/--port moved to the loopback test endpoint; hybrid
services additionally carry exactly the two section-0.5 changes (binding prefix and
--moe-strategy offload -> hybrid). Any other difference is rejected before spawn.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from window_measure import write, run as measure

ROOT = Path('/data2/FreeToken')
HERE = Path(__file__).resolve().parent


def load_d07():
    spec = importlib.util.spec_from_file_location('window_d07', ROOT / 'development/d07_g3g4_prepare.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_argv(baseline, mode, host, port):
    if baseline[:3] != ['taskset', '-c', '1,3-47']:
        raise ValueError('unexpected baseline affinity prefix')
    tail = list(baseline[3:])
    for flag, value in (('--host', str(host)), ('--port', str(port))):
        if tail.count(flag) != 1:
            raise ValueError(f'unexpected baseline {flag} count')
        tail[tail.index(flag) + 1] = value
    if mode == 'offload':
        return ['taskset', '-c', '1,3-47', *tail]
    if mode == 'hybrid':
        if tail.count('--moe-strategy') != 1 or tail[tail.index('--moe-strategy') + 1] != 'offload':
            raise ValueError('unexpected baseline strategy')
        tail[tail.index('--moe-strategy') + 1] = 'hybrid'
        return ['numactl', '--interleave=all', 'taskset', '-c', '1,3-23,25,27-47', *tail]
    raise ValueError(f'unknown service mode {mode!r}')


def argv_diff(baseline, actual):
    diff = []
    width = max(len(baseline), len(actual))
    for index in range(width):
        old = baseline[index] if index < len(baseline) else None
        new = actual[index] if index < len(actual) else None
        if old != new:
            diff.append({'index': index, 'baseline': old, 'actual': new})
    return diff


def alive_members(group):
    members = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group and fields[0] != 'Z':
                members.append(int(path.name))
        except (OSError, ValueError, IndexError):
            pass
    return members


def capture_birth(proc, d07):
    # Popen owns an unreaped child; the POSIX start_new_session exec handshake
    # completes before Popen returns. Independent OS session checks are fallback
    # evidence if the /proc birth reader transiently fails.
    try:
        identity = d07.process_identity(proc.pid)
    except OSError:
        identity = None
    if identity is not None:
        return identity
    try:
        pgid, session = os.getpgid(proc.pid), os.getsid(proc.pid)
    except ProcessLookupError:
        return None
    if pgid != proc.pid or session != proc.pid:
        raise RuntimeError('fresh child private session mismatch')
    return {'pid': proc.pid, 'pgid': pgid, 'session': session, 'start_ticks': None,
            'proof': 'Popen_unreaped_child_plus_OS_private_session'}


def idle(d07, checks=()):
    d07.require_gpu_idle()
    if subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip():
        raise RuntimeError('compute process remains')
    for host, port in checks:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))


def cleanup(proc, birth, d07, output, checks=()):
    errors = []
    import signal
    try:
        current = d07.process_identity(proc.pid)
        if current and birth['start_ticks'] is not None and current['start_ticks'] != birth['start_ticks']:
            raise RuntimeError('owned PID recycled')
        if current:
            if current['pgid'] != proc.pid or current['session'] != proc.pid:
                raise RuntimeError('owned process escaped frozen session')
            os.killpg(proc.pid, signal.SIGTERM)
        end = time.monotonic() + 30
        while alive_members(proc.pid) and time.monotonic() < end:
            time.sleep(.2)
        if alive_members(proc.pid):
            # A remaining member must retain the original owned process group/session.
            for pid in alive_members(proc.pid):
                identity = d07.process_identity(pid)
                if not identity or identity['session'] != proc.pid:
                    raise RuntimeError('group ownership changed')
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)
        end = time.monotonic() + 120
        while True:
            try:
                if alive_members(proc.pid):
                    raise RuntimeError('owned group remains')
                idle(d07, checks)
                break
            except Exception:
                if time.monotonic() >= end:
                    raise
                time.sleep(.2)
    except Exception as exc:
        errors.append(repr(exc))
    write(output / 'cleanup.json', {'proved': not errors, 'pid': proc.pid, 'birth': birth,
                                    'errors': errors, 'remaining_members': alive_members(proc.pid)})
    return not errors


def require_master_context(doc, deadline, d07):
    main_file = getattr(sys.modules.get('__main__'), '__file__', None)
    expected = HERE / 'gpu_window.py'
    if main_file is None or Path(main_file).resolve() != expected.resolve():
        raise RuntimeError('service launch requires the actual GPU master entry')
    if hashlib.sha256(expected.read_bytes()).hexdigest() != doc['controller_source_pins'][str(expected)]:
        raise RuntimeError('master source pin changed')
    events = [json.loads(line) for line in (Path(doc['output_root']) / 'events.jsonl').read_text().splitlines()]
    starts = [row for row in events if row['event'] == 'window_started']
    if len(starts) != 1 or not any(row['event'] == 'preconditions_passed' for row in events):
        raise RuntimeError('master lifecycle has not passed the stopped-production preconditions')
    identity = d07.process_identity(os.getpid())
    recorded = starts[0]['master_identity']
    if identity is None or (identity['pid'], identity['start_ticks']) != (recorded['pid'], recorded['start_ticks']):
        raise RuntimeError('actual master process birth differs')
    if time.time() >= deadline or deadline > starts[0]['deadline_epoch'] - 60:
        raise RuntimeError('service deadline escapes the window reserve')


def execute(path, service, deadline):
    doc = json.loads(Path(path).read_text())
    if Path(path).is_symlink() or Path(path).stat().st_mode & 0o222 or not doc.get('admit'):
        raise ValueError('sealed root admission required')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != doc['hybrid_controller_sha256']:
        raise ValueError('service controller source pin changed')
    if service not in doc['services']:
        raise ValueError(f'service {service!r} not admitted')
    spec = doc['services'][service]
    argv = expected_argv(doc['baseline_owner']['argv'], spec['mode'], doc['host'], doc['port'])
    pinned = doc['hybrid_argv'] if spec['mode'] == 'hybrid' else doc['offload_argv']
    if pinned != argv:
        raise ValueError('admission argv has unapproved differences')
    d07 = load_d07()
    require_master_context(doc, deadline, d07)
    checks = [(doc['host'], doc['port'])]
    idle(d07, checks)
    output = Path(doc['output_root']) / f'service_{service}'
    output.mkdir(exist_ok=False)
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('FT_DEV_'):
            env.pop(key)
    env.update(PYTHONPATH=doc['baseline_pythonpath'], MASTER_PORT='8096',
               CUDA_VISIBLE_DEVICES='0', PYTHONDONTWRITEBYTECODE='1')
    allowed = ['--host/--port moved to the loopback test endpoint']
    if spec['mode'] == 'hybrid':
        allowed = ['binding prefix per runbook 0.5', '--moe-strategy offload->hybrid per runbook 0.5'] + allowed
    write(output / 'argv_diff.json', {'baseline': doc['baseline_owner']['argv'], 'actual': argv,
                                      'mode': spec['mode'], 'allowed_changes': allowed,
                                      'positional_diff': argv_diff(doc['baseline_owner']['argv'], argv),
                                      'commit': doc['commit']})
    proc = birth = None
    error = None
    safe = False
    log = (output / 'serve.log').open('xb')
    owner = d07.take_d07_gpu_lock(f'HYBRID-VERIFY-20261011-{service}', 0)
    try:
        proc = subprocess.Popen(argv, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        birth = capture_birth(proc, d07)
        if not birth or birth['pgid'] != proc.pid or birth['session'] != proc.pid:
            raise RuntimeError('service process identity missing')
        write(output / 'owner.json', {'birth': birth, 'argv': argv, 'gpu_owner': owner})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready_limit = min(deadline - 180, time.time() + 600)
        last_progress = 0
        endpoint = f"http://{doc['host']}:{doc['port']}"
        while True:
            if proc.poll() is not None:
                raise RuntimeError('service exited before readiness')
            if time.time() >= ready_limit:
                raise TimeoutError('service readiness deadline 600s')
            if time.time() - last_progress >= 30:
                progress = (output / 'serve.log').read_text(errors='replace')[-3000:]
                with (output / 'loading_progress.jsonl').open('a') as handle:
                    handle.write(json.dumps({'at': time.time(), 'tail': progress}) + '\n')
                last_progress = time.time()
            try:
                with opener.open(endpoint + '/health', timeout=3) as response:
                    health = json.load(response)
                if health.get('status') == 'ok' and health.get('maintenance') == 'serving':
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        text = (output / 'serve.log').read_text(errors='replace')
        import re
        sizes = re.findall(r'moe_cache_size[\s:=]+(\d+)', text)
        if not sizes:
            raise RuntimeError('moe_cache_auto actual slot count unavailable')
        actual = int(sizes[-1])
        runtime = {'moe_cache_size': actual,
                   'confounded_more_than_5_percent': abs(actual / 2700 - 1) > .05}
        if spec['mode'] == 'hybrid':
            fetch_lines = [line for line in text.splitlines()
                           if 'moe-hybrid-max-fetch auto:' in line or 'fixed fetch cap' in line]
            if doc['max_fetch'] == -1 and not fetch_lines:
                raise RuntimeError('actual hybrid auto fetch branch unavailable')
            resolved = 1 if any('fixed fetch cap of 1' in line for line in fetch_lines) else None
            fraction_match = re.search(r'fetching ([0-9.]+)% of each decode step', '\n'.join(fetch_lines))
            if resolved is None and fraction_match is None and doc['max_fetch'] < 0:
                raise RuntimeError('hybrid auto cap semantics not parseable')
            fraction = float(fraction_match.group(1)) / 100 if fraction_match else None
            max_fetch = resolved if resolved is not None else (512 if fraction is not None else doc['max_fetch'])
            runtime.update(requested_moe_hybrid_max_fetch=doc['max_fetch'],
                           resolved_moe_hybrid_max_fetch=max_fetch,
                           resolved_fixed_fetch_cap=resolved,
                           fetch_fraction_rounded_from_log=fraction,
                           actual_fetch_branch_log=fetch_lines,
                           max_fetch_semantics=doc['max_fetch_semantics'])
        write(output / 'runtime_config.json', runtime)
        subprocess.run(['taskset', '-pc', str(proc.pid)], stdout=(output / 'affinity.txt').open('x'), check=True)
        subprocess.run(['numastat', '-p', str(proc.pid)], stdout=(output / 'numastat_before.txt').open('x'), check=True)
        subprocess.run(['ps', '-L', '-p', str(proc.pid), '-o', 'pid,tid,psr,pcpu,stat,comm'],
                       stdout=(output / 'threads_before.txt').open('x'), check=True)
        for tid in Path(f"/proc/{proc.pid}/task").iterdir():
            with (output / 'thread_affinities.txt').open('a') as handle:
                subprocess.run(['taskset', '-pc', tid.name], stdout=handle, stderr=subprocess.STDOUT, check=True)
        import threading
        stop_sampling = threading.Event()

        def sample_cpu():
            with (output / 'cpu_during_calls.jsonl').open('x') as handle:
                while not stop_sampling.is_set():
                    snapshot = subprocess.run(['ps', '-L', '-p', str(proc.pid), '-o', 'pid,tid,psr,pcpu,stat,comm'],
                                              capture_output=True, text=True)
                    handle.write(json.dumps({'at': time.time(), 'threads': snapshot.stdout,
                                             'returncode': snapshot.returncode}) + '\n')
                    handle.flush()
                    stop_sampling.wait(2)

        sampling = threading.Thread(target=sample_cpu, daemon=True)
        sampling.start()
        try:
            if spec.get('warmup', True):
                warmup_bounded(path, output, deadline - 120)
            for phase, repeats in spec['matrix']:
                for repeat in range(1, repeats + 1):
                    result = measure(path, service, phase, repeat, proc.pid, birth['start_ticks'], deadline - 60)
                    if any(x['decode_tps'] < 7.8 for x in result):
                        raise RuntimeError(f'abnormal per-lane speed in {phase}_{repeat}; stop arm')
            if spec.get('quality60'):
                run_quality60(doc, service, endpoint, output, deadline - 60)
        finally:
            stop_sampling.set()
            sampling.join(timeout=5)
        subprocess.run(['numastat', '-p', str(proc.pid)], stdout=(output / 'numastat_after.txt').open('x'), check=True)
    except BaseException as exc:
        error = repr(exc)
    finally:
        log.close()
        if proc is not None:
            if birth is None:
                try:
                    birth = capture_birth(proc, d07)
                except Exception:
                    pass
            if birth is not None:
                safe = cleanup(proc, birth, d07, output, checks)
            elif proc.poll() is not None and not alive_members(proc.pid):
                try:
                    idle(d07, checks)
                    safe = True
                except Exception:
                    pass
        elif proc is None:
            try:
                idle(d07, checks)
                safe = True
            except Exception:
                pass
        if safe:
            d07.release_d07_gpu_lock(owner)
        write(output / 'terminal.json',
              {'service': service, 'measurement_error': error, 'cleanup_proved': safe,
               'lock_retained': not safe, 'status': 'complete' if error is None and safe else 'failed_harness'})
    if not safe:
        raise RuntimeError('owned cleanup failed, preserve lock and inspect')
    return error is None


def run_quality60(doc, service, endpoint, output, deadline):
    from window_measure import load_old
    old = load_old()
    q = doc['quality60']
    if old.sha(q['script']) != q['script_sha256'] or old.sha(q['prompts']) != q['prompts_sha256']:
        raise RuntimeError('quality60 source or corpus pin changed')
    run_dir = output / 'quality60'
    argv = [q['python'], q['script'], '--api-base', endpoint + '/v1', '--model', q['model'],
            '--prompts', q['prompts'], '--run-dir', str(run_dir)]
    seconds = min(3600, max(1, int(deadline - time.time())))
    write(output / 'quality60_command.json', argv)
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=seconds)
    (output / 'quality60_stdout.txt').write_text(completed.stdout or '')
    (output / 'quality60_stderr.txt').write_text(completed.stderr or '')
    write(output / 'quality60_exit.json', {'returncode': completed.returncode, 'budget_seconds': seconds})
    if completed.returncode:
        raise RuntimeError('quality60 run failed')
    results = run_dir / f"quality_results_{q['model']}.jsonl"
    rows = [json.loads(line) for line in results.read_text().splitlines() if line.strip()]
    score = sum(1 for row in rows if row.get('passed') is True)
    statuses = {}
    for row in rows:
        statuses[row.get('graded_status')] = statuses.get(row.get('graded_status'), 0) + 1
    write(output / 'quality60_score.json',
          {'score_pass': score, 'total': len(rows), 'statuses': statuses,
           'results_sha256': old.sha(results),
           'runtime_errors': [row.get('question_id') for row in rows if row.get('graded_status') == 'RUNTIME_ERROR']})


def warmup_bounded(path, output, deadline):
    import signal
    with (output / 'warmup_client.log').open('xb') as handle:
        proc = subprocess.Popen([sys.executable, str(HERE / 'warmup_client.py'), str(path), str(output), str(deadline)],
                                stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=max(1, min(180, deadline - time.time())))
            if code:
                raise RuntimeError('SDK warmup client failed')
        except BaseException:
            if proc.poll() is None:
                if os.getpgid(proc.pid) != proc.pid or os.getsid(proc.pid) != proc.pid:
                    raise RuntimeError('warmup child ownership changed')
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
            raise


def warmup(doc, output, deadline):
    from window_measure import load_old
    old = load_old()
    inputs = Path(doc['warmup_inputs_path'])
    adapter = Path(doc['warmup_adapter_path'])
    if old.sha(inputs) != doc['warmup_inputs_sha256'] or old.sha(adapter) != doc['warmup_adapter_sha256']:
        raise RuntimeError('SDK warmup source pin changed')
    spec = importlib.util.spec_from_file_location('verify_sdk_warmup', adapter)
    sdk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sdk)
    rows = json.loads(inputs.read_text())['items']
    folder = output / 'warmup'
    folder.mkdir()
    endpoint = f"http://{doc['host']}:{doc['port']}"
    records = []
    for key in ['short', 'long']:
        if time.time() >= deadline:
            raise TimeoutError('warmup budget expired')
        record = sdk.collect_one(endpoint, 'Qwen3.8-Flash-Next-NVFP4', key, rows[key], folder)
        projection = record['projection']
        expected = 512 if key == 'short' else 8257
        if projection['usage']['prompt_tokens'] != expected or projection['usage']['completion_tokens'] != 128 \
                or projection['finish_reason'] != 'length':
            raise RuntimeError('SDK warmup token contract differs')
        records.append({'key': key, 'usage': projection['usage'], 'finish_reason': projection['finish_reason']})
    write(folder / 'terminal.json', {'calls': 2, 'not_scored': True, 'endpoint': endpoint, 'records': records})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--admission')
    parser.add_argument('--deadline', type=float)
    args = parser.parse_args()
    if not args.run:
        print('inert')
        return
    parser.error('services are master-only components; use the root-admitted gpu_window entry')


if __name__ == '__main__':
    main()
