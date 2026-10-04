import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
continuation = importlib.import_module("equiv_suite.continuation")


def _segment(uid, start, end, mode="ordinary"):
    return {"reqs": [{"rid": uid, "cached_tokens": start, "new_tokens": end - start}],
            "start": start, "end": end, "mode": mode, "subchunks": [end - start]}


class FakeRun:
    def __init__(self, root, same_pid=False):
        self.root, self.same_pid, self.calls, self.proc = root, same_pid, [], None

    def request(self, arm, label, ids, cached, maximum):
        self.calls.append((arm.name, label, cached, maximum, tuple(ids)))
        return {"label": label}

    def service(self, name, operation, *, schedule=None, health_only=False):
        arm = self.root / name
        arm.mkdir()
        uid = "hit" if name.endswith("warm") else "query"
        rows = ([_segment("donor", 0, 8193, "layer_major"), _segment("hit", 8192, 8257)]
                if name.endswith("warm") else [_segment(uid, 0, 8193, "layer_major"), _segment(uid, 8192, 8257)])
        (arm / "d0_prefill.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.proc = type("Proc", (), {"pid": 100 if self.same_pid else len(self.calls) + 100})()
        self.calls.append((name, "service", schedule, health_only))
        return operation(arm)


def case():
    return {"name": "prefix-8192-tail-65", "length": 8192, "tail": 65,
            "trace_index": 1, "expected_ngram": [7, 8],
            "donor": list(range(8193)), "query": list(range(8257))}


def warm(*_args, **_kwargs):
    return {"warm": {"token_ids": [1, 2], "text": "ok",
                     "input_ids_sha256": continuation.gate.token_sha(list(range(8257)))} ,
            "donor_uid": "donor", "hit_uid": "hit", "actual_cached_tokens": 8192,
            "restore_roles": {role: {"bitwise_equal": True} for role in continuation.gate.ROLES},
            "first_child": {"has_initial_state": True, "fresh_state_indices": [],
                            "cached_tokens": 8192, "device_tokens": 8257}}


def resources(tmp_path, *, reference=None, same_pid=False):
    run = FakeRun(tmp_path / "arms", same_pid=same_pid)
    run.root.mkdir()
    compiled = [{"start": 0, "end": 8193, "mode": "layer_major", "subchunks": [8193]},
                {"start": 8192, "end": 8257, "mode": "ordinary", "subchunks": [65]}]
    return {"run": run, "legacy": object(), "schedule_dir": tmp_path / "schedule",
            "read_warm": warm, "read_proc_stat": lambda pid: f"{pid} (service name with spaces) R " + " ".join(["0"] * 18 + [str(pid + 1)]),
            "read_reference": reference or (lambda *_args, **kwargs: {"token_ids": [1, 2], "text": "ok",
                "input_ids_sha256": continuation.gate.token_sha(list(range(8257))), "process_identity": kwargs["identity"], "structure_verified": True,
                "schedule_sha256": continuation.schedule.read_schedule(kwargs["schedule_path"])[1],
                "actual_segments": compiled})}


def test_runs_warm_then_two_fresh_references_with_one_generation_each(tmp_path):
    item = resources(tmp_path)
    result = continuation.run_case(item, case())
    requests = [call for call in item["run"].calls if call[1] in {"donor", "hit", "query"}]
    assert [call[1] for call in requests] == ["donor", "hit", "query", "query"]
    assert all(call[3] == 128 for call in requests[2:])
    assert result["result"]["admitted"] is False
    assert (tmp_path / "schedule" / "schedule.json").stat().st_mode & 0o222 == 0


def test_rejects_donor_query_identity_before_any_service(tmp_path):
    item = resources(tmp_path)
    broken = case(); broken["donor"][-1] = -1
    with pytest.raises(ValueError, match="do not bind"):
        continuation.run_case(item, broken)
    assert item["run"].calls == []


def test_duplicate_physical_process_proof_stops_before_cold(tmp_path):
    item = resources(tmp_path, same_pid=True)
    with pytest.raises(ValueError, match="identities missing or duplicated"):
        continuation.run_case(item, case())
    assert not any("cold" in call[0] for call in item["run"].calls if isinstance(call[0], str))


def test_repeat_failure_stops_after_two_references_and_preserves_evidence(tmp_path):
    def differing_reference(_legacy, arm, **kwargs):
        return {"token_ids": [1, 2 if arm.name.endswith("1") else 3], "text": "ok",
                "input_ids_sha256": continuation.gate.token_sha(list(range(8257))), "process_identity": kwargs["identity"],
                "structure_verified": True, "schedule_sha256": continuation.schedule.read_schedule(kwargs["schedule_path"])[1],
                "actual_segments": continuation.schedule.read_schedule(kwargs["schedule_path"])[0]}
    item = resources(tmp_path, reference=differing_reference)
    result = continuation.run_case(item, case())
    assert result["stopped"] == "failed_harness" and len(result["evidence"]["references"]) == 2
    assert not any("cold" in call[0] for call in item["run"].calls if isinstance(call[0], str))


def test_structure_mismatch_stops_before_token_comparison(tmp_path):
    item = resources(tmp_path, reference=lambda *_args, **kwargs: {"actual_segments": [], "token_ids": [9], "text": "bad",
        "input_ids_sha256": continuation.gate.token_sha(list(range(8257))), "process_identity": kwargs["identity"], "structure_verified": True,
        "schedule_sha256": "0" * 64})
    with pytest.raises(ValueError, match="actual D0"):
        continuation.run_case(item, case())


def test_nonpass_handoff_starts_no_reference(tmp_path):
    item = resources(tmp_path)
    item["read_warm"] = lambda *_args, **_kwargs: dict(warm(), first_child={"has_initial_state": True})
    result = continuation.run_case(item, case())
    assert result["stopped"] == "state_handoff"
    assert [call[1] for call in item["run"].calls if call[1] == "service"] == ["service"]


def test_allowed_ordinary_cold_records_actual_output_envelope(tmp_path):
    item = resources(tmp_path)
    item["allow_cold_envelope"] = True
    item["request_evidence"] = lambda *_args: {
        "tokens": [1, 2], "input_sha256": continuation.gate.token_sha(list(range(8257))),
        "response": {"text": "ok"},
    }
    result = continuation.run_case(item, case())
    envelope = result["ordinary_cold_envelope"]
    assert envelope["recorded"] and not envelope["admitted"]
    assert envelope["output"]["tokens_equal"] and "T04" in envelope["limits"]
    assert len([call for call in item["run"].calls
                if call[1] == "service" and "cold-envelope" in call[0]]) == 1


def test_warm_reference_not_met_does_not_launch_ordinary_cold(tmp_path):
    def forked_reference(_legacy, _arm, **kwargs):
        return {"token_ids": [9, 2], "text": "ok",
                "input_ids_sha256": continuation.gate.token_sha(list(range(8257))),
                "process_identity": kwargs["identity"], "structure_verified": True,
                "schedule_sha256": continuation.schedule.read_schedule(kwargs["schedule_path"])[1],
                "actual_segments": continuation.schedule.read_schedule(kwargs["schedule_path"])[0]}
    item = resources(tmp_path, reference=forked_reference)
    item["allow_cold_envelope"] = True
    result = continuation.run_case(item, case())
    assert result["stopped"] == "not_met" and result["result"]["diagnostic_required"]
    assert not any("cold-envelope" in call[0] for call in item["run"].calls if isinstance(call[0], str))
