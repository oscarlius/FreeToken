"""Fail-closed D16 reader for retained exact-ID workload evidence.

The caller supplies a SHA-pinned evidence map.  This module never sends a
request, creates a scheduler event, or treats concurrent HTTP submission as a
physical batch proof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any

from .sampler_capture import CaptureError, _receipt_rows


SCHEMA = "ft_d16_native_workloads/v1"
MAP_SCHEMA = "ft_d16_native_workload_map/v1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _token_sha(ids: list[int]) -> str:
    if not ids or any(type(value) is not int or not -(2 ** 31) <= value < 2 ** 31 for value in ids):
        raise ValueError("token IDs must be nonempty signed int32 values")
    return _sha(struct.pack("<%di" % len(ids), *ids))


def _identity(value: object) -> dict[str, object]:
    if (not isinstance(value, dict) or type(value.get("pid")) is not int or value["pid"] <= 0
            or type(value.get("start_ticks")) is not int or value["start_ticks"] <= 0
            or not isinstance(value.get("execution_id"), str) or not value["execution_id"]):
        raise ValueError("typed process birth identity is required")
    return {"pid": value["pid"], "start_ticks": value["start_ticks"], "execution_id": value["execution_id"]}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _safe_evidence_path(root: Path, value: object, *, directory: bool) -> Path:
    """Resolve a map path without allowing lexical or symlink escape."""
    if not isinstance(value, str) or not value:
        raise ValueError("evidence paths must be nonempty relative paths")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise ValueError("evidence path escapes its root")
    base = root.resolve()
    candidate = root / relative
    try:
        candidate.resolve().relative_to(base)
    except ValueError as error:
        raise ValueError("evidence path escapes its root") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("evidence path traverses a symbolic link")
    if candidate.resolve() == base or (directory and not candidate.is_dir()) or (not directory and not candidate.is_file()):
        raise ValueError("evidence directory is unavailable" if directory else "evidence path is not a regular file")
    return candidate


def _relative(root: Path, value: object) -> Path:
    return _safe_evidence_path(root, value, directory=False)


def _relative_dir(root: Path, value: object) -> Path:
    return _safe_evidence_path(root, value, directory=True)

def _all_files(root: Path, map_path: Path) -> set[str]:
    result: set[str] = set()
    for path in root.rglob("*"):
        if path == map_path:
            continue
        if path.is_symlink():
            raise ValueError("evidence tree contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("evidence tree contains a non-file node")
        result.add(path.relative_to(root).as_posix())
    return result


def _pinned_map(root: Path, map_name: str, expected_sha256: str) -> tuple[dict[str, Any], dict[str, Path]]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("external evidence-map SHA is required")
    map_path = _relative(root, map_name)
    raw = map_path.read_bytes()
    if _sha(raw) != expected_sha256:
        raise ValueError("external evidence-map SHA differs")
    document = _load_json(map_path)
    files = document.get("files")
    if document.get("schema") != MAP_SCHEMA or not isinstance(files, dict) or not files:
        raise ValueError("evidence map schema or file inventory is invalid")
    paths: dict[str, Path] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise ValueError("evidence map file digest is invalid")
        path = _relative(root, name)
        if _sha(path.read_bytes()) != digest:
            raise ValueError("evidence-map file digest differs")
        paths[name] = path
    if set(paths) != _all_files(root, map_path):
        raise ValueError("evidence tree has undeclared or missing files")
    return document, paths


def _response(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    value = _load_json(path)
    value = value.get("response", value)
    if (not isinstance(value, dict) or value.get("uid") != row["uid"] or value.get("finished") is not True
            or value.get("input_ids_sha256") != row["input_ids_sha256"]
            or value.get("usage", {}).get("completion_tokens") != 128
            or not isinstance(value.get("text"), str)):
        raise ValueError("raw HTTP response is not terminal exact-ID evidence")
    return value


def _sampler_stream(root: Path, identity: dict[str, object], uids: set[int]) -> tuple[dict[int, list[int]], dict[int, list[object]]]:
    """Re-read every snapshot receipt; no service-delivery summary is trusted."""
    import torch
    manifest_path = root / "manifest.json"
    if root.is_symlink() or not root.is_dir() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("sampler root is unavailable")
    manifest = _load_json(manifest_path)
    captures = manifest.get("captures")
    if (manifest.get("schema") != "ft_equiv_sampler_capture/v1" or manifest.get("terminal") != "complete"
            or not isinstance(captures, list) or type(manifest.get("serialized_bytes")) is not int):
        raise ValueError("sampler manifest is not terminal")
    declared, total, streams = set(), 0, {uid: [] for uid in uids}
    logits_by_uid = {uid: [] for uid in uids}
    for entry in captures:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in declared:
            raise ValueError("sampler manifest entry is invalid")
        declared.add(entry["id"])
        directory = root / entry["id"]
        if (directory.is_symlink() or not directory.is_dir()
                or {item.name for item in directory.iterdir()} != {"receipt.json", "logits_fp32.pt"}):
            raise ValueError("sampler capture has undeclared children")
        receipt_path, logits_path = directory / "receipt.json", directory / "logits_fp32.pt"
        raw_receipt, raw_logits = receipt_path.read_bytes(), logits_path.read_bytes()
        if (entry.get("receipt_sha256") != _sha(raw_receipt) or entry.get("serialized_bytes") != len(raw_receipt) + len(raw_logits)
                or entry.get("capture_count") is None):
            raise ValueError("sampler manifest does not bind raw capture bytes")
        receipt = _load_json(receipt_path)
        logits = torch.load(logits_path, map_location="cpu", weights_only=True)
        try:
            _receipt_rows(receipt, logits, len(raw_logits))
        except CaptureError as error:
            raise ValueError("sampler receipt is invalid: " + str(error)) from error
        if _identity(receipt.get("process_identity")) != identity:
            raise ValueError("sampler receipt process birth differs from service capture")
        for sample in receipt["rows"]:
            uid = sample["uid"]
            if uid not in streams:
                raise ValueError("sampler contains an undeclared workload UID")
            if sample["generation_index"] != len(streams[uid]):
                raise ValueError("sampler UID stream is incomplete or reordered")
            row_index = sample.get("row_index")
            if type(row_index) is not int or not 0 <= row_index < logits.shape[0]:
                raise ValueError("sampler receipt row has no snapshot row")
            streams[uid].append(sample["sampled_token_id"])
            logits_by_uid[uid].append(logits[row_index].detach().clone())
        total += entry["serialized_bytes"]
    if total != manifest["serialized_bytes"] or {item.name for item in root.iterdir()} != {"manifest.json", *declared}:
        raise ValueError("sampler manifest omits retained bytes")
    if any(len(tokens) != 128 for tokens in streams.values()):
        raise ValueError("sampler does not retain a complete 128-token UID stream")
    return streams, logits_by_uid


def _service(path: Path, sampler_root: Path, rows: list[dict[str, Any]], identity: dict[str, object], slots: int) -> tuple[dict[int, list[int]], dict[int, list[object]]]:
    document = _load_json(path)
    uids = {row["uid"] for row in rows}
    if (document.get("schema") != "ft_equiv_service_capture/v2" or document.get("terminal") != "complete"
            or document.get("admitted") is not False or document.get("process_identity") != identity):
        raise ValueError("service capture terminal/process contract differs")
    admissions = document.get("admission_receipts")
    if not isinstance(admissions, list) or {item.get("uid") for item in admissions if isinstance(item, dict)} != uids:
        raise ValueError("service capture admissions do not exactly bind workload UIDs")
    by_uid = {row["uid"]: row for row in rows}
    for admission in admissions:
        receipt_path = admission.get("receipt_path")
        if not isinstance(receipt_path, str) or Path(receipt_path).is_absolute() or ".." in Path(receipt_path).parts:
            raise ValueError("admission receipt path is invalid")
        raw = path.parent / receipt_path
        if raw.is_symlink() or not raw.is_file() or _sha(raw.read_bytes()) != admission.get("receipt_sha256"):
            raise ValueError("admission receipt SHA differs")
        receipt = _load_json(raw)
        if receipt.get("uid") not in by_uid or receipt.get("input_ids_sha256") != by_uid[receipt["uid"]]["input_ids_sha256"]:
            raise ValueError("admission input binding differs")
    matching = []
    for event in document.get("scheduler_batches", []):
        if not isinstance(event, dict) or event.get("phase") != "decode":
            continue
        request_rows = event.get("requests")
        padded = event.get("padded_requests")
        active = event.get("active_table_idx")
        if (not isinstance(request_rows, list) or not isinstance(padded, list) or event.get("physical_size") != slots
                or event.get("padded_size") != len(padded) or len(request_rows) != slots):
            continue
        if {item.get("uid") for item in request_rows if isinstance(item, dict)} != uids:
            continue
        if any(item.get("input_ids_sha256") != by_uid[item["uid"]]["input_ids_sha256"] or type(item.get("table_idx")) is not int
               or item.get("linear_slot_idx") is not None and type(item.get("linear_slot_idx")) is not int for item in request_rows):
            continue
        if not isinstance(active, list) or [item.get("table_idx") for item in padded] != active:
            continue
        matching.append(event)
    if not matching:
        raise ValueError("no actual decode scheduler batch simultaneously contains every workload UID")
    sampled, logits = _sampler_stream(sampler_root, identity, uids)
    delivered = {uid: [] for uid in uids}
    for item in document.get("deliveries", []):
        if not isinstance(item, dict) or item.get("uid") not in delivered:
            raise ValueError("service delivery contains an undeclared UID")
        uid = item["uid"]
        if item.get("generation_index") != len(delivered[uid]) or item.get("next_token") != sampled[uid][len(delivered[uid])]:
            raise ValueError("delivery does not match sampler token stream")
        delivered[uid].append(item["next_token"])
    if any(len(values) != 128 for values in delivered.values()):
        raise ValueError("service delivery does not contain complete 128-token UID streams")
    return delivered, logits


def _top2_difference(batch: object, alone: object) -> dict[str, object]:
    """Derive a fork metric from retained fp32 sampler snapshots only."""
    import torch
    difference = (batch - alone).abs()
    batch_top = torch.topk(batch, k=min(2, batch.numel()))
    alone_top = torch.topk(alone, k=min(2, alone.numel()))
    return {"batch_top2": {"indices": [int(x) for x in batch_top.indices.tolist()], "logits": [float(x) for x in batch_top.values.tolist()]},
            "alone_top2": {"indices": [int(x) for x in alone_top.indices.tolist()], "logits": [float(x) for x in alone_top.values.tolist()]},
            "max_abs_logit_difference": float(difference.max().item())}


def read_native_workloads(root: Path | str, *, evidence_map: str, evidence_map_sha256: str, slots: int) -> dict[str, Any]:
    """Read batch/repeat/single workload receipts and return diagnostic-only evidence."""
    try:
        if type(slots) is not int or slots not in (2, 4):
            raise ValueError("only two- and four-slot D16 workloads are supported")
        base = Path(root)
        if base.is_symlink() or not base.is_dir():
            raise ValueError("workload root is unavailable")
        mapping, paths = _pinned_map(base, evidence_map, evidence_map_sha256)
        collection_name = mapping.get("collection")
        collection_path = _relative(base, collection_name)
        if collection_path.relative_to(base).as_posix() not in paths:
            raise ValueError("collection is not covered by evidence map")
        collection = _load_json(collection_path)
        if collection.get("schema") != "ft_d16_exact_id_collection/v1" or collection.get("admitted") is not False:
            raise ValueError("collection contract is invalid")
        runs = mapping.get("runs")
        if not isinstance(runs, list):
            raise ValueError("run map is missing")
        output: dict[tuple[str, int, int | None], dict[int, dict[str, Any]]] = {}
        births: set[tuple[int, int, str]] = set()
        for run in runs:
            if not isinstance(run, dict) or run.get("kind") not in {"batch", "single"} or type(run.get("repeat")) is not int:
                raise ValueError("run descriptor is invalid")
            slot = run.get("slot")
            if run["kind"] == "single" and (type(slot) is not int or not 0 <= slot < slots):
                raise ValueError("single run slot is invalid")
            if run["kind"] == "batch" and slot is not None:
                raise ValueError("batch run must not declare one slot")
            key = (run["kind"], run["repeat"], slot)
            if key in output:
                raise ValueError("duplicate workload run descriptor")
            identity = _identity(run.get("process_identity")); birth = (identity["pid"], identity["start_ticks"], identity["execution_id"])
            if birth in births:
                raise ValueError("workload runs reuse a process birth identity")
            births.add(birth)
            labels = ([f"batch-{run['repeat']}-slot-{index}" for index in range(slots)] if run["kind"] == "batch"
                      else [f"alone-{run['repeat']}-slot-{slot}"])
            source_rows = collection.get("batch" if run["kind"] == "batch" else "alone")
            if not isinstance(source_rows, list) or run["repeat"] >= len(source_rows):
                raise ValueError("collection repeat is unavailable")
            selected = source_rows[run["repeat"]]
            if not isinstance(selected, list):
                raise ValueError("collection run rows are invalid")
            rows = [item for item in selected if isinstance(item, dict) and item.get("label") in labels]
            if {item.get("label") for item in rows} != set(labels):
                raise ValueError("collection labels do not bind run descriptor")
            for row in rows:
                for field in ("request", "response_path"):
                    rel = row.get(field)
                    if not isinstance(rel, str) or rel not in paths:
                        raise ValueError("collection raw request/response is not map-bound")
                request = _load_json(paths[row["request"]])
                ids = request.get("input_ids")
                if request.get("label") != row["label"] or row.get("input_ids_sha256") != _token_sha(ids):
                    raise ValueError("collection raw input IDs differ")
                _response(paths[row["response_path"]], row)
            service = _relative(base, run.get("service_capture")); sampler = _relative_dir(base, run.get("sampler_root"))
            if service.relative_to(base).as_posix() not in paths or not any(name.startswith(sampler.relative_to(base).as_posix() + "/") for name in paths):
                raise ValueError("service/sampler paths are not fully map-bound")
            rows_by_uid = {row["uid"]: row for row in rows}
            tokens_by_uid, logits_by_uid = _service(service, sampler, rows, identity, len(rows))
            output[key] = {uid: {"token_ids": tokens, "text": _response(paths[rows_by_uid[uid]["response_path"]], rows_by_uid[uid])["text"],
                                 "input_ids_sha256": rows_by_uid[uid]["input_ids_sha256"], "logits": logits_by_uid[uid]}
                           for uid, tokens in tokens_by_uid.items()}
        required_batches = [("batch", repeat, None) for repeat in (0, 1)]
        required_singles = [("single", repeat, slot) for repeat in (0, 1) for slot in range(slots)]
        if any(key not in output for key in required_batches + required_singles):
            raise ValueError("two independently restarted batches and two single repetitions are required")
        def by_input(rows: dict[int, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            normalized = {row["input_ids_sha256"]: row for row in rows.values()}
            if len(normalized) != len(rows):
                raise ValueError("workload slot inputs are not uniquely bound")
            return normalized
        def stable_equal(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> bool:
            return set(left) == set(right) and all(
                left[name]["token_ids"] == right[name]["token_ids"] and left[name]["text"] == right[name]["text"]
                for name in left)
        primary, repeat = by_input(output[required_batches[0]]), by_input(output[required_batches[1]])
        if not stable_equal(primary, repeat):
            return {"schema": SCHEMA, "admitted": False, "verdict": "unverified", "reason": "batch repetitions differ; retain for batch-envelope diagnostics"}
        forks: list[dict[str, object]] = []
        for slot in range(slots):
            singles = [by_input(output[("single", repeat_index, slot)]) for repeat_index in (0, 1)]
            if len(singles[0]) != 1 or not stable_equal(singles[0], singles[1]):
                return {"schema": SCHEMA, "admitted": False, "verdict": "unverified", "reason": "single repetitions differ; no batch-envelope comparison"}
            input_sha, single = next(iter(singles[0].items()))
            batch = primary.get(input_sha)
            if batch is None:
                return {"schema": SCHEMA, "admitted": False, "verdict": "unverified", "reason": "single input is absent from physical batch"}
            token_fork = next((index for index, pair in enumerate(zip(batch["token_ids"], single["token_ids"])) if pair[0] != pair[1]), None)
            if token_fork is None and len(batch["token_ids"]) != len(single["token_ids"]):
                token_fork = min(len(batch["token_ids"]), len(single["token_ids"]))
            if token_fork is not None or batch["text"] != single["text"]:
                diagnostic: dict[str, object] = {"input_ids_sha256": input_sha, "batch_uid_token_stream": batch["token_ids"],
                    "alone_uid_token_stream": single["token_ids"], "batch_text": batch["text"], "alone_text": single["text"],
                    "first_token_fork_generation_index": token_fork, "text_differs": batch["text"] != single["text"]}
                if token_fork is not None:
                    if token_fork >= len(batch["logits"]) or token_fork >= len(single["logits"]):
                        return {"schema": SCHEMA, "admitted": False, "verdict": "unverified", "reason": "fork has no retained fp32 logits"}
                    diagnostic["top2_logit_difference"] = _top2_difference(batch["logits"][token_fork], single["logits"][token_fork])
                forks.append(diagnostic)
        if forks:
            return {"schema": SCHEMA, "admitted": False, "verdict": "batch_envelope_diagnostic", "reason": "stable physical batch differs from stable alone runs",
                    "first_forks": forks, "limits": "diagnostic only; neither not_met nor accepted"}
        return {"schema": SCHEMA, "admitted": False, "verdict": "measurements_pass_pending_independent_review", "slots": primary,
                "limits": "raw UID/batch evidence only; never accepts a model or scheduler"}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, RuntimeError, StopIteration) as error:
        return {"schema": SCHEMA, "admitted": False, "verdict": "unverified", "reason": str(error)}
