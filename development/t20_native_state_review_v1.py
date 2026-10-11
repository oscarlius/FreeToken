"""Offline reviewer for frozen T20 native parking/cache captures.

This module is deliberately inert: callers must supply an externally pinned map and
explicitly invoke ``review_native_state``.  It never starts a service or writes round
artifacts.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from pathlib import Path
from typing import Any, Callable

SCHEMA = "ft_t20_native_state_review/v1"
MAP_SCHEMA = "ft_t20_native_state_map/v1"
ROLES = ("conv", "recurrent", "ple_conv", "ple_ngram_ctx")
LABELS = ("before_decode", "after_decode127")


class NativeStateReviewError(RuntimeError):
    """The immutable capture cannot prove the required native-state claim."""


class NativeStateRawProofMissing(NativeStateReviewError):
    """The producer did not retain the physical raw state required for review."""


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_symlink(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise NativeStateReviewError(f"symlink is forbidden: {current}")


def _regular(path: Path, *, root: Path | None = None) -> Path:
    _no_symlink(path)
    resolved = path.resolve(strict=True)
    if root is not None:
        _no_symlink(root)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise NativeStateReviewError(f"path escapes capture root: {path}") from exc
    if not resolved.is_file():
        raise NativeStateReviewError(f"missing regular file: {path}")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeStateReviewError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise NativeStateReviewError(f"JSON object required: {path}")
    return value


def _identity(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("pid"), int) or not isinstance(value.get("start_ticks"), int):
        raise NativeStateReviewError(f"invalid process identity for {name}")
    if not isinstance(value.get("execution_id"), str) or not value["execution_id"]:
        raise NativeStateReviewError(f"missing execution identity for {name}")
    return value


def _input_sha(ids: Any) -> str:
    if not isinstance(ids, list) or not ids or any(type(item) is not int or not -(2 ** 31) <= item < 2 ** 31 for item in ids):
        raise NativeStateReviewError("input_ids must be nonempty signed int32")
    return hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()


def _path(root: Path, rel: Any, files: dict[str, str]) -> Path:
    if not isinstance(rel, str) or rel not in files or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise NativeStateReviewError(f"unpinned capture path: {rel!r}")
    target = _regular(root / rel, root=root)
    if _sha_file(target) != files[rel]:
        raise NativeStateReviewError(f"pinned SHA differs: {rel}")
    return target


def _pinned_map(root: Path, map_path: Path, expected_sha256: str) -> tuple[dict[str, Any], dict[str, str]]:
    _no_symlink(root)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NativeStateReviewError("capture root is not a directory")
    _regular(map_path)
    if _sha_file(map_path) != expected_sha256:
        raise NativeStateReviewError("state map SHA differs from registered pin")
    document = _read_json(map_path)
    if document.get("schema") != MAP_SCHEMA:
        raise NativeStateReviewError("unexpected state map schema")
    files = document.get("files")
    if not isinstance(files, dict) or not files or any(not isinstance(key, str) or not isinstance(value, str) or len(value) != 64 for key, value in files.items()):
        raise NativeStateReviewError("invalid pinned file map")
    actual = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
    if actual != set(files):
        raise NativeStateReviewError("pinned map does not cover exactly the capture tree")
    for rel in sorted(files):
        _path(root, rel, files)
    return document, files


def _response(root: Path, rel: Any, files: dict[str, str], expected_input: str) -> tuple[str, list[Any]]:
    document = _read_json(_path(root, rel, files))
    response = document.get("response", document)
    status = document.get("status", 200)
    if not isinstance(response, dict) or status != 200 or response.get("uid") != 0 or response.get("finished") is not True:
        raise NativeStateReviewError("terminal response identity differs")
    if response.get("input_ids_sha256") != expected_input or response.get("usage", {}).get("completion_tokens") != 128:
        raise NativeStateReviewError("terminal response input or length differs")
    text = response.get("text")
    if not isinstance(text, str):
        raise NativeStateReviewError("terminal response text is missing")
    return text, [response]


def _delivery(root: Path, rel: Any, files: dict[str, str], worker: dict[str, Any]) -> list[int]:
    document = _read_json(_path(root, rel, files))
    rows = document.get("deliveries")
    if document.get("terminal") != "complete" or document.get("process_identity") != worker or not isinstance(rows, list) or len(rows) != 128:
        raise NativeStateReviewError("terminal native delivery differs")
    tokens: list[int] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("uid") != 0 or row.get("generation_index") != index or row.get("delivered") is not True or type(row.get("sampled_token_id")) is not int:
            raise NativeStateReviewError("terminal native delivery is incomplete")
        tokens.append(row["sampled_token_id"])
    return tokens


def _tensor_bytes(value: Any) -> tuple[bytes, list[int] | None, str | None]:
    if isinstance(value, bytes):
        return value, None, None
    try:
        tensor = value.detach().cpu().contiguous()
        return tensor.view(__import__("torch").uint8).numpy().tobytes(), list(tensor.shape), str(tensor.dtype)
    except Exception as exc:  # noqa: BLE001 - report malformed raw codec consistently
        raise NativeStateReviewError("raw state codec did not return CPU tensors") from exc


def _torch_loader(path: Path) -> Any:
    try:
        import torch
    except ImportError as exc:
        raise NativeStateReviewError("CPU torch is required to inspect raw native state") from exc
    return torch.load(path, map_location="cpu", weights_only=True)


def _resident_slots(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and all(type(item) is int for item in value):
        return list(value)
    try:
        flattened = value.detach().cpu().reshape(-1).tolist()
    except Exception as exc:  # noqa: BLE001
        raise NativeStateReviewError("initial cache residency codec is not CPU integer slots") from exc
    if not all(type(item) is int for item in flattened):
        raise NativeStateReviewError("initial cache residency contains non-integer slots")
    return flattened


def _initial_residency(root: Path, arm: dict[str, Any], files: dict[str, str], loader: Callable[[Path], Any], init: dict[str, Any]) -> None:
    path = arm.get("initial_residency")
    if path is None:
        raise NativeStateRawProofMissing("physical initial cache residency is absent")
    slots = _resident_slots(loader(_path(root, path, files)))
    if sum(slot >= 0 for slot in slots) != init.get("resident_count"):
        raise NativeStateReviewError("physical initial cache residency differs")


def _states(root: Path, arm: dict[str, Any], files: dict[str, str], loader: Callable[[Path], Any]) -> dict[str, dict[str, bytes]]:
    raw = arm.get("state_files")
    if not isinstance(raw, dict) or set(raw) != set(LABELS):
        raise NativeStateRawProofMissing("four-role raw parking/cache state files are absent")
    result: dict[str, dict[str, bytes]] = {}
    for label in LABELS:
        record = raw[label]
        if not isinstance(record, dict):
            raise NativeStateReviewError("invalid state file binding")
        metadata = _read_json(_path(root, record.get("json"), files))
        raw_path = _path(root, record.get("pt"), files)
        if metadata.get("uid") != 0 or metadata.get("label") != label or set(metadata.get("states", {})) != set(ROLES):
            raise NativeStateReviewError("four-role state metadata differs")
        loaded = loader(raw_path)
        if not isinstance(loaded, dict) or set(loaded) != set(ROLES):
            raise NativeStateReviewError("raw state codec lacks a four-role state")
        roles: dict[str, bytes] = {}
        for role in ROLES:
            encoded, shape, dtype = _tensor_bytes(loaded[role])
            expected = metadata["states"][role]
            if not isinstance(expected, dict) or expected.get("sha256") != hashlib.sha256(encoded).hexdigest():
                raise NativeStateReviewError(f"raw state hash differs for {label}/{role}")
            if shape is not None and (expected.get("shape") != shape or expected.get("dtype") != dtype):
                raise NativeStateReviewError(f"raw state codec metadata differs for {label}/{role}")
            roles[role] = encoded
        result[label] = roles
    return result


def _arm(root: Path, arm: Any, files: dict[str, str]) -> tuple[dict[str, Any], str, list[int], str]:
    if not isinstance(arm, dict) or not isinstance(arm.get("name"), str):
        raise NativeStateReviewError("invalid state arm")
    input_document = _read_json(_path(root, arm.get("input"), files))
    expected_input = _input_sha(input_document.get("input_ids"))
    if input_document.get("max_tokens") != 128:
        raise NativeStateReviewError("native state arm does not request 128 tokens")
    admission = _read_json(_path(root, arm.get("admission"), files))
    worker = _identity(admission.get("process_identity"), name=arm["name"])
    if admission.get("uid") != 0:
        raise NativeStateReviewError("native state admission UID differs")
    owned = _read_json(_path(root, arm.get("worker"), files))
    birth = owned.get('live_birth', {})
    if (owned.get("identity") != worker or not isinstance(birth, dict)
            or birth.get('pid') != worker['pid'] or birth.get('start_ticks') != worker['start_ticks']
            or not isinstance(owned.get("frontend"), dict)):
        raise NativeStateReviewError("native worker provenance differs")
    text, _ = _response(root, arm.get("response"), files, expected_input)
    tokens = _delivery(root, arm.get("delivery"), files, worker)
    return worker, text, tokens, expected_input


def review_native_state(root: str | Path, *, map_path: str | Path, map_sha256: str, kind: str,
                        state_loader: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Independently inspect a frozen four-arm parking or cache capture.

    `map_path` is an external, SHA-pinned inventory.  This function has no
    network, GPU, process, or round-writing side effects.
    """
    if kind not in ("parking", "cache"):
        raise ValueError("kind must be parking or cache")
    root_path = Path(root)
    document, files = _pinned_map(root_path, Path(map_path), map_sha256)
    if document.get("kind") != kind:
        raise NativeStateReviewError("pinned map kind differs")
    arms = document.get("arms")
    names = ("control_0", "control_1", "restore_0", "restore_1") if kind == "parking" else ("cold_0", "cold_1", "warm_0", "warm_1")
    if not isinstance(arms, list) or [item.get("name") if isinstance(item, dict) else None for item in arms] != list(names):
        raise NativeStateReviewError("four independent state arms differ")
    records = [_arm(root_path, arm, files) for arm in arms]
    if len({(item[0]["pid"], item[0]["start_ticks"]) for item in records}) != 4:
        raise NativeStateReviewError("state arms do not have four independent process births")
    baseline = records[0][1:]
    if any(item[1:] != baseline for item in records[1:]):
        raise NativeStateReviewError("two references or restored native continuation differs")
    if kind == "parking":
        transport_proofs = {}
        for arm, (worker, _, _, expected_input) in zip(arms, records):
            trigger = _read_json(_path(root_path, arm.get("trigger"), files))
            receipt = trigger.get("receipt", trigger)
            rows = receipt.get("rows") if isinstance(receipt, dict) else None
            if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("uid") != 0 or not 7 <= rows[0].get("generation_index", -1) <= 125:
                raise NativeStateReviewError("physical parking decode trigger differs")
            pause = _read_json(_path(root_path, arm.get("pause"), files))
            if pause.get("response", {}).get("status") != "accepted":
                raise NativeStateReviewError("parking pause was not physically accepted")
            roundtrip = arm.get("roundtrip")
            restored = arm["name"].startswith("restore_")
            if restored != isinstance(roundtrip, str):
                raise NativeStateReviewError("parking restore proof presence differs")
            if restored:
                proof = _read_json(_path(root_path, roundtrip, files))
                requests = proof.get('requests')
                if (proof.get("request_id") != pause["response"].get("request_id")
                        or proof.get("state_transport_bitwise") is not True
                        or proof.get('pid') != worker['pid'] or proof.get('execution_id') != worker['execution_id']
                        or not isinstance(requests, list) or len(requests) != 1
                        or requests[0].get('uid') != 0
                        or any(type(requests[0].get(k)) is not int for k in ('table_idx','linear_slot_idx','host_slot'))
                        or requests[0]['table_idx'] < 0 or requests[0]['linear_slot_idx'] <= 0 or requests[0]['host_slot'] < 0):
                    raise NativeStateReviewError("parking raw transport proof differs")
                transport_proofs[arm['name']] = proof
        # R040a v3 retains physical before/host/cleared/restored dictionaries.
        loader = state_loader or _torch_loader
        parking_states=[]
        for arm in arms:
            restored = arm["name"].startswith("restore_")
            raw_index = arm.get("raw_capture_index")
            if restored != isinstance(raw_index, str):
                raise NativeStateRawProofMissing("parking four-role raw capture presence differs")
            if not restored:
                continue
            index = _read_json(_path(root_path, raw_index, files))
            proof = transport_proofs[arm['name']]
            if (index.get("schema") != "ft_r040a_native_parking_raw_capture/v2"
                    or index.get("state_transport_bitwise") is not True
                    or any(index.get(k) != proof.get(k) for k in ('request_id','pid','execution_id','requests'))):
                raise NativeStateReviewError("parking raw capture identity differs")
            fills = index.get('clear_fill_values')
            if (not isinstance(fills,dict) or set(fills)!=set(ROLES)
                    or any(type(x) not in (int,float) or not math.isfinite(x) for x in fills.values())
                    or fills['conv'] != 0 or fills['recurrent'] != 0):
                raise NativeStateRawProofMissing('parking actual clear fill values are absent')
            stages=index.get("stages")
            if not isinstance(stages,dict) or set(stages)!={"before","host","cleared","restored"}:
                raise NativeStateRawProofMissing("parking physical four-stage raw capture is absent")
            values={}
            for stage,item in stages.items():
                path=_path(root_path, (Path(raw_index).parent / item.get("path", "")).as_posix(), files)
                if item.get("sha256") != _sha_file(path): raise NativeStateReviewError("parking raw capture SHA differs")
                loaded=loader(path)
                if not isinstance(loaded,dict) or set(loaded)!=set(ROLES): raise NativeStateReviewError("parking raw capture lacks four roles")
                metadata = item.get('states')
                if not isinstance(metadata,dict) or set(metadata)!=set(ROLES):
                    raise NativeStateReviewError('parking raw tensor metadata differs')
                values[stage]={}
                for role in ROLES:
                    encoded, shape, dtype = _tensor_bytes(loaded[role])
                    if shape is None or dtype is None:
                        raise NativeStateRawProofMissing('parking requires physical CPU tensors')
                    expected = metadata[role]
                    if (expected.get('sha256')!=hashlib.sha256(encoded).hexdigest()
                            or expected.get('shape')!=shape or expected.get('dtype')!=dtype):
                        raise NativeStateReviewError('parking raw tensor metadata differs')
                    if stage == 'cleared':
                        cleared = loaded[role].new_full(shape, fills[role])
                        if _tensor_bytes(cleared)[0] != encoded:
                            raise NativeStateReviewError('parking clear fill raw state differs')
                    values[stage][role]=encoded
            if values["before"] != values["host"] or values["before"] != values["restored"]:
                raise NativeStateReviewError("parking D2H/H2D raw state differs")
            parking_states.append(values)
        if len(parking_states)!=2 or parking_states[0]["before"] != parking_states[1]["before"] or parking_states[0]["restored"] != parking_states[1]["restored"]:
            raise NativeStateReviewError("parking restore physical states differ")
        return {"schema": SCHEMA, "kind": kind, "verdict": "bitwise_pending_independent_review", "arms": list(names), "input_ids_sha256": records[0][3], "token_count": 128}
    loader = state_loader or _torch_loader
    baseline_states = _states(root_path, arms[0], files, loader)
    for index, arm in enumerate(arms):
        if _states(root_path, arm, files, loader) != baseline_states:
            raise NativeStateReviewError("raw cache four-role states differ")
        init = _read_json(_path(root_path, arm.get("initialization"), files))
        stats = _read_json(_path(root_path, arm.get("terminal_stats"), files))
        warm = arm["name"].startswith("warm_")
        if (init.get("mode") != ("warm" if warm else "cold") or init.get("execution_id") != records[index][0]["execution_id"]
                or init.get("priming_requests") != 0 or init.get("resident_count") != (len(init.get("eligible_layers", [])) if warm else 0)):
            raise NativeStateReviewError("cache initial residency differs")
        _initial_residency(root_path, arm, files, loader, init)
        if (warm and stats.get("prefill_hit_rows", 0) <= 0) or (not warm and stats.get("prefill_hit_rows") != 0):
            raise NativeStateReviewError("cache terminal stats differ")
    return {"schema": SCHEMA, "kind": kind, "verdict": "bitwise_pending_independent_review", "arms": list(names), "input_ids_sha256": records[0][3], "token_count": 128}


