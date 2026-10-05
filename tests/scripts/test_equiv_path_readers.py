import copy
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
paths = importlib.import_module("equiv_suite.path_readers")
gate = importlib.import_module("equiv_suite.gate")


def identity(number):
    return {"pid": number, "start_ticks": number + 100, "execution_id": f"{number}:x"}


def slot(event, number):
    prompt = [number, number + 10]
    return {"event_identity": f"{event}:slot:{number}", "input_ids_sha256": gate.token_sha(prompt), "input_token_ids": prompt,
            "actual_cached_tokens": 0, "segment_reasons": ["actual"], "token_ids": [number, number + 1], "text": str(number)}


def run(event, count, *, events=None):
    value = {"process_identity": identity(sum(map(ord, event))), "event_identity": event,
             "batch_shape": [count, 32], "slots": {f"u{index}": slot(event, index + 1) for index in range(count)}}
    if events is not None:
        value["interleave_events"] = [{"event_identity": f"{event}:{entry['uid']}", **entry} for entry in events]
    return value


def prompt_sha(number):
    return gate.token_sha([number, number + 10])


def d03_probe(evidence, uid, fork):
    batch = evidence["batch"]
    single = evidence["singles"]
    number = int(uid[1:]) + 1
    prompt = [number, number + 10]
    prefix = batch["slots"][uid]["token_ids"][:fork]
    context = prompt + prefix
    receipt = b"captured D03 receipt"
    return {"fork_generation_index": fork, "original_prompt_sha": gate.token_sha(prompt),
            "shared_generated_prefix_token_ids": prefix, "actual_captured_context_token_ids": context,
            "input_prefix_sha256": gate.token_sha(context), "input_length": len(context), "k": 1,
            "batch_slot_event_identity": batch["slots"][uid]["event_identity"],
            "single_slot_event_identity": single["slots"][uid]["event_identity"],
            "batch_process_identity": batch["process_identity"], "single_process_identity": single["process_identity"],
            "capture_receipt_base64": base64.b64encode(receipt).decode(), "capture_receipt_sha256": hashlib.sha256(receipt).hexdigest(),
            "positions": [len(context) - 1], "peer_vs_recompute": {"top1_per_position": [False],
            "top2_margin": [0.5], "reference_top2_margin": [0.25], "first_top1_mismatch": 0}}


def test_four_slot_batch_records_single_envelope_without_admission():
    evidence = {"batch": run("batch", 4), "repeat": run("repeat", 4), "singles": run("single", 4)}
    result = paths.batch_four_slots(evidence)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    assert set(result["slots"]) == {"u0", "u1", "u2", "u3"}
    evidence["singles"]["slots"]["u0"]["token_ids"] = [1, 99]
    evidence["top2_logit_difference"] = {"u0": d03_probe(evidence, "u0", 1)}
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


def test_two_slot_batch_requires_d03_diagnostics_for_a_single_fork():
    evidence = {"batch": run("batch", 2), "repeat": run("repeat", 2), "singles": run("single", 2)}
    evidence["repeat"]["process_identity"]["execution_id"] = evidence["batch"]["process_identity"]["execution_id"]
    assert paths.batch_two_slots(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2), "repeat": run("repeat", 2), "singles": run("single", 2)}
    evidence["singles"]["slots"]["u1"]["token_ids"] = [2, 99]
    assert paths.batch_two_slots(evidence)["verdict"] == "indeterminate"
    evidence["top2_logit_difference"] = {"u1": d03_probe(evidence, "u1", 1)}
    result = paths.batch_two_slots(evidence)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    evidence = json.loads(json.dumps(evidence))
    assert json.loads(json.dumps(paths.batch_two_slots(evidence)))["verdict"] == "recorded"
    evidence["top2_logit_difference"]["u1"]["capture_receipt_base64"] = base64.b64encode(b"tampered").decode()
    assert paths.batch_two_slots(evidence)["verdict"] == "indeterminate"
    evidence["top2_logit_difference"]["u1"] = d03_probe(evidence, "u1", 1)
    evidence["top2_logit_difference"]["u1"]["capture_receipt_base64"] = "!not-base64!"
    assert paths.batch_two_slots(evidence)["verdict"] == "indeterminate"
    evidence["top2_logit_difference"]["u1"] = d03_probe(evidence, "u1", 1)
    evidence["top2_logit_difference"]["u1"]["actual_captured_context_token_ids"] = [2, 12]
    evidence["top2_logit_difference"]["u1"]["input_prefix_sha256"] = prompt_sha(2)
    evidence["top2_logit_difference"]["u1"]["input_length"] = 2
    evidence["top2_logit_difference"]["u1"]["positions"] = [1]
    assert paths.batch_two_slots(evidence)["verdict"] == "indeterminate"


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
    sequence = [{"uid": "u0", "kind": "prefill", "role": "long_prefill", "input_ids_sha256": prompt_sha(1)},
                {"uid": "u1", "kind": "decode", "role": "decode", "input_ids_sha256": prompt_sha(2)}]
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    result = paths.interleave_envelope(evidence)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    evidence["repeat"]["interleave_events"].reverse()
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    evidence["repeat"]["process_identity"] = evidence["batch"]["process_identity"]
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    evidence["repeat"]["process_identity"]["execution_id"] = evidence["batch"]["process_identity"]["execution_id"]
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence), "repeat": run("repeat", 2, events=sequence),
                "singles": run("single", 2, events=sequence)}
    evidence["batch"]["interleave_events"][0]["kind"] = "decode"
    evidence["batch"]["interleave_events"][0]["role"] = "decode"
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    same_uid = [sequence[0], {**sequence[1], "uid": "u0", "input_ids_sha256": prompt_sha(1)}]
    evidence = {"batch": run("batch", 2, events=same_uid), "repeat": run("repeat", 2, events=same_uid),
                "singles": run("single", 2, events=same_uid)}
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
    evidence = {"batch": run("batch", 2, events=sequence + [sequence[1]]),
                "repeat": run("repeat", 2, events=sequence + [sequence[1]]),
                "singles": run("single", 2, events=sequence + [sequence[1]])}
    assert paths.interleave_envelope(evidence)["verdict"] == "indeterminate"
