"""Bind decisions to retained endpoint/state readers and actual D0 records."""
from pathlib import Path

from .schedule import read_jsonl, read_schedule, validate_reference


def actual_child_flags(observations):
    children = [row for row in observations if row.get("kind") == "layer-children"]
    if children:
        values = children[0].get("children", [])
        child = dict(values[0]) if values else None
    else:
        prefills = [row for row in observations if row.get("kind") == "prefill"]
        value = prefills[0].get("first_child") if prefills else None
        child = dict(value) if isinstance(value, dict) else None
    if child is not None and "fresh_state_indices" in child and child["fresh_state_indices"] is None:
        # Present-null is the actual FLA empty value. Missing stays missing.
        child["fresh_state_indices"] = []
    return child


def read_warm(legacy, arm: Path, case: dict, *, query="hit"):
    donor = legacy.request_evidence(arm, "donor", 0, 2)
    hit = legacy.request_evidence(arm, query, case["length"], 128)
    if (len(donor["input_ids"]) != case["length"] + 1
            or donor["input_ids"] != hit["input_ids"][:case["length"] + 1]):
        raise ValueError("actual donor and continuation IDs do not bind")
    donation, restored, restore, roles = legacy._validate_states(
        case, arm / "dump", donor, hit, read=legacy.load_tensor, equal=legacy.bit_equal)
    return {"warm": {"token_ids": hit["tokens"], "text": hit["response"]["text"],
                     "input_ids_sha256": hit["input_sha256"]},
            "donor_uid": donor["uid"], "hit_uid": hit["uid"],
            "actual_cached_tokens": hit["actual_cached_tokens"], "restore_roles": roles,
            "first_child": actual_child_flags(hit["observations"]),
            "raw_bindings": {"donor_response_sha256": donor["response_sha256"],
                             "hit_response_sha256": hit["response_sha256"],
                             "observations_sha256": hit["observation_sha256"],
                             "donation_seq": donation["seq"], "restore_seq": restored["seq"],
                             "source_slot": restore["src"], "destination_slot": restore["dst"]}}


def read_reference(legacy, arm: Path, *, schedule_path: Path, identity: dict):
    observed = legacy.request_evidence(arm, "query", 0, 128)
    schedule, schedule_sha = read_schedule(schedule_path)
    rows, d0_sha = read_jsonl(arm / "d0_prefill.jsonl")
    actual = validate_reference(rows, uid=observed["uid"], schedule=schedule)
    return {"token_ids": observed["tokens"], "text": observed["response"]["text"],
            "input_ids_sha256": observed["input_sha256"], "process_identity": identity,
            "structure_verified": True, "schedule_sha256": schedule_sha,
            "actual_segments": actual,
            "d0_sha256": d0_sha, "response_sha256": observed["response_sha256"],
            "observations_sha256": observed["observation_sha256"]}
