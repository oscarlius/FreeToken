"""Reject false admission and preserve the measured GEMM geometry."""
import copy
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
schedule = importlib.import_module("equiv_suite.schedule")
gate = importlib.import_module("equiv_suite.gate")
cases = importlib.import_module("equiv_suite.cases")
raw = importlib.import_module("equiv_suite.raw")


def row(uid, start, end, mode, chunks):
    return {"reqs": [{"rid": uid, "cached_tokens": start, "new_tokens": end - start}],
            "start": start, "end": end, "mode": mode, "subchunks": chunks}


def measured():
    return [row(1, 0, 512, "ordinary", [512]),
            row(1, 512, 8193, "layer_major", [4096, 3585]),
            row(2, 8192, 8257, "ordinary", [65])]


def test_overread_row_is_preserved_and_reference_checked_before_output():
    rows = measured()
    rows[1]["reqs"][0]["cached_tokens"] = 0
    result = schedule.compile_schedule(rows, donor_uid="1", hit_uid="2",
                                       cached_tokens=8192, prompt_tokens=8257)
    assert result[1]["end"] == 8193 and result[1]["subchunks"] == [4096, 3585]
    ref = [dict(item, reqs=[{"rid": 9, "cached_tokens": item["start"],
                            "new_tokens": item["end"] - item["start"]}]) for item in result]
    assert schedule.validate_reference(ref, uid="9", schedule=result) == result
    ref[1]["subchunks"] = [4096, 3584, 1]
    with pytest.raises(ValueError, match="differs"):
        schedule.validate_reference(ref, uid="9", schedule=result)


@pytest.mark.parametrize("change", ["missing_grid", "wrong_sum", "wrong_hit", "batched", "trim_donor"])
def test_unobserved_or_changed_geometry_cannot_be_compiled(change):
    rows = measured()
    if change == "missing_grid":
        rows[1].pop("subchunks")
    elif change == "wrong_sum":
        rows[1]["subchunks"][-1] -= 1
    elif change == "wrong_hit":
        rows[-1]["reqs"][0]["cached_tokens"] += 1
    elif change == "batched":
        rows[1]["reqs"].append(dict(rows[1]["reqs"][0], rid=8))
    else:
        rows[1]["end"] = 8191
        rows[1]["subchunks"][-1] -= 2
        rows[1]["reqs"][0]["new_tokens"] -= 2
    with pytest.raises(ValueError):
        schedule.compile_schedule(rows, donor_uid="1", hit_uid="2", cached_tokens=8192, prompt_tokens=8257)


def evidence():
    out = {"token_ids": [3, 4, 5], "text": "abc", "input_ids_sha256": "a" * 64}
    return {"restore_roles": {role: {"bitwise_equal": True} for role in gate.ROLES},
            "compiled_schedule_sha256": "c" * 64,
            "actual_cached_tokens": 8192,
            "first_child": {"cached_tokens": 8192, "device_tokens": 8257,
                            "has_initial_state": True, "fresh_state_indices": []},
            "warm": out,
            "references": [dict(out, structure_verified=True, schedule_sha256="c" * 64,
                                process_identity={"pid": i, "birth": i, "execution_id": str(i)}) for i in (1, 2)]}


def test_missing_reference_never_passes_despite_correct_restore():
    data = evidence()
    data.pop("references")
    result = gate.evaluate(data)
    assert result["state_handoff"]["verdict"] == "PASS"
    assert result["verdict"] == "indeterminate" and not result["admitted"]


def test_reference_repeat_failure_precedes_warm_comparison():
    data = evidence()
    data["references"][1]["token_ids"] = [3, 6, 5]
    assert gate.evaluate(data)["verdict"] == "failed_harness"


@pytest.mark.parametrize("change", ["structure", "input", "process", "process_label"])
def test_invalid_reference_preconditions_stop(change):
    data = evidence()
    if change == "structure":
        data["references"][0]["structure_verified"] = False
    elif change == "input":
        data["references"][0]["input_ids_sha256"] = "b" * 64
    elif change == "process":
        data["references"][1]["process_identity"] = data["references"][0]["process_identity"]
    else:
        data["references"][1]["process_identity"] = dict(data["references"][0]["process_identity"], execution_id="new-label")
    with pytest.raises(ValueError):
        gate.evaluate(data)


