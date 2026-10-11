"""Audit/close a RID-scoped corrected T17 projection diagnostic; never grants T17 acceptance."""
from __future__ import annotations
import argparse, contextlib, hashlib, importlib.util, io, json, os, re, runpy, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
CPU_STAGE = Path('/data2/FreeToken/runs/dev_D14/projection_95638b538008')
CPU_SHA = '5336d493a67695f46e1ba634d34556678ab9af907ee503640491f3cda11428f4'
CANDIDATE = 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
EXPECTED_CPU_SOURCES = 19
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
def terminal(identity: dict, name: str) -> None:
    pid, ticks = identity.get('pid'), identity.get('start_ticks')
    if type(pid) is not int or type(ticks) is not int: raise ValueError(f'{name} identity is incomplete')
    stat = Path('/proc') / str(pid) / 'stat'
    if not stat.exists(): return
    fields = stat.read_text().rpartition(') ')[2].split()
    if len(fields) < 20 or int(fields[19]) != ticks or fields[0] != 'Z':
        raise ValueError(f'{name} is live or its process birth changed')
def exact(actual: object, expected: object, name: str) -> None:
    if actual != expected: raise ValueError(f'{name} differs from frozen binding')


def metadata(review: dict, batch_log: Path) -> dict:
    receipt = review['receipt']
    return {'schema': 'ft_round/v2', 'round_id': review['rid'], 'epoch': 2, 'card': 'T17', 'title': 'Corrected projection diagnostic',
            'base': {'commit': CANDIDATE, 'code_version': 'D14 candidate@e4f3202'}, 'experimental': {'diagnostic_only': True, 'FT_LM_CHUNK': 4096},
            'serve': {'arms': {name: {'commit': CANDIDATE, **identity} for name, identity in review['services'].items()}},
            'results': review['observed'], 'acceptance_limits': review['limits'], 'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
            'batch_logs': [{'path': str(batch_log), 'sha256': sha(batch_log)}]}


