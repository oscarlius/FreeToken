"""Review and seal only the measured R023 T17 counterexample as not_met."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-R023-gate-T17'
BATCH = 51
PID = 300919
START = 121959591
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
CANDIDATE = 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
READER_SHA = '44e02b4ca298f4ee8f64127c9698bb3c357fd1644cebe0eaa3863275e4618bcc'
APPEND_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
CLOSE_SHA = 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def terminal(pid, start=None):
    stat = Path('/proc') / str(pid) / 'stat'
    if not stat.exists():
        return True
    fields = stat.read_text().rpartition(') ')[2].split()
    if start is not None and int(fields[19]) != start:
        raise ValueError('observed PID identity was reused')
    return fields[0] == 'Z'


def audit():
    directory = ROUNDS / RID
    for path in (directory, *directory.parents, *directory.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink evidence path')
    if any(path.stat().st_uid != os.geteuid() for path in (directory, *directory.rglob('*'))):
        raise ValueError('foreign evidence owner')
    if any((directory / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256', 'review_batch51.json', 'batch.sh', 'source_tools')):
        raise ValueError('exact unprepared R023 round required')
    receipt = json.loads((ROOT / 'runs/dev_D14' / ('launch_' + RID + '.json')).read_text())
    expected = {'rid': RID, 'batch': BATCH, 'batch_pid': PID, 'batch_pgid': PID,
                'candidate_commit': CANDIDATE, 'parent_commit': PARENT,
                'cpu_stage_sha256': '530a49543c54c4a3b4e1abd130dcc33f150a98765c5d942d892a81d305cbaae8',
                'runner_sha256': '24928eae2ac36e79157db0a18b5f25086d576f5bda267462c2f7ff79b6d96070'}
    if any(receipt.get(key) != value for key, value in expected.items()) or not terminal(PID, START):
        raise ValueError('exact terminal launch identity differs')
    stage = Path(receipt['source_stage'])
    report = json.loads((stage / 'cpu_validation.json').read_text())
    if sha(stage / 'cpu_validation.json') != receipt['cpu_stage_sha256'] or report.get('gpu_started') is not False:
        raise ValueError('CPU stage binding differs')
    frozen = Path(receipt['frozen_runner']).parent
    for name, digest in receipt['source_files'].items():
        for root in (stage, frozen):
            path = root / name
            if path.is_symlink() or path.stat().st_mode & 0o222 or sha(path) != digest:
                raise ValueError('frozen source changed: ' + name)
    for name in ('helper_tests', 'gate_tests', 'raw_tests', 'byte_comparison', 'startup_spawn', 'build_inputs'):
        step = report[name]
        if step['returncode'] != 0 or sha(stage / (name + '.log')) != step['log_sha256']:
            raise ValueError('CPU proof log changed: ' + name)
    if sha(HERE / 't17_r023_read.py') != READER_SHA:
        raise ValueError('independent raw reader changed')
    reader = runpy.run_path(str(HERE / 't17_r023_read.py'), run_name='ft_r023_closure_reader')
    previous_stdin = sys.stdin
    output = io.StringIO()
    try:
        sys.stdin = io.StringIO(json.dumps(receipt))
        with contextlib.redirect_stdout(output):
            exec(compile(reader['PROGRAM'], 'R023_raw_CPU_audit', 'exec'), {'__name__': 'ft_r023_raw_cpu'})
    finally:
        sys.stdin = previous_stdin
    observed = json.loads(output.getvalue())
    status = observed['status']
    if (status.get('rid'), status.get('batch'), status.get('batch_pid'), status.get('state')) != (RID, BATCH, PID, 'failed'):
        raise ValueError('terminal measured failure status differs')
    if observed['cuda_initialized'] or observed['tokens_equal'] or observed['text_equal']:
        raise ValueError('original measured counterexample did not independently recompute')
    if observed['first_token_fork'] != 36 or not all(observed['restore_roles'].values()):
        raise ValueError('measured output fork or separate restore proof differs')
    arms = {}
    first_args = None
    first_extensions = None
    base = runpy.run_path(str(frozen / 't16_full_tail_base_runner.py'), run_name='ft_r023_args_auditor')
    lock = base['LOCK']
    if lock.exists() and json.loads(lock.read_text()).get('owner') == RID:
        raise ValueError('owned T17 lock still exists')
    for name, pid in (("start-short-child-8192_warm", 301317), ("start-short-child-8192_short_cold", 317673)):
        arm = directory / name
        args = json.loads((arm / 'serve_args.txt').read_text())
        if re.findall(r'\.pid=(\d+)', args['_unique_suffix']) != [str(pid)] or not terminal(pid):
            raise ValueError('owned service is live or ambiguous')
        if CANDIDATE not in (arm / 'ENV.txt').read_text() or args['mamba_host_slots'] != '0':
            raise ValueError('actual service source or device-only contract differs')
        extensions = json.loads((arm / 'compiled_extensions.json').read_text())
        if first_args is not None:
            base['strict_args'](first_args, args, {})
            if extensions != first_extensions:
                raise ValueError('actual extension bindings differ')
        first_args, first_extensions = args, extensions
        arms[name] = {'owned_service_pid': pid}
    log = ROUNDS / 'batch51.log'
    text = log.read_text()
    if any('STOP PASS owned_pid=' + str(pid) + ' gpu=4' not in text for pid in (301317, 317673)):
        raise ValueError('owned service stop receipts missing')
    if sha(receipt['wrapper']) != receipt['wrapper_sha256']:
        raise ValueError('actual batch wrapper changed')
    original = {p.relative_to(directory).as_posix(): sha(p) for p in directory.rglob('*') if p.is_file()}
    return {'schema': 'ft_t17_counterexample_review/v1', 'rid': RID, 'batch': BATCH,
            'proposed_verdict': 'not_met', 'classification': 'measured output and computed-state inequality',
            'observed': observed, 'arms': arms, 'receipt': receipt,
            'original_raw_files': original, 'batch_log_sha256': sha(log),
            'limits': ['Only the first 8192 short cold-vs-hit comparison completed; remaining cases were not measured.',
                       'Device restore-copy correctness and retained long-child initialization do not prove continuation equivalence.',
                       'Service PID start ticks were not archived; terminal identity evidence is bounded.']}


def close():
    result = audit()
    if json.loads((HERE / 'review.json').read_text()) != result:
        raise ValueError('staged independent review no longer recomputes')
    cpu = json.loads((HERE / 'closure_cpu.json').read_text())
    if cpu.get('returncode') != 0 or cpu.get('close_sha256') != CLOSE_SHA or sha(HERE / 'tests.log') != cpu.get('tests_log_sha256'):
        raise ValueError('actual Linux closure regression proof missing')
    directory = ROUNDS / RID
    tool_names = ('round_json_append.py', 'round_close.py', 'round_close.sh')
    if sha(HERE / 'round_json_append.py') != APPEND_SHA or sha(HERE / 'round_close.py') != CLOSE_SHA:
        raise ValueError('D04 writer or tested closure source changed')
    if (ROOT / 'scripts/round_json_append.py').read_bytes() != (HERE / 'round_json_append.py').read_bytes():
        raise ValueError('D04 canonical append writer differs')
    receipt = result['receipt']
    for origin, target in ((Path(receipt['frozen_runner']).parent, 'runtime_source'),
                           (Path(receipt['source_stage']), 'cpu_source'), (HERE, 'closure_source')):
        for path in origin.rglob('*'):
            if path.is_symlink():
                raise ValueError('archive source symlink')
            if path.is_file() and '__pycache__' not in path.parts:
                write(directory / 'source_tools' / target / path.relative_to(origin), path.read_bytes())
    write(directory / 'review_batch51.json', encoded(result))
    write(directory / 'source_tools/launch_receipt.json', encoded(receipt))
    write(directory / 'batch.sh', Path(receipt['wrapper']).read_bytes())
    for name in tool_names:
        write(directory / name, (HERE / name).read_bytes())
    metadata = {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T17',
                'title': 'D14 first measured prefix-hit continuation counterexample', 'parent': 'E2-R022-gate-D14',
                'base': {'commit': PARENT, 'code_version': 'E2-base@23f2e2c'},
                'experimental': {'candidate_commit': CANDIDATE, 'worktree': '/data2/FreeToken/wt/e2d14'},
                'serve': {'arms': result['arms']}, 'design': {'batch': BATCH, 'planned_boundaries': [8192, 12416, 18944, 12736]},
                'results': result['observed'], 'acceptance_limits': result['limits'],
                'diagnostics': {'independent_review_sha256': sha(directory / 'review_batch51.json'),
                                'original_raw_files': result['original_raw_files'], 'cpu_stage_sha256': receipt['cpu_stage_sha256']},
                'proposed_verdict': 'not_met', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [{'path': str(ROUNDS / 'batch51.log'), 'sha256': result['batch_log_sha256']}]}
    write(directory / 'round.json', encoded(metadata))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)],
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict',
                    '--new', 'not_met', '--reason', 'Same exact 8257 input: both 128-token generations terminate, but the first token fork is index36 and three computed-state roles differ. Four-role D2D restore passes separately. This is a measured counterexample; D14/T17 is not accepted.',
                    '--evidence', 'review_batch51.json', 'start-short-child-8192_short_comparison.json',
                    '--by', 'Codex mainline under CODEX_HANDOFF_20261004b T17'], check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True)
    if any(sha(directory / name) != digest for name, digest in result['original_raw_files'].items()):
        raise ValueError('original raw bytes changed')
    if any(path.stat().st_mode & 0o222 for path in (directory, *directory.rglob('*'))):
        raise ValueError('R023 closure is not read-only')
    return {'rid': RID, 'verdict': 'not_met', 'round_sha256': sha(directory / 'round.json'),
            'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'review_sha256': sha(directory / 'review_batch51.json'),
            'original_raw_files_verified': len(result['original_raw_files'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    options = parser.parse_args()
    if sys.platform != 'linux':
        raise SystemExit('actual Linux evidence host required')
    print(json.dumps(close() if options.close else audit(), ensure_ascii=False, sort_keys=True))
