"""R040a anchor supplement on the admitted owner's private endpoint.

Formal and CPU file-only collection use the same service and request writers.
The CPU branch stops before Popen and labels every result as a file probe.
The frozen historical probe supplies all payloads and all formal timing logic.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

PROBE_SHA = 'a67471a9d123c0c183f34d65066b86a35ce80e0832bc02f4ecfccc09b8c0a0c0'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
LOCK = Path('/data2/_shared/gpu.lock')
FT = str(ROOT / 'venv/bin/ft')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
SAFE_ENV = ('PYTHONPATH', 'PYTHONUNBUFFERED', 'VIRTUAL_ENV', 'PATH',
            'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write('\n')


def _cpu_probe(**values):
    return {'schema': 'ft_r040a_cpu_file_probe/v1', 'kind': 'CPU_FILE_PROBE',
            'not_measurement': True, **values}


def _private_port(port):
    if type(port) is not int or not 1024 <= port <= 65535 or port == 8095:
        raise ValueError('anchor requires the owner private port; 8095 is forbidden')
    return port


def _writable_directory(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError('anchor output must be a regular directory')
    path.chmod(stat.S_IMODE(path.stat().st_mode) | 0o700)


def bind_seed(source, destination, expected_sha256):
    """Copy only the SHA-bound business input, never previous raw results."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file() or destination.exists() or destination.is_symlink():
        raise ValueError('anchor input must be a regular source and new destination')
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('anchor input SHA differs from startup review')
    if not data.decode('utf-8', errors='replace'):
        raise ValueError('anchor input is empty')
    with destination.open('xb') as stream:
        stream.write(data)
    destination.chmod(0o444)
    return {'source_path': str(source), 'path': str(destination),
            'sha256': expected_sha256, 'bytes': len(data)}


def _request_record(arm, records, data, *, ttft=None):
    index = len(records)
    path = arm / 'requests' / f'{index:02d}.json'
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(0o444)
    record = {'index': index, 'rep': index // 2,
              'shape': 'single' if index % 2 == 0 else 'multi',
              'cell': 'cold' if index // 2 == 0 else 'warm',
              'path': path.relative_to(arm).as_posix(),
              'sha256': hashlib.sha256(data).hexdigest()}
    if ttft is not None:
        record['ttft_s'] = ttft
    records.append(record)


def _historical_payloads(probe, probe_path):
    """Evaluate the pinned main's input construction, without its timed loop."""
    tree = ast.parse(Path(probe_path).read_text(encoding='utf-8'))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    prefix = []
    for node in main.body:
        if isinstance(node, ast.For):
            break
        prefix.append(node)
    else:
        raise ValueError('historical anchor repetition loop is missing')
    prefix.append(ast.Return(value=ast.Tuple(elts=[ast.Name(id='single', ctx=ast.Load()),
                                                   ast.Name(id='multi', ctx=ast.Load())], ctx=ast.Load())))
    main.name = '_r040a_file_payloads'
    main.body = prefix
    module = ast.fix_missing_locations(ast.Module(body=[main], type_ignores=[]))
    namespace = dict(probe.__dict__)
    exec(compile(module, str(probe_path), 'exec'), namespace)
    old_argv = sys.argv
    try:
        sys.argv = [str(probe_path), 'CPU_FILE_PROBE', 'CPU_FILE_PROBE']
        return namespace[main.name]()
    finally:
        sys.argv = old_argv


