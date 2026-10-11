#!/usr/bin/env python3
"""Prepare or run the bounded D06 G3/G4 development self-check.

This runner is deliberately separate from T16 and T05.  ``--run`` is the only
path that acquires the shared GPU lock or creates the output directory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import shlex


ROOT = Path('/data2/FreeToken')
PARENT = ROOT / 'wt' / 'e2base'
CANDIDATE = ROOT / 'wt' / 'e2d06'
PARENT_COMMIT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
CANDIDATE_COMMIT = '03692633df48456fb0baa78de7b64e5628a12ab1'
OUT = ROOT / 'runs' / 'dev_D06' / 'gpu_selfcheck_03692633'
LOCK = Path('/data2/_shared/gpu.lock')
PYTHON = ROOT / 'venv' / 'bin' / 'python'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
PROBE_REL = Path('scripts/multisession_probe.py')
G3_TPS = 31.7
G3_MIN_TPS, G3_MAX_TPS = G3_TPS * .8, G3_TPS * 1.2
LOG_TIME = re.compile(r'\[(\d{4}-\d\d-\d\d)\|(\d\d:\d\d:\d\d)\|')
BATCH_LINE = re.compile(r'\b(?:Prefill|Decode) batch\b')
STOP_STEPS = ((signal.SIGINT, 30), (signal.SIGTERM, 15), (getattr(signal, 'SIGKILL', 9), 10))
LOCK_TOKEN = None
LOCK_INODE = None
CLEANUP_FAILED = False


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output(argv, **kwargs) -> str:
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def write_exclusive(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')


def process_birth(pid: int) -> dict:
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rpartition(') ')[2].split()
    if len(fields) < 20 or int(fields[2]) != pid or int(fields[3]) != pid:
        raise RuntimeError('owned service birth/session cannot be verified')
    return {'pid': pid, 'starttime': int(fields[19]),
            'uid': (Path('/proc') / str(pid)).stat().st_uid,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def owned_group_members(pgid: int) -> set[int]:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return set()
    members = set()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / 'stat').read_text().rpartition(') ')[2].split()
        except FileNotFoundError:
            continue
        if len(fields) < 4:
            raise RuntimeError(f'malformed proc stat: {entry}')
        state, group, session = fields[0], int(fields[2]), int(fields[3])
        if group == pgid:
            if session != pgid:
                raise RuntimeError('owned process group escaped its session')
            if state != 'Z':
                members.add(int(entry.name))
    return members


def verified_group_members(pgid: int, birth: dict) -> set[int]:
    if (birth.get('pid') != pgid or type(birth.get('starttime')) is not int
            or birth.get('uid') != os.geteuid()
            or birth.get('boot_id') != Path('/proc/sys/kernel/random/boot_id').read_text().strip()):
        raise RuntimeError('saved owned service birth is invalid')
    members = owned_group_members(pgid)
    checked = set()
    for pid in members:
        path = Path('/proc') / str(pid)
        try:
            fields = (path / 'stat').read_text().rpartition(') ')[2].split()
            owner = path.stat().st_uid
        except FileNotFoundError:
            continue
        if (len(fields) < 20 or int(fields[2]) != pgid or int(fields[3]) != pgid
                or owner != birth['uid'] or int(fields[19]) < birth['starttime']):
            raise RuntimeError('owned child process identity cannot be verified')
        if pid == pgid and process_birth(pid) != birth:
            raise RuntimeError('owned service birth changed; refusing group signal')
        checked.add(pid)
    # A surviving private session retains the original PGID even after its
    # leader exits. Kernel ID ownership and the checked births bind its children.
    return checked


def environment(arm: Path) -> dict:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('FT_DEV_', 'FT_D3_')):
            env.pop(key)
    env.update({
        'PYTHONPATH': str(CANDIDATE / 'python'), 'PYTHONUNBUFFERED': '1',
        'VIRTUAL_ENV': str(ROOT / 'venv'), 'CUDA_VISIBLE_DEVICES': '0',
        'FT_DEV_PAUSE_ENDPOINT': '1', 'FT_DEV_D0': '1',
        'FT_DEV_D0_PATH': str(arm / 'd0'), 'FT_DEV_D0_TIMELINE': '1',
        'FT_DEV_D0_TIMELINE_STEPS': '20000',
    })
    env['PATH'] = '/usr/local/cuda-13.0/bin:' + str(ROOT / 'venv/bin') + ':' + env.get('PATH', '')
    env['LD_LIBRARY_PATH'] = '/usr/local/cuda-13.0/lib64:' + env.get('LD_LIBRARY_PATH', '')
    return env


def bootstrap(worktree: Path) -> str:
    root = str(worktree.resolve())
    return (
        'import pathlib,sys\n'
        f'root=pathlib.Path({root!r})\n'
        "sys.path[:0]=[str(root/'python'),str(root)]\n"
        "site=pathlib.Path(sys.executable).parents[1]/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'\n"
        'assert site.is_dir(),site\n'
        'sys.path.append(str(site))\n'
        'import freetoken\n'
        "assert freetoken.__file__ == str(root/'python/freetoken/__init__.py'),freetoken.__file__\n"
        'from freetoken.cli import main\nraise SystemExit(main(sys.argv[1:]))\n'
    )


def gate() -> dict:
    if LOCK.exists():
        raise RuntimeError('shared GPU lock already exists')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', 8095)) == 0:
            raise RuntimeError('port 8095 is occupied')
    used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    if not used or any(int(value) >= 1000 for value in used.splitlines()):
        raise RuntimeError(f'GPU is occupied: {used}')
    for worktree, commit in ((PARENT, PARENT_COMMIT), (CANDIDATE, CANDIDATE_COMMIT)):
        if output(['git', '-C', str(worktree), 'rev-parse', 'HEAD']) != commit:
            raise RuntimeError(f'wrong source commit: {worktree}')
        if output(['git', '-C', str(worktree), 'status', '--porcelain', '--untracked-files=no']):
            raise RuntimeError(f'tracked source is dirty: {worktree}')
    if output(['git', '-C', str(CANDIDATE), 'show', '-s', '--format=%P', 'HEAD']) != PARENT_COMMIT:
        raise RuntimeError('candidate direct parent differs from the declared D06 parent')
    env = environment(OUT / '_gate')
    proof = output([str(PYTHON), '-S', '-c', bootstrap(CANDIDATE), '--help'], cwd=CANDIDATE, env=env)
    if not proof:
        raise RuntimeError('candidate isolated import proof did not execute')
    probe = CANDIDATE / PROBE_REL
    if not probe.is_file():
        raise RuntimeError(f'candidate probe missing: {probe}')
    return {'parent_commit': PARENT_COMMIT, 'candidate_commit': CANDIDATE_COMMIT,
            'candidate_probe_sha256': sha256(probe)}


def validate_g3(data: dict) -> dict:
    if data.get('schema') != 'multisession_probe/v1' or data.get('command') != 'two-decode':
        raise ValueError('G3 probe schema/command mismatch')
    if data.get('same_prompt') is not True or len(data.get('reps', [])) != 1:
        raise ValueError('G3 requires exactly one same-prompt repetition')
    rows = data['reps'][0].get('per_way')
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError('G3 requires two per-way records')
    if rows[0].get('uid') == rows[1].get('uid'):
        raise ValueError('G3 requires two distinct request UIDs')
    if data['reps'][0].get('frontend_token_counts') != [32000, 32000]:
        raise ValueError('G3 lacks actual 32K frontend input proof')
    prompts = data['reps'][0].get('prompt_sha256')
    if not isinstance(prompts, list) or len(prompts) != 2 or prompts[0] != prompts[1]:
        raise ValueError('G3 same-prompt proof is absent or differs')
    checked = []
    for row in rows:
        value = row.get('decode_tps')
        if type(value) not in (int, float) or isinstance(value, bool) or not G3_MIN_TPS <= value <= G3_MAX_TPS:
            raise ValueError(f'G3 per-way decode_tps outside {G3_MIN_TPS:.2f}..{G3_MAX_TPS:.2f}: {value!r}')
        if row.get('completion_tokens') != 512 or type(row.get('uid')) is not int or row['uid'] < 0:
            raise ValueError('G3 per-way acknowledgement/length evidence invalid')
        sidecar = Path(row.get('token_timestamps', ''))
        evidence = json.loads(sidecar.read_text())
        events = evidence.get('token_events')
        if evidence.get('uid') != row['uid'] or not isinstance(events, list) or len(events) != 512:
            raise ValueError('G3 sidecar acknowledgement evidence is incomplete')
        previous_t = None
        for number, event in enumerate(events, 1):
            timestamp = event.get('t_s')
            if (event.get('uid') != row['uid'] or event.get('request_seq') != number
                    or event.get('completion_tokens_delta') != 1
                    or event.get('completion_tokens_cumulative') != number
                    or type(timestamp) not in (int, float) or isinstance(timestamp, bool)
                    or not math.isfinite(timestamp) or (previous_t is not None and timestamp <= previous_t)):
                raise ValueError('G3 sidecar acknowledgement sequence is invalid')
            previous_t = timestamp
        first, last = events[0]['t_s'], events[-1]['t_s']
        calculated = 511 / (last - first)
        if not math.isclose(float(row.get('t_first')), first, rel_tol=1e-9, abs_tol=1e-9) or not math.isclose(float(row.get('t_last')), last, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('G3 per-way timestamps disagree with ACK sidecar')
        if not math.isclose(float(value), calculated, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('G3 reported decode_tps disagrees with ACK timestamps')
        checked.append(calculated)
    return {'per_way_decode_tps': checked, 'bounds': [G3_MIN_TPS, G3_MAX_TPS]}


def parse_batch_lines(log: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(log.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if not BATCH_LINE.search(line):
            continue
        match = LOG_TIME.search(line)
        if not match:
            raise ValueError(f'G4 batch line lacks wall-clock timestamp at {number}')
        stamp = dt.datetime.strptime('|'.join(match.groups()), '%Y-%m-%d|%H:%M:%S').timestamp()
        rows.append({'line': number, 'wallclock_s': stamp, 'text': line})
    return rows


def stable_log_evidence(log: Path) -> dict:
    before = log.stat().st_size
    time.sleep(1.0)
    after = log.stat().st_size
    if before != after:
        raise RuntimeError('serve.log is still growing; asynchronous log flush is not proven')
    return {'path': str(log), 'size_samples': [before, after], 'stable_for_s': 1.0,
            'sha256': sha256(log)}


def validate_g4(data: dict, log: Path) -> dict:
    if data.get('schema') != 'multisession_probe/v1' or data.get('command') != 'h1':
        raise ValueError('G4 probe schema/command mismatch')
    rows = data.get('reps')
    if not isinstance(rows, list) or not rows:
        raise ValueError('G4 has no H1 repetitions')
    batches = parse_batch_lines(log)
    intervals = []
    for rep in rows:
        idle = rep.get('idle') if isinstance(rep, dict) else None
        event = idle.get('event') if isinstance(idle, dict) else None
        start, end = (event or {}).get('event_start_wallclock_s'), (event or {}).get('event_end_wallclock_s')
        if type(start) not in (int, float) or type(end) not in (int, float) or isinstance(start, bool) or isinstance(end, bool) or end <= start:
            raise ValueError('G4 idle interval lacks valid pause timestamps')
        pause = (event or {}).get('pause', {}).get('response')
        if not isinstance(pause, dict) or pause.get('pause_started_wallclock_s') != start or pause.get('deadline_wallclock_s') != end:
            raise ValueError('G4 pause acknowledgement does not bind the idle interval')
        evidence = idle.get('evidence') if isinstance(idle, dict) else None
        counters = (evidence or {}).get('event_counters')
        if not isinstance(counters, dict) or counters.get('steps') != []:
            raise ValueError('G4 H1 output lacks an empty UID-bound D0 idle counter window')
        base = (evidence or {}).get('d0_base')
        if not isinstance(base, str) or not base:
            raise ValueError('G4 H1 output lacks D0 evidence base')
        def rows(suffix):
            path = Path(base + suffix)
            if not path.is_file():
                raise ValueError(f'G4 D0 evidence is missing: {path}')
            return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        steps, timeline, prefill = rows('_decode_steps.jsonl'), rows('_decode_timeline.jsonl'), rows('_prefill.jsonl')
        timeline_by_step = {entry.get('step'): entry for entry in timeline}
        if len(timeline_by_step) != len(timeline):
            raise ValueError('G4 D0 timeline has duplicate steps')
        for step in steps:
            stamp = step.get('t')
            timeline_row = timeline_by_step.get(step.get('step'))
            if (type(stamp) not in (int, float) or isinstance(stamp, bool) or not math.isfinite(stamp)
                    or not isinstance(timeline_row, dict) or timeline_row.get('t') != stamp):
                raise ValueError('G4 D0 step/timeline timestamps are incomplete')
        active_steps = [step for step in steps if start <= step['t'] < end]
        active_prefill = [row for row in prefill if row.get('t_start') < end and row.get('t_end') > start]
        if active_steps or active_prefill:
            raise ValueError('G4 exact D0 evidence records scheduler work during idle')
        # Full log coverage remains mandatory.  Its timestamp is only second
        # precision, so boundary-second rows are decided by exact D0 evidence.
        overlap = [row for row in batches if start < row['wallclock_s'] < end]
        if overlap:
            raise ValueError(f'G4 idle interval contains scheduler batch lines: {overlap}')
        intervals.append({'start_wallclock_s': start, 'end_wallclock_s': end,
                          'd0_steps_checked': len(steps), 'd0_prefill_checked': len(prefill),
                          'log_timestamp_resolution_s': 1})
    return {'idle_intervals': intervals, 'batch_lines_checked': len(batches),
            'flush': stable_log_evidence(log)}


def stop(proc: subprocess.Popen, birth: dict) -> None:
    previous = {signum: signal.signal(signum, signal.SIG_IGN)
                for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        _stop(proc, birth)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _stop(proc: subprocess.Popen, birth: dict) -> None:
    global CLEANUP_FAILED
    CLEANUP_FAILED = True
    for sig, timeout in STOP_STEPS:
        members = verified_group_members(proc.pid, birth)
        if not members:
            break
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and verified_group_members(proc.pid, birth):
            time.sleep(.25)
    survivors = verified_group_members(proc.pid, birth)
    if survivors:
        raise RuntimeError(f'owned service group survived: {sorted(survivors)}')
    proc.wait(timeout=1)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            port_free = sock.connect_ex(('127.0.0.1', 8095)) != 0
        used = output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
        if port_free and used and all(int(value) < 1000 for value in used.splitlines()):
            CLEANUP_FAILED = False
            return
        time.sleep(2)
    raise RuntimeError('owned process stopped but port/GPU release was not proven')


def run() -> dict:
    global LOCK_TOKEN, LOCK_INODE, CLEANUP_FAILED
    proof = gate()
    OUT.mkdir(parents=True, exist_ok=False)
    token = json.dumps({'owner': 'dev_D06_G3_G4', 'pid': os.getpid(), 'since': time.time()})
    proc = None
    birth = None
    CLEANUP_FAILED = True
    try:
        with os.fdopen(os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), 'w') as lock:
            lock.write(token)
        LOCK_TOKEN, LOCK_INODE = token, LOCK.stat().st_ino
        arm = OUT / 'candidate'
        arm.mkdir()
        env = environment(arm)
        argv = [str(PYTHON), '-S', '-c', bootstrap(CANDIDATE), 'serve', '--model-path', str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
                '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', '8095', '--memory-ratio', '.88',
                '--moe-cache-auto', '--moe-prefill-hit-d2d', '--ple-backend', 'pinned', '--moe-strategy', 'offload',
                '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2', '--cuda-graph-max-bs', '2',
                '--kv-reserve-tokens', '73728', '--max-seq-len-override', '73728', '--max-prefill-length', '4096',
                '--enable-cache-report', '--enable-special-token-ckpt', '--tool-call-parser', 'qwen3_coder', '--reasoning-parser', 'qwen3', '--prefill-layer-major']
        selected = ('PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH', 'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES',
                    'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_D0', 'FT_DEV_D0_PATH', 'FT_DEV_D0_TIMELINE', 'FT_DEV_D0_TIMELINE_STEPS')
        (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(key + '=' + shlex.quote(env[key]) for key in selected)
                                            + ' ' + shlex.join(argv) + '\n')
        (arm / 'ENV.txt').write_text(json.dumps({'parent_commit': PARENT_COMMIT, 'candidate_commit': CANDIDATE_COMMIT,
                                                  'candidate_probe_sha256': proof['candidate_probe_sha256'],
                                                  'environment': {key: env[key] for key in selected}}, indent=2) + '\n')
        with (arm / 'serve.log').open('x') as log:
            proc = subprocess.Popen(argv, cwd=CANDIDATE, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            if os.getpgid(proc.pid) != proc.pid or os.getsid(proc.pid) != proc.pid:
                raise RuntimeError('service did not receive a private PGID/session')
            birth = process_birth(proc.pid)
            write_exclusive(arm / 'owned_process.json', {'pid': proc.pid, 'pgid': proc.pid, 'session': proc.pid, 'birth': birth})
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('owned service exited during startup')
                try:
                    with __import__('urllib.request').request.urlopen('http://127.0.0.1:8095/health', timeout=3) as response:
                        if json.load(response).get('status') == 'ok':
                            break
                except OSError:
                    time.sleep(2)
            else:
                raise TimeoutError('service readiness exceeded 600 seconds')
            g3_path, g4_path = arm / 'g3.json', arm / 'g4.json'
            subprocess.run([str(PYTHON), str(CANDIDATE / PROBE_REL), 'two-decode', '--ctx', '32000', '--max-tokens', '512', '--same-prompt', '1', '--reps', '1', '--out', str(g3_path)], cwd=CANDIDATE, env=env, check=True, timeout=1800)
            g3 = validate_g3(json.loads(g3_path.read_text()))
            subprocess.run([str(PYTHON), str(CANDIDATE / PROBE_REL), 'h1', '--H', '1,8,32', '--reps', '1', '--prefill-target', '32000', '--out', str(g4_path)], cwd=CANDIDATE, env=env, check=True, timeout=1800)
        # The whole owned group must exit before its complete log is accepted.
        stop(proc, birth)
        proc = None
        g4 = validate_g4(json.loads(g4_path.read_text()), arm / 'serve.log')
        g4['log_finalized_after_owned_group_exit'] = True
        result = {'mode': 'development_selfcheck_not_T05_or_T16', **proof, 'g3': g3, 'g4': g4}
        write_exclusive(OUT / 'result.json', result)
        return result
    except BaseException as exc:
        if OUT.exists() and not (OUT / 'error.json').exists():
            write_exclusive(OUT / 'error.json', {'error': repr(exc), **proof})
        raise
    finally:
        if proc is not None and birth is not None:
            stop(proc, birth)
        if not CLEANUP_FAILED and LOCK.exists() and LOCK_TOKEN == token and LOCK.stat().st_ino == LOCK_INODE and LOCK.read_text() == token:
            LOCK.unlink()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sidecars = []
        for index in range(2):
            sidecar = root / f'way{index}.json'
            events = [{'uid': index, 'request_seq': number, 'completion_tokens_delta': 1,
                       'completion_tokens_cumulative': number, 't_s': number / 31.7}
                      for number in range(1, 513)]
            write_exclusive(sidecar, {'uid': index, 'token_events': events})
            sidecars.append(sidecar)
        data = {'schema': 'multisession_probe/v1', 'command': 'two-decode', 'same_prompt': True,
                'reps': [{'per_way': [{'uid': index, 'decode_tps': 31.7, 'completion_tokens': 512,
                                        't_first': 1 / 31.7, 't_last': 512 / 31.7,
                                        'token_timestamps': str(sidecar)} for index, sidecar in enumerate(sidecars)],
                          'frontend_token_counts': [32000, 32000], 'prompt_sha256': ['same', 'same']}]}
        assert all(math.isclose(value, 31.7) for value in validate_g3(data)['per_way_decode_tps'])
        log = root / 'serve.log'
        log.write_text('[2026-10-04|12:00:00|core] Prefill batch\n')
        start, end = dt.datetime(2026, 10, 4, 12, 0, 1).timestamp(), dt.datetime(2026, 10, 4, 12, 0, 2).timestamp()
        base = root / 'd0'
        for suffix, value in (('_decode_steps.jsonl', {'step': 1, 't': start - 1}),
                              ('_decode_timeline.jsonl', {'step': 1, 't': start - 1}),
                              ('_prefill.jsonl', {'t_start': start - 2, 't_end': start - 1})):
            (root / (base.name + suffix)).write_text(json.dumps(value) + '\n')
        h1 = {'schema': 'multisession_probe/v1', 'command': 'h1', 'reps': [{'idle': {
            'event': {'event_start_wallclock_s': start, 'event_end_wallclock_s': end,
                      'pause': {'response': {'pause_started_wallclock_s': start, 'deadline_wallclock_s': end}}},
            'evidence': {'d0_base': str(base), 'event_counters': {'steps': []}},
        }}]}
        assert validate_g4(h1, log)['batch_lines_checked'] == 1
    print('SELFTEST PASS: strict G3 TPS/ACK and G4 real-idle log checks')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.run or sys.platform != 'linux':
        parser.error('--run on the Linux GPU host is required')
    interrupt_seen = False
    def interrupted(signum, _frame):
        nonlocal interrupt_seen
        if interrupt_seen:
            return
        interrupt_seen = True
        raise InterruptedError('selfcheck interrupted by signal ' + str(signum))
    previous = {signum: signal.signal(signum, interrupted)
                for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        run()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
