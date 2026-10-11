"""Seal only the proven R021 harness failure; retain every existing raw byte."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-R021-gate-D14'
BATCH = 49
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
NEW = 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42'
WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
ERROR = "ValueError('prefill count mismatch: old=13/12, new=13/13')"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def terminal(pid):
    path = Path('/proc') / str(pid) / 'stat'
    return not path.exists() or path.read_text().rpartition(') ')[2].split()[0] == 'Z'


def close():
    directory = ROUNDS / RID
    for path in [directory, *directory.rglob('*')]:
        if path.is_symlink() or path.stat().st_uid != os.geteuid():
            raise ValueError('foreign or symlink evidence')
    if any((directory / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256', 'failure_review.json', 'batch.sh')):
        raise ValueError('R021 already prepared or closed; inspect retained evidence')
    status = json.loads((directory / 'status_batch49.json').read_text())
    if (status.get('state'), status.get('rid'), status.get('batch'), status.get('batch_pid'), status.get('error')) != ('failed', RID, 49, 120974, ERROR):
        raise ValueError('exact terminal R021 harness failure required')
    receipt_path = ROOT / 'runs/dev_D14' / ('launch_' + RID + '.json')
    receipt = json.loads(receipt_path.read_text())
    if any(receipt.get(k) != v for k, v in {'rid': RID, 'batch': 49, 'batch_pid': 120974, 'parent_commit': PARENT, 'candidate_commit': NEW}.items()):
        raise ValueError('launch receipt identity differs')
    if not terminal(120974):
        raise ValueError('batch still alive')
    arms = {}
    for name, pid in [('PARENT_b49', 121678), ('NEW_b49', 141134)]:
        arm = directory / name
        args = (arm / 'serve_args.txt').read_text()
        if re.findall(r'\.pid=(\d+)', args) != [str(pid)] or not terminal(pid):
            raise ValueError('owned service is live or ambiguous')
        expected = PARENT if name.startswith('PARENT') else NEW
        if expected not in (arm / 'ENV.txt').read_text():
            raise ValueError('source binding differs')
        for name_required in ('SERVE_CMD.txt', 'serve.log', 'serve_args.txt', 'ENV.txt'):
            if not (arm / name_required).stat().st_size:
                raise ValueError('empty service evidence')
        arms[name] = {'owned_service_pid': pid}
    if any((directory / name).exists() for name in ('PARENT_P_b49', 'NEW_P_b49', 'gate_batch49.json')):
        raise ValueError('unexpected production-arm or successful gate evidence')
    before = {p.relative_to(directory).as_posix(): sha(p) for p in directory.rglob('*') if p.is_file()}
    tool_names = ('round_json_append.py', 'round_close.py', 'round_close.sh')
    sources = {name: (ROOT / 'scripts' / name).read_bytes() for name in tool_names}
    if hashlib.sha256(sources['round_json_append.py']).hexdigest() != WRITER_SHA:
        raise ValueError('reviewed D04 writer changed')
    for name, data in sources.items():
        if data != (Path(__file__).parent / name).read_bytes():
            raise ValueError('local-to-server D04 tool binding differs: ' + name)
    batch_log = ROUNDS / 'batch49.log'
    text = batch_log.read_text()
    if ERROR.removeprefix('ValueError(').removesuffix(')').strip("'") not in text or text.count('STOP PASS') != 2:
        raise ValueError('failure and two owned stops are not retained')
    frozen = Path(receipt['frozen_runner']).parent
    stage = Path(receipt['source_stage'])
    raw_bindings = {'receipt_sha256': sha(receipt_path), 'raw_files': before,
                    'diagnosis': 'R021 live comparator omitted D14 from parent full-tail card whitelist; observed parent/new are both 13 rows.',
                    'independent_report': '/root/d14_gate_review reported FAIL; four-arm gate incomplete',
                    'missing_arms': ['PARENT_P_b49', 'NEW_P_b49']}
    put(directory / 'failure_review.json', encoded(raw_bindings))
    put(directory / 'batch.sh', (directory / 'batch49.sh').read_bytes())
    tools = directory / 'failure_tools'
    tools.mkdir()
    for source in [Path(__file__), *[frozen / name for name in ('t16_d14_runner.py', 't16_candidate_runner_full_tail.py', 't16_full_tail_base_runner.py')],
                   stage / 't16_candidate_launch_full_tail.py', stage / 'cpu_validation.json', receipt_path]:
        put(tools / source.name, source.read_bytes())
    for name, data in sources.items():
        put(directory / name, data)
    metadata = {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T16', 'title': 'D14 T16 failed harness; complete four-arm gate not run',
                'parent': 'E2-pre-gate-D00', 'base': {'commit': PARENT, 'code_version': 'E2-base@23f2e2c', 'worktree': '/data2/FreeToken/wt/e2base'},
                'experimental': {'candidate_commit': NEW, 'worktree': '/data2/FreeToken/wt/e2d14'},
                'serve': {'arms': arms}, 'design': {'batch': 49, 'planned_arms': ['PARENT_b49', 'NEW_b49', 'PARENT_P_b49', 'NEW_P_b49']},
                'anomalies': [{'kind': 'failed_harness', 'reason': ERROR, 'evidence': ['status_batch49.json', 'failure_review.json']}],
                'diagnostics': raw_bindings, 'proposed_verdict': 'failed_harness', 'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [{'path': str(batch_log), 'sha256': sha(batch_log)}]}
    put(directory / 'round.json', encoded(metadata))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)],
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict',
                    '--new', 'failed_harness', '--reason', 'T16 live parent-tail comparison omitted D14; both observed D0 arms have 13 rows, but two production arms were never run. Original raw evidence retained.',
                    '--evidence', 'status_batch49.json', 'failure_review.json', '--by', 'Codex mainline under CODEX_HANDOFF_20261004b section 1.2'], check=True)
    if any(sha(directory / name) != digest for name, digest in before.items()):
        raise ValueError('original raw bytes changed')
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True)
    if any(p.stat().st_mode & 0o222 for p in [directory, *directory.rglob('*')]):
        raise ValueError('failure closure is not read-only')
    return {'rid': RID, 'verdict': 'failed_harness', 'round_sha256': sha(directory / 'round.json'),
            'manifest_sha256': sha(directory / 'MANIFEST.sha256'), 'original_files_verified': len(before)}


if __name__ == '__main__':
    if sys.platform != 'linux':
        raise SystemExit('Linux exact evidence host required')
    print(json.dumps(close(), sort_keys=True))
