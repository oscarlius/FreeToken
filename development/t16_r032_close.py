"""Prepare, and only explicitly seal, the independently reviewed R032 T16 gate."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID, BATCH = 'E2-R032-gate-D14', 60
ARMS = ('PARENT_b60', 'NEW_b60', 'PARENT_P_b60', 'NEW_P_b60',
        'CHUNK_PARENT_b60', 'CHUNK_NEW_b60', 'CHUNK_PARENT_P_b60', 'CHUNK_NEW_P_b60')
HERE = Path(__file__).resolve().parent
REVIEW_STAGE = Path('/data2/FreeToken/runs/dev_D14/t16_r032_review_f151c1b2a29d')
REVIEW_STAGE_SHA = '00f62df2a9da6fb45d5fe165181f95cd93621104ce1c72f0bfda5aafcbf97e4e'
REVIEW_SHA = '83f6677fb6b795c627870a82a7f21b94194fa5517882df3096edcb9ca1d64f24'
HELPERS_SHA = 'd212243e709d521ad93c91893103eb202ae9497c736c38692480c340e68662ec'
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
         'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
         'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}
CONTROL = ('round.json', 'round_history', 'MANIFEST.sha256', 'initial_metadata.json', f'review_batch{BATCH}.json')
CLOSURE_FILES = ('t16_r032_close.py', 't16_r032_close_stage.py', 'tests/test_t16_r032_close.py', 'stage_program.py',
                 'round_json_append.py', 'round_close.py', 'round_close.sh')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encoded(value): return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(data)


def raw_files(directory):
    return {path.relative_to(directory).as_posix(): sha(path) for path in directory.rglob('*')
            if path.is_file() and path.relative_to(directory).parts[0] not in CONTROL}


def _load_frozen_reviewer():
    report_path = REVIEW_STAGE / 'cpu_validation.json'
    if sha(report_path) != REVIEW_STAGE_SHA: raise ValueError('R032 review CPU stage report differs')
    report = json.loads(report_path.read_text())
    if report.get('verdict') != 'PASS' or report.get('passed') != 11 or report.get('gpu_started') is not False: raise ValueError('R032 review CPU stage is not a CPU PASS')
    if report.get('files', {}).get('t16_r032_review.py') != REVIEW_SHA or report['files'].get('t16_r022_review.py') != HELPERS_SHA: raise ValueError('frozen reviewer/helper binding differs')
    source = REVIEW_STAGE / 't16_r032_review.py'
    if sha(source) != REVIEW_SHA: raise ValueError('frozen reviewer source differs')
    spec = importlib.util.spec_from_file_location('r032_frozen_reviewer', source)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module, report


def metadata(packet):
    result, receipt = packet['review'], packet['receipt']
    return {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T16',
            'title': 'D14 schedule eight-arm default-path gate', 'parent': 'E2-R022-gate-D14',
            'base': {'commit': 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42', 'worktree': '/data2/FreeToken/wt/e2d14'},
            'experimental': {'candidate_commit': 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7', 'worktree': '/data2/FreeToken/wt/e2d14-schedule'},
            'serve': {'arms': {name: {'owned_service_pid': pid} for name, pid in result['service_pids'].items()}},
            'design': {'batch': BATCH, 'serve_order': list(result['service_pids'])},
            'independent_review_sha256': packet['review_sha256'],
            'diagnostics': {'gate_sha256': result['gate_sha256'], 'independent_review_sha256': packet['review_sha256'],
                            'review_cpu_stage_sha256': REVIEW_STAGE_SHA, 'original_raw_files': packet['raw_files']},
            'results': result['recomputed'],
            'acceptance_limits': ['Eight-arm default-path T16 evidence only.', 'T17 and D17 remain pending; this does not admit either gate.'],
            'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
            'batch_logs': [{'path': str(ROUNDS / 'batch60.log'), 'sha256': sha(ROUNDS / 'batch60.log')}],
            'launch_receipt_sha256': sha(packet['receipt_path'])}


def audit_first():
    reviewer, report = _load_frozen_reviewer()
    directory = reviewer.guarded(ROUNDS / RID)
    result = reviewer.audit(allow_review=True)
    review_path = directory / f'review_batch{BATCH}.json'
    if reviewer.load(review_path) != result: raise ValueError('actual audit JSON differs from immediate recomputation')
    receipt_path = ROOT / 'runs/dev_D14' / f'launch_{RID}.json'
    receipt = reviewer.load(receipt_path)
    raw = raw_files(directory)
    if raw != result.get('raw_files'): raise ValueError('raw map changed before closure')
    return {'directory': directory, 'review': result, 'review_sha256': sha(review_path), 'receipt_path': receipt_path,
            'receipt': receipt, 'raw_files': raw, 'review_stage_report': report}


def _copy_tree(origin, target):
    for path in origin.rglob('*'):
        if path.is_symlink(): raise ValueError('source archive symlink: ' + str(path))
        if path.is_file(): write(target / path.relative_to(origin), path.read_bytes())


def validate_closure_stage(stage: Path) -> dict:
    """Accept only the dedicated immutable close-stage, never development/."""
    stage = Path(stage)
    if stage.is_symlink() or not stage.is_dir() or stage.stat().st_uid != os.geteuid() or stage.stat().st_mode & 0o222:
        raise ValueError('owned readonly closure stage required')
    report_path = stage / 'cpu_validation.json'
    if report_path.is_symlink() or not report_path.is_file() or report_path.stat().st_mode & 0o222:
        raise ValueError('closure stage report must be readonly regular file')
    report = json.loads(report_path.read_text())
    if report.get('schema') != 'ft_t16_r032_close_stage/v1' or report.get('verdict') != 'PASS' or report.get('gpu_started') is not False or report.get('requests_sent') is not False:
        raise ValueError('exact successful closure CPU stage required')
    files = report.get('files')
    if not isinstance(files, dict) or set(files) != set(CLOSURE_FILES):
        raise ValueError('closure stage source map differs')
    if HERE != stage or sha(Path(__file__)) != files['t16_r032_close.py']:
        raise ValueError('closer must execute its own frozen CPU-tested source')
    if report.get('passed') != 7:
        raise ValueError('complete seven-test closure CPU proof required')
    for name, digest in files.items():
        relative = Path(name)
        path = stage / relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.is_file() or path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o222 or sha(path) != digest:
            raise ValueError('closure stage source differs: ' + name)
    log = stage / 'regression.log'
    step = report.get('step', {})
    if log.is_symlink() or not log.is_file() or log.stat().st_mode & 0o222 or step.get('returncode') != 0 or sha(log) != step.get('log_sha256'):
        raise ValueError('closure CPU regression evidence differs')
    return report


def _copy_verified(stage: Path, report: dict, target: Path):
    for name in CLOSURE_FILES:
        write(target / name, (stage / name).read_bytes())


def close(*, execute=False, closure_stage: Path | None = None, audit_receipt: Path | None = None):
    packet = audit_first()
    if not execute:
        return {'state': 'audit_first_only', 'packet': packet}
    if closure_stage is None:
        raise ValueError('exact immutable closure stage is required')
    if audit_receipt is None:
        raise ValueError('explicit independent audit receipt is required')
    closure_report = validate_closure_stage(closure_stage)
    if sha(audit_receipt) != packet['review_sha256'] or json.loads(Path(audit_receipt).read_text()) != packet['review']:
        raise ValueError('explicit independent audit receipt differs from immediate recomputation')
    directory, receipt = packet['directory'], packet['receipt']
    if any((directory / name).exists() for name in CONTROL[:4]): raise ValueError('round is already sealed')
    for name, digest in TOOLS.items():
        local, server = HERE / name, ROOT / 'scripts' / name
        if sha(local) != digest or sha(server) != digest or local.read_bytes() != server.read_bytes(): raise ValueError('canonical D04 source differs: ' + name)
    frozen = Path(receipt['frozen_runner']).parent
    stage = Path(receipt['source_stage'])
    _copy_tree(frozen, directory / 'source_tools' / 'runtime_source')
    _copy_tree(stage, directory / 'source_tools' / 'cpu_source')
    _copy_tree(REVIEW_STAGE, directory / 'source_tools' / 'review_cpu_source')
    _copy_verified(Path(closure_stage), closure_report, directory / 'source_tools' / 'closure_cpu_source')
    for path in (packet['receipt_path'], ROOT / 'scripts' / 'serve_args_diff.py'):
        write(directory / 'source_tools' / path.name, path.read_bytes())
    for name in TOOLS: write(directory / name, (ROOT / 'scripts' / name).read_bytes())
    write(directory / 'batch.sh', (directory / f'batch{BATCH}.sh').read_bytes())
    document = metadata(packet)
    write(directory / 'round.json', encoded(document))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)], check=True,
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable})
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict', '--new', 'kept',
                    '--reason', 'Eight-arm default-path full text and 128-token-count evidence; PID-only arguments and complete D0 evidence. T17/D17 remain pending.',
                    '--evidence', f'review_batch{BATCH}.json', f'gate_batch{BATCH}.json', '--by', 'authorized R032 closer'], check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True)
    if any(sha(directory / name) != digest for name, digest in packet['raw_files'].items()) or any(path.stat().st_mode & 0o222 for path in (directory, *directory.rglob('*'))): raise ValueError('closure changed raw evidence or remained writable')
    return {'rid': RID, 'batch': BATCH, 'verdict': 'kept', 'round_sha256': sha(directory / 'round.json'),
            'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'original_raw_files_verified': len(packet['raw_files'])}


if __name__ == '__main__':
    if '--close' not in sys.argv or sys.platform != 'linux': raise SystemExit('explicit --close on actual Linux host required')
    print(json.dumps(close(execute=True), sort_keys=True))
