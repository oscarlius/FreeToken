"""Bind R040a anchor requests while reusing the exact historical timing probe.

This component cannot allocate a batch or start a model. Its caller must own
the admitted R040a service. Request files are written after each timed probe.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.request

PROBE_SHA = 'a67471a9d123c0c183f34d65066b86a35ce80e0832bc02f4ecfccc09b8c0a0c0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write('\n')


def bind_seed(source, destination, expected_sha256):
    """Copy only the business input into the new round, never failed raw data."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file() or destination.exists():
        raise ValueError('anchor input must be a regular source and new destination')
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('anchor input SHA differs from startup review')
    # The historical probe intentionally decodes with errors="replace".
    if not data.decode('utf-8', errors='replace'):
        raise ValueError('anchor input is empty')
    with destination.open('xb') as stream:
        stream.write(data)
    destination.chmod(0o444)
    return {'source_path': str(source), 'path': str(destination),
            'sha256': expected_sha256, 'bytes': len(data)}


def run_bound_probe(*, probe_path, seed_path, seed_sha256, arm, checkpoint,
                    service_pid, service_start_ticks, port, opener=None, sleep=None):
    """Run the pinned five repetitions and bind all ten exact wire payloads.

    Capturing Request.data happens before the historical probe starts its
    clock. Hashing/writing happens after first_real returns. The probe itself
    retains its original first-content stopping condition and timing logic.
    """
    probe_path, seed_path, arm = map(Path, (probe_path, seed_path, arm))
    if (type(checkpoint) is not bool or type(service_pid) is not int
            or service_pid <= 0 or type(service_start_ticks) is not int or service_start_ticks <= 0
            or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError('anchor process/config identity differs')
    if probe_path.is_symlink() or sha(probe_path) != PROBE_SHA:
        raise ValueError('historical anchor probe SHA differs')
    if (seed_path.is_symlink() or seed_path.stat().st_mode & 0o222
            or sha(seed_path) != seed_sha256):
        raise ValueError('bound anchor input differs or is writable')
    if not arm.is_dir() or any((arm/name).exists() for name in ('tax.json', 'request_binding.json', 'requests')):
        raise ValueError('anchor output must be a new service arm')
    spec = importlib.util.spec_from_file_location('r040a_historical_tax', probe_path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    probe.URL = f'http://127.0.0.1:{port}/v1/chat/completions'
    probe.SEED = str(seed_path)
    requests = arm/'requests'
    requests.mkdir()
    pending, records = [], []
    real_request = urllib.request.Request

    def request(*args, **kwargs):
        value = real_request(*args, **kwargs)
        if value.full_url != probe.URL or not isinstance(value.data, bytes):
            raise ValueError('anchor actual wire request differs')
        pending.append(value.data)
        return value

    probe.urllib = SimpleNamespace(request=SimpleNamespace(
        Request=request, urlopen=opener or urllib.request.urlopen))
    if sleep is not None:
        probe.time = SimpleNamespace(perf_counter=probe.time.perf_counter, sleep=sleep)
    original = probe.first_real

    def measured(payload):
        if pending:
            raise ValueError('unexpected unbound anchor request')
        ttft = original(payload)
        if len(pending) != 1 or not isinstance(ttft, (int, float)) or not math.isfinite(ttft) or ttft <= 0:
            raise ValueError('anchor requires one request and finite first-content timing')
        data = pending.pop()
        index = len(records)
        path = requests/f'{index:02d}.json'
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(0o444)
        records.append({'index': index, 'rep': index//2,
                        'shape': 'single' if index % 2 == 0 else 'multi',
                        'cell': 'cold' if index//2 == 0 else 'warm',
                        'path': path.relative_to(arm).as_posix(),
                        'sha256': hashlib.sha256(data).hexdigest(), 'ttft_s': ttft})
        return ttft

    probe.first_real = measured
    old_argv = sys.argv
    try:
        sys.argv = [str(probe_path), str(arm/'tax.json'), arm.name]
        probe.main()
    finally:
        sys.argv = old_argv
    if len(records) != 10 or pending:
        raise ValueError('anchor requires one cold plus four warm requests per shape')
    for shape in ('single', 'multi'):
        if len({x['sha256'] for x in records if x['shape'] == shape}) != 1:
            raise ValueError('anchor warm/cold input payload differs')
    result = {'schema': 'ft_r040a_anchor_request_binding/v1', 'arm': arm.name,
              'checkpoint': checkpoint, 'service_pid': service_pid,
              'service_start_ticks': service_start_ticks,
              'seed_sha256': seed_sha256, 'probe_sha256': PROBE_SHA,
              'tax_sha256': sha(arm/'tax.json'), 'requests': records,
              'cold_per_shape': 1, 'warm_per_shape': 4,
              'cache_hit_proved': False, 'model_admitted': False}
    write_new(arm/'request_binding.json', result)
    return result


# The service scope below reproduces the actual T20 production_service.
# R040a changes only its round identity and source check (one pinned probe,
# avoiding unrelated completed T20 inputs). Production settings stay identical.
from contextlib import contextmanager
import os
import shlex
import subprocess

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
LOCK = Path('/data2/_shared/gpu.lock')
FT = str(ROOT/'venv/bin/ft')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'


def command(argv):
    return subprocess.check_output(argv, text=True).strip()


def process_birth(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rpartition(') ')[2].split()
    ticks = int(fields[19])
    if ticks <= 0 or fields[0] == 'Z':
        raise ValueError('anchor service has no live process birth')
    return pid, ticks


@contextmanager
def production_service(runner, name, *, candidate_commit, probe_path, checkpoint=True):
    """Service scope used after the full batch's formal admission and lock take.

    Reuses the common Runner's preflight/readiness/owned cleanup. This is not an
    admission function: the outer batch must verify the accepted T17/T16 proofs.
    """
    if (runner.options.rid != 'E2-R040a' or runner.options.gate != 'T20'
            or not runner.options.run or runner.directory != ROUNDS / 'E2-R040a'
            or runner.proc is not None):
        raise ValueError('T20 service requires its actual running batch scope')
    if (not runner.token or not LOCK.exists()
            or LOCK.read_text() != runner.token or LOCK.stat().st_ino != runner.lock_inode):
        raise RuntimeError('T20 service requires the enclosing batch owned GPU lock')
    lock = json.loads(runner.token)
    if lock.get('owner') != 'E2-R040a' or lock.get('pid') != os.getpid() or lock.get('card') != 'T20':
        raise RuntimeError('T20 lock identity differs from the actual caller')
    if type(checkpoint) is not bool or len(candidate_commit) != 40:
        raise ValueError('full candidate commit and boolean checkpoint setting required')
    wt = ROOT / 'wt/e2base1-ordinary-rewind'
    source = runner.gate(wt, candidate_commit)
    tag = command(['git', '-C', str(wt), 'describe', '--tags', '--exact-match'])
    if tag != 'E2-base.1@' + candidate_commit[:8]:
        raise ValueError('T20 requires the exact admitted candidate tag')
    gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    if not gpu or any(int(value) > 100 for value in gpu.splitlines()):
        raise RuntimeError('T20 requires all GPUs <=100 MiB before each service')
    if sha(probe_path) != PROBE_SHA:
        raise ValueError('historical anchor probe SHA differs')
    arm = runner.directory / name
    if arm.parent != runner.directory or arm.name in ('', '.', '..'):
        raise ValueError('T20 arm must be a direct child of its round')
    arm.mkdir(exist_ok=False)
    env = runner.environment(wt, arm, False)
    for key in list(env):
        if key.startswith(('FT_T17_', 'FT_D16_', 'FT_DEV_', 'FT_D3_', 'FT_D0_')):
            env.pop(key)
    env['CUDA_VISIBLE_DEVICES'] = '0'
    argv = ['taskset', '-c', '1,3-47', FT, 'serve', '--model-path',
            str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
            '--served-model-name', MODEL, '--host', '0.0.0.0', '--port', '8095',
            '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d',
            '--ple-backend', 'pinned', '--moe-strategy', 'offload',
            '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2',
            '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '73728',
            '--max-seq-len-override', '73728', '--max-prefill-length', '4096',
            '--enable-cache-report', '--tool-call-parser', 'qwen3_coder',
            '--reasoning-parser', 'qwen3', '--prefill-layer-major']
    if checkpoint:
        argv.append('--enable-special-token-ckpt')
    selected = ('PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH',
                'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES')
    (arm / 'SERVE_CMD.txt').write_text('env ' + ' '.join(
        key + '=' + shlex.quote(env[key]) for key in selected) + ' ' + shlex.join(argv) + '\n')
    write_new(arm / 'source.json', {'commit': candidate_commit, 'code_version': tag,
                                  'import': source, 'checkpoint': checkpoint})
    write_new(arm / 'compiled_extensions.json', runner.compiled_extensions(wt))
    with (arm / 'serve.log').open('x') as log:
        runner.proc = subprocess.Popen(argv, env=env, cwd=wt, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        try:
            runner.set_status(state='loading', arm=name, service_pid=runner.proc.pid)
            if os.getpgid(runner.proc.pid) != runner.proc.pid or os.getsid(runner.proc.pid) != runner.proc.pid:
                raise RuntimeError('T20 service process-group ownership differs')
            runner.ready(arm)
            parsed = runner.parser(str(arm / 'serve.log'))
            expected = {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
                        'special_token_ckpt': str(checkpoint), 'max_seq_len_override': '73728',
                        'kv_reserve_tokens': '73728', 'max_running_req': '2',
                        'cuda_graph_max_bs': '2', 'memory_ratio': '0.88',
                        'moe_cache_auto': 'True', 'moe_prefill_hit_d2d': 'True',
                        'moe_strategy': repr('offload'), 'ple_backend': repr('pinned'),
                        'quant_backend': repr('moe.nvfp4=triton'),
                        '_unique_suffix': repr('.pid=' + str(runner.proc.pid))}
            for key, value in expected.items():
                if parsed.get(key) != value:
                    raise ValueError(f'T20 production argument differs: {key}')
            affinity = sorted(os.sched_getaffinity(runner.proc.pid))
            if set(affinity) != {1, *range(3, 48)}:
                raise ValueError('T20 production CPU affinity differs')
            write_new(arm / 'args_preprobe_checked.json', expected)
            write_new(arm / 'affinity.json', {'actual': affinity})
            runner.set_status(state='probing', arm=name, service_pid=runner.proc.pid)
            yield arm, env, wt
            if runner.proc.poll() is not None:
                raise RuntimeError('T20 service exited before live verification')
            if list(arm.glob('d0*')) or any(token in (arm / 'serve.log').read_text() for token in
                    ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                raise RuntimeError('T20 production D0 diagnostic leakage')
        finally:
            runner.stop()


def collect_anchor_four_cell(owner, review, *, service_scope=production_service):
    """Six distinct production processes; one cold/four warm per message shape."""
    if (owner.options.rid != 'E2-R040a' or owner.options.gate != 'T20'
            or owner.options.run is not True):
        raise ValueError('anchor requires the admitted R040a owner')
    cfg = review['anchor_four_cell']
    if cfg.get('state') != 'queued_bound_supplement':
        raise ValueError('anchor bound supplement is not admitted by source review')
    probe = Path(cfg['probe_path'])
    if cfg.get('probe_sha256') != PROBE_SHA or sha(probe) != PROBE_SHA:
        raise ValueError('anchor source review probe differs')
    binding = cfg['input_binding']
    seed = owner.directory/'anchor_seed.txt'
    bound = bind_seed(Path(binding['path']), seed, binding['sha256'])
    write_new(owner.directory/'anchor_seed_binding.json', bound)
    results = []
    births = set()
    for rep in range(1, 4):
        for checkpoint, prefix in ((False, 'OFF'), (True, 'ON')):
            name = f'{prefix}_p{rep}'
            with service_scope(owner, name, candidate_commit=review['candidate_commit'],
                               probe_path=probe, checkpoint=checkpoint) as (arm, env, wt):
                pid = owner.proc.pid
                birth = process_birth(pid)
                if birth in births:
                    raise ValueError('anchor requires six independent process births')
                births.add(birth)
                result = run_bound_probe(probe_path=probe, seed_path=seed,
                          seed_sha256=bound['sha256'], arm=arm, checkpoint=checkpoint,
                          service_pid=pid, service_start_ticks=birth[1], port=8095)
                if process_birth(pid) != birth:
                    raise ValueError('anchor service birth changed during probe')
                results.append(result)
    result = {'schema':'ft_r040a_anchor_four_cell_measurements/v1',
              'seed_binding':bound, 'arms':results, 'independent_processes':len(births),
              'cold_per_checkpoint_per_shape':3, 'warm_per_process_per_shape':4,
              'state':'measured_pending_independent_raw_review', 'model_admitted':False}
    write_new(owner.directory/'anchor_four_cell.json', result)
    return result
