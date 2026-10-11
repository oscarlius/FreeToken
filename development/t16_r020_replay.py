"""Read-only CPU audit of the four actual R020 arms and archived protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType

RID = 'E2-R020-gate-D06'
BATCH = 48
PID = 3817162
DIRECTORY = Path('/data2/_shared/runs/ft_rounds') / RID
RUNNER_SHA = 'd29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1'
BASE_SHA = '66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125'
RECEIPT_SHA = '913d82b367dd8c0f736b7767f323c7e1075cbc2d327ad4b43a515ce8f1d221b8'
WRAPPER_SHA = '73e6ab5ed555aef2979c9b7c501df91635030e7a32f098192b78df4366ed0b0e'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
NEW = '03692633df48456fb0baa78de7b64e5628a12ab1'
ARMS = tuple(name + '_b48' for name in ('PARENT', 'NEW', 'PARENT_P', 'NEW_P'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError('missing actual artifact: ' + str(path))
    return path


def load(path):
    return json.loads(require(path).read_text(encoding='utf-8'))


def terminal(pid):
    path = Path('/proc') / str(pid) / 'stat'
    return not path.exists() or path.read_text().rpartition(') ')[2].split()[0] == 'Z'


def audit():
    d = DIRECTORY
    if d.is_symlink() or d.resolve(strict=True) != d:
        raise ValueError('canonical actual round required')
    status = load(d / 'status_batch48.json')
    if any(status.get(k) != v for k, v in {'rid': RID, 'batch': BATCH,
            'batch_pid': PID, 'candidate_case': 'D06', 'gate': 'D06',
            'state': 'complete_measurements_pending_review'}.items()) or not terminal(PID):
        raise ValueError('R020 measurements must be terminal before audit')
    receipt = Path('/data2/FreeToken/runs/dev_D06/launch_' + RID + '.json')
    if digest(require(receipt)) != RECEIPT_SHA:
        raise ValueError('actual launch receipt changed')
    raw = load(d / 'gate_batch48.json')
    binding = load(d / 'candidate_binding.json')
    for data in (raw, binding):
        if data.get('parent_commit') != PARENT or data.get('new_commit') != NEW:
            raise ValueError('actual candidate/parent identity differs')
    if raw.get('arms') != list(ARMS) or raw.get('gate') != 'D06' or raw.get('candidate_case') != 'D06':
        raise ValueError('four actual D06 arms required')
    if binding.get('case') != 'D06' or binding.get('compiled_extensions') != raw.get('compiled_extensions'):
        raise ValueError('archived candidate binding differs')
    sources = {'t16_candidate_runner_full_tail.py': d / 'runner_batch48.py',
               't16_full_tail_base_runner.py': d / 'base_runner_batch48.py'}
    for name, expected in (('t16_candidate_runner_full_tail.py', RUNNER_SHA),
                           ('t16_full_tail_base_runner.py', BASE_SHA)):
        if digest(require(sources[name])) != expected:
            raise ValueError('archived source bytes differ: ' + name)
    if digest(require(d / 'batch48.sh')) != WRAPPER_SHA:
        raise ValueError('actual batch wrapper differs')
    parser = Path('/data2/FreeToken/scripts/serve_args_diff.py')
    source = require(parser).read_bytes()
    if hashlib.md5(source).hexdigest() != 'ce123cb0af201d99baac91f7f8e4f8c7':
        raise ValueError('reviewed args parser differs')
    parser_scope = {'__file__': str(parser), '__name__': 'r020_parser'}
    exec(compile(source, str(parser), 'exec'), parser_scope)
    arm_hashes = {}
    for arm in ARMS:
        files = {name: require(d / arm / name) for name in (
            'det.json', 'tax.json', 'prefill_seq.txt', 'serve.log',
            'serve_args.txt', 'ENV.txt', 'SERVE_CMD.txt')}
        arm_hashes[arm] = {name: digest(path) for name, path in files.items()}
    with tempfile.TemporaryDirectory(prefix='r020-archival-cpu-') as temporary:
        stage = Path(temporary)
        for name, path in sources.items():
            (stage / name).write_bytes(path.read_bytes())
        runner = stage / 't16_candidate_runner_full_tail.py'
        selftest = subprocess.run([sys.executable, str(runner), '--self-test'],
            text=True, capture_output=True, timeout=60, check=True)
        module = ModuleType('r020_actual_archival_runner')
        module.__file__ = str(runner)
        exec(compile(runner.read_bytes(), str(runner), 'exec'), module.__dict__)
        replay = object.__new__(module.CandidateRunner)
        replay.parser = parser_scope['parse']
        result = module.CandidateRunner.compare(replay, *(d / arm for arm in ARMS))
        result = json.loads(json.dumps(result, allow_nan=False))
        if result != raw.get('layer_major'):
            raise ValueError('recomputed actual data differs from gate summary')
        if result['prefill']['parent_rows'] != 13 or result['prefill']['new_rows'] != 13:
            raise ValueError('complete D02 tail coverage required')
    return {'schema': 'ft_t16_r020_archival_cpu_replay/v1', 'rid': RID, 'batch': BATCH,
        'scope': 'read-only actual archival CPU recomputation; no GPU or resource gate',
        'gate_sha256': digest(d / 'gate_batch48.json'),
        'candidate_binding_sha256': digest(d / 'candidate_binding.json'),
        'runner_sha256': RUNNER_SHA, 'base_runner_sha256': BASE_SHA,
        'receipt_sha256': RECEIPT_SHA, 'wrapper_sha256': WRAPPER_SHA,
        'selftest_output': selftest.stdout.strip(), 'arms': arm_hashes,
        'recomputed': result, 'matched_gate_outcomes': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', action='store_true')
    options = parser.parse_args()
    if not options.audit or sys.platform != 'linux':
        parser.error('--audit on the actual Linux host required')
    print(json.dumps(audit(), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
