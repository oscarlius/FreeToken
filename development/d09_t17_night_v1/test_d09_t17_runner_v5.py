import importlib.util
import json
import uuid
from pathlib import Path


RUNNER = Path(__file__).with_name('d09_t17_runner_v5.py')


def module():
    spec = importlib.util.spec_from_file_location('d09_t17_v5_test', RUNNER)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_filedry_runs_controller_child_and_releases_task_lock():
    runner = module()
    name = 'evidence_cpu_filedry_pytest_' + uuid.uuid4().hex
    terminal = runner.filedry_v5_e2e(name)
    data = json.loads(terminal.read_text())
    assert data['calls'] == 8 and len(data['services_cleaned']) == 6
    assert data['post_cleanup_closed'] and data['gpu_lock_released']
    assert all(x['cold_stable'] and x['hot_equals_cold'] for x in data['cells'])
    assert data['controller_child_chain']['controller']
    assert not (runner.HERE / name / 'task_owned_fake.lock').exists()


def test_filedry_rebind_failure_preserves_task_lock_and_has_no_closed_terminal():
    runner = module()
    name = 'evidence_cpu_filedry_pytest_failure_' + uuid.uuid4().hex
    try:
        runner.filedry_v5_e2e(name, fail_rebind=True)
        raise AssertionError('expected unsafe cleanup failure')
    except RuntimeError as exc:
        assert 'unsafe cleanup preserves lock' in str(exc)
    root = runner.HERE / name
    assert (root / 'task_owned_fake.lock').exists()
    assert (root / 'runs' / runner.RID / 'unsafe_cleanup.json').is_file()
    assert not (root / 'e2e_terminal.json').exists()
