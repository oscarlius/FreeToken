"""Read-only retained-file verifier for a future P1 decode-snapshot packet.

The verifier opens only files declared beneath an explicit evidence root, rejects
symlinks and escapes, hashes their bytes, and compares raw JSON records with
the declared baseline/source/process bindings. It validates retained evidence
but neither launches a service nor proves that the retained records were
created by an accepted P1 GPU run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "p1_snapshot_evidence_files/v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SOURCE_FIELDS = ("serve_cmd_sha256", "startup_sha256", "runner_sha256", "compiled_extensions_sha256")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _identity(value: Any, name: str) -> dict[str, Any]:
    item = _mapping(value, name)
    uid = item.get("uid")
    if not isinstance(uid, (str, int)) or isinstance(uid, bool) or not str(uid):
        raise ValueError(f"{name}.uid is invalid")
    slot = item.get("slot")
    if type(slot) is not int or slot < 0:
        raise ValueError(f"{name}.slot is invalid")
    return {"uid": str(uid), "slot": slot, "device_tokens": _positive(item.get("device_tokens"), f"{name}.device_tokens")}


def _safe_file(root: Path, relative: Any, name: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{name}.path must be a nonempty relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{name}.path escapes evidence root")
    path = root / candidate
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{name}.path contains a symlink")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(f"{name}.path is missing or escapes evidence root") from error
    if not path.is_file():
        raise ValueError(f"{name}.path is not a regular file")
    return path


def _file(root: Path, declared: Any, name: str) -> tuple[Path, str]:
    item = _mapping(declared, name)
    expected = _sha(item.get("sha256"), f"{name}.sha256")
    path = _safe_file(root, item.get("path"), name)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"{name}.sha256 does not match retained file")
    return path, actual


def _json_file(root: Path, declared: Any, name: str) -> dict[str, Any]:
    path, _ = _file(root, declared, name)
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), name + ".json")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not a JSON object") from error


def _same(actual: Any, declared: Any, name: str) -> None:
    if actual != declared:
        raise ValueError(f"{name} differs from retained record")


def verify(packet: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    """Fail closed unless all declared bindings agree with retained bytes and JSON."""
    packet = _mapping(packet, "packet")
    if packet.get("schema") != SCHEMA:
        raise ValueError("unsupported retained evidence schema")
    root = evidence_root.resolve(strict=True)
    if evidence_root.is_symlink() or not root.is_dir():
        raise ValueError("evidence root must be a real directory")
    base = _mapping(packet.get("base"), "base")
    commit = base.get("commit")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ValueError("base.commit must be a full lowercase commit")
    code_version = base.get("code_version")
    if not isinstance(code_version, str) or not code_version.startswith("E2-base.1@"):
        raise ValueError("base.code_version must name E2-base.1")
    accepted = _json_file(root, base.get("accepted_receipt"), "base.accepted_receipt")
    _same(accepted.get("commit"), commit, "accepted receipt commit")
    _same(accepted.get("code_version"), code_version, "accepted receipt code_version")
    _same(accepted.get("verdict"), "accepted", "accepted receipt verdict")
    t16 = _mapping(packet.get("t16_default_gate"), "t16_default_gate")
    t16_receipt = _json_file(root, t16.get("receipt"), "t16_default_gate.receipt")
    _same(t16.get("verdict"), "kept", "declared T16 verdict")
    _same(t16_receipt.get("verdict"), "kept", "T16 receipt verdict")
    _same(t16_receipt.get("commit"), commit, "T16 receipt commit")

    inputs = _mapping(packet.get("tokenized_input"), "tokenized_input")
    for field in ("input_ids", "trace_source", "tokenizer_source"):
        path, actual = _file(root, inputs.get(field), "tokenized_input." + field)
        _same(inputs[field].get("sha256"), actual, f"tokenized_input.{field} hash")
    _positive(inputs.get("input_tokens"), "tokenized_input.input_tokens")

    processes = packet.get("processes")
    if not isinstance(processes, list) or len(processes) != 3:
        raise ValueError("exactly three process packets are required")
    ids: set[str] = set()
    report = []
    for index, declared in enumerate(processes):
        declared = _mapping(declared, f"processes[{index}]")
        process_id = declared.get("process_id")
        if not isinstance(process_id, str) or not process_id or process_id in ids:
            raise ValueError("process_id must be unique and nonempty")
        ids.add(process_id)
        raw = _json_file(root, declared.get("record"), f"{process_id}.record")
        for field in ("process_id", "commit"):
            _same(raw.get(field), declared.get(field), f"{process_id}.{field}")
        _same(raw.get("commit"), commit, f"{process_id} raw commit")
        source = _mapping(declared.get("source_bindings"), f"{process_id}.source_bindings")
        raw_source = _mapping(raw.get("source_bindings"), f"{process_id}.record.source_bindings")
        for field in _SOURCE_FIELDS:
            _, source_hash = _file(root, source.get(field), f"{process_id}.source_bindings.{field}")
            _same(raw_source.get(field), source_hash, f"{process_id} raw {field}")
        for field in ("decode_snapshot", "donation", "restore", "admission", "consumer"):
            _same(raw.get(field), declared.get(field), f"{process_id}.{field}")
        decode = _identity(raw.get("decode_snapshot"), f"{process_id}.decode_snapshot")
        _positive(_mapping(raw["decode_snapshot"], f"{process_id}.decode_snapshot").get("successful_snapshot_count"), f"{process_id}.decode_snapshot.successful_snapshot_count")
        donation = _identity(raw.get("donation"), f"{process_id}.donation")
        restore = _identity(raw.get("restore"), f"{process_id}.restore")
        if donation != decode:
            raise ValueError(f"{process_id}: donation does not bind decode")
        if raw["restore"].get("source_slot") != donation["slot"] or restore["device_tokens"] != donation["device_tokens"]:
            raise ValueError(f"{process_id}: restore does not bind donated slot/length")
        if restore["slot"] == donation["slot"] or restore["uid"] == donation["uid"]:
            raise ValueError(f"{process_id}: restore aliases donor slot or UID")
        admission = _mapping(raw.get("admission"), f"{process_id}.admission")
        if str(admission.get("uid")) != restore["uid"] or admission.get("cached_tokens") != donation["device_tokens"]:
            raise ValueError(f"{process_id}: admission does not bind restored cache")
        if _positive(admission.get("prompt_tokens"), f"{process_id}.admission.prompt_tokens") <= donation["device_tokens"]:
            raise ValueError(f"{process_id}: consumer has no suffix")
        consumer = _mapping(raw.get("consumer"), f"{process_id}.consumer")
        if str(consumer.get("uid")) != restore["uid"] or consumer.get("finished") is not True:
            raise ValueError(f"{process_id}: consumer terminal record is invalid")
        _positive(consumer.get("completion_tokens"), f"{process_id}.consumer.completion_tokens")
        report.append({"process_id": process_id, "donor_uid": donation["uid"], "consumer_uid": restore["uid"]})
    return {"schema": "p1_snapshot_retained_verification/v1", "commit": commit, "processes": report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.packet.read_text(encoding="utf-8")), args.evidence_root), sort_keys=True))


if __name__ == "__main__":
    main()
