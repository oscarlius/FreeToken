"""Audit and close one operator-only T17 GEMM diagnostic; no acceptance is granted."""
from __future__ import annotations

import argparse, contextlib, hashlib, importlib.util, io, json, os, re, runpy, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
CPU_STAGE = ROOT / 'runs/dev_D14/gemm_e1154756dd3c'
CPU_SHA = 'dcbb21c2df0b49cdd25311375431f6f7250ce8b6873688c8d8a38ba4faf55e56'
CANDIDATE = 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
EXPECTED_CPU_SOURCES = 17
TOOLS = ('round_json_append.py', 'round_close.py', 'round_close.sh')
TOOL_SHA = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
            'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
            'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}
D04_STAGE = ROOT / 'runs/dev_D14/r023_close_cc5852e4750a'
D04_REPORT_SHA = 'cce7e9b30ffb34bd1c96003331926e49e9ec6c84e0352aef433cafe202ad9505'


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def encode(value: object) -> bytes: return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def load(path: Path, name: str) -> dict:
    if path.is_symlink() or not path.is_file(): raise ValueError(f'{name} must be a regular file')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict): raise ValueError(f'{name} must be a JSON object')
    return value
def write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(raw)
def exact(actual: object, expected: object, name: str) -> None:
    if actual != expected: raise ValueError(f'{name} differs from frozen binding')
def terminal(identity: dict, name: str) -> None:
    pid, ticks = identity.get('pid'), identity.get('start_ticks')
    if type(pid) is not int or type(ticks) is not int: raise ValueError(f'{name} identity is incomplete')
    stat = Path('/proc') / str(pid) / 'stat'
    if not stat.exists(): return
    fields = stat.read_text().rpartition(') ')[2].split()
    if len(fields) < 20 or int(fields[19]) != ticks or fields[0] != 'Z':
        raise ValueError(f'{name} is live or its process birth changed')


def metadata(review: dict, batch_log: Path) -> dict:
    return {'schema': 'ft_round/v2', 'round_id': review['rid'], 'epoch': 2, 'card': 'T17',
            'title': 'GDN operator-only diagnostic',
            'base': {'commit': CANDIDATE, 'code_version': 'D14 candidate@e4f3202'},
            'experimental': {'diagnostic_only': True, 'source_model_lm_chunk': 4096,
                             'operator_only': True, 'operator': 'gdn'},
            'serve': 'none', 'results': review['observed'], 'acceptance_limits': review['limits'],
            'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
            'batch_logs': [{'path': str(batch_log), 'sha256': sha(batch_log)}]}


