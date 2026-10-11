"""Fail-closed R027 diagnostic archive; it never changes T17 acceptance.

The independently run numeric reader must first publish its immutable v2 output
and the exact reader plus retained companion source beside this tool.

They are intentionally not generated here.  This closer is only allowed to
archive a review that binds every raw tensor and every pre-existing round file.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-R027-diagnostic-T17'
BATCH = 55
CPU_STAGE_SHA = '85cf811e1d0d91c8c6e6e0dbd826edfc80a9793f7061b3cb7e4f653a8148ec7c'
EXPECTED_STATUS = {'rid': RID, 'batch': BATCH, 'batch_pid': 588986,
                   'batch_start_ticks': 122554334,
                   'state': 'complete_measurements_pending_review'}
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
         'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
         'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def terminal(pid, ticks=None):
    stat = Path('/proc') / str(pid) / 'stat'
    if not stat.exists():
        return True
    fields = stat.read_text().rpartition(') ')[2].split()
    if ticks is not None and int(fields[19]) != ticks:
        raise ValueError('PID identity changed: ' + str(pid))
    return fields[0] == 'Z'


def raw_files(directory):
    return {path.relative_to(directory).as_posix(): sha(path)
            for path in sorted(directory.rglob('*')) if path.is_file()}


def load_review(directory, raw):
    review_path = HERE / 't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json'
    reader_path = HERE / 't17_prefix_numeric_read.py'
    companion_path = HERE / 't17_r027_independent_cpu_review.py'
    if not review_path.is_file() or not reader_path.is_file() or not companion_path.is_file():
        raise ValueError('independent numeric reader source, companion, and review are required before archival')
    review = json.loads(review_path.read_bytes())
    module = runpy.run_path(str(reader_path), run_name='r027_reader_schema')
    required = {'schema': 'ft_t17_prefix_numeric_independent_cpu_review/v1', 'rid': RID, 'batch': BATCH,
                'diagnostic_only': True, 'cpu_only': True, 'cuda_initialized': False}
    if any(review.get(key) != value for key, value in required.items()):
        raise ValueError('numeric reader output schema differs')
    expected = {f'{field}_{start}' for start in (512, 4608)
                for field in ('conv_in', 'q', 'k', 'v', 'g', 'beta')} | {'h_8192'}
    tensors = review.get('tensor_comparisons')
    if not isinstance(tensors, dict) or set(tensors) != expected:
        raise ValueError('numeric reader tensor set is incomplete or unlisted')
    for name, item in tensors.items():
        if not isinstance(item, dict) or set(('equal', 'shape', 'dtype', 'warm_sha256', 'cold_sha256',
                                               'max_abs', 'different_bytes')) - set(item):
            raise ValueError('numeric tensor comparison is incomplete: ' + name)
    tensors = review.get('raw_tensors')
    if not isinstance(tensors, dict) or set(tensors) != set(module['EXPECTED_TENSORS']):
        raise ValueError('raw tensor inventory is incomplete or unlisted')
    for name, item in tensors.items():
        if not isinstance(item, dict) or set(('sha256', 'shape', 'dtype', 'nbytes', 'role')) - set(item):
            raise ValueError('raw tensor metadata is incomplete: ' + name)
        if raw.get(name) != item['sha256']:
            raise ValueError('raw tensor bytes differ: ' + name)
    if (review.get('reader_source_sha256') != sha(reader_path)
            or review.get('companion_source_sha256') != sha(companion_path)
            or review.get('cpu_stage', {}).get('source_bad') != []):
        raise ValueError('numeric reader summary is incomplete')
    return review, {'reader_source_sha256': sha(reader_path), 'companion_source_sha256': sha(companion_path),
                    'reader_output_sha256': sha(review_path),
                    'raw_files': raw}


def recompute_reader(directory, receipt, expected):
    """Run the exact reader source; it validates the complete 42-tensor inventory."""
    reader_path, companion_path = HERE / 't17_prefix_numeric_read.py', HERE / 't17_r027_independent_cpu_review.py'
    module = runpy.run_path(str(reader_path), run_name='r027_numeric_reader_recompute')
    observed = module['read_actual'](receipt, reader_sha=sha(reader_path))
    if observed != expected:
        raise ValueError('saved numeric reader output differs from exact recomputation')
    return {'reader_source_sha256': sha(reader_path), 'companion_source_sha256': sha(companion_path),
            'reader_output_sha256': sha(HERE / 't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json'),
            'raw_tensor_paths': sorted(observed['raw_tensors'])}


def audit():
    directory = ROUNDS / RID
    if not directory.is_dir() or any(path.is_symlink() or path.stat().st_uid != os.geteuid()
                                     for path in (directory, *directory.rglob('*'))):
        raise ValueError('regular owned exact R027 evidence required')
    if any((directory / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256',
                                                     'review_batch55.json', 'batch.sh', 'source_tools')):
        raise ValueError('exact unprepared R027 required')
    status = json.loads((directory / 'status_batch55.json').read_bytes())
    if any(status.get(key) != value for key, value in EXPECTED_STATUS.items()):
        raise ValueError('exact completed R027 status required')
    if not terminal(588986, 122554334):
        raise ValueError('batch controller remains live')
    for arm in ('numeric_warm', 'numeric_cold'):
        identity = json.loads((directory / arm / 'process_identity.json').read_bytes())
        stopped = json.loads((directory / arm / 'stop_identity.json').read_bytes())
        if stopped != {'terminal': True, **identity} or not terminal(identity['pid'], identity['start_ticks']):
            raise ValueError('owned service remains live: ' + arm)
    receipt = json.loads((ROOT / 'runs/dev_D14' / ('launch_' + RID + '.json')).read_bytes())
    required_receipt = {'rid': RID, 'batch': BATCH, 'batch_pid': 588986, 'batch_pgid': 588986,
                        'diagnostic_only': True, 'FT_LM_CHUNK': 4096, 'cpu_stage_sha256': CPU_STAGE_SHA}
    if any(receipt.get(key) != value for key, value in required_receipt.items()):
        raise ValueError('exact R027 launch receipt required')
    stage, frozen = Path(receipt['source_stage']), Path(receipt['frozen_runner']).parent
    cpu_path = stage / 'cpu_validation.json'
    if sha(cpu_path) != CPU_STAGE_SHA:
        raise ValueError('CPU source proof changed')
    cpu = json.loads(cpu_path.read_bytes())
    if cpu.get('gpu_started') is not False or cpu.get('source_files') != receipt.get('source_files'):
        raise ValueError('CPU validation/source binding differs')
    for name, step in cpu.get('steps', {}).items():
        if step.get('returncode') != 0 or sha(stage / (name + '.log')) != step.get('log_sha256'):
            raise ValueError('CPU step changed: ' + name)
    for name, digest in receipt['source_files'].items():
        if sha(stage / name) != digest or sha(frozen / name) != digest or (stage / name).stat().st_mode & 0o222:
            raise ValueError('frozen runtime/source binding changed: ' + name)
    if sha(Path(receipt['wrapper'])) != receipt['wrapper_sha256']:
        raise ValueError('batch wrapper changed')
    for name, digest in TOOLS.items():
        if sha(ROOT / 'scripts' / name) != digest:
            raise ValueError('canonical D04 source changed: ' + name)
    raw = raw_files(directory)
    review, numeric_binding = load_review(directory, raw)
    numeric_binding.update(recompute_reader(directory, receipt, review))
    prior = ROUNDS / 'E2-R023-gate-T17' / 'round.json'
    if json.loads(prior.read_bytes()).get('verdict') != 'not_met':
        raise ValueError('R023 not_met must remain authoritative')
    return {'schema': 'ft_t17_r027_diagnostic_closure_review/v1', 'rid': RID, 'batch': BATCH,
            'diagnostic_only': True, 'original_T17_verdict': 'not_met_retained',
            'proposed_verdict': 'kept', 'receipt': receipt, 'status': status,
            'numeric_review': review, 'numeric_binding': numeric_binding, 'original_raw_files': raw,
            'batch_log_sha256': sha(ROUNDS / 'batch55.log'),
            'limits': ['Default-4096 numeric diagnostic only; R023 not_met remains authoritative.',
                       'No T17 acceptance, E2-base.1 admission, T10 rerun, or performance conclusion.']}


def close():
    review = audit()
    staged = HERE / 't17_r027_closure_review.json'
    if not staged.is_file() or json.loads(staged.read_bytes()) != review:
        raise ValueError('separately staged closure review differs')
    directory, receipt = ROUNDS / RID, review['receipt']
    frozen, stage = Path(receipt['frozen_runner']).parent, Path(receipt['source_stage'])
    binding = review['numeric_binding']
    if (sha(HERE / 't17_prefix_numeric_read.py') != binding['reader_source_sha256']
            or sha(HERE / 't17_r027_independent_cpu_review.py') != binding['companion_source_sha256']
            or sha(HERE / 't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json') != binding['reader_output_sha256']):
        raise ValueError('reader source or output changed after audit')
    for name, digest in receipt['source_files'].items():
        raw = (frozen / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('runtime source changed before archive: ' + name)
        write(directory / 'source_tools/runtime' / name, raw)
    for path in stage.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log'):
            write(directory / 'source_tools/launch_cpu' / path.name, path.read_bytes())
    for path in (HERE / 't17_r027_d04_close.py', HERE / 't17_prefix_numeric_read.py',
                 HERE / 't17_r027_independent_cpu_review.py',
                 HERE / 't17_prefix_numeric_E2-R027-diagnostic-T17_reader_v3.json', HERE / 't17_r027_closure_review.json'):
        write(directory / 'source_tools/closure' / path.name, path.read_bytes())
    write(directory / 'launch_receipt.json', encoded(receipt))
    write(directory / 'review_batch55.json', encoded(review))
    write(directory / 'batch.sh', Path(receipt['wrapper']).read_bytes())
    for name in TOOLS:
        write(directory / name, (ROOT / 'scripts' / name).read_bytes())
    metadata = {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T17',
                'title': 'Default-4096 prefix numeric diagnostic', 'parent': 'E2-R023-gate-T17',
                'base': {'code_version': 'E2-base@23f2e2c', 'commit': '23f2e2caa3395837c9474735ffc83321f3b9b5a1'},
                'candidate_commit': receipt['candidate_commit'], 'actual_runtime_commit': receipt['candidate_commit'],
                'experimental': {'diagnostic_only': True, 'FT_LM_CHUNK': 4096}, 'diagnostics': review,
                'results': review['numeric_review'], 'acceptance_limits': review['limits'],
                'proposed_verdict': 'kept', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [{'path': str(ROUNDS / 'batch55.log'), 'sha256': review['batch_log_sha256']}]}
    write(directory / 'round.json', encoded(metadata))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)],
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict',
                    '--new', 'kept', '--reason', 'Independent numeric CPU review accepts this diagnostic only; R023 not_met remains authoritative and no T17 acceptance is granted.',
                    '--by', 'Codex D04 diagnostic closure', '--evidence', 'review_batch55.json'], check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True)
    if any(sha(directory / name) != digest for name, digest in review['original_raw_files'].items()):
        raise ValueError('original raw evidence changed')
    if any(path.stat().st_mode & 0o222 for path in (directory, *directory.rglob('*'))):
        raise ValueError('closed diagnostic remains writable')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    options = parser.parse_args()
    if options.close:
        close()
    else:
        print(json.dumps(audit(), ensure_ascii=False))
