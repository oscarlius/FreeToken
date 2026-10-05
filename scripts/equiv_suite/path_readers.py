"""CPU-only readers for the D16 batch, parking, cache, and interleave paths."""
from __future__ import annotations

import re

from .cases import batch_envelope, restoration_output
from .gate import ROLES, output_comparison


def _indeterminate(schema: str, reason: str) -> dict:
    return {"schema": schema, "verdict": "indeterminate", "admitted": False, "reason": reason}


def _identity(value: object) -> bool:
    return (isinstance(value, dict) and type(value.get("pid")) is int and value["pid"] > 0
            and type(value.get("start_ticks")) is int and value["start_ticks"] > 0
            and isinstance(value.get("execution_id"), str) and bool(value["execution_id"]))


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _output(value: object) -> bool:
    return (isinstance(value, dict) and isinstance(value.get("token_ids"), list) and bool(value["token_ids"])
            and all(type(token) is int for token in value["token_ids"])
            and isinstance(value.get("text"), str))


def _slot(value: object) -> bool:
    return (_output(value) and type(value.get("actual_cached_tokens")) is int
            and value["actual_cached_tokens"] >= 0
            and isinstance(value.get("segment_reasons"), list) and bool(value["segment_reasons"]))


def _bound_run(run: object, *, slots: int | None = None) -> str | None:
    if not isinstance(run, dict):
        return "run record missing"
    if not _identity(run.get("process_identity")):
        return "actual process identity missing"
    event = run.get("event_identity")
    if not isinstance(event, str) or not event:
        return "actual event identity missing"
    observations = run.get("slots")
    if not isinstance(observations, dict) or (slots is not None and len(observations) != slots):
        return "actual slot collection missing"
    event_ids = set()
    for uid, item in observations.items():
        if not isinstance(uid, str) or not _slot(item):
            return "slot observation is malformed"
        item_event = item.get("event_identity")
        if not isinstance(item_event, str) or not item_event or not _sha(item.get("input_ids_sha256")):
            return "slot event or input binding missing"
        event_ids.add(item_event)
    if len(event_ids) != len(observations):
        return "per-slot event identities must be unique"
    return None


def batch_four_slots(evidence: dict) -> dict:
    """Record a four-slot batch envelope; it never grants admission."""
    schema = "ft_equiv_batch_four_slots/v1"
    if not isinstance(evidence, dict):
        return _indeterminate(schema, "evidence object missing")
    runs = [evidence.get(name) for name in ("batch", "repeat", "singles")]
    for run in runs[:2]:
        issue = _bound_run(run, slots=4)
        if issue:
            return _indeterminate(schema, issue)
    singles = runs[2]
    issue = _bound_run(singles, slots=4)
    if issue:
        return _indeterminate(schema, issue)
    if len({run["event_identity"] for run in runs}) != 3:
        return _indeterminate(schema, "batch, repeat, and single event identities must differ")
    if any(not isinstance(run.get("batch_shape"), list) or not run["batch_shape"] or run["batch_shape"][0] != 4
           for run in runs[:2]):
        return _indeterminate(schema, "actual four-slot batch shape missing")
    if len({(run["process_identity"]["pid"], run["process_identity"]["start_ticks"]) for run in runs}) != 3:
        return _indeterminate(schema, "batch, repeat, and single processes must differ")
    result = batch_envelope(evidence)
    return {"schema": schema, "verdict": result["verdict"], "admitted": False,
            "slots": result["slots"], "limits": result["limits"]}


def parking_restore(evidence: dict) -> dict:
    """Require four restored roles even when the visible output is identical."""
    schema = "ft_equiv_parking/v1"
    if not isinstance(evidence, dict):
        return _indeterminate(schema, "evidence object missing")
    for name in ("baseline", "restored"):
        item = evidence.get(name)
        if not isinstance(item, dict) or not _identity(item.get("process_identity")):
            return _indeterminate(schema, name + " process identity missing")
        if not isinstance(item.get("event_identity"), str) or not item["event_identity"]:
            return _indeterminate(schema, name + " event identity missing")
        if not _sha(item.get("input_ids_sha256")):
            return _indeterminate(schema, name + " input binding missing")
        if not _output(item):
            return _indeterminate(schema, name + " output missing")
    roles = evidence.get("restore_roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES) or any(
            not isinstance(role, dict) or type(role.get("bitwise_equal")) is not bool for role in roles.values()):
        return _indeterminate(schema, "actual restore roles missing")
    if evidence["baseline"]["event_identity"] == evidence["restored"]["event_identity"]:
        return _indeterminate(schema, "parking and restore events must be distinct")
    if (evidence["baseline"]["process_identity"]["pid"], evidence["baseline"]["process_identity"]["start_ticks"]) == (
            evidence["restored"]["process_identity"]["pid"], evidence["restored"]["process_identity"]["start_ticks"]):
        return _indeterminate(schema, "parking and restore processes must differ")
    result = restoration_output(evidence)
    return {"schema": schema, "verdict": result["verdict"], "admitted": False,
            "restore_roles": result["restore_roles"], "output": result["output"]}


