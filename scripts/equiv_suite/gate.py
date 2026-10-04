"""Three-layer T17 decision; absent evidence can never grant admission."""
from __future__ import annotations

import hashlib
import struct
import re


ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")


def token_sha(ids: list[int]) -> str:
    if not isinstance(ids, list) or not ids or any(type(value) is not int for value in ids):
        raise ValueError("actual sampled token IDs must be a nonempty integer list")
    return hashlib.sha256(struct.pack(f"<{len(ids)}i", *ids)).hexdigest()


def first_fork(left: list[int], right: list[int]) -> int | None:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def output_comparison(left: dict, right: dict) -> dict:
    a, b = left["token_ids"], right["token_ids"]
    if type(left.get("text")) is not str or type(right.get("text")) is not str:
        raise ValueError("full actual text required")
    return {"tokens_equal": a == b, "text_equal": left["text"].encode() == right["text"].encode(),
            "first_token_fork": first_fork(a, b),
            "token_sha256": [token_sha(a), token_sha(b)],
            "text_sha256": [hashlib.sha256(x["text"].encode()).hexdigest() for x in (left, right)]}


def handoff(evidence: dict) -> dict:
    roles = evidence.get("restore_roles", {})
    missing = [role for role in ROLES if role not in roles]
    if missing:
        return {"verdict": "indeterminate", "missing_roles": missing}
    equality = {role: roles[role].get("bitwise_equal") for role in ROLES}
    if any(value is not True for value in equality.values()):
        return {"verdict": "not_met", "roles": equality}
    child = evidence.get("first_child")
    if child is None:
        return {"verdict": "indeterminate", "roles_verdict": "PASS", "roles": equality,
                "reason": "first-child state flags missing"}
    required = {"has_initial_state", "fresh_state_indices", "cached_tokens", "device_tokens"}
    if not isinstance(child, dict) or not required.issubset(child):
        return {"verdict": "indeterminate", "roles_verdict": "PASS",
                "reason": "first-child state flags incomplete"}
    cache = evidence.get("actual_cached_tokens")
    expected_end = evidence.get("expected_first_child_end")
    if type(expected_end) is not int or type(cache) is not int or expected_end <= cache:
        return {"verdict": "indeterminate", "roles_verdict": "PASS",
                "reason": "actual first-subchunk absolute end missing"}
    passed = (type(cache) is int and cache > 0 and child["has_initial_state"] is True
              and child["fresh_state_indices"] == [] and child["cached_tokens"] == cache
              and type(child["device_tokens"]) is int and child["device_tokens"] == expected_end)
    return {"verdict": "PASS" if passed else "not_met", "roles_verdict": "PASS",
            "roles": equality, "first_child": child}


def evaluate(evidence: dict) -> dict:
    state = handoff(evidence)
    result = {"schema": "ft_equiv_t17/v1", "state_handoff": state,
              "same_structure_reference": {"verdict": "indeterminate", "reason": "reference_missing"},
              "envelope": evidence.get("envelope"), "verdict": "indeterminate",
              "admitted": False}
    refs = evidence.get("references")
    if refs is None or refs == []:
        if state["verdict"] == "not_met":
            result["verdict"] = "not_met"
        return result
    if not isinstance(refs, list) or len(refs) != 2:
        raise ValueError("exactly two independent reference processes required")
    warm = evidence["warm"]
    identities = [ref.get("process_identity") for ref in refs]
    if (any(not isinstance(identity, dict) or not {"pid", "start_ticks", "execution_id"}.issubset(identity)
            for identity in identities) or identities[0] == identities[1]
            or identities[0]["execution_id"] == identities[1]["execution_id"]):
        raise ValueError("independent reference process identities missing or duplicated")
    if any(type(identity[key]) is not int or identity[key] <= 0
           for identity in identities for key in ("pid", "start_ticks")) or (
            identities[0]["pid"], identities[0]["start_ticks"]) == (
            identities[1]["pid"], identities[1]["start_ticks"]):
        raise ValueError("reference labels do not establish independent live process identities")
    if any(ref.get("structure_verified") is not True for ref in refs):
        raise ValueError("reference D0 structure must be verified before output comparison")
    schedule_sha = evidence.get("compiled_schedule_sha256")
    if not isinstance(schedule_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", schedule_sha) or any(
            ref.get("schedule_sha256") != schedule_sha for ref in refs):
        raise ValueError("reference structure receipts do not bind to the compiled schedule")
    prompt_sha = warm.get("input_ids_sha256")
    if not isinstance(prompt_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", prompt_sha) or any(
            ref.get("input_ids_sha256") != prompt_sha for ref in refs):
        raise ValueError("reference and warm actual input IDs differ")
    repeat = output_comparison(refs[0], refs[1])
    if not repeat["tokens_equal"] or not repeat["text_equal"]:
        result.update(verdict="failed_harness")
        result["same_structure_reference"] = {"verdict": "failed_harness", "repeat": repeat}
        return result
    compare = output_comparison(warm, refs[0])
    same = compare["tokens_equal"] and compare["text_equal"]
    result["same_structure_reference"] = {"verdict": "PASS" if same else "not_met",
                                          "repeat": repeat, "warm_comparison": compare}
    if not same:
        result["first_layer_operator_difference"] = evidence.get("first_layer_operator_difference")
        result["diagnostic_required"] = result["first_layer_operator_difference"] is None
    verdicts = (state["verdict"], result["same_structure_reference"]["verdict"])
    if "not_met" in verdicts:
        result["verdict"] = "not_met"
    elif verdicts == ("PASS", "PASS"):
        result["verdict"] = "measurements_pass_pending_independent_review"
    return result