def test_envelope_cannot_override_output_fork():
    data = evidence()
    data["warm"] = copy.deepcopy(data["warm"])
    data["warm"]["token_ids"][1] = 9
    data["envelope"] = {"max_abs": 0.001, "within_tolerance": True}
    result = gate.evaluate(data)
    assert result["verdict"] == "not_met" and result["diagnostic_required"]
    assert result["same_structure_reference"]["warm_comparison"]["first_token_fork"] == 1


def test_correct_measurements_still_require_independent_review():
    result = gate.evaluate(evidence())
    assert result["verdict"] == "measurements_pass_pending_independent_review"
    assert not result["admitted"]


def test_missing_fresh_flag_cannot_be_inferred_from_initial_state():
    data = evidence()
    data["first_child"].pop("fresh_state_indices")
    result = gate.evaluate(data)
    assert result["state_handoff"]["verdict"] == "indeterminate"


def test_reference_echo_must_bind_to_the_actual_compiled_file():
    data = evidence()
    data["references"][1]["schedule_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="compiled schedule"):
        gate.evaluate(data)


def test_schedule_file_hash_detects_changed_grid(tmp_path):
    path = tmp_path / "schedule.json"
    schedule.write_new(path, [{key: value for key, value in row.items() if key != "reqs"}
                              for row in measured()])
    original, sha = schedule.read_schedule(path)
    original[1]["subchunks"] = [7681]
    path.write_text(__import__("json").dumps(original))
    changed, changed_sha = schedule.read_schedule(path)
    assert changed_sha != sha and changed[1]["subchunks"] == [7681]


def test_actual_null_fresh_indices_normalize_but_missing_is_not_inferred():
    flags = {"cached_tokens": 8192, "device_tokens": 8257,
             "has_initial_state": True, "fresh_state_indices": None}
    result = raw.actual_child_flags([{"kind": "prefill", "first_child": flags}])
    assert result["fresh_state_indices"] == []
    flags.pop("fresh_state_indices")
    result = raw.actual_child_flags([{"kind": "prefill", "first_child": flags}])
    assert "fresh_state_indices" not in result


def test_continuation_coverage_includes_exact_grid_and_adjacent_lengths():
    matrix = cases.continuation_matrix()
    assert len(matrix) == 28
    assert {row["tail"] for row in matrix} == {65, 4095, 4096, 4097, 8191, 8192, 8193}
    assert all(row["donor_tokens"] == row["boundary"] + 1 for row in matrix)


def test_batch_single_fork_is_record_only_but_repeat_fork_stops():
    slot = {"input_ids_sha256": "a" * 64, "actual_cached_tokens": 0,
            "segment_reasons": ["other"], "token_ids": [1, 2], "text": "ok"}
    data = {"batch": {"batch_shape": [2, 100], "slots": {"a": slot}},
            "repeat": {"batch_shape": [2, 100], "slots": {"a": copy.deepcopy(slot)}},
            "singles": {"slots": {"a": dict(slot, token_ids=[1, 3])}}}
    result = cases.batch_envelope(data)
    assert result["verdict"] == "recorded" and not result["admitted"]
    assert result["slots"]["a"]["single_envelope"]["first_token_fork"] == 1
    data["repeat"]["slots"]["a"]["text"] = "changed"
    assert cases.batch_envelope(data)["verdict"] == "failed_harness"


def test_parking_state_failure_cannot_be_hidden_by_equal_output():
    output = {"input_ids_sha256": "a" * 64, "token_ids": [1, 2], "text": "ok"}
    data = {"baseline": output, "restored": dict(output),
            "restore_roles": {role: {"bitwise_equal": True} for role in gate.ROLES}}
    data["restore_roles"][gate.ROLES[0]]["bitwise_equal"] = False
    assert cases.restoration_output(data)["verdict"] == "not_met"
