"""Read fixed retained D03 rows without polling, serving, or rewriting D03 indexes."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

SCHEMA = "ft_equiv_retained_d03/v1"
SERVICE_SCHEMA = "ft_equiv_retained_service/v1"
STATE_ROLES = {"conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx"}


class RetainedD03Error(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> bool:
    return (isinstance(value, dict) and type(value.get("pid")) is int and value["pid"] > 0
            and type(value.get("start_ticks")) is int and value["start_ticks"] > 0
            and isinstance(value.get("execution_id"), str) and bool(value["execution_id"]))


def _file(root: Path, relative: object) -> Path:
    if root.is_symlink() or not root.is_dir() or not isinstance(relative, str):
        raise RetainedD03Error("retained artifact path is missing")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise RetainedD03Error("retained artifact path escapes its arm")
    raw = root / part
    current = raw
    while current != root:
        if current.is_symlink():
            raise RetainedD03Error("retained artifact path has a symlink ancestor")
        current = current.parent
    try:
        resolved = raw.resolve(strict=True)
    except OSError as error:
        raise RetainedD03Error("retained artifact file is missing") from error
    if raw.is_symlink() or not resolved.is_file() or root.resolve() not in resolved.parents:
        raise RetainedD03Error("retained artifact path is not a regular arm file")
    return resolved


def _selection(value: object) -> tuple[int, object]:
    if not isinstance(value, dict) or set(value) != {"seq", "uid"} or type(value.get("seq")) is not int or value["seq"] <= 0:
        raise RetainedD03Error("retained selection requires exact seq and uid")
    return value["seq"], value["uid"]


def _tool(path: Path, expected_sha256: str):
    if path.is_symlink() or not path.is_file() or not _digest(expected_sha256):
        raise RetainedD03Error("pinned D03 logits_probe.py is unavailable")
    raw = path.read_bytes()
    if _sha(raw) != expected_sha256:
        raise RetainedD03Error("pinned D03 logits_probe.py SHA differs")
    spec = importlib.util.spec_from_file_location("retained_d03_logits_probe_" + expected_sha256[:12], path)
    if spec is None or spec.loader is None:
        raise RetainedD03Error("pinned D03 logits_probe.py is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sidecar(path: Path, expected_sha256: str, *, index_sha256: str, line_sha256: str, seq: int, uid: object) -> dict:
    if path.is_symlink() or not path.is_file() or not _digest(expected_sha256):
        raise RetainedD03Error("retained service sidecar is unavailable")
    raw = path.read_bytes()
    if _sha(raw) != expected_sha256:
        raise RetainedD03Error("retained service sidecar SHA differs")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RetainedD03Error("retained service sidecar is not JSON") from error
    if (not isinstance(document, dict) or document.get("schema") != SERVICE_SCHEMA
            or document.get("index_sha256") != index_sha256 or document.get("capture_receipt_sha256") != line_sha256
            or document.get("seq") != seq or document.get("uid") != uid
            or not _identity(document.get("process_identity"))
            or not isinstance(document.get("event_identity"), str) or not document["event_identity"]):
        raise RetainedD03Error("retained service sidecar does not bind original D03 bytes")
    return {"path": str(path.resolve()), "sha256": expected_sha256, "bytes_base64": base64.b64encode(raw).decode(),
            "process_identity": document["process_identity"], "event_identity": document["event_identity"]}


def _selected(root: Path, selection: dict, probe) -> tuple[dict, object, dict]:
    seq, uid = _selection(selection)
    index = _file(root, "index.jsonl")
    raw_index = index.read_bytes()
    matches = []
    for line in raw_index.splitlines(keepends=True):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise RetainedD03Error("retained logits index has invalid JSON") from error
            if isinstance(row, dict) and row.get("kind") == "logits" and row.get("seq") == seq and row.get("uid") == uid:
                matches.append((row, line))
    if len(matches) != 1:
        raise RetainedD03Error("retained logits UID/seq selection is not unique")
    row, line = matches[0]
    files, hashes = row.get("files"), row.get("sha256")
    if not isinstance(files, dict) or set(files) != STATE_ROLES | {"logits"} or not isinstance(hashes, dict) or set(hashes) != set(files):
        raise RetainedD03Error("retained logits row has incomplete role files or SHA map")
    for role, relative in files.items():
        path = _file(root, relative)
        if not _digest(hashes.get(role)) or _sha(path.read_bytes()) != hashes[role]:
            raise RetainedD03Error("retained role file SHA differs: " + role)
    row = dict(row, _dir=str(root))
    logits = probe.read_tensor(root, row, "logits")
    bound = probe.binding(row, logits)
    for role in STATE_ROLES:
        probe.read_tensor(root, row, role)
    source = {"arm": str(root.resolve()), "index": {"path": "index.jsonl", "sha256": _sha(raw_index), "bytes_base64": base64.b64encode(raw_index).decode()},
              "capture_receipt": {"path": "index.jsonl", "sha256": _sha(line), "bytes_base64": base64.b64encode(line).decode(), "seq": seq, "uid": uid},
              "role_files": {role: {"path": files[role], "sha256": hashes[role]} for role in sorted(files)}}
    return row, logits, {"bound": bound, "source": source}


def compare_retained(left: Path, right: Path, *, left_selection: dict, right_selection: dict,
                     logits_probe: Path, logits_probe_sha256: str, left_sidecar: Path,
                     left_sidecar_sha256: str, right_sidecar: Path, right_sidecar_sha256: str) -> dict:
    """Recompute D03 compare on exact retained rows with independently bound services."""
    probe = _tool(logits_probe, logits_probe_sha256)
    reference, reference_logits, reference_data = _selected(left, left_selection, probe)
    peer, peer_logits, peer_data = _selected(right, right_selection, probe)
    if reference_data["bound"] != peer_data["bound"]:
        raise RetainedD03Error("retained D03 input binding differs between arms")
    left_seq, left_uid = _selection(left_selection)
    right_seq, right_uid = _selection(right_selection)
    left_service = _sidecar(left_sidecar, left_sidecar_sha256, index_sha256=reference_data["source"]["index"]["sha256"], line_sha256=reference_data["source"]["capture_receipt"]["sha256"], seq=left_seq, uid=left_uid)
    right_service = _sidecar(right_sidecar, right_sidecar_sha256, index_sha256=peer_data["source"]["index"]["sha256"], line_sha256=peer_data["source"]["capture_receipt"]["sha256"], seq=right_seq, uid=right_uid)
    left_id, right_id = left_service["process_identity"], right_service["process_identity"]
    if ((left_id["pid"], left_id["start_ticks"]) == (right_id["pid"], right_id["start_ticks"])
            or left_id["execution_id"] == right_id["execution_id"]):
        raise RetainedD03Error("retained service sidecars do not prove independent processes")
    values = probe.metrics(peer_logits, reference_logits)
    first = values["first_bitwise_mismatch"]
    values["first_bitwise_input_position"] = reference_data["bound"][3][first] if first is not None else None
    values["first_state_difference"] = probe.state_difference(peer, reference)
    digest, k, length, positions = reference_data["bound"]
    reference_data["source"]["service_binding"] = left_service
    peer_data["source"]["service_binding"] = right_service
    return {"schema": SCHEMA, "admitted": False, "verdict": "recorded", "input_prefix_sha256": digest,
            "k": k, "input_length": length, "positions": positions, "peer_vs_recompute": values,
            "sources": {"recompute": reference_data["source"], "peer": peer_data["source"]}}


def read_retained(left: Path, right: Path, *, left_selection: dict, right_selection: dict,
                  logits_probe: Path, logits_probe_sha256: str, left_sidecar: Path,
                  left_sidecar_sha256: str, right_sidecar: Path, right_sidecar_sha256: str) -> dict:
    """Return an indeterminate non-admitting receipt when retained proof is incomplete."""
    try:
        return compare_retained(left, right, left_selection=left_selection, right_selection=right_selection,
                                logits_probe=logits_probe, logits_probe_sha256=logits_probe_sha256,
                                left_sidecar=left_sidecar, left_sidecar_sha256=left_sidecar_sha256,
                                right_sidecar=right_sidecar, right_sidecar_sha256=right_sidecar_sha256)
    except (RetainedD03Error, OSError, RuntimeError, ValueError) as error:
        return {"schema": SCHEMA, "admitted": False, "verdict": "indeterminate", "reason": str(error)}
