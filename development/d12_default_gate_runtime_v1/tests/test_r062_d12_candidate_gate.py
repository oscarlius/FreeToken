import importlib.util
from pathlib import Path
import pytest

SOURCE = Path(__file__).parents[1] / "r062_d12_candidate_gate.py"
spec = importlib.util.spec_from_file_location("r062_gate", SOURCE)
m = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m)


def test_final_candidate_is_bound_but_run_stays_fail_closed():
    assert m.FINAL_CANDIDATE_COMMIT == "8f6a912ea6066f192c37dc74435efc9da0c7591c"
    assert m.require_final_candidate() == m.FINAL_CANDIDATE_COMMIT
    with pytest.raises(RuntimeError, match="no executable runner"):
        m.main(["--run"])


def test_final_binding_requires_exact_commit_and_keeps_full_protocol_contract(monkeypatch):
    final = "1" * 40
    monkeypatch.setattr(m, "FINAL_CANDIDATE_COMMIT", final)
    binding = m.candidate_binding(final)
    assert binding["parent_commit"] == "effb9969706922ddad9e59b96377e46469ebe97f"
    assert binding["candidate_worktree"] == "/data2/FreeToken/wt/e2d12-short-suffix"
    assert binding["arms"] == ["PARENT_D0OFF", "CANDIDATE_D0OFF", "PARENT_D0ON", "CANDIDATE_D0ON"]
    assert binding["config"] == {"kv_reserve_tokens": 98304, "max_seq_len_override": 98304, "memory_ratio": 0.88}
    assert binding["native_reuse"]["source_commit"] is None
    assert all(binding["disabled"].values())
    with pytest.raises(RuntimeError, match="differs"):
        m.candidate_binding("2" * 40)


def test_protocol_and_owned_lifecycle_inputs_are_explicit_closure_members():
    expected = {"r062_t16_full_runner.py", "r062_owned_launch.py"}
    assert expected <= set(m.SOURCE_CLOSURE)


def test_actual_full_runner_and_owned_launch_are_rebound_but_missing_native_provenance_blocks_execution(monkeypatch):
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / filename)
        module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module
    runner = load("r062_full_runner", "r062_t16_full_runner.py")
    owned = load("r062_owned", "r062_owned_launch.py")
    assert runner.ASSIGNED_RID == "E2-R062-gate-D12"
    assert runner.CASES["D12"]["new_wt"] == "e2d12-short-suffix"
    assert runner.CASES["D12"]["new_commit"] == m.FINAL_CANDIDATE_COMMIT
    assert owned.SPECS["D12"] == (runner.ASSIGNED_RID, m.FINAL_CANDIDATE_COMMIT, "r062_t16_full_runner.py")
    assert len(runner.CANDIDATE_NATIVE_PROVENANCE_SHA256) == 64
    monkeypatch.setattr(runner, "CANDIDATE_NATIVE_PROVENANCE_SHA256", None)
    with pytest.raises(ValueError, match="provenance SHA is pending"):
        runner.require_native_provenance()


def test_default_gate_forces_adaptation_off(monkeypatch):
    runner = _load = None
    spec = importlib.util.spec_from_file_location("r062_env", Path(__file__).parents[1] / "r062_t16_full_runner.py")
    runner = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(runner)
    monkeypatch.setattr(runner.base['Runner'], 'environment', lambda *_: {'FT_DEV_EXPERT_POLICY': 'profile+adapt'})
    options = type('Options', (), {'case': 'D12', 'rid': runner.ASSIGNED_RID,
                                   'batch': 1, 'candidate_commit': runner.CASES['D12']['new_commit']})()
    env = runner.CandidateRunner(options).environment(Path('/tmp'))
    assert {key: env[key] for key in ('FT_DEV_EXPERT_POLICY', 'FT_DEV_EXPERT_ADAPT_EVERY', 'FT_DEV_EXPERT_ADAPT_SWAPS')} == {
        'FT_DEV_EXPERT_POLICY': 'lru', 'FT_DEV_EXPERT_ADAPT_EVERY': '0', 'FT_DEV_EXPERT_ADAPT_SWAPS': '0'}


def test_default_short_suffix_argument_is_the_only_allowed_zero_delta():
    runner = _load = None
    spec = importlib.util.spec_from_file_location("r062_args", Path(__file__).parents[1] / "r062_t16_full_runner.py")
    runner = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(runner)
    runner.CandidateRunner.assert_default_off_args({'foo': 1}, {'foo': 1, 'moe_short_suffix_max_tokens': 0})
    with pytest.raises(ValueError, match="default-off parsed arguments"):
        runner.CandidateRunner.assert_default_off_args({'foo': 1}, {'foo': 2, 'moe_short_suffix_max_tokens': 0})
    with pytest.raises(ValueError, match="default-off parsed arguments"):
        runner.CandidateRunner.assert_default_off_args({'foo': 1}, {'foo': 1, 'moe_short_suffix_max_tokens': 1})
