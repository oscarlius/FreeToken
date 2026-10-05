import copy
import importlib
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
paths = importlib.import_module("equiv_suite.path_readers")
gate = importlib.import_module("equiv_suite.gate")


def identity(number):
    return {"pid": number, "start_ticks": number + 100, "execution_id": f"{number}:x"}


def slot(event, number):
    return {"event_identity": f"{event}:slot:{number}", "input_ids_sha256": ("%064x" % number),
            "actual_cached_tokens": 0, "segment_reasons": ["actual"], "token_ids": [number, number + 1], "text": str(number)}


def run(event, count, *, events=None):
    value = {"process_identity": identity(sum(map(ord, event))), "event_identity": event,
             "batch_shape": [count, 32], "slots": {f"u{index}": slot(event, index + 1) for index in range(count)}}
    if events is not None:
        value["interleave_events"] = [{"event_identity": f"{event}:{entry['uid']}", **entry} for entry in events]
    return value


def test_four_slot_batch_records_single_envelope_without_admission():
    evidence = {"batch": run("batch", 4), "repeat": run("repeat", 4), "singles": run("single", 4)}
    result = paths.batch_four_slots(evidence)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    assert set(result["slots"]) == {"u0", "u1", "u2", "u3"}
    evidence["singles"]["slots"]["u0"]["token_ids"] = [1, 99]
    result = paths.batch_four_slots(evidence)
    assert result["verdict"] == "recorded" and result["slots"]["u0"]["single_envelope"]["first_token_fork"] == 1
    evidence["batch"].pop("process_identity")
    assert paths.batch_four_slots(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 4), "repeat": run("repeat", 4), "singles": run("single", 4)}
    evidence["batch"]["slots"]["u1"]["event_identity"] = evidence["batch"]["slots"]["u0"]["event_identity"]
    assert paths.batch_four_slots(evidence)["verdict"] == "indeterminate"
    evidence["batch"]["slots"]["u0"]["input_ids_sha256"] = "not-a-sha"
    assert paths.batch_four_slots(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 4), "repeat": run("repeat", 4), "singles": run("single", 4)}
    evidence["batch"]["slots"]["u0"].pop("token_ids")
    assert paths.batch_four_slots(evidence)["verdict"] == "indeterminate"


def test_parking_four_restore_roles_precede_equal_output():
    output = {"input_ids_sha256": "a" * 64, "token_ids": [1, 2], "text": "ok"}
    evidence = {"baseline": {**output, "process_identity": identity(1), "event_identity": "online"},
                "restored": {**output, "process_identity": identity(2), "event_identity": "restored"},
                "restore_roles": {role: {"bitwise_equal": True} for role in gate.ROLES}}
    evidence["restore_roles"][gate.ROLES[-1]]["bitwise_equal"] = False
    result = paths.parking_restore(evidence)
    assert result["verdict"] == "not_met" and result["output"]["tokens_equal"]
    evidence["restored"]["input_ids_sha256"] = "wrong"
    assert paths.parking_restore(evidence)["verdict"] == "indeterminate"
    evidence["restored"]["input_ids_sha256"] = "a" * 64
    evidence.pop("restore_roles")
    assert paths.parking_restore(evidence)["verdict"] == "indeterminate"


def test_cache_requires_distinct_captured_paths_and_detects_fork():
    cold = {"process_identity": identity(1), "event_identity": "cold", "cache_state": "empty",
            "input_ids_sha256": "a" * 64, "token_ids": [1, 2], "text": "ok",
            "cache_observation": {"path": "cache/cold", "generation": 0, "hit": False, "miss": True}}
    warm = {**cold, "process_identity": identity(2), "event_identity": "warm", "cache_state": "prewarmed"}
    warm["cache_observation"] = {"path": "cache/warm", "generation": 1, "hit": True, "miss": False}
    assert paths.cache_parity({"cold": cold, "warm": warm})["verdict"] == "measurements_pass_pending_independent_review"
    warm["token_ids"] = [1, 3]
    assert paths.cache_parity({"cold": cold, "warm": warm})["verdict"] == "not_met"
    warm.pop("cache_state")
    assert paths.cache_parity({"cold": cold, "warm": warm})["verdict"] == "indeterminate"
    warm["cache_state"] = "prewarmed"
    warm.pop("token_ids")
    assert paths.cache_parity({"cold": cold, "warm": warm})["verdict"] == "indeterminate"


def test_interleave_requires_event_identity_and_repeat_order():
    sequence = [{"uid": "u0", "kind": "prefill", "role": "long_prefill", "input_ids_sha256": "%064x" % 1},
                {"uid": "u1", "kind": "decode", "role": "decode", "input_ids_sha256": "%064x" % 2}]
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    result = paths.interleave_envelope(evidence)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    evidence["repeat"]["interleave_events"].reverse()
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    evidence["batch"]["interleave_events"][0]["kind"] = "decode"
    evidence["batch"]["interleave_events"][0]["role"] = "decode"
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    same_uid = [sequence[0], {**sequence[1], "uid": "u0", "input_ids_sha256": "%064x" % 1}]
    evidence = {"batch": run("batch", 2, events=same_uid), "repeat": run("repeat", 2, events=same_uid),
                "singles": run("single", 2, events=same_uid)}
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence + [sequence[1]]),
                "repeat": run("repeat", 2, events=sequence + [sequence[1]]),
                "singles": run("single", 2, events=sequence + [sequence[1]])}
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
