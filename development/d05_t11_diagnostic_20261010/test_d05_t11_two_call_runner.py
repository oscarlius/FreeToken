import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('d05runner', HERE/'d05_t11_two_call_runner.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def test_plan_is_exactly_two_calls_and_uses_retained_t11_binding():
    plan = m.plan()
    assert plan['generation_calls'] == 2 and plan['services'] == 1
    assert [x['role'] for x in plan['calls']] == ['uid7_target', 'uid8_followup']
    assert plan['calls'][1]['only_after'] == 'donor_and_cold_P_state_sha256_equal'


def test_full_logical_state_gate_accepts_equal_and_rejects_difference(tmp_path):
    equal = tmp_path/'equal'; m._write_fake_dump(equal, donor=b'P', cold=b'P')
    assert m.require_equal_p_state(equal, donor_uid=7, cold_uid=8)
    different = tmp_path/'different'; m._write_fake_dump(different, donor=b'P', cold=b'Q')
    try: m.require_equal_p_state(different, donor_uid=7, cold_uid=8)
    except m.FailedHarness as exc: assert 'donor/cold P-state hash differs' in str(exc)
    else: raise AssertionError('mismatched P state must fail before output')


def test_filedry_exercises_materialization_fake_child_and_owned_cleanup(tmp_path):
    result = m.filedry(tmp_path/'dry')
    assert result['status'] == 'CPU_FILEDRY_READY_NOT_GPU_ADMITTED'
    assert len(result['calls_materialized']) == 2
    assert result['events'][-1]['event'] == 'cleanup'
    assert result['gpu_started'] is False and result['http_sent'] is False


def test_run_requires_sealed_root_admission_before_any_effects(tmp_path):
    admission = tmp_path/'admission.json'; admission.write_text(json.dumps({'root_approved': False}))
    got = subprocess.run([sys.executable, str(HERE/'d05_t11_two_call_runner.py'), '--run', '--admission', str(admission)], text=True, capture_output=True)
    assert got.returncode != 0 and 'root-sealed admission required' in got.stderr


def test_controller_child_receipt_binds_exact_fresh_rid_and_child_argv(tmp_path):
    admission = tmp_path/'sealed_admission.json'; admission.write_text('{}')
    receipt = tmp_path/'launch.json'
    argv = m.child_argv(admission, receipt)
    import hashlib
    receipt.write_text(json.dumps({'schema': 'ft_d05_t11_controller_child/v1', 'rid': m.RID,
                                   'candidate': m.CANDIDATE, 'controller_birth': {'pid': 1, 'start_ticks': 2},
                                   'child_argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest()}))
    assert m.require_child_receipt(receipt, admission)['rid'] == m.RID
    receipt.write_text(json.dumps({'schema': 'ft_d05_t11_controller_child/v1', 'rid': m.RID,
                                   'candidate': m.CANDIDATE, 'controller_birth': {'pid': 1}, 'child_argv_sha256': 'wrong'}))
    try: m.require_child_receipt(receipt, admission)
    except RuntimeError as exc: assert 'controller receipt differs' in str(exc)
    else: raise AssertionError('wrong child argv binding must be rejected')
