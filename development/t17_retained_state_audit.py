"""Read-only retained-donate audit for a terminal T17 case.

This creates only a new ``dev_D16/retained_state_readonly_<hash>`` directory.
It never writes an arm, index, service, or round artifact.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import re
from typing import Any


SCHEMA = "ft_t17_retained_state_readonly/v1"
SIDECAR_SCHEMA = "ft_equiv_retained_state_sidecar/v1"
ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
ARM_NAMES = ("warm", "reference_1", "reference_2", "cold_envelope")


class AuditError(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_case_name(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise AuditError("case name is not a safe canonical/arm mapping")
    return value.replace("-", "_")


def token_sha(ids: list[int]) -> str:
    if not ids or any(type(value) is not int or not 0 <= value < 2**31 for value in ids):
        raise AuditError("observed input IDs are not a nonempty int32 list")
    return sha(struct.pack(f"<{len(ids)}i", *ids))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError("unreadable JSON source: " + str(path)) from error


def file_receipt(path: Path, *, include_bytes: bool = False) -> dict:
    raw = path.read_bytes()
    receipt = {"path": str(path), "sha256": sha(raw), "bytes": len(raw)}
    if include_bytes:
        receipt["bytes_base64"] = base64.b64encode(raw).decode()
    return receipt


def arm_paths(case_root: Path) -> dict[str, Path]:
    names = {
        "warm": case_root.with_name(case_root.name + "_warm"),
        "reference_1": case_root.with_name(case_root.name + "_reference_1"),
        "reference_2": case_root.with_name(case_root.name + "_reference_2"),
        "cold_envelope": case_root.with_name(case_root.name + "_cold_envelope"),
    }
    for label, path in names.items():
        if path.is_symlink() or not path.is_dir():
            raise AuditError("missing arm directory: " + label)
    return names


def terminal_proof(arm: Path, label: str) -> dict:
    required = ("donor.response.bin", "hit.response.bin") if label == "warm" else ("query.response.bin",)
    missing = [name for name in required if not (arm / name).is_file()]
    if missing:
        raise AuditError("arm lacks terminal saved response: " + label)
    response = {name: file_receipt(arm / name) for name in required}
    d0 = arm / "d0_decode.json"
    if not d0.is_file():
        raise AuditError("arm lacks D0 terminal record: " + label)
    prefill = arm / "d0_prefill.jsonl"
    if not prefill.is_file():
        raise AuditError("arm lacks D0 prefill record: " + label)
    return {"responses": response, "d0_decode": file_receipt(d0), "d0_prefill": file_receipt(prefill)}


def observed_input(arm: Path, uid: str, snapshot_length: int) -> tuple[list[int], dict]:
    path = arm / "observations.jsonl"
    if not path.is_file():
        raise AuditError("arm lacks observations: " + str(arm))
    matches = []
    for raw in path.read_bytes().splitlines(keepends=True):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AuditError("observations JSON is invalid") from error
        ids = row.get("input_ids") if isinstance(row, dict) else None
        if (isinstance(ids, list) and row.get("kind") == "input" and str(row.get("uid")) == uid
                and type(row.get("input_length")) is int and row["input_length"] == len(ids)
                and len(ids) >= snapshot_length):
            if row.get("ids_int32le_sha256") != token_sha(ids):
                raise AuditError("observations input SHA differs")
            matches.append((ids, raw, row))
    if len(matches) != 1:
        raise AuditError("observations do not uniquely bind Scheduler UserMsg input/UID")
    ids, raw, row = matches[0]
    return ids, {"path": str(path), "sha256": sha(raw), "bytes_base64": base64.b64encode(raw).decode(),
                 "uid": uid, "input_ids_sha256": row["ids_int32le_sha256"]}


def input_receipt(arm: Path, uid: str, ids: list[int]) -> dict:
    path = arm / "inputs" / (uid + ".json")
    document = load_json(path)
    if (not isinstance(document, dict) or str(document.get("uid")) != uid
            or document.get("numel") != len(ids) or document.get("int32le_sha256") != token_sha(ids)):
        raise AuditError("input receipt does not bind Scheduler UserMsg IDs/UID")
    return file_receipt(path, include_bytes=True)


def selected_donate(arm: Path, *, uid: str, input_length: int) -> tuple[dict, bytes, bytes]:
    index = arm / "dump" / "index.jsonl"
    if index.is_symlink() or not index.is_file():
        raise AuditError("arm lacks regular dump/index.jsonl")
    raw_index = index.read_bytes()
    matches = []
    for raw in raw_index.splitlines(keepends=True):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if (isinstance(row, dict) and row.get("kind") == "donate" and type(row.get("seq")) is int
                and row["seq"] > 0 and str(row.get("uid")) == uid and type(row.get("length")) is int
                and 0 < row["length"] < input_length):
            matches.append((row, raw))
    if len(matches) != 1:
        raise AuditError("donate selection is not unique for arm")
    return matches[0][0], raw_index, matches[0][1]


def reference_identity(reference: object, source: Path) -> tuple[dict, dict]:
    """Use the saved case's reference identity, never a caller supplied replacement."""
    identity = reference.get("process_identity") if isinstance(reference, dict) else None
    if (not isinstance(identity, dict) or type(identity.get("pid")) is not int or identity["pid"] <= 0
            or type(identity.get("start_ticks")) is not int or identity["start_ticks"] <= 0
            or not isinstance(identity.get("execution_id"), str) or not identity["execution_id"]):
        raise AuditError("saved case reference lacks physical process identity")
    return identity, {"source": file_receipt(source, include_bytes=True)}


