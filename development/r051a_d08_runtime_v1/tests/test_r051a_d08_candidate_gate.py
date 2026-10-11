import importlib.util
from pathlib import Path
import pytest

SOURCE = Path(__file__).parents[1] / "r051a_d08_candidate_gate.py"
spec = importlib.util.spec_from_file_location("r051a_gate", SOURCE)
m = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m)


def test_final_candidate_is_bound_but_run_stays_fail_closed():
    assert m.FINAL_CANDIDATE_COMMIT == "76af7584d7595d9cc52dcd60deff3aacdae1d9d6"
    assert m.require_final_candidate() == m.FINAL_CANDIDATE_COMMIT
    with pytest.raises(RuntimeError, match="no executable runner"):
        m.main(["--run"])


def test_final_binding_requires_exact_commit_and_keeps_full_protocol_contract(monkeypatch):
    final = "1" * 40
    monkeypatch.setattr(m, "FINAL_CANDIDATE_COMMIT", final)
    binding = m.candidate_binding(final)
    assert binding["parent_commit"] == "effb9969706922ddad9e59b96377e46469ebe97f"
    assert binding["candidate_worktree"] == "/data2/FreeToken/wt/e2d08-capture-trace"
    assert binding["arms"] == ["PARENT_D0OFF", "CANDIDATE_D0OFF", "PARENT_D0ON", "CANDIDATE_D0ON"]
    assert binding["config"] == {"kv_reserve_tokens": 98304, "max_seq_len_override": 98304, "memory_ratio": 0.88}
    assert binding["native_reuse"]["source_commit"] == "8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8"
    assert all(binding["disabled"].values())
    with pytest.raises(RuntimeError, match="differs"):
        m.candidate_binding("2" * 40)


def test_protocol_and_owned_lifecycle_inputs_are_explicit_closure_members():
    expected = {"r051a_t16_full_runner.py", "r051a_owned_launch.py"}
    assert expected <= set(m.SOURCE_CLOSURE)


def test_actual_full_runner_and_owned_launch_are_rebound_but_missing_native_provenance_blocks_execution(monkeypatch):
    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / filename)
        module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module
    runner = load("r051a_full_runner", "r051a_t16_full_runner.py")
    owned = load("r051a_owned", "r051a_owned_launch.py")
    assert runner.ASSIGNED_RID == "E2-R051a-gate-D08"
    assert runner.CASES["D08"]["new_wt"] == "e2d08-capture-trace"
    assert runner.CASES["D08"]["new_commit"] == m.FINAL_CANDIDATE_COMMIT
    assert owned.SPECS["D08"] == (runner.ASSIGNED_RID, m.FINAL_CANDIDATE_COMMIT, "r051a_t16_full_runner.py")
    assert runner.CANDIDATE_NATIVE_PROVENANCE_SHA256 == 'a27531136810e6dd84bb896fef688644b01eb0ca7f3acb68fbbe163c9a26cadf'
    monkeypatch.setattr(runner, 'CANDIDATE_NATIVE_PROVENANCE_SHA256', None)
    with pytest.raises(ValueError, match="provenance SHA is pending"):
        runner.require_native_provenance()
