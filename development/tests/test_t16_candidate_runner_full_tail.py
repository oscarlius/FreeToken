import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


adapter_path = Path(__file__).resolve().parents[1] / 't16_candidate_runner_full_tail.py'
if not adapter_path.is_file():
    adapter_path = adapter_path.with_name('t16_candidate_runner.py')
spec = importlib.util.spec_from_file_location('t16_candidate_runner_full_tail', adapter_path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def options(case='D03-continuation', run=False):
    return SimpleNamespace(case=case, gate=None, rid='E2-R999-gate-' + runner.CASES[case]['card'],
        batch=999, candidate_commit=runner.CASES[case]['new_commit'], run=run)


@pytest.mark.parametrize('field,value', [('rid', 'E2-R002-gate-D06'), ('rid', '../E2-R999-gate-D03'),
    ('candidate_commit', 'f5067bb'), ('candidate_commit', '0' * 40), ('batch', 0), ('batch', True)])
def test_identity_rejects_alias_wrong_card_and_invalid_batch(field, value):
    opts = options()
    setattr(opts, field, value)
    with pytest.raises(ValueError):
        runner.validate_identity(opts)


def make_runner(monkeypatch, tmp_path, case='D03-continuation', run=False):
    monkeypatch.setattr(runner, 'ROUNDS', tmp_path)
    monkeypatch.setattr(runner, 'ROOT', tmp_path / 'source')
    monkeypatch.setattr(runner, 'HERE', tmp_path)
    monkeypatch.setattr(runner, 'WRAPPERS', tmp_path)
    monkeypatch.setattr(runner.base['runpy'], 'run_path', lambda _: {'parse': lambda _: {}})
    made = runner.CandidateRunner(options(case, run))
    made.directory = tmp_path / made.options.rid
    made.status = made.directory / 'status_batch999.json'
    monkeypatch.setattr(made, 'gate', lambda *_: None)
    monkeypatch.setattr(made, 'compiled_extensions', lambda *_: {'cpu': {'sha256': 'same'}})
    monkeypatch.setitem(runner.base, 'has_d02_prefill_tail', lambda *_: True)
    def command(argv, **_):
        return made.case['parent_commit'] if argv[0] == 'git' else ''
    monkeypatch.setitem(runner.base, 'command', command)
    probes = tmp_path / 'probes'
    probes.mkdir()
    (probes / 'probe.py').write_bytes(b'probe')
    monkeypatch.setitem(runner.base, 'SCR', probes)
    monkeypatch.setitem(runner.base, 'TOOL_MD5', {'probe.py': runner.hashlib.md5(b'probe').hexdigest()})
    return made


def test_preflight_has_no_reservation_directory_lock_or_model_launch(monkeypatch, tmp_path):
    made = make_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(made, 'lock_take', lambda: pytest.fail('dry run acquired GPU lock'))
    monkeypatch.setattr(made, 'run_arm', lambda *_: pytest.fail('dry run launched a model'))
    made.execute()
    assert not made.directory.exists()


@pytest.mark.parametrize('failure', ['parent', 'extensions', 'tail', 'probes', 'existing'])
def test_prerequisite_failures_never_create_round_or_take_lock(monkeypatch, tmp_path, failure):
    made = make_runner(monkeypatch, tmp_path, run=True)
    monkeypatch.setattr(made, 'lock_take', lambda: pytest.fail('failed prerequisite acquired GPU lock'))
    if failure == 'parent':
        monkeypatch.setitem(runner.base, 'command', lambda *_args, **_kwargs: 'bad-parent')
    elif failure == 'extensions':
        monkeypatch.setattr(made, 'compiled_extensions', lambda wt: {'cpu': {'sha256': wt.name}})
    elif failure == 'tail':
        monkeypatch.setitem(runner.base, 'has_d02_prefill_tail', lambda *_: False)
    elif failure == 'probes':
        monkeypatch.setitem(runner.base, 'TOOL_MD5', {'probe.py': 'wrong'})
    else:
        made.directory.mkdir()
        (made.directory / 'history').write_text('sealed')
    with pytest.raises(ValueError):
        made.execute()
    if failure == 'existing':
        assert (made.directory / 'history').read_text() == 'sealed'
    else:
        assert not made.directory.exists()


@pytest.mark.parametrize('case,expected_count', [('D03-continuation', 8), ('D06', 4), ('D07', 4)])
def test_declared_arm_coverage_and_pending_review(monkeypatch, tmp_path, case, expected_count):
    made = make_runner(monkeypatch, tmp_path, case, True)
    (tmp_path / f'batch999_{made.options.rid}_python.sh').write_text('owned wrapper')
    ownership = []
    monkeypatch.setattr(made, 'lock_take', lambda: ownership.append('take'))
    monkeypatch.setattr(made, 'lock_release', lambda: ownership.append('release'))
    monkeypatch.setattr(made, 'stop', lambda: None)
    seen = []
    def arm(name, wt, commit, d0, layer_major=True, **kwargs):
        seen.append((name, wt.name, commit, d0, layer_major, kwargs.get('cases')))
        return made.directory / name
    monkeypatch.setattr(made, 'run_arm', arm)
    monkeypatch.setattr(made, 'compare', lambda *_: {'verified': True})
    made.execute()
    assert ownership == ['take', 'release']
    assert len(seen) == expected_count
    assert [a[3] for a in seen] == [True, True, False, False] * (expected_count // 4)
    if case == 'D03-continuation':
        assert all(not a[4] and [x[2] for x in a[5]] == [2000, 32052] for a in seen[4:])
    status = json.loads(made.status.read_text())
    assert status['state'] == 'complete_measurements_pending_review'
    assert status['rid'] == made.options.rid
    binding = json.loads((made.directory / 'candidate_binding.json').read_text())
    assert binding['new_commit'] == made.case['new_commit']
    assert binding['base_runner_sha256'] == runner.BASE_SHA256


def test_default_environment_isolates_all_dev_flags_and_restores_gpu_visibility(monkeypatch, tmp_path):
    made = make_runner(monkeypatch, tmp_path)
    for key in ('FT_DEV_ROUTE_TRACE', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_D0', 'FT_D3_DUMP', 'CUDA_VISIBLE_DEVICES'):
        monkeypatch.setenv(key, 'bad-inherited-value')
    env = made.environment(tmp_path)
    assert env['CUDA_VISIBLE_DEVICES'] == '0'
    assert not any(k.startswith(('FT_DEV_', 'FT_D3_')) for k in env)


def test_real_d0_arm_keeps_only_its_owned_measurement_flags(monkeypatch, tmp_path):
    made = make_runner(monkeypatch, tmp_path, 'D07', True)
    made.directory.mkdir()
    monkeypatch.setattr(made, 'gate', lambda *_: 'verified source fixture')
    for key in ('FT_DEV_ROUTE_TRACE', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_D0',
                'FT_DEV_D0_PATH', 'FT_D3_DUMP'):
        monkeypatch.setenv(key, 'bad-inherited-value')
    captured = {}

    class ReachedOwnedLaunch(Exception):
        pass

    def launch(argv, **kwargs):
        captured.update(argv=argv, **kwargs)
        raise ReachedOwnedLaunch

    monkeypatch.setattr(runner.base['subprocess'], 'Popen', launch)
    wt = tmp_path / 'candidate'
    with pytest.raises(ReachedOwnedLaunch):
        made.run_arm('D0_owned', wt, made.case['new_commit'], True)
    env = captured['env']
    arm = made.directory / 'D0_owned'
    assert {k: v for k, v in env.items() if k.startswith(('FT_DEV_', 'FT_D3_'))} == {
        'FT_DEV_D0': '1', 'FT_DEV_D0_PATH': str(arm / 'd0')}
    assert env['CUDA_VISIBLE_DEVICES'] == '0'
    assert captured['cwd'] == wt
    assert captured['start_new_session'] is True
    command = (arm / 'SERVE_CMD.txt').read_text()
    assert 'FT_DEV_D0=1' in command and 'bad-inherited-value' not in command


def test_directory_collision_after_preflight_never_writes_foreign_status(monkeypatch, tmp_path):
    made = make_runner(monkeypatch, tmp_path, run=True)
    (tmp_path / f'batch999_{made.options.rid}_python.sh').write_text('owned wrapper')
    def take_lock():
        made.directory.mkdir()
        (made.directory / 'foreign_history').write_text('keep')
    monkeypatch.setattr(made, 'lock_take', take_lock)
    released = []
    monkeypatch.setattr(made, 'lock_release', lambda: released.append(True))
    monkeypatch.setattr(made, 'stop', lambda: None)
    with pytest.raises(FileExistsError):
        made.execute()
    assert list(made.directory.iterdir()) == [made.directory / 'foreign_history']
    assert released == [True]