def cache_parity(evidence: dict) -> dict:
    """Compare cold and pre-warmed cache paths with their captured identities."""
    schema = "ft_equiv_cache/v1"
    if not isinstance(evidence, dict):
        return _indeterminate(schema, "evidence object missing")
    cold, warm = evidence.get("cold"), evidence.get("warm")
    for name, item in (("cold", cold), ("warm", warm)):
        if not isinstance(item, dict) or not _identity(item.get("process_identity")):
            return _indeterminate(schema, name + " process identity missing")
        if not isinstance(item.get("event_identity"), str) or not item["event_identity"]:
            return _indeterminate(schema, name + " event identity missing")
        if not isinstance(item.get("cache_state"), str) or not item["cache_state"]:
            return _indeterminate(schema, name + " cache state missing")
        if not _sha(item.get("input_ids_sha256")):
            return _indeterminate(schema, name + " input binding missing")
        if not _output(item):
            return _indeterminate(schema, name + " output missing")
        observation = item.get("cache_observation")
        if (not isinstance(observation, dict) or not isinstance(observation.get("path"), str) or not observation["path"]
                or type(observation.get("generation")) is not int or observation["generation"] < 0
                or type(observation.get("hit")) is not bool or type(observation.get("miss")) is not bool):
            return _indeterminate(schema, name + " cache hit/miss observation missing")
    if cold["input_ids_sha256"] != warm["input_ids_sha256"]:
        return _indeterminate(schema, "cold and warm inputs differ")
    if cold["event_identity"] == warm["event_identity"] or cold["cache_state"] == warm["cache_state"]:
        return _indeterminate(schema, "cache path identity is not independent")
    if (cold["process_identity"]["pid"], cold["process_identity"]["start_ticks"]) == (
            warm["process_identity"]["pid"], warm["process_identity"]["start_ticks"]):
        return _indeterminate(schema, "cache path processes must differ")
    if (cold["cache_observation"]["hit"], cold["cache_observation"]["miss"]) != (False, True) or (
            warm["cache_observation"]["hit"], warm["cache_observation"]["miss"]) != (True, False):
        return _indeterminate(schema, "cold/warm cache hit-miss relation missing")
    comparison = output_comparison(cold, warm)
    return {"schema": schema, "verdict": "measurements_pass_pending_independent_review"
            if comparison["tokens_equal"] and comparison["text_equal"] else "not_met",
            "admitted": False, "output": comparison,
            "cache_states": [cold["cache_state"], warm["cache_state"]], "cache_accepted": False,
            "limits": "captured cache parity is an envelope and never accepts a cache implementation"}


def interleave_envelope(evidence: dict) -> dict:
    """Record an interleaved prefill/decode envelope with exact event bindings."""
    schema = "ft_equiv_interleave/v1"
    if not isinstance(evidence, dict):
        return _indeterminate(schema, "evidence object missing")
    runs = [evidence.get(name) for name in ("batch", "repeat", "singles")]
    for run in runs:
        issue = _bound_run(run, slots=2)
        if issue:
            return _indeterminate(schema, issue)
        events = run.get("interleave_events")
        if not isinstance(events, list) or len(events) != 2 or any(not isinstance(event, dict) for event in events):
            return _indeterminate(schema, "actual interleave events missing")
        if any((not isinstance(event.get("event_identity"), str) or not event["event_identity"]
                or event.get("uid") not in run["slots"] or event.get("kind") not in {"prefill", "decode"}
                or event.get("role") not in {"long_prefill", "decode"}
                or not _sha(event.get("input_ids_sha256"))
                or event["input_ids_sha256"] != run["slots"][event["uid"]]["input_ids_sha256"])
               for event in events):
            return _indeterminate(schema, "interleave event does not bind to captured slot")
        if len({event["event_identity"] for event in events}) != len(events):
            return _indeterminate(schema, "interleave event identities must be unique")
        if len({event["uid"] for event in events}) != 2:
            return _indeterminate(schema, "interleave events must bind two distinct slots")
        roles = {(event["kind"], event["role"], event["uid"]) for event in events}
        if len(roles) != 2 or {(kind, role) for kind, role, _ in roles} != {("prefill", "long_prefill"), ("decode", "decode")}:
            return _indeterminate(schema, "interleave requires one long-prefill slot and one decode slot")
    def sequence(run: dict) -> list[dict]:
        return [{key: value for key, value in event.items() if key != "event_identity"}
                for event in run["interleave_events"]]
    if sequence(runs[0]) != sequence(runs[1]):
        return _indeterminate(schema, "repeat interleave event order differs")
    if any(not isinstance(run.get("batch_shape"), list) or not run["batch_shape"] or run["batch_shape"][0] != 2
           for run in runs[:2]):
        return _indeterminate(schema, "actual two-slot interleave batch shape missing")
    result = batch_envelope(evidence)
    return {"schema": schema, "verdict": result["verdict"], "admitted": False,
            "slots": result["slots"], "limits": result["limits"]}
