"""Run one T17 same-structure continuation case with retained physical evidence."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import gate, raw, schedule


def _value(resources: Any, name: str, default: Any = None) -> Any:
    return resources.get(name, default) if isinstance(resources, dict) else getattr(resources, name, default)


def _reader(resources: Any, name: str, default: Any) -> Any:
    readers = _value(resources, "readers")
    if readers is not None:
        return _value(readers, name, default)
    return _value(resources, name, default)


def _read_proc_stat(pid: int) -> str:
    return (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")


def _proc_identity(pid: Any, *, read_stat: Any = _read_proc_stat) -> dict:
    if type(pid) is not int or pid <= 0:
        raise ValueError("live service PID required for reference identity")
    try:
        values = read_stat(pid).rpartition(") ")[2].split()
        start_ticks = int(values[19])
    except (OSError, IndexError, ValueError) as error:
        raise ValueError("live service /proc start_ticks required") from error
    if not values or values[0] == "Z" or start_ticks <= 0:
        raise ValueError("live service start_ticks must be positive")
    return {"pid": pid, "start_ticks": start_ticks,
            "execution_id": f"{pid}:{start_ticks}"}


def _identity(resources: Any, runner: Any) -> dict:
    pid = getattr(getattr(runner, "proc", None), "pid", None)
    if type(pid) is not int or pid <= 0:
        raise ValueError("live service PID required for reference identity")
    read_stat = _reader(resources, "read_proc_stat", _read_proc_stat)
    read_process = _reader(resources, "read_process", None)
    if read_process is None:
        read_process = lambda process_id: _proc_identity(process_id, read_stat=read_stat)
    identity = read_process(pid)
    if not isinstance(identity, dict):
        raise ValueError("physical process reader must return an identity object")
    if any(key not in identity or type(identity[key]) is not int or identity[key] <= 0
           for key in ("pid", "start_ticks")) or identity["pid"] != pid:
        raise ValueError("physical PID/start_ticks identity is incomplete")
    execution_id = identity.get("execution_id", f"{pid}:{identity['start_ticks']}")
    if not isinstance(execution_id, str) or not execution_id:
        raise ValueError("physical execution identity is incomplete")
    return {"pid": pid, "start_ticks": identity["start_ticks"], "execution_id": execution_id}


def _case_inputs(resources: Any, case: dict) -> tuple[list[int], list[int]]:
    provider = _value(resources, "case_inputs")
    supplied = provider(case) if callable(provider) else case
    if not isinstance(supplied, dict):
        raise ValueError("target frontend must provide concrete input IDs")
    donor = supplied.get("donor")
    query = supplied.get("query")
    if query is None:
        query = supplied.get("short") if case.get("tail") == 65 else supplied.get("long")
    if not isinstance(donor, list) or not isinstance(query, list):
        raise ValueError("target frontend donor and query IDs are required")
    if any(type(token) is not int for token in donor + query):
        raise ValueError("target frontend input IDs must be integers")
    length, tail = case.get("length"), case.get("tail")
    if type(length) is not int or type(tail) is not int or length <= 0 or tail <= 0:
        raise ValueError("case length and tail must be positive integers")
    if len(donor) != length + 1 or len(query) != length + tail or donor != query[:length + 1]:
        raise ValueError("actual target frontend IDs do not bind L+1 donor to query")
    query_sha = gate.token_sha(query)
    expected_sha = supplied.get("input_ids_sha256", supplied.get("query_input_ids_sha256"))
    if expected_sha is not None and expected_sha != query_sha:
        raise ValueError("target frontend query token SHA differs before request")
    return list(donor), list(query)


def _state_case(case: dict) -> dict:
    context = case.get("context", case.get("expected_ngram"))
    if not isinstance(context, list) or any(type(token) is not int for token in context):
        raise ValueError("actual target boundary context required for state validation")
    if type(case.get("trace_index")) is not int or not isinstance(case.get("name"), str):
        raise ValueError("actual target case identity required for state validation")
    return {"name": case["name"], "length": case["length"],
            "trace_index": case["trace_index"], "context": context}


def _write_schedule(directory: Path, case: dict, rows: list[dict], warm: dict) -> tuple[Path, str, list[dict]]:
    directory.mkdir(exist_ok=False)
    compiled = schedule.compile_schedule(rows, donor_uid=str(warm["donor_uid"]),
                                         hit_uid=str(warm["hit_uid"]),
                                         cached_tokens=warm["actual_cached_tokens"],
                                         prompt_tokens=case["length"] + case["tail"])
    path = directory / "schedule.json"
    sha = schedule.write_new(path, compiled)
    os.chmod(path, 0o444)
    receipt = {"schema": "ft_equiv_t17_schedule/v1", "schedule_sha256": sha,
               "donor_uid": warm["donor_uid"], "hit_uid": warm["hit_uid"],
               "prompt_tokens": case["length"] + case["tail"]}
    schedule.write_new(directory / "schedule_receipt.json", receipt)
    os.chmod(directory / "schedule_receipt.json", 0o444)
    return path, sha, compiled


def _source_segment(rows: list[dict], uid: str) -> int:
    first = schedule.request_segments(rows, uid)[0]
    return first["start"] + first["subchunks"][0]


def run_case(resources: Any, case: dict) -> dict:
    """Collect one warm arm and two fresh same-structure references.

    ``resources`` belongs to the outer runner: it owns the round directory, lock,
    service lifecycle, and any optional ordinary-cold envelope collection.
    """
    runner = _value(resources, "run", resources)
    if not callable(getattr(runner, "service", None)) or not callable(getattr(runner, "request", None)):
        raise ValueError("resources must expose the retained Run.service/request lifecycle")
    donor_ids, query_ids = _case_inputs(resources, case)
    query_sha = gate.token_sha(query_ids)
    state_case = _state_case(case)
    legacy = _reader(resources, "legacy", None)
    warm_reader = _reader(resources, "read_warm", raw.read_warm)
    reference_reader = _reader(resources, "read_reference", raw.read_reference)
    if legacy is None:
        raise ValueError("actual t17_d14_artifacts reader is required")
    schedule_root = _value(resources, "schedule_dir")
    if not isinstance(schedule_root, Path):
        raise ValueError("outer runner must provide an exclusive round schedule directory")

    warm_arm: Path | None = None

    def warm_operation(arm: Path) -> dict:
        nonlocal warm_arm
        warm_arm = arm
        runner.request(arm, "donor", donor_ids, 0, 2)
        runner.request(arm, "hit", query_ids, case["length"], 128)
        return warm_reader(legacy, arm, state_case, query="hit")

    warm = runner.service(case["name"] + "-warm", warm_operation, health_only=True)
    # The physical D0 rows, not the declared case, are the only schedule source.
    if not isinstance(warm, dict) or warm_arm is None:
        raise ValueError("Run.service must return warm reader evidence")
    if warm.get("warm", {}).get("input_ids_sha256") != query_sha:
        raise ValueError("warm actual reader input IDs differ from this target frontend query")
    rows, d0_sha = schedule.read_jsonl(warm_arm / "d0_prefill.jsonl")
    schedule_path, schedule_sha, compiled = _write_schedule(schedule_root, case, rows, warm)
    donor_first_segment_end = _source_segment(rows, str(warm["donor_uid"]))
    expected_first_child_end = _source_segment(rows, str(warm["hit_uid"]))
    evidence = {**warm, "warm": warm["warm"], "compiled_schedule_sha256": schedule_sha,
                "warm_d0_sha256": d0_sha, "expected_first_child_end": expected_first_child_end,
                "donor_first_segment_end": donor_first_segment_end,
                "requested_input_ids_sha256": query_sha,
                "references": []}
    handoff = gate.handoff(evidence)
    if handoff["verdict"] != "PASS":
        return {"case": case["name"], "schedule": str(schedule_path), "evidence": evidence,
                "result": gate.evaluate(evidence), "stopped": "state_handoff"}

    references = []
    for number in (1, 2):
        name = f"{case['name']}-reference-{number}"
        def reference_operation(reference_arm: Path, *, number: int = number) -> dict:
            identity = _identity(resources, runner)
            runner.request(reference_arm, "query", query_ids, 0, 128)
            record = reference_reader(legacy, reference_arm, schedule_path=schedule_path, identity=identity)
            if record.get("actual_segments") != compiled:
                raise ValueError("reference actual D0 segments differ from the compiled schedule")
            return record
        references.append(runner.service(name, reference_operation, schedule=schedule_path, health_only=True))
    evidence["references"] = references
    result = dict(gate.evaluate(evidence), admitted=False)
    if (result.get("same_structure_reference", {}).get("verdict") == "not_met"):
        result.setdefault("diagnostic_required", True)
    output = {"case": case["name"], "schedule": str(schedule_path), "evidence": evidence, "result": result}
    if result["verdict"] in {"failed_harness", "not_met"}:
        output["stopped"] = result["verdict"]
        return output
    if (_value(resources, "allow_cold_envelope", False)
            and result["verdict"] == "measurements_pass_pending_independent_review"):
        request_evidence = _reader(resources, "request_evidence", getattr(legacy, "request_evidence", None))
        if not callable(request_evidence):
            raise ValueError("actual ordinary-cold evidence reader is required")
        def cold_operation(cold_arm: Path) -> dict:
            runner.request(cold_arm, "query", query_ids, 0, 128)
            observed = request_evidence(cold_arm, "query", 0, 128)
            cold = {"token_ids": observed["tokens"], "text": observed["response"]["text"],
                    "input_ids_sha256": observed["input_sha256"]}
            if cold["input_ids_sha256"] != query_sha:
                raise ValueError("ordinary cold actual input IDs differ from this target frontend query")
            return cold
        cold = runner.service(case["name"] + "-cold-envelope", cold_operation, health_only=True)
        output["ordinary_cold_envelope"] = {
            "recorded": True, "admitted": False,
            "output": gate.output_comparison(warm["warm"], cold),
            "limits": "output envelope only; numerical state envelope and T04 remain unimplemented",
        }
    return output