def build_sidecar(arm: Path, *, reference: dict, saved_case: Path) -> tuple[dict, dict]:
    reference_sha = reference.get("input_ids_sha256")
    if not isinstance(reference_sha, str):
        raise AuditError("saved case reference lacks input IDs SHA")
    candidates = []
    observations = arm / "observations.jsonl"
    for raw in observations.read_bytes().splitlines(keepends=True):
        row = json.loads(raw)
        ids = row.get("input_ids") if isinstance(row, dict) else None
        if (isinstance(ids, list) and row.get("kind") == "input" and row.get("ids_int32le_sha256") == token_sha(ids)
                and token_sha(ids) == reference_sha):
            candidates.append((str(row.get("uid")), ids, raw))
    if len(candidates) != 1:
        raise AuditError("saved case reference does not uniquely bind arm input IDs/UID")
    uid, ids, input_line = candidates[0]
    selected, index, line = selected_donate(arm, uid=uid, input_length=len(ids))
    selection = {"kind": "donate", "seq": selected["seq"], "uid": uid}
    snapshot_length = selected["length"]
    if reference.get("d0_sha256") != sha((arm / "d0_prefill.jsonl").read_bytes()):
        raise AuditError("saved case reference D0 SHA differs")
    segments = reference.get("actual_segments")
    if not isinstance(segments, list) or not segments or segments[-1].get("end") != len(ids):
        raise AuditError("saved case reference does not bind full query coordinates")
    files = selected.get("files")
    if not isinstance(files, dict) or set(files) != set(ROLES):
        raise AuditError("selected donate row lacks four role paths")
    observed_receipt = {"path": str(observations), "sha256": sha(input_line),
                        "bytes_base64": base64.b64encode(input_line).decode(), "uid": uid,
                        "input_ids_sha256": reference_sha, "receipt": input_receipt(arm, uid, ids)}
    identity, birth_info = reference_identity(reference, saved_case)
    roles = {}
    for role in ROLES:
        relative = files[role]
        path = arm / "dump" / relative
        if not isinstance(relative, str) or path.is_symlink() or not path.is_file() or path.resolve().parent != (arm / "dump").resolve():
            raise AuditError("donate role path is unsafe: " + role)
        roles[role] = {"path": relative, "sha256": sha(path.read_bytes())}
    document = {"schema": SIDECAR_SCHEMA, "index_sha256": sha(index), "capture_receipt_sha256": sha(line),
                "kind": "donate", "seq": selection["seq"], "uid": selection["uid"],
                "process_identity": identity,
                "event_identity": str(arm.resolve()) + ":" + uid + ":" + sha(line),
                "input_ids": ids, "input_ids_sha256": reference_sha, "snapshot_length": snapshot_length,
                "snapshot_prefix_ids": ids[:snapshot_length], "snapshot_prefix_ids_sha256": token_sha(ids[:snapshot_length]),
                "role_files": roles}
    evidence = {"index": {"path": str(arm / "dump" / "index.jsonl"), "sha256": sha(index)},
                "selected_index_line": {"sha256": sha(line), "bytes_base64": base64.b64encode(line).decode(), **selection},
                "input": observed_receipt, "d0_prefill": file_receipt(arm / "d0_prefill.jsonl"),
                "case_reference_identity": birth_info, "role_files": roles}
    return document, evidence


