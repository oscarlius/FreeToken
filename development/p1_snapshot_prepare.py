"""Read-only validator for a future P1 non-zero decode-snapshot evidence bundle.

This tool neither launches a service nor writes a round/artifact. It validates
only a declared dictionary schema: SHA syntax and relational consistency among
declared fields. It does not open or hash retained raw files, validate receipt
contents or accepted-baseline contents, or establish process birth. A passing
bundle therefore never proves a GPU run or a real positive control.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "p1_snapshot_evidence/v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _nonnegative_int(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} integer")
    return value


def _identity(value: Any, name: str) -> dict:
    item = _mapping(value, name)
    uid = item.get("uid")
    if not isinstance(uid, (str, int)) or isinstance(uid, bool) or str(uid) == "":
        raise ValueError(f"{name}.uid is invalid")
    return {
        "uid": str(uid),
        "slot": _nonnegative_int(item.get("slot"), f"{name}.slot"),
        "device_tokens": _nonnegative_int(item.get("device_tokens"), f"{name}.device_tokens", positive=True),
    }


def validate(evidence: dict) -> dict:
    """Fail closed unless three retained decode->donate->restore chains bind."""
    evidence = _mapping(evidence, "evidence")
    if evidence.get("schema") != SCHEMA:
        raise ValueError("unsupported P1 evidence schema")
    base = _mapping(evidence.get("base"), "base")
    commit = base.get("commit")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ValueError("base.commit must be a full lowercase commit")
    if not isinstance(base.get("code_version"), str) or not base["code_version"].startswith("E2-base.1@"):
        raise ValueError("P1 needs an accepted E2-base.1 code version")
    _sha(base.get("accepted_e2_base1_receipt_sha256"), "base.accepted_e2_base1_receipt_sha256")
    t16 = _mapping(evidence.get("t16_default_gate"), "t16_default_gate")
    if t16.get("verdict") != "kept" or t16.get("commit") != commit:
        raise ValueError("default T16 gate is not kept on this exact E2-base.1 commit")
    _sha(t16.get("receipt_sha256"), "t16_default_gate.receipt_sha256")

    inputs = _mapping(evidence.get("tokenized_input"), "tokenized_input")
    for field in ("input_ids_int32le_sha256", "trace_source_sha256", "tokenizer_source_sha256"):
        _sha(inputs.get(field), "tokenized_input." + field)
    if type(inputs.get("input_tokens")) is not int or inputs["input_tokens"] <= 0:
        raise ValueError("tokenized_input.input_tokens must be positive")

    processes = evidence.get("processes")
    if not isinstance(processes, list) or len(processes) != 3:
        raise ValueError("P1 requires exactly three independent process records")
    process_ids, chains = set(), []
    for index, raw in enumerate(processes):
        process = _mapping(raw, f"processes[{index}]")
        process_id = process.get("process_id")
        if not isinstance(process_id, str) or not process_id or process_id in process_ids:
            raise ValueError("process_id must be unique and nonempty")
        process_ids.add(process_id)
        if process.get("commit") != commit:
            raise ValueError(f"{process_id}: process commit differs from base")
        source = _mapping(process.get("source_bindings"), f"{process_id}.source_bindings")
        for field in ("serve_cmd_sha256", "startup_sha256", "runner_sha256", "compiled_extensions_sha256"):
            _sha(source.get(field), f"{process_id}.source_bindings.{field}")
        if source.get("tokenizer_source_sha256") != inputs["tokenizer_source_sha256"]:
            raise ValueError(f"{process_id}: tokenizer binding differs")

        decode = _identity(process.get("decode_snapshot"), f"{process_id}.decode_snapshot")
        _nonnegative_int(process["decode_snapshot"].get("successful_snapshot_count"),
                         f"{process_id}.decode_snapshot.successful_snapshot_count", positive=True)
        donation = _identity(process.get("donation"), f"{process_id}.donation")
        if donation != decode:
            raise ValueError(f"{process_id}: donation does not bind decode UID/slot/device length")
        restore = _identity(process.get("restore"), f"{process_id}.restore")
        source_slot = _nonnegative_int(process["restore"].get("source_slot"), f"{process_id}.restore.source_slot")
        if source_slot != donation["slot"] or restore["device_tokens"] != donation["device_tokens"]:
            raise ValueError(f"{process_id}: restore source slot or device length differs from donation")
        if restore["slot"] == source_slot:
            raise ValueError(f"{process_id}: restore destination slot aliases donated slot")
        if restore["uid"] == donation["uid"]:
            raise ValueError(f"{process_id}: restored consumer UID must differ from donor UID")
        admission = _mapping(process.get("admission"), f"{process_id}.admission")
        if str(admission.get("uid")) != restore["uid"]:
            raise ValueError(f"{process_id}: admission UID does not bind restored consumer")
        if _nonnegative_int(admission.get("cached_tokens"), f"{process_id}.admission.cached_tokens") != donation["device_tokens"]:
            raise ValueError(f"{process_id}: admission cache length does not bind donated device length")
        if _nonnegative_int(admission.get("prompt_tokens"), f"{process_id}.admission.prompt_tokens", positive=True) <= donation["device_tokens"]:
            raise ValueError(f"{process_id}: consumer prompt has no continuation beyond restored prefix")
        consumer = _mapping(process.get("consumer"), f"{process_id}.consumer")
        if str(consumer.get("uid")) != restore["uid"] or consumer.get("finished") is not True:
            raise ValueError(f"{process_id}: consumer terminal evidence does not bind restored UID")
        _nonnegative_int(consumer.get("completion_tokens"), f"{process_id}.consumer.completion_tokens", positive=True)
        if consumer.get("prefix_input_ids_int32le_sha256") != inputs["input_ids_int32le_sha256"]:
            raise ValueError(f"{process_id}: consumer prefix IDs differ from donor binding")
        _sha(consumer.get("raw_response_sha256"), f"{process_id}.consumer.raw_response_sha256")
        chains.append({"process_id": process_id, "donor_uid": donation["uid"],
                       "consumer_uid": restore["uid"], "device_tokens": donation["device_tokens"],
                       "source_slot": source_slot, "destination_slot": restore["slot"]})
    return {"schema": "p1_snapshot_validation/v1", "commit": commit,
            "code_version": base["code_version"], "processes": chains,
            "positive_decode_snapshot_coverage": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(args.evidence.read_text(encoding="utf-8"))), sort_keys=True))


if __name__ == "__main__":
    main()