def canonical_preflight(directory: Path, document: dict, wrapper: Path) -> None:
    """Canonical prepare on a private copy before any raw-round write."""
    here = Path(__file__).parent
    with tempfile.TemporaryDirectory(prefix='ft-gemm-close-preflight-') as temp:
        root = Path(temp) / directory.name; root.mkdir()
        write(root / 'round.json', encode(document)); write(root / 'batch.sh', wrapper.read_bytes())
        sys.path.insert(0, str(here))
        try:
            spec = importlib.util.spec_from_file_location('gemm_close_round_close', here / 'round_close.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.prepare(root)
        finally: sys.path.pop(0)


def audit(receipt_path: Path, bindings_path: Path, monitor_path: Path) -> dict:
    receipt, bindings, monitor = load(receipt_path, 'launch receipt'), load(bindings_path, 'bindings'), load(monitor_path, 'monitor')
    rid = receipt.get('rid')
    if not isinstance(rid, str) or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', rid): raise ValueError('exact diagnostic RID required')
    if bindings.get('schema') != 'ft_t17_gemm_close_bindings/v1': raise ValueError('unsupported GEMM close bindings')
    exact(bindings.get('rid'), rid, 'binding RID'); exact(bindings.get('batch'), receipt.get('batch'), 'binding batch')
    exact(bindings.get('monitor_sha256'), sha(monitor_path), 'monitor raw SHA')
    if receipt.get('schema') != 'ft_t17_gemm_launch/v1' or receipt.get('operator') != 'gdn' or receipt.get('operator_only') is not True:
        raise ValueError('exact GDN operator launch receipt required')
    exact(receipt.get('candidate_commit'), CANDIDATE, 'candidate commit')
    if receipt.get('baseline_acceptance') != 'not_granted; R023_not_met_retained': raise ValueError('R023 retention binding required')
    exact(receipt.get('source_stage'), str(CPU_STAGE), 'CPU stage'); exact(receipt.get('cpu_stage_sha256'), CPU_SHA, 'CPU stage SHA')
    exact(load(ROOT / 'runs/dev_D14' / ('launch_' + rid + '.json'), 'server launch receipt'), receipt, 'server launch receipt')
    if sha(CPU_STAGE / 'cpu_validation.json') != CPU_SHA: raise ValueError('CPU stage report changed')
    cpu = load(CPU_STAGE / 'cpu_validation.json', 'CPU stage report')
    if cpu.get('schema') != 'ft_t17_gemm_cpu/v1' or cpu.get('gpu_started') is not False: raise ValueError('CPU-only stage required')
    sources = cpu.get('source_files')
    if not isinstance(sources, dict) or len(sources) != EXPECTED_CPU_SOURCES or sources != receipt.get('source_files'):
        raise ValueError('exact 17-source CPU/runtime binding required')
    frozen = Path(receipt.get('frozen_runner', '')).parent
    for name, digest in sources.items():
        for path in (CPU_STAGE / name, frozen / name):
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest:
                raise ValueError('frozen runtime/source differs: ' + name)
    for name, step in cpu.get('steps', {}).items():
        if step.get('returncode') != 0 or sha(CPU_STAGE / (name + '.log')) != step.get('log_sha256'):
            raise ValueError('CPU stage log differs: ' + name)
    here = Path(__file__).parent
    for name, digest in TOOL_SHA.items():
        if sha(here / name) != digest or sha(ROOT / 'scripts' / name) != digest: raise ValueError('canonical D04 source differs: ' + name)
    d04 = load(D04_STAGE / 'closure_cpu.json', 'prior D04 proof')
    if sha(D04_STAGE / 'closure_cpu.json') != D04_REPORT_SHA or d04.get('returncode') != 0 or d04.get('close_sha256') != TOOL_SHA['round_close.py'] or sha(D04_STAGE / 'tests.log') != d04.get('tests_log_sha256'):
        raise ValueError('prior exact Linux D04 proof is invalid')
    directory = ROUNDS / rid
    forbidden = ('round.json', 'MANIFEST.sha256', 'round_history', 'gemm_close_review.json', 'source_tools', 'batch.sh')
    if any((directory / name).exists() for name in forbidden): raise ValueError('completed or partially closed round cannot be re-closed')
    if directory.is_symlink() or any(p.is_symlink() or p.stat().st_uid != os.geteuid() for p in (directory, *directory.rglob('*'))):
        raise ValueError('regular owned raw round evidence required')
    status_file, identity_file = directory / ('status_batch' + str(receipt['batch']) + '.json'), directory / 'process_identity.json'
    status, identity = load(status_file, 'status receipt'), load(identity_file, 'process identity')
    status_binding, identity_binding = bindings.get('batch_status'), bindings.get('process_identity')
    if not isinstance(status_binding, dict) or not isinstance(identity_binding, dict): raise ValueError('status/process bindings missing')
    exact(sha(status_file), status_binding.get('sha256'), 'status raw SHA'); exact(sha(identity_file), identity_binding.get('sha256'), 'identity raw SHA')
    exact(status, status_binding.get('value'), 'status binding'); exact(identity, identity_binding.get('value'), 'identity binding')
    if status.get('rid') != rid or status.get('batch') != receipt['batch'] or status.get('state') != 'complete_measurements_pending_review': raise ValueError('terminal status differs')
    exact(status.get('batch_pid'), identity.get('pid'), 'status/identity PID'); exact(status.get('batch_start_ticks'), identity.get('start_ticks'), 'status/identity birth')
    exact(receipt.get('batch_pid'), identity.get('pid'), 'launch/identity PID')
    exact(receipt.get('batch_pgid'), identity.get('pgid'), 'launch/identity PGID')
    exact(identity.get('pgid'), identity.get('pid'), 'owned process group')
    exact(identity.get('session'), identity.get('pid'), 'owned session')
    terminal(identity, 'batch')
    if monitor.get('rid') != rid or monitor.get('batch') != receipt['batch']: raise ValueError('monitor RID/batch differs')
    exact(monitor.get('identity'), identity, 'monitor process identity')
    monitor_binding = bindings.get('monitor_identity')
    if monitor_binding is not None: exact(monitor_binding, identity, 'bound monitor identity')
    wrapper, batch_log = Path(receipt.get('wrapper', '')), Path(receipt.get('batch_log', ''))
    if wrapper.is_symlink() or not wrapper.is_file() or sha(wrapper) != receipt.get('wrapper_sha256'): raise ValueError('actual batch wrapper differs')
    if batch_log.is_symlink() or not batch_log.is_file(): raise ValueError('actual batch log missing')
    reader_path = Path(__file__).with_name('t17_gemm_read.py')
    if sha(reader_path) != sources.get('t17_gemm_read.py'): raise ValueError('closure reader differs from frozen runtime source')
    reader = runpy.run_path(str(reader_path), run_name='gemm_close_reader')
    stream, prior = io.StringIO(), sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(receipt))
        with contextlib.redirect_stdout(stream): exec(compile(reader['PROGRAM'], 'gemm_close_cpu_reader', 'exec'), {'__name__': 'gemm_close_cpu'})
    finally: sys.stdin = prior
    observed = json.loads(stream.getvalue())
    runs = observed.get('runs')
    if observed.get('schema') != 'ft_t17_gemm_cpu_read/v1' or observed.get('cuda_initialized') or observed.get('real_inputs_equal') is not True or not isinstance(runs, dict) or not runs:
        raise ValueError('complete CPU replay recomputation required')
    for row in runs.values():
        if type(row.get('repeats_equal')) is not bool or len(row.get('repeat_pair_metrics', ())) != 2:
            raise ValueError('three-repeat replay evidence required')
    exact(observed.get('identity'), identity, 'reader process identity')
    raw = {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    # The first preflight proves the proposed metadata is canonically sealable
    # without changing the raw round; close repeats it immediately before write.
    canonical_preflight(directory, metadata({'rid': rid, 'receipt': receipt, 'observed': observed,
                                             'limits': ['GDN operator diagnostic only; original R023 not_met retained.',
                                                        'No T17/E2-base.1/T10 acceptance or performance conclusion.']}, batch_log), wrapper)
    return {'schema': 'ft_t17_gemm_close_review/v1', 'rid': rid, 'batch': receipt['batch'], 'diagnostic_only': True,
            'receipt_sha256': sha(receipt_path), 'bindings_sha256': sha(bindings_path), 'monitor_sha256': sha(monitor_path),
            'receipt': receipt, 'status': status, 'identity': identity, 'observed': observed, 'canonical_preflight': 'PASS', 'original_raw_files': raw,
            'limits': ['GDN operator diagnostic only; original R023 not_met retained.', 'No T17/E2-base.1/T10 acceptance or performance conclusion.']}


def close(receipt_path: Path, bindings_path: Path, monitor_path: Path, audit_path: Path) -> None:
    review = load(audit_path, 'separately staged audit')
    if review.get('receipt_sha256') != sha(receipt_path) or review.get('bindings_sha256') != sha(bindings_path) or review.get('monitor_sha256') != sha(monitor_path): raise ValueError('staged review inputs changed')
    exact(audit(receipt_path, bindings_path, monitor_path), review, 'fresh audit review')
    directory = ROUNDS / review['rid']
    if any((directory / name).exists() for name in ('round.json', 'MANIFEST.sha256', 'round_history', 'source_tools')): raise ValueError('completed closure cannot be rerun')
    for name, digest in review['original_raw_files'].items():
        if sha(directory / name) != digest: raise ValueError('raw map changed before closure')
    receipt = review['receipt']; wrapper = Path(receipt['wrapper']); batch_log = Path(receipt['batch_log'])
    proposed = metadata(review, batch_log); canonical_preflight(directory, proposed, wrapper)
    frozen = Path(receipt['frozen_runner']).parent
    for name, digest in receipt['source_files'].items():
        raw = (frozen / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('runtime changed before copy')
        write(directory / 'source_tools/runtime' / name, raw)
    for path in CPU_STAGE.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log'): write(directory / 'source_tools/launch_cpu' / path.name, path.read_bytes())
    here = Path(__file__).parent
    sources = {'t17_gemm_close.py': here / 't17_gemm_close.py', 't17_gemm_close_stage.py': here / 't17_gemm_close_stage.py',
               't17_gemm_read.py': here / 't17_gemm_read.py', 'bindings.json': bindings_path, 'launch_receipt.json': receipt_path, 'monitor.json': monitor_path}
    for name, source in sources.items(): write(directory / 'source_tools/closure' / name, source.read_bytes())
    for name in TOOLS:
        raw = (here / name).read_bytes(); write(directory / 'source_tools/closure' / name, raw); write(directory / name, raw)
    for path in audit_path.parent.rglob('*'):
        if path.is_file(): write(directory / 'source_tools/closure_stage' / path.relative_to(audit_path.parent), path.read_bytes())
    write(directory / 'gemm_close_review.json', encode(review)); write(directory / 'launch_receipt.json', receipt_path.read_bytes()); write(directory / 'batch.sh', wrapper.read_bytes()); write(directory / 'round.json', encode(proposed))
    env = {**os.environ, 'FT_ROUND_PYTHON': sys.executable}
    subprocess.run(['bash', str(directory / 'round_close.sh'), review['rid'], '--round-root', str(ROUNDS)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict', '--new', 'kept', '--reason', review['limits'][0], '--by', 'authorized closer', '--evidence', 'gemm_close_review.json'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['sha256sum', '-c', 'MANIFEST.sha256'], cwd=directory, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if any(path.stat().st_mode & 0o222 for path in (directory, *directory.rglob('*'))): raise ValueError('closure is not read-only')
    print(json.dumps({'rid': review['rid'], 'verdict': 'kept', 'diagnostic_only': True, 'original_T17_verdict': 'not_met_retained', 'original_raw_files_verified': len(review['original_raw_files']), 'round_sha256': sha(directory / 'round.json'), 'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'review_sha256': sha(directory / 'gemm_close_review.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--receipt', type=Path, required=True); parser.add_argument('--bindings', type=Path, required=True); parser.add_argument('--monitor', type=Path, required=True); parser.add_argument('--audit-file', type=Path); parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if args.close:
        if not args.audit_file: parser.error('--close requires --audit-file')
        close(args.receipt, args.bindings, args.monitor, args.audit_file)
    else: print(json.dumps(audit(args.receipt, args.bindings, args.monitor), ensure_ascii=False))