def run_bound_probe(*, probe_path, seed_path, seed_sha256, arm, checkpoint,
                    port, service_pid=None, service_start_ticks=None,
                    opener=None, sleep=None, file_dry_run=False):
    """Bind ten historical wire payloads; preserve formal first-content timing."""
    probe_path, seed_path, arm = map(Path, (probe_path, seed_path, arm))
    _private_port(port)
    if type(checkpoint) is not bool or type(file_dry_run) is not bool:
        raise ValueError('anchor configuration identity differs')
    if file_dry_run:
        if service_pid is not None or service_start_ticks is not None:
            raise ValueError('CPU file probe cannot claim a service process')
    elif (type(service_pid) is not int or service_pid <= 0
          or type(service_start_ticks) is not int or service_start_ticks <= 0):
        raise ValueError('anchor process identity differs')
    if probe_path.is_symlink() or not probe_path.is_file() or sha(probe_path) != PROBE_SHA:
        raise ValueError('historical anchor probe SHA differs')
    if (seed_path.is_symlink() or not seed_path.is_file() or seed_path.stat().st_mode & 0o222
            or sha(seed_path) != seed_sha256):
        raise ValueError('bound anchor input differs or is writable')
    if not arm.is_dir() or any((arm / name).exists() for name in ('tax.json', 'request_binding.json', 'requests')):
        raise ValueError('anchor output must be a new service arm')
    spec = importlib.util.spec_from_file_location('r040a_historical_tax', probe_path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    if probe.REPS != 5:
        raise ValueError('historical anchor requires five request pairs')
    probe.URL = f'http://127.0.0.1:{port}/v1/chat/completions'
    probe.SEED = str(seed_path)
    _writable_directory(arm)
    requests = arm / 'requests'
    requests.mkdir()
    _writable_directory(requests)
    pending, records = [], []
    if file_dry_run:
        single, multi = _historical_payloads(probe, probe_path)
        for _ in range(probe.REPS):
            for payload in (single, multi):
                _request_record(arm, records, json.dumps(payload, ensure_ascii=False).encode())
        write_new(arm / 'tax.json', _cpu_probe(arm=arm.name, planned_reps=probe.REPS,
                                            planned_endpoint=probe.URL, requests_sent=False))
    else:
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
            if (len(pending) != 1 or not isinstance(ttft, (int, float))
                    or not math.isfinite(ttft) or ttft <= 0):
                raise ValueError('anchor requires one request and finite first-content timing')
            _request_record(arm, records, pending.pop(), ttft=ttft)
            return ttft

        probe.first_real = measured
        old_argv = sys.argv
        try:
            sys.argv = [str(probe_path), str(arm / 'tax.json'), arm.name]
            probe.main()
        finally:
            sys.argv = old_argv
    if len(records) != 10 or pending:
        raise ValueError('anchor requires one cold plus four warm requests per shape')
    for shape in ('single', 'multi'):
        if len({record['sha256'] for record in records if record['shape'] == shape}) != 1:
            raise ValueError('anchor warm/cold input payload differs')
    result = {'schema': 'ft_r040a_anchor_request_binding/v2', 'arm': arm.name,
              'checkpoint': checkpoint, 'port': port, 'endpoint': probe.URL,
              'seed_sha256': seed_sha256, 'probe_sha256': PROBE_SHA,
              'tax_sha256': sha(arm / 'tax.json'), 'requests': records,
              'cold_per_shape': 1, 'warm_per_shape': 4,
              'cache_hit_proved': False, 'model_admitted': False}
    if file_dry_run:
        result.update(kind='CPU_FILE_PROBE', not_measurement=True,
                      requests_sent=False, service_started=False)
    else:
        result.update(service_pid=service_pid, service_start_ticks=service_start_ticks)
    write_new(arm / 'request_binding.json', result)
    return result


def command(argv):
    return subprocess.check_output(argv, text=True).strip()


def _owner_scope(owner, file_dry_run):
    if (owner.options.rid != 'E2-R040a' or owner.options.gate != 'T20'
            or owner.options.run is not True or owner.proc is not None):
        raise ValueError('anchor requires its actual running batch scope')
    directory = Path(owner.directory)
    formal = ROUNDS / 'E2-R040a'
    if file_dry_run:
        if (directory.parent != ROUNDS or not directory.name.startswith('.dryrun_R040a_')
                or directory == formal or getattr(owner, 'token', None)
                or getattr(owner, 'lock_inode', None) is not None):
            raise ValueError('CPU file probe requires an unlocked sibling .dryrun_R040a_* directory')
        if LOCK.is_symlink():
            raise RuntimeError('foreign GPU lock is symlinked')
        if LOCK.exists():
            proof = getattr(owner, '_r040a_file_probe_foreign_lock', None)
            if (not isinstance(proof, dict) or proof.get('state') != 'held'
                    or LOCK.stat().st_ino != proof.get('inode')
                    or LOCK.read_bytes() != proof.get('raw')):
                raise RuntimeError('foreign GPU lock lacks unchanged file-probe binding')
    elif directory != formal:
        raise ValueError('anchor requires its actual running batch scope')
    if any(path.is_symlink() for path in (directory, *directory.parents)):
        raise ValueError('anchor output cannot traverse a symlink')
    _private_port(owner.port)
    _writable_directory(directory)


def _owned_lock(owner):
    if (not owner.token or LOCK.is_symlink() or not LOCK.is_file()
            or LOCK.read_text(encoding='utf-8') != owner.token
            or LOCK.stat().st_ino != owner.lock_inode):
        raise RuntimeError('anchor requires the enclosing batch owned GPU lock')
    if hasattr(owner, 'lock_device') and LOCK.stat().st_dev != owner.lock_device:
        raise RuntimeError('anchor GPU lock device differs')
    token = json.loads(owner.token)
    lifecycle = owner._r040a_private_lifecycle
    birth = lifecycle.process_identity(os.getpid())
    if (not isinstance(birth, dict) or type(token.get('batch')) is not int
            or token.get('batch') != owner.options.batch
            or token.get('owner') != 'E2-R040a' or token.get('pid') != os.getpid()
            or type(token.get('start_ticks')) is not int or token['start_ticks'] <= 0
            or token.get('execution_id') != f"{token['pid']}:{token['start_ticks']}"
            or any(token.get(key) != birth.get(key) for key in ('pid', 'start_ticks', 'execution_id'))):
        raise RuntimeError('anchor D07 lock identity differs from the actual caller')


def _service_birth(owner, pid):
    birth = owner._r040a_private_lifecycle.process_identity(pid)
    if (not isinstance(birth, dict) or birth.get('pid') != pid
            or type(birth.get('start_ticks')) is not int or birth['start_ticks'] <= 0
            or birth.get('pgid') != pid or birth.get('session') != pid
            or birth.get('execution_id') != f"{pid}:{birth['start_ticks']}" or birth.get('state') == 'Z'):
        raise RuntimeError('anchor service lacks an owned process birth/group/session')
    return birth


def _same_birth(left, right):
    return isinstance(right, dict) and all(left.get(key) == right.get(key)
        for key in ('pid', 'start_ticks', 'execution_id', 'pgid', 'session'))


def _stop_owned_service(owner):
    if owner.proc is None:
        return
    proc = owner.proc
    try:
        birth = getattr(owner, 'service_birth', None)
        if not isinstance(birth, dict):
            raise RuntimeError('anchor service birth unknown; preserve enclosing lock')
        current = owner._r040a_private_lifecycle.process_identity(proc.pid)
        if current is not None and any(current.get(key) != birth.get(key)
                                       for key in ('pid', 'start_ticks', 'execution_id', 'pgid', 'session')):
            raise RuntimeError('anchor service birth changed; preserve enclosing lock')
        owner.stop()
        if owner.proc is not None or owner._r040a_private_lifecycle.owned_group_alive(proc.pid):
            raise RuntimeError('anchor owned process group remains; preserve enclosing lock')
    except BaseException as error:
        error.owned_cleanup_failed = True
        error.owned_process = proc
        raise


@contextmanager
def production_service(owner, name, *, candidate_commit, probe_path, checkpoint=True,
                       file_dry_run=None):
    """Retain T20 production settings; vary only endpoint and owned lifecycle."""
    if file_dry_run is None:
        file_dry_run = getattr(owner, '_r040a_file_dry_run', False)
    if type(file_dry_run) is not bool or file_dry_run != getattr(owner, '_r040a_file_dry_run', False):
        raise ValueError('anchor file probe mode differs from its owner')
    _owner_scope(owner, file_dry_run)
    if not file_dry_run:
        _owned_lock(owner)
    if type(checkpoint) is not bool or candidate_commit != CANDIDATE:
        raise ValueError('full candidate commit and boolean checkpoint setting required')
    wt = ROOT / 'wt/e2base1-ordinary-rewind'
    source = owner.gate(wt, candidate_commit)
    tag = 'E2-base.1@' + candidate_commit[:8]
    if command(['git', '-C', str(wt), 'describe', '--tags', '--exact-match']) != tag:
        raise ValueError('anchor requires the exact admitted candidate tag')
    gpu = command(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    if not gpu or any(int(value) > 100 for value in gpu.splitlines()):
        raise RuntimeError('anchor requires all GPUs <=100 MiB before each service')
    if Path(probe_path).is_symlink() or sha(probe_path) != PROBE_SHA:
        raise ValueError('historical anchor probe SHA differs')
    arm = Path(owner.directory) / name
    if arm.parent != Path(owner.directory) or arm.name != name or name in ('', '.', '..'):
        raise ValueError('anchor arm must be a direct child of its round')
    arm.mkdir(exist_ok=False)
    _writable_directory(arm)
    env = owner.environment(wt, arm, False)
    for key in list(env):
        if key.startswith(('FT_T17_', 'FT_D16_', 'FT_DEV_', 'FT_D3_', 'FT_D0_')):
            env.pop(key)
    env['CUDA_VISIBLE_DEVICES'] = '0'
    argv = ['taskset', '-c', '1,3-47', FT, 'serve', '--model-path',
            str(ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'),
            '--served-model-name', MODEL, '--host', '127.0.0.1', '--port', str(owner.port),
            '--memory-ratio', '0.88', '--moe-cache-auto', '--moe-prefill-hit-d2d',
            '--ple-backend', 'pinned', '--moe-strategy', 'offload',
            '--quant-backend', 'moe.nvfp4=triton', '--max-running-requests', '2',
            '--cuda-graph-max-bs', '2', '--kv-reserve-tokens', '98304',
            '--max-seq-len-override', '98304', '--max-prefill-length', '4096',
            '--enable-cache-report', '--tool-call-parser', 'qwen3_coder',
            '--reasoning-parser', 'qwen3', '--prefill-layer-major']
    if checkpoint:
        argv.append('--enable-special-token-ckpt')
    declared = {key: env[key] for key in SAFE_ENV}
    env_text = ' '.join(key + '=' + shlex.quote(value) for key, value in declared.items())
    with (arm / 'SERVE_CMD.txt').open('x', encoding='utf-8') as stream:
        stream.write('env ' + env_text + ' ' + shlex.join(argv) + '\n')
    with (arm / 'ENV.txt').open('x', encoding='utf-8') as stream:
        stream.write(env_text + '\n')
    write_new(arm / 'environment.json', declared)
    write_new(arm / 'source.json', {'commit': candidate_commit, 'code_version': tag,
                                  'import': source, 'checkpoint': checkpoint})
    write_new(arm / 'compiled_extensions.json', owner.compiled_extensions(wt))
    expected = {'prefill_layer_major': 'True', 'max_extend_tokens': '4096',
                'special_token_ckpt': str(checkpoint), 'max_seq_len_override': '98304',
                'kv_reserve_tokens': '98304', 'max_running_req': '2',
                'cuda_graph_max_bs': '2', 'memory_ratio': '0.88',
                'moe_cache_auto': 'True', 'moe_prefill_hit_d2d': 'True',
                'moe_strategy': repr('offload'), 'ple_backend': repr('pinned'),
                'quant_backend': repr('moe.nvfp4=triton'), 'server_port': str(owner.port)}
    with (arm / 'serve.log').open('x', encoding='utf-8') as log:
        if file_dry_run:
            write_new(arm / 'args_preprobe_checked.json', _cpu_probe(planned_args=expected))
            write_new(arm / 'affinity.json', _cpu_probe(planned_affinity=[1, *range(3, 48)]))
            write_new(arm / 'owned_process.json', _cpu_probe(service_started=False, planned_port=owner.port))
            yield arm, env, wt
            return
        owner.service_birth = None
        owner.proc = subprocess.Popen(argv, env=env, cwd=wt, stdout=log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
        try:
            owner.service_birth = _service_birth(owner, owner.proc.pid)
            write_new(arm / 'owned_process.json', {'pid': owner.proc.pid, 'port': owner.port,
                                                  'birth': owner.service_birth})
            owner.set_status(state='loading', arm=name, service_pid=owner.proc.pid)
            owner.ready(arm)
            parsed = owner.parser(str(arm / 'serve.log'))
            expected['_unique_suffix'] = repr('.pid=' + str(owner.proc.pid))
            for key, value in expected.items():
                if parsed.get(key) != value:
                    raise ValueError(f'anchor production argument differs: {key}')
            affinity = sorted(os.sched_getaffinity(owner.proc.pid))
            if set(affinity) != {1, *range(3, 48)}:
                raise ValueError('anchor production CPU affinity differs')
            write_new(arm / 'args_preprobe_checked.json', expected)
            write_new(arm / 'affinity.json', {'actual': affinity})
            owner.set_status(state='probing', arm=name, service_pid=owner.proc.pid)
            yield arm, env, wt
            if owner.proc.poll() is not None:
                raise RuntimeError('anchor service exited before live verification')
            if list(arm.glob('d0*')) or any(token in (arm / 'serve.log').read_text() for token in
                    ('GDN bank:', 'D0 seg:', 'D0 prefill', 'D0 instrumentation enabled')):
                raise RuntimeError('anchor production D0 diagnostic leakage')
        finally:
            _stop_owned_service(owner)


def collect_anchor_four_cell(owner, review, *, service_scope=production_service, file_dry_run=None):
    """Six OFF/ON service scopes; one cold/four warm requests per shape."""
    if file_dry_run is None:
        file_dry_run = getattr(owner, '_r040a_file_dry_run', False)
    if type(file_dry_run) is not bool or file_dry_run != getattr(owner, '_r040a_file_dry_run', False):
        raise ValueError('anchor file probe mode differs from its owner')
    _owner_scope(owner, file_dry_run)
    if not file_dry_run:
        _owned_lock(owner)
    if review.get('candidate_commit') != CANDIDATE:
        raise ValueError('anchor source review candidate differs')
    cfg = review['anchor_four_cell']
    if cfg.get('state') != 'queued_bound_supplement':
        raise ValueError('anchor bound supplement is not admitted by source review')
    probe = Path(cfg['probe_path'])
    sources = review.get('sources', {})
    if (cfg.get('probe_sha256') != PROBE_SHA or sha(probe) != PROBE_SHA
            or sources.get(str(probe)) != PROBE_SHA
            or sources.get(str(Path(__file__).resolve())) != sha(__file__)):
        raise ValueError('anchor source review probe or collector differs')
    binding = cfg['input_binding']
    seed = Path(owner.directory) / 'anchor_seed.txt'
    bound = bind_seed(Path(binding['path']), seed, binding['sha256'])
    write_new(Path(owner.directory) / 'anchor_seed_binding.json', bound)
    results, births = [], set()
    for rep in range(1, 4):
        for checkpoint, prefix in ((False, 'OFF'), (True, 'ON')):
            name = f'{prefix}_p{rep}'
            with service_scope(owner, name, candidate_commit=review['candidate_commit'],
                               probe_path=probe, checkpoint=checkpoint,
                               file_dry_run=file_dry_run) as (arm, env, wt):
                identity = {}
                if not file_dry_run:
                    birth = _service_birth(owner, owner.proc.pid)
                    if not _same_birth(birth, owner.service_birth):
                        raise ValueError('anchor service birth differs before probe')
                    key = (birth['pid'], birth['start_ticks'])
                    if key in births:
                        raise ValueError('anchor requires six independent process births')
                    births.add(key)
                    identity = {'service_pid': birth['pid'], 'service_start_ticks': birth['start_ticks']}
                result = run_bound_probe(probe_path=probe, seed_path=seed,
                          seed_sha256=bound['sha256'], arm=arm, checkpoint=checkpoint,
                          port=owner.port, file_dry_run=file_dry_run, **identity)
                if not file_dry_run and not _same_birth(_service_birth(owner, owner.proc.pid), birth):
                    raise ValueError('anchor service birth changed during probe')
                results.append(result)
    result = {'schema': 'ft_r040a_anchor_four_cell_measurements/v2',
              'seed_binding': bound, 'arms': results,
              'cold_per_checkpoint_per_shape': 3, 'warm_per_process_per_shape': 4,
              'model_admitted': False}
    if file_dry_run:
        result.update(kind='CPU_FILE_PROBE', not_measurement=True,
                      state='cpu_file_probe_completed', planned_services=6,
                      service_started=False, requests_sent=False, gpu_lock_taken=False)
    else:
        result.update(independent_processes=len(births),
                      state='measured_pending_independent_raw_review')
    write_new(Path(owner.directory) / 'anchor_four_cell.json', result)
    return result
