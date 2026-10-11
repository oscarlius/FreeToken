"""Audit and seal the exact completed R025 diagnostic without changing T17 acceptance."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-R025-diagnostic-T17'
CPU_STAGE_SHA = '7eb1e1d44725b513fc19a1d46f1da20bbae307200d9aaa2c76852b1960d31fba'
APPEND_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
CLOSE_SHA = 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def audit():
    directory = ROUNDS / RID
    if any(p.is_symlink() for p in (directory, *directory.parents, *directory.rglob('*'))):
        raise ValueError('regular exact evidence paths required')
    if any(p.stat().st_uid != os.geteuid() for p in (directory, *directory.rglob('*'))):
        raise ValueError('foreign evidence owner')
    if any((directory / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256', 'review_batch53.json', 'batch.sh', 'source_tools')):
        raise ValueError('exact unprepared R025 required')
    receipt = json.loads((ROOT / 'runs/dev_D14' / ('launch_' + RID + '.json')).read_bytes())
    if (receipt.get('rid') != RID or receipt.get('batch') != 53 or receipt.get('batch_pid') != 442080
            or receipt.get('batch_pgid') != 442080 or receipt.get('diagnostic_only') is not True
            or receipt.get('cpu_stage_sha256') != CPU_STAGE_SHA or receipt.get('FT_LM_CHUNK') != 7680):
        raise ValueError('exact actual diagnostic launch required')
    stage = Path(receipt['source_stage'])
    if sha(stage / 'cpu_validation.json') != CPU_STAGE_SHA:
        raise ValueError('actual Linux CPU stage changed')
    cpu = json.loads((stage / 'cpu_validation.json').read_bytes())
    if cpu.get('gpu_started') is not False or cpu['source_files'] != receipt['source_files']:
        raise ValueError('Linux CPU/source proof differs')
    for name, step in cpu['steps'].items():
        if step['returncode'] != 0 or sha(stage / (name + '.log')) != step['log_sha256']:
            raise ValueError('Linux CPU proof log changed')
    for name, digest in receipt['source_files'].items():
        if sha(stage / name) != digest or (stage / name).stat().st_mode & 0o222:
            raise ValueError('CPU source binding changed')
    reader = runpy.run_path(str(HERE / 't17_matched_read.py'), run_name='r025_cpu_raw_reader')
    stream, old_input = io.StringIO(), sys.stdin
    try:
        sys.stdin = io.StringIO(json.dumps(receipt))
        with contextlib.redirect_stdout(stream):
            exec(compile(reader['PROGRAM'], 'R025_independent_CPU_audit', 'exec'), {'__name__': 'r025_independent_cpu'})
    finally:
        sys.stdin = old_input
    observed = json.loads(stream.getvalue())
    if observed['cuda_initialized'] or observed['token_count'] != {'cold': 128, 'hit': 128}:
        raise ValueError('complete CPU raw comparison required')
    if observed['status']['batch_start_ticks'] != 122229157 or not all(observed['restored_roles'].values()):
        raise ValueError('exact process birth or separate restore evidence differs')
    if sha(Path(receipt['wrapper'])) != receipt['wrapper_sha256']:
        raise ValueError('actual process wrapper changed')
    for name, digest in [('round_json_append.py', APPEND_SHA), ('round_close.py', CLOSE_SHA)]:
        if sha(HERE / name) != digest or sha(ROOT / 'scripts' / name) != digest:
            raise ValueError('tested canonical D04 source changed')
    tested_stage = ROOT / 'runs/dev_D14/r023_close_cc5852e4750a'
    if sha(tested_stage / 'closure_cpu.json') != 'cce7e9b30ffb34bd1c96003331926e49e9ec6c84e0352aef433cafe202ad9505':
        raise ValueError('retained Linux D04 regression proof changed')
    tested = json.loads((tested_stage / 'closure_cpu.json').read_bytes())
    if (tested.get('returncode') != 0 or tested.get('close_sha256') != CLOSE_SHA
            or sha(tested_stage / 'tests.log') != tested['tests_log_sha256']):
        raise ValueError('D04 prior exact-source test proof invalid')
    original = {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    return {'schema': 'ft_t17_matched_closure_review/v1', 'rid': RID, 'batch': 53,
            'diagnostic_only': True, 'proposed_verdict': 'kept', 'observed': observed, 'receipt': receipt,
            'closure_tools': {'round_close_sha256': CLOSE_SHA, 'round_json_append_sha256': APPEND_SHA},
            'original_raw_files': original, 'batch_log_sha256': sha(ROUNDS / 'batch53.log'),
            'limits': ['Aligned-chunk 8192 short-prefix diagnostic only; original R023 not_met retained.',
                       'No remaining-boundary T17 acceptance, E2-base.1 admission, T10 rerun or performance conclusion.']}


def close():
    result = audit()
    if json.loads((HERE / 'review.json').read_bytes()) != result:
        raise ValueError('staged independent raw review changed')
    directory = ROUNDS / RID
    frozen = Path(result['receipt']['frozen_runner']).parent
    for name, digest in result['receipt']['source_files'].items():
        raw = (frozen / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('actual executed source changed before archival')
        write(directory / 'source_tools/runtime' / name, raw)
    stage = Path(result['receipt']['source_stage'])
    for path in stage.iterdir():
        if path.is_file() and path.name.endswith(('.json', '.log')):
            write(directory / 'source_tools/launch_cpu' / path.name, path.read_bytes())
    for path in HERE.iterdir():
        if path.is_file():
            write(directory / 'source_tools/closure' / path.name, path.read_bytes())
    receipt = result['receipt']
    write(directory / 'launch_receipt.json', encode(receipt))
    write(directory / 'review_batch53.json', encode(result))
    write(directory / 'batch.sh', Path(receipt['wrapper']).read_bytes())
    for name in ('round_json_append.py', 'round_close.py', 'round_close.sh'):
        write(directory / name, (HERE / name).read_bytes())
    metadata = {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T17',
                'title': 'Aligned-chunk prefix and continuation diagnostic', 'parent': 'E2-R023-gate-T17',
                'base': {'code_version': 'E2-base@23f2e2c', 'commit': '23f2e2caa3395837c9474735ffc83321f3b9b5a1'},
                'candidate_commit': receipt['candidate_commit'], 'actual_runtime_commit': receipt['candidate_commit'],
                'experimental': {'diagnostic_only': True, 'FT_LM_CHUNK': 7680},
                'serve': {'arms': {name: {'commit': receipt['candidate_commit'], **identity}
                                    for name, identity in result['observed']['arms'].items()}},
                'results': result['observed'], 'acceptance_limits': result['limits'],
                'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [{'path': str(ROUNDS / 'batch53.log'), 'sha256': result['batch_log_sha256']}]}
    write(directory / 'round.json', encode(metadata))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)],
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict',
                    '--new', 'kept', '--reason', 'Independent raw CPU recomputation accepts this aligned-chunk diagnostic measurement only; original T17 R023 remains not_met and no baseline acceptance is granted.',
                    '--by', 'Codex mainline under authorized handoff', '--evidence', 'review_batch53.json'],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['sha256sum', '-c', 'MANIFEST.sha256'], cwd=directory, check=True, stdout=subprocess.DEVNULL)
    for name, digest in result['original_raw_files'].items():
        if sha(directory / name) != digest:
            raise ValueError('original diagnostic raw artifact changed during closure')
    if any(p.stat().st_mode & 0o222 for p in (directory, *directory.rglob('*'))):
        raise ValueError('closed diagnostic not read-only')
    print(json.dumps({'rid': RID, 'verdict': 'kept', 'diagnostic_only': True,
                      'original_raw_files_verified': len(result['original_raw_files']),
                      'round_sha256': sha(directory / 'round.json'), 'manifest_sha256': sha(directory / 'MANIFEST.sha256'),
                      'review_sha256': sha(directory / 'review_batch53.json'), 'original_T17_verdict': 'not_met_retained'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    options = parser.parse_args()
    if options.close:
        close()
    else:
        print(json.dumps(audit(), ensure_ascii=False))
