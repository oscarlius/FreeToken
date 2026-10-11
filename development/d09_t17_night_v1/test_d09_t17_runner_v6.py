import importlib.util
import json
import uuid
from pathlib import Path


RUNNER = Path(__file__).with_name('d09_t17_runner_v6.py')


def module():
    spec = importlib.util.spec_from_file_location('d09_t17_v6_test', RUNNER)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_filedry_v6_controller_child_success_releases_task_lock():
    runner = module()
    name = 'evidence_cpu_filedry_v6_pytest_' + uuid.uuid4().hex
    terminal = runner.filedry_v6_e2e(name)
    data = json.loads(terminal.read_text())
    assert data['calls'] == 8 and len(data['services_cleaned']) == 6
    assert data['post_cleanup_closed'] and data['gpu_lock_released']
    assert data['controller_child_chain']['sealed_t16']
    assert not (runner.HERE / name / 'task_owned_fake.lock').exists()


def test_actual_oserror_rebind_failure_is_unsafe_and_retains_task_lock():
    runner = module()
    name = 'evidence_cpu_filedry_v6_oserror_' + uuid.uuid4().hex
    try:
        runner.filedry_v6_e2e(name, fail_rebind=True)
        raise AssertionError('expected OSError(98) rebind failure')
    except RuntimeError as exc:
        assert 'unsafe cleanup preserves lock' in str(exc)
    root = runner.HERE / name
    unsafe = json.loads((root / 'runs' / runner.RID / 'unsafe_cleanup.json').read_text())
    assert (root / 'task_owned_fake.lock').exists()
    assert unsafe['outcome'] == 'failed_harness'
    assert unsafe['post_cleanup_closed'] is False
    assert unsafe['product_acceptance'] is False
    assert not (root / 'runs' / runner.RID / 'terminal.json').exists()
    assert not (root / 'e2e_terminal.json').exists()
