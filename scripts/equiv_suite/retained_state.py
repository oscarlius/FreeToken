"""Read SHA-pinned retained donate snapshots as a non-admitting diagnostic."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import struct

import torch


SCHEMA = "ft_equiv_retained_state/v1"
SIDECAR_SCHEMA = "ft_equiv_retained_state_sidecar/v1"
ROLE_ORDER = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
ROLE_SET = set(ROLE_ORDER)


class RetainedStateError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _token_sha(ids: object) -> str:
    if (not isinstance(ids, list) or not ids or any(type(item) is not int or not 0 <= item < 2**31 for item in ids)):
        raise RetainedStateError("sidecar input IDs must be a nonempty int32 list")
    return _sha(struct.pack(f"<{len(ids)}i", *ids))


def _identity(value: object) -> bool:
    return (isinstance(value, dict) and type(value.get("pid")) is int and value["pid"] > 0
            and type(value.get("start_ticks")) is int and value["start_ticks"] > 0
            and isinstance(value.get("execution_id"), str) and bool(value["execution_id"]))


def _file(root: Path, relative: object) -> Path:
    """Return a regular in-arm file, rejecting all symlink traversal."""
    if root.is_symlink() or not root.is_dir() or not isinstance(relative, str):
        raise RetainedStateError("retained artifact path is missing")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise RetainedStateError("retained artifact path escapes its arm")
    raw = root / part
    current = raw
    while current != root:
        if current.is_symlink():
            raise RetainedStateError("retained artifact path has a symlink ancestor")
        current = current.parent
    try:
        resolved = raw.resolve(strict=True)
    except OSError as error:
        raise RetainedStateError("retained artifact file is missing") from error
    if raw.is_symlink() or not resolved.is_file() or root.resolve() not in resolved.parents:
        raise RetainedStateError("retained artifact path is not a regular arm file")
    return resolved


def _selection(value: object) -> tuple[str, int, object]:
    if (not isinstance(value, dict) or set(value) != {"kind", "seq", "uid"}
            or value.get("kind") != "donate" or type(value.get("seq")) is not int or value["seq"] <= 0):
        raise RetainedStateError("retained selection requires exact donate kind, seq, and uid")
    return value["kind"], value["seq"], value["uid"]


def _same(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _selected(root: Path, selection: dict) -> tuple[dict, bytes, bytes]:
    _kind, seq, uid = _selection(selection)
    index = _file(root, "index.jsonl")
    raw_index = index.read_bytes()
    matches = []
    for line in raw_index.splitlines(keepends=True):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RetainedStateError("retained state index has invalid JSON") from error
        if (isinstance(row, dict) and row.get("kind") == "donate"
                and _same(row.get("seq"), seq) and _same(row.get("uid"), uid)):
            matches.append((row, line))
    if len(matches) != 1:
        raise RetainedStateError("retained state kind/UID/seq selection is not unique")
    return matches[0][0], raw_index, matches[0][1]


def _sidecar(path: Path, expected_sha256: str, *, root: Path, index_sha256: str,
             line_sha256: str, selection: dict) -> tuple[dict, dict]:
    if path.is_symlink() or not path.is_file() or not _digest(expected_sha256):
        raise RetainedStateError("retained state sidecar is unavailable")
    raw = path.read_bytes()
    if _sha(raw) != expected_sha256:
        raise RetainedStateError("retained state sidecar SHA differs")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RetainedStateError("retained state sidecar is not JSON") from error
    kind, seq, uid = _selection(selection)
    if (not isinstance(document, dict) or document.get("schema") != SIDECAR_SCHEMA
            or document.get("index_sha256") != index_sha256
            or document.get("capture_receipt_sha256") != line_sha256
            or document.get("kind") != kind or not _same(document.get("seq"), seq) or not _same(document.get("uid"), uid)
            or not _identity(document.get("process_identity"))
            or not isinstance(document.get("event_identity"), str) or not document["event_identity"]):
        raise RetainedStateError("retained state sidecar does not bind original index bytes")
    input_ids = document.get("input_ids")
    if document.get("input_ids_sha256") != _token_sha(input_ids):
        raise RetainedStateError("retained state sidecar input IDs SHA differs")
    snapshot_ids = document.get("snapshot_prefix_ids")
    if (type(document.get("snapshot_length")) is not int or document["snapshot_length"] <= 0
            or not isinstance(snapshot_ids, list) or len(snapshot_ids) != document["snapshot_length"]
            or document.get("snapshot_prefix_ids_sha256") != _token_sha(snapshot_ids)
            or len(snapshot_ids) > len(input_ids) or snapshot_ids != input_ids[:len(snapshot_ids)]):
        raise RetainedStateError("retained state sidecar snapshot prefix does not bind input IDs")
    files = document.get("role_files")
    if not isinstance(files, dict) or set(files) != ROLE_SET:
        raise RetainedStateError("retained state sidecar lacks the four role files")
    tensors, receipts = {}, {}
    for role in ROLE_ORDER:
        entry = files[role]
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"} or not _digest(entry["sha256"]):
            raise RetainedStateError("retained state sidecar role binding is invalid: " + role)
        file_path = _file(root, entry["path"])
        raw_file = file_path.read_bytes()
        if _sha(raw_file) != entry["sha256"]:
            raise RetainedStateError("retained state role file SHA differs: " + role)
        try:
            tensor = torch.load(file_path, map_location="cpu", weights_only=True)
        except (OSError, RuntimeError, ValueError) as error:
            raise RetainedStateError("retained state tensor is unreadable: " + role) from error
        if not isinstance(tensor, torch.Tensor) or tensor.device.type != "cpu" or not torch.isfinite(tensor).all().item():
            raise RetainedStateError("retained state tensor is invalid or non-finite: " + role)
        tensors[role] = tensor
        receipts[role] = {"path": entry["path"], "sha256": entry["sha256"]}
    receipt = {"path": str(path.resolve()), "sha256": expected_sha256,
               "bytes_base64": base64.b64encode(raw).decode(),
               "process_identity": document["process_identity"], "event_identity": document["event_identity"],
               "input_ids_sha256": document["input_ids_sha256"], "snapshot_length": document["snapshot_length"],
               "snapshot_prefix_ids_sha256": document["snapshot_prefix_ids_sha256"], "role_files": receipts}
    return receipt, tensors


def _bitwise(left: torch.Tensor, right: torch.Tensor) -> bool:
    return torch.equal(left.contiguous().view(torch.uint8), right.contiguous().view(torch.uint8))


def _metrics(left: torch.Tensor, right: torch.Tensor, role: str) -> dict:
    if left.dtype != right.dtype or left.shape != right.shape:
        raise RetainedStateError("retained state dtype/shape differs: " + role)
    equal = _bitwise(left, right)
    if not (left.is_floating_point() or left.is_complex()):
        return {"dtype": str(left.dtype), "shape": list(left.shape), "exact_equal": equal, "bitwise_equal": equal}
    metric_dtype = torch.complex128 if left.is_complex() else torch.float64
    delta = (left.to(metric_dtype) - right.to(metric_dtype)).abs()
    return {"dtype": str(left.dtype), "shape": list(left.shape), "bitwise_equal": equal,
            "max_abs": float(delta.max().item()), "rms": float(delta.square().mean().sqrt().item())}


def compare_retained_state(left: Path, right: Path, *, left_selection: dict, right_selection: dict,
                           left_sidecar: Path, left_sidecar_sha256: str,
                           right_sidecar: Path, right_sidecar_sha256: str) -> dict:
    """Recompute an offline four-role snapshot envelope from pinned bytes only."""
    left_root, right_root = Path(left), Path(right)
    _left_row, left_index, left_line = _selected(left_root, left_selection)
    _right_row, right_index, right_line = _selected(right_root, right_selection)
    left_receipt, left_tensors = _sidecar(left_sidecar, left_sidecar_sha256, root=left_root,
        index_sha256=_sha(left_index), line_sha256=_sha(left_line), selection=left_selection)
    right_receipt, right_tensors = _sidecar(right_sidecar, right_sidecar_sha256, root=right_root,
        index_sha256=_sha(right_index), line_sha256=_sha(right_line), selection=right_selection)
    if Path(left_sidecar).resolve() == Path(right_sidecar).resolve():
        raise RetainedStateError("retained state arms cannot share a sidecar")
    left_id, right_id = left_receipt["process_identity"], right_receipt["process_identity"]
    if left_receipt["event_identity"] == right_receipt["event_identity"]:
        raise RetainedStateError("retained state sidecars do not prove independent events")
    if ((left_id["pid"], left_id["start_ticks"]) == (right_id["pid"], right_id["start_ticks"])
            or left_id["execution_id"] == right_id["execution_id"]):
        raise RetainedStateError("retained state sidecars do not prove independent processes")
    for key in ("input_ids_sha256", "snapshot_length", "snapshot_prefix_ids_sha256"):
        if left_receipt[key] != right_receipt[key]:
            raise RetainedStateError("retained state arms do not share original input and snapshot prefix")
    role_metrics = {role: _metrics(left_tensors[role], right_tensors[role], role) for role in ROLE_ORDER}
    first = next((role for role in ROLE_ORDER if not role_metrics[role]["bitwise_equal"]), None)
    return {"schema": SCHEMA, "admitted": False, "verdict": "recorded",
            "diagnostic_only": "snapshot envelope is never restore equivalence or a T17 gate",
            "input_ids_sha256": left_receipt["input_ids_sha256"], "snapshot_length": left_receipt["snapshot_length"],
            "snapshot_prefix_ids_sha256": left_receipt["snapshot_prefix_ids_sha256"],
            "roles": role_metrics, "first_role_difference": first,
            "sources": {"left": {"arm": str(left_root.resolve()),
                         "index": {"path": "index.jsonl", "sha256": _sha(left_index), "bytes_base64": base64.b64encode(left_index).decode()},
                         "capture_receipt": {"path": "index.jsonl", "sha256": _sha(left_line), "bytes_base64": base64.b64encode(left_line).decode(), **left_selection},
                         "sidecar": left_receipt},
                        "right": {"arm": str(right_root.resolve()),
                         "index": {"path": "index.jsonl", "sha256": _sha(right_index), "bytes_base64": base64.b64encode(right_index).decode()},
                         "capture_receipt": {"path": "index.jsonl", "sha256": _sha(right_line), "bytes_base64": base64.b64encode(right_line).decode(), **right_selection},
                         "sidecar": right_receipt}}}


def read_retained_state(left: Path, right: Path, **kwargs) -> dict:
    """Fail closed as an indeterminate, non-admitting offline diagnostic."""
    try:
        return compare_retained_state(left, right, **kwargs)
    except (RetainedStateError, OSError, RuntimeError, ValueError, struct.error) as error:
        return {"schema": SCHEMA, "admitted": False, "verdict": "indeterminate", "reason": str(error)}


compare_retained = compare_retained_state
read_retained = read_retained_state