def load_reader(suite_root: Path):
    sys.path.insert(0, str(suite_root / "scripts"))
    return importlib.import_module("equiv_suite.retained_state")


def saved_case_receipt(path: Path, case_root: Path) -> tuple[dict, list[dict]]:
    document = load_json(path)
    result = document.get("result") if isinstance(document, dict) else None
    ordinary = document.get("ordinary_cold_envelope") if isinstance(document, dict) else None
    references = document.get("evidence", {}).get("references") if isinstance(document.get("evidence"), dict) else None
    if (not isinstance(document, dict) or canonical_case_name(document.get("case")) != canonical_case_name(case_root.name)
            or not isinstance(result, dict)
            or result.get("verdict") != "measurements_pass_pending_independent_review"
            or not isinstance(ordinary, dict) or ordinary.get("recorded") is not True
            or not isinstance(references, list) or len(references) != 2):
        raise AuditError("saved case evidence is not a completed two-reference result")
    return file_receipt(path, include_bytes=True), references


def audit(case_root: Path, sidecar_root: Path, reader, *, case_receipt: Path) -> dict:
    sidecar_root.mkdir(parents=True, exist_ok=True)
    arms = arm_paths(case_root)
    saved_case, references = saved_case_receipt(case_receipt, case_root)
    terminal = {"saved_case": saved_case,
                "arms": {label: terminal_proof(arm, label) for label, arm in arms.items()}}
    sidecars, sources = {}, {}
    for label, reference in zip(("reference_1", "reference_2"), references, strict=True):
        document, sources[label] = build_sidecar(arms[label], reference=reference, saved_case=case_receipt)
        path = sidecar_root / (label + ".json")
        path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
        sidecars[label] = {"path": path, "sha256": sha(path.read_bytes())}
    envelope = reader.read_retained(arms["reference_1"] / "dump", arms["reference_2"] / "dump",
        left_selection={key: sources["reference_1"]["selected_index_line"][key] for key in ("kind", "seq", "uid")},
        right_selection={key: sources["reference_2"]["selected_index_line"][key] for key in ("kind", "seq", "uid")},
        left_sidecar=sidecars["reference_1"]["path"], left_sidecar_sha256=sidecars["reference_1"]["sha256"],
        right_sidecar=sidecars["reference_2"]["path"], right_sidecar_sha256=sidecars["reference_2"]["sha256"])
    return {"schema": SCHEMA, "admitted": False, "verdict": "recorded",
            "scope": "offline donate-state envelope only; not restore equivalence, logits, or T17 gate",
            "case": case_root.name, "terminal_proof": terminal, "reference_sources": sources,
            "reference_repeat_envelope": envelope,
            "unbound_arms": {label: {"verdict": "indeterminate", "reason": "missing per-arm service birth identity"}
                             for label in ("warm", "cold_envelope")}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, required=True)
    parser.add_argument("--suite-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--case-receipt", type=Path, required=True)
    args = parser.parse_args()
    run_id = sha(str(args.case_root.resolve()).encode() + args.case_receipt.read_bytes())[:12]
    if args.out_root.resolve().name != "dev_D16":
        parser.error("--out-root must be the dedicated dev_D16 directory")
    output = args.out_root / ("retained_state_readonly_" + run_id)
    version = 2
    while output.exists():
        output = args.out_root / ("retained_state_readonly_" + run_id + "_v" + str(version))
        version += 1
    output.mkdir(parents=True)
    runtime = None
    try:
        import torch
        runtime = {"torch_version": torch.__version__, "cuda_initialized": bool(torch.cuda.is_initialized())}
        result = audit(args.case_root, output, load_reader(args.suite_root), case_receipt=args.case_receipt)
        result["runtime"] = runtime
    except (AuditError, OSError, ValueError, json.JSONDecodeError) as error:
        result = {"schema": SCHEMA, "admitted": False, "verdict": "indeterminate", "reason": str(error)}
        if runtime is not None:
            result["runtime"] = runtime
    report = output / "report.json"
    report.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(output), "report_sha256": sha(report.read_bytes()),
                      "verdict": result["verdict"], "admitted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
