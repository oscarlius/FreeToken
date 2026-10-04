"""Declare continuation coverage and compare batch/parking/cache observations."""
from __future__ import annotations

from .gate import ROLES, output_comparison


BOUNDARIES = (8192, 12416, 12736, 18944)
TAILS = (65, 4095, 4096, 4097, 8191, 8192, 8193)


def continuation_matrix() -> list[dict]:
    return [{"name": f"prefix-{prefix}-tail-{tail}", "boundary": prefix, "tail": tail,
             "prompt_tokens": prefix + tail, "donor_tokens": prefix + 1,
             "case": "S-continuation-short" if tail <= 4096 else "S-continuation-long"}
            for prefix in BOUNDARIES for tail in TAILS]


def _slots(run: dict) -> dict:
    slots = run.get("slots")
    if not isinstance(slots, dict) or not slots:
        raise ValueError("actual per-slot observations required")
    for uid, observation in slots.items():
        required = {"input_ids_sha256", "actual_cached_tokens", "segment_reasons", "token_ids", "text"}
        if not isinstance(uid, str) or not isinstance(observation, dict) or not required.issubset(observation):
            raise ValueError("slot observation is incomplete")
        if type(observation["actual_cached_tokens"]) is not int or observation["actual_cached_tokens"] < 0:
            raise ValueError("actual cached-token count required")
        if not isinstance(observation["segment_reasons"], list) or not observation["segment_reasons"]:
            raise ValueError("actual segment reasons required")
    return slots


def batch_envelope(evidence: dict) -> dict:
    first, repeat, singles = evidence["batch"], evidence["repeat"], evidence["singles"]
    for run in (first, repeat):
        if not isinstance(run.get("batch_shape"), list) or not run["batch_shape"]:
            raise ValueError("actual batch-shape signature required")
    if first["batch_shape"] != repeat["batch_shape"]:
        raise ValueError("repeat changed the batch shape")
    a, b, c = _slots(first), _slots(repeat), _slots(singles)
    if set(a) != set(b) or set(a) != set(c):
        raise ValueError("batch/repeat/single slot identities differ")
    results = {}
    deterministic = True
    for uid in a:
        if a[uid]["input_ids_sha256"] != b[uid]["input_ids_sha256"] or a[uid]["input_ids_sha256"] != c[uid]["input_ids_sha256"]:
            raise ValueError("slot actual prompt IDs differ")
        repeat_result = output_comparison(a[uid], b[uid])
        deterministic &= repeat_result["tokens_equal"] and repeat_result["text_equal"]
        results[uid] = {"repeat": repeat_result, "single_envelope": output_comparison(a[uid], c[uid]),
                        "top2_logit_difference": evidence.get("top2_logit_difference", {}).get(uid)}
    return {"schema": "ft_equiv_batch/v1", "verdict": "recorded" if deterministic else "failed_harness",
            "admitted": False, "slots": results,
            "limits": "single/batch differences are envelope records and never grant admission"}


def restoration_output(evidence: dict) -> dict:
    roles = evidence.get("restore_roles", {})
    if set(roles) != set(ROLES):
        raise ValueError("all four actual state-restore roles required")
    restored = all(roles[role].get("bitwise_equal") is True for role in ROLES)
    left, right = evidence["baseline"], evidence["restored"]
    if not left.get("input_ids_sha256") or left.get("input_ids_sha256") != right.get("input_ids_sha256"):
        raise ValueError("baseline and restored actual prompt IDs differ")
    compare = output_comparison(left, right)
    same = restored and compare["tokens_equal"] and compare["text_equal"]
    return {"schema": "ft_equiv_restoration/v1",
            "verdict": "measurements_pass_pending_independent_review" if same else "not_met",
            "admitted": False, "restore_roles": roles, "output": compare}