def canonical_preflight(directory: Path, document: dict, wrapper: Path) -> None:
    """Run canonical prepare on a private copy; never writes the raw round."""
    here = Path(__file__).parent
    with tempfile.TemporaryDirectory(prefix='ft-projection-close-preflight-') as temp:
        root = Path(temp) / directory.name
        root.mkdir()
        write(root / 'round.json', encode(document))
        write(root / 'batch.sh', wrapper.read_bytes())
        for arm in document['serve']['arms']:
            for name in ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt'):
                source = directory / arm / name
                if source.is_symlink() or not source.is_file(): raise ValueError('missing actual service artifact: ' + str(source))
                write(root / arm / name, source.read_bytes())
        sys.path.insert(0, str(here))
        try:
            spec = importlib.util.spec_from_file_location('projection_close_round_close', here / 'round_close.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.prepare(root)
        finally:
            sys.path.pop(0)


def audit(receipt_path: Path, bindings_path: Path, early_monitor_path: Path) -> dict:
    receipt, bindings = load(receipt_path, 'launch receipt'), load(bindings_path, 'bindings')
    early_monitor = load(early_monitor_path, 'early monitor')
    rid = receipt.get('rid')
    if not isinstance(rid, str) or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17', rid): raise ValueError('exact diagnostic RID required')
    if bindings.get('schema') != 'ft_t17_projection_close_bindings/v1': raise ValueError('unsupported close bindings')
    exact(bindings.get('rid'), rid, 'binding RID'); exact(bindings.get('batch'), receipt.get('batch'), 'binding batch')
    exact(bindings.get('early_monitor_sha256'), sha(early_monitor_path), 'early-monitor raw SHA')
    exact(receipt.get('candidate_commit'), CANDIDATE, 'candidate commit')
    if receipt.get('diagnostic_only') is not True or receipt.get('FT_LM_CHUNK') != 4096: raise ValueError('corrected original-chunk diagnostic receipt required')
    if receipt.get('baseline_acceptance') != 'not_granted; R023_not_met_retained': raise ValueError('R023 not_met retention binding required')
    exact(receipt.get('source_stage'), str(CPU_STAGE), 'CPU stage'); exact(receipt.get('cpu_stage_sha256'), CPU_SHA, 'CPU stage hash')
    server_receipt = load(ROOT / 'runs/dev_D14' / ('launch_' + rid + '.json'), 'server launch receipt')
    exact(server_receipt, receipt, 'server launch receipt')
    if sha(CPU_STAGE / 'cpu_validation.json') != CPU_SHA: raise ValueError('corrected CPU stage report changed')
    cpu = load(CPU_STAGE / 'cpu_validation.json', 'CPU stage report')
    if cpu.get('schema') != 'ft_t17_projection_cpu/v1' or cpu.get('gpu_started') is not False: raise ValueError('CPU-only stage required')
    sources = cpu.get('source_files')
    if not isinstance(sources, dict) or len(sources) != EXPECTED_CPU_SOURCES or sources != receipt.get('source_files'):
        raise ValueError('exact 19-source CPU/runtime binding required')
    for name, digest in sources.items():
        for location in (CPU_STAGE / name, Path(receipt['frozen_runner']).parent / name):
            if location.is_symlink() or not location.is_file() or location.stat().st_mode & 0o222 or sha(location) != digest:
                raise ValueError('frozen runtime/source differs: ' + name)
    for name, step in cpu.get('steps', {}).items():
        if step.get('returncode') != 0 or sha(CPU_STAGE / (name + '.log')) != step.get('log_sha256'):
            raise ValueError('CPU stage log differs: ' + name)
    here = Path(__file__).parent
    for name, digest in TOOL_SHA.items():
        if sha(here / name) != digest or sha(ROOT / 'scripts' / name) != digest:
            raise ValueError('canonical D04 source differs: ' + name)
    if sha(D04_STAGE / 'closure_cpu.json') != D04_REPORT_SHA:
        raise ValueError('prior exact Linux D04 proof changed')
    d04 = load(D04_STAGE / 'closure_cpu.json', 'prior D04 proof')
    if d04.get('returncode') != 0 or d04.get('close_sha256') != TOOL_SHA['round_close.py'] or sha(D04_STAGE / 'tests.log') != d04.get('tests_log_sha256'):
        raise ValueError('prior exact Linux D04 proof is invalid')
    directory = ROUNDS / rid
    forbidden = ('round.json', 'MANIFEST.sha256', 'round_history', 'projection_close_review.json', 'source_tools', 'batch.sh')
    if any((directory / name).exists() for name in forbidden): raise ValueError('completed or partially closed round cannot be re-closed')
    if directory.is_symlink() or any(p.is_symlink() or p.stat().st_uid != os.geteuid() for p in (directory, *directory.rglob('*'))):
        raise ValueError('regular owned raw round evidence required')
    status_file = directory / ('status_batch' + str(receipt['batch']) + '.json')
    status = load(status_file, 'status receipt'); status_binding = bindings.get('batch_status')
    if not isinstance(status_binding, dict): raise ValueError('batch status binding missing')
    exact(sha(status_file), status_binding.get('sha256'), 'status raw SHA'); exact(status.get('rid'), rid, 'status RID')
    exact(status.get('batch'), receipt['batch'], 'status batch'); exact(status.get('state'), 'complete_measurements_pending_review', 'status state')
    batch_identity = {key: status.get(key) for key in ('batch_pid', 'batch_start_ticks')}
    exact(batch_identity, status_binding.get('identity'), 'captured batch identity'); terminal({'pid': status['batch_pid'], 'start_ticks': status['batch_start_ticks']}, 'batch')
    exact(receipt.get('batch_pid'), status['batch_pid'], 'launch/status batch PID')
    monitor_identity = early_monitor.get('handle')
    if not isinstance(monitor_identity, dict): raise ValueError('early monitor handle is missing')
    exact(early_monitor.get('rid'), rid, 'early monitor RID'); exact(early_monitor.get('batch'), receipt['batch'], 'early monitor batch')
    exact(monitor_identity, bindings.get('batch_early_identity'), 'captured early batch identity')
    exact(monitor_identity.get('pid'), receipt['batch_pid'], 'launch/early batch PID')
    exact(monitor_identity.get('start_ticks'), status['batch_start_ticks'], 'status/early batch birth')
    exact(monitor_identity.get('pgid'), receipt['batch_pgid'], 'launch/early batch PGID')
    exact(monitor_identity.get('session'), receipt['batch_pgid'], 'launch/early batch session')
    services = bindings.get('services')
    if not isinstance(services, dict) or set(services) != {'projection_warm', 'projection_cold'}: raise ValueError('two captured service identities required')
    actual_services = {}
    for arm, bound in services.items():
        if not isinstance(bound, dict): raise ValueError('service binding must be object')
        arm_dir = directory / arm; identity_file, stop_file = arm_dir / 'process_identity.json', arm_dir / 'stop_identity.json'
        identity, stop = load(identity_file, arm + ' identity'), load(stop_file, arm + ' terminal')
        exact(sha(identity_file), bound.get('process_identity_sha256'), arm + ' identity raw SHA')
        exact(sha(stop_file), bound.get('stop_identity_sha256'), arm + ' terminal raw SHA')
        exact(identity, bound.get('identity'), arm + ' captured identity'); exact(stop, {'terminal': True, **identity}, arm + ' terminal receipt')
        terminal(identity, arm); actual_services[arm] = identity
    reader = runpy.run_path(str(Path(__file__).with_name('t17_projection_read.py')), run_name='projection_close_reader')
    stream, prior = io.StringIO(), sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(receipt))
        with contextlib.redirect_stdout(stream): exec(compile(reader['PROGRAM'], 'projection_close_cpu_reader', 'exec'), {'__name__': 'projection_close_cpu'})
    finally: sys.stdin = prior
    observed = json.loads(stream.getvalue())
    if observed.get('cuda_initialized') or observed.get('token_count') != {'cold': 128, 'hit': 128} or set(observed.get('restored_roles', ())) != {'conv_states', 'recurrent_states', 'slot:ple_conv', 'slot:ple_ngram_ctx'} or not all(observed['restored_roles'].values()):
        raise ValueError('complete CPU token/restore recomputation required')
    exact(observed.get('arms'), actual_services, 'reader service identities')
    raw = {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    return {'schema': 'ft_t17_projection_close_review/v1', 'rid': rid, 'batch': receipt['batch'], 'diagnostic_only': True,
            'receipt_sha256': sha(receipt_path), 'bindings_sha256': sha(bindings_path), 'early_monitor_sha256': sha(early_monitor_path), 'receipt': receipt,
            'status': status, 'services': actual_services, 'observed': observed, 'original_raw_files': raw,
            'limits': ['Corrected projection diagnostic only; original R023 not_met retained.', 'No T17/E2-base.1/T10 acceptance or performance conclusion.']}


def close(receipt_path: Path, bindings_path: Path, early_monitor_path: Path, audit_path: Path) -> None:
    review = load(audit_path, 'separately staged audit')
    if (review.get('receipt_sha256') != sha(receipt_path) or review.get('bindings_sha256') != sha(bindings_path)
            or review.get('early_monitor_sha256') != sha(early_monitor_path)): raise ValueError('staged review inputs changed')
    exact(audit(receipt_path, bindings_path, early_monitor_path), review, 'fresh audit review')
    directory = ROUNDS / review['rid']
    if any((directory / n).exists() for n in ('round.json', 'MANIFEST.sha256', 'round_history', 'source_tools')): raise ValueError('completed closure cannot be rerun')
    for name, digest in review['original_raw_files'].items():
        if sha(directory / name) != digest: raise ValueError('raw map changed before closure')
    receipt = review['receipt']; frozen = Path(receipt['frozen_runner']).parent
    for name, digest in receipt['source_files'].items():
        raw = (frozen / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('runtime changed before copy')
        write(directory / 'source_tools/runtime' / name, raw)
    for path in CPU_STAGE.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log'): write(directory / 'source_tools/launch_cpu' / path.name, path.read_bytes())
    here = Path(__file__).parent
    for name in ('t17_projection_close.py', 't17_projection_close_stage.py', 't17_projection_read.py', 'bindings.json', 'launch_receipt.json', 'early_monitor.json'):
        source = here / name if (here / name).exists() else (bindings_path if name == 'bindings.json' else early_monitor_path if name == 'early_monitor.json' else receipt_path)
        write(directory / 'source_tools/closure' / name, source.read_bytes())
    for name in TOOLS:
        raw = (here / name).read_bytes()
        write(directory / 'source_tools/closure' / name, raw)
        write(directory / name, raw)
    stage_root = audit_path.parent
    for path in stage_root.rglob('*'):
        if path.is_file(): write(directory / 'source_tools/closure_stage' / path.relative_to(stage_root), path.read_bytes())
    wrapper = Path(receipt['wrapper'])
    if wrapper.is_symlink() or sha(wrapper) != receipt.get('wrapper_sha256'): raise ValueError('actual batch wrapper differs')
    batch_log = Path(receipt['batch_log'])
    if batch_log.is_symlink() or not batch_log.is_file(): raise ValueError('actual batch log missing')
    proposed = metadata(review, batch_log)
    canonical_preflight(directory, proposed, wrapper)
    write(directory / 'projection_close_review.json', encode(review)); write(directory / 'launch_receipt.json', receipt_path.read_bytes()); write(directory / 'batch.sh', wrapper.read_bytes())
    write(directory / 'round.json', encode(proposed))
    subprocess.run(['bash', str(directory / 'round_close.sh'), review['rid'], '--round-root', str(ROUNDS)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, 'FT_ROUND_PYTHON': sys.executable})
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict', '--new', 'kept', '--reason', review['limits'][0], '--by', 'authorized closer', '--evidence', 'projection_close_review.json'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['sha256sum', '-c', 'MANIFEST.sha256'], cwd=directory, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if any(p.stat().st_mode & 0o222 for p in (directory, *directory.rglob('*'))): raise ValueError('closure is not read-only')
    print(json.dumps({'rid': review['rid'], 'verdict': 'kept', 'diagnostic_only': True, 'original_T17_verdict': 'not_met_retained', 'original_raw_files_verified': len(review['original_raw_files']), 'round_sha256': sha(directory / 'round.json'), 'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'review_sha256': sha(directory / 'projection_close_review.json')}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--receipt', type=Path, required=True); parser.add_argument('--bindings', type=Path, required=True); parser.add_argument('--early-monitor', type=Path, required=True); parser.add_argument('--audit-file', type=Path); parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if args.close:
        if not args.audit_file: parser.error('--close requires --audit-file')
        close(args.receipt, args.bindings, args.early_monitor, args.audit_file)
    else: print(json.dumps(audit(args.receipt, args.bindings, args.early_monitor), ensure_ascii=False))
