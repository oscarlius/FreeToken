import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).parents[1]
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('schedule_launch_test', HERE/'t16_d14_schedule_launch.py')
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


def test_launch_freezes_exact_sources_and_leaves_run_transition_to_atomic_helper(tmp_path, monkeypatch):
    stage = tmp_path/'stage'; stage.mkdir()
    (stage/'cpu_validation.json').write_text('CPU evidence')
    report = {'files': {'t16_d14_schedule_runner.py': 'runner'}}
    argv = ['python', '-u', str(stage/'t16_d14_schedule_runner.py')]
    helper = object()
    def reserve(actual_helper, batch, rid, actual, receipt, reserved):
        assert actual_helper is helper and batch == 60 and rid == 'E2-R032-gate-D14'
        assert '--run' not in actual
        assert actual[2] == str(tmp_path/'frozen/t16_d14_schedule_runner.py')
        assert reserved['source_files'] == report['files']
        assert reserved['candidate_commit'] == launch.CANDIDATE
        return {'state': 'launched'}
    life = SimpleNamespace(reserve_process=reserve)
    monkeypatch.setattr(launch, 'preflight', lambda _: (report, life, helper, argv, 'E2-R032-gate-D14', 60))
    monkeypatch.setattr(launch, 'load', lambda *_: SimpleNamespace(freeze=lambda *_: tmp_path/'frozen'))
    assert launch.launch(stage)['state'] == 'launched'


def test_preflight_ledger_change_stops_before_reservation(tmp_path, monkeypatch):
    numbers = iter((32, 33))
    life = SimpleNamespace(next_round=lambda _: next(numbers), verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: 60))
    monkeypatch.setattr(launch, 'read_stage', lambda _: {'files': {}})
    monkeypatch.setattr(launch, 'load', lambda *_: life)
    def run(argv, **kwargs):
        assert '--run' not in argv and kwargs['check'] is True
    monkeypatch.setattr(launch.subprocess, 'run', run)
    with pytest.raises(ValueError, match='ledger changed'):
        launch.preflight(tmp_path)


def test_preflight_rejects_round_outside_reserved_range(tmp_path, monkeypatch):
    life = SimpleNamespace(next_round=lambda _: 40, verified_module=lambda *_: SimpleNamespace(next_batch=lambda _: 60))
    monkeypatch.setattr(launch, 'read_stage', lambda _: {'files': {}})
    monkeypatch.setattr(launch, 'load', lambda *_: life)
    with pytest.raises(ValueError, match='reserved round range'):
        launch.preflight(tmp_path)


@pytest.fixture
def frozen_stage(tmp_path, monkeypatch):
    from t16_d14_schedule_stage import SOURCE_NAMES, TESTS
    stage = tmp_path/'stage'; stage.mkdir()
    root = tmp_path/'root'; root.mkdir()
    engine = tmp_path/'engine'; engine.mkdir()
    candidate = root/'wt/e2d14-ordinary-rewind/source.py'
    candidate.parent.mkdir(parents=True); candidate.write_bytes(b'committed engine')
    cpu_report = {'candidate_commit': launch.CANDIDATE, 'verdict': 'PASS',
                  'source_files': {'source.py': launch.sha(candidate)}}
    engine_proof = engine/'cpu_validation.json'
    engine_proof.write_text(json.dumps(cpu_report)); engine_proof.chmod(0o444)
    receipt = {'stage': str(engine), 'report': cpu_report, 'report_sha256': launch.sha(engine_proof)}
    for name in SOURCE_NAMES:
        target = stage/name; target.parent.mkdir(parents=True, exist_ok=True)
        if name in launch.PINNED or name == Path(launch.__file__).name:
            raw = (HERE/name).read_bytes()
        elif name == 'd14_schedule_cpu_receipt.json':
            raw = json.dumps(receipt).encode()
        else:
            raw = b'frozen source fixture'
        target.write_bytes(raw); target.chmod(0o444)
    steps = {}
    for name, text in (('regression', '70 passed in 0.3s\n'), ('d18_binding', '{"bound":true}\n')):
        log = stage/(name+'.log'); log.write_text(text); log.chmod(0o444)
        steps[name] = {'returncode': 0, 'log_sha256': launch.sha(log)}
    report = {'schema': 'ft_t16_d14_schedule_stage/v1', 'gpu_started': False,
              'requests_sent': False, 'verdict': 'PASS', 'passed': 70, 'tests': list(TESTS),
              'files': {name: launch.sha(stage/name) for name in SOURCE_NAMES}, 'steps': steps}
    proof = stage/'cpu_validation.json'; proof.write_text(json.dumps(report)); proof.chmod(0o444)
    for path in sorted(stage.rglob('*'), reverse=True):
        if path.is_dir(): path.chmod(0o555)
    stage.chmod(0o555)
    monkeypatch.setattr(launch, 'HERE', stage); monkeypatch.setattr(launch, 'ROOT', root)
    yield stage, engine_proof, candidate
    stage.chmod(0o755)
    for path in stage.rglob('*'): path.chmod(0o755 if path.is_dir() else 0o644)
    engine_proof.chmod(0o644)


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux file ownership and mode proof')
def test_read_stage_accepts_frozen_complete_cpu_proof(frozen_stage):
    assert launch.read_stage(frozen_stage[0])['passed'] == 70


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux file ownership and mode proof')
@pytest.mark.parametrize('failure', ['source', 'log', 'missing_test', 'failed_status', 'embedded_engine', 'candidate', 'writable_proof'])
def test_read_stage_rejects_changed_or_incomplete_evidence(frozen_stage, failure):
    stage, engine, candidate = frozen_stage
    proof = stage/'cpu_validation.json'
    if failure in ('source', 'log'):
        path = stage/('t16_d14_schedule_runner.py' if failure == 'source' else 'regression.log')
        path.chmod(0o644); path.write_bytes(path.read_bytes()+b'changed'); path.chmod(0o444)
    elif failure == 'candidate':
        candidate.write_bytes(b'changed source')
    elif failure == 'writable_proof':
        proof.chmod(0o644)
    else:
        report = json.loads(proof.read_bytes())
        if failure == 'missing_test': report['tests'].pop()
        elif failure == 'failed_status': report['verdict'] = 'FAIL'
        else:
            path = stage/'d14_schedule_cpu_receipt.json'; data = json.loads(path.read_bytes())
            data['report']['source_files']['source.py'] = '0'*64
            path.chmod(0o644); path.write_text(json.dumps(data)); path.chmod(0o444)
            report['files'][path.name] = launch.sha(path)
        proof.chmod(0o644); proof.write_text(json.dumps(report)); proof.chmod(0o444)
    with pytest.raises(ValueError): launch.read_stage(stage)
