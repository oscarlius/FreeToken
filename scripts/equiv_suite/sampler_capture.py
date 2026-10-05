"""Explicit, instance-scoped sampler capture for D16 retained evidence.

This observer deliberately observes the sampler input already produced by an
Engine.  It never projects logits, changes sampler arguments, or installs a
global hook.  Captures are diagnostic evidence only and are never admitting.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import struct
import types
import uuid

SCHEMA = "ft_equiv_sampler_capture/v1"


class CaptureError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _token_bytes(ids: list[int]) -> bytes:
    if not all(type(value) is int and -(2**31) <= value < 2**31 for value in ids):
        raise CaptureError("token IDs must fit the suite int32-le contract")
    return struct.pack("<%di" % len(ids), *ids)


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> dict:
    if (not isinstance(value, dict) or type(value.get("pid")) is not int or value["pid"] <= 0
            or type(value.get("start_ticks")) is not int or value["start_ticks"] <= 0
            or not isinstance(value.get("execution_id"), str) or not value["execution_id"]):
        raise CaptureError("process identity requires pid, start_ticks and execution_id")
    return {"pid": value["pid"], "start_ticks": value["start_ticks"], "execution_id": value["execution_id"]}


def _self_identity() -> dict:
    """Production default: derive the worker identity from the running process."""
    execution_id = os.environ.get("FT_D16_EXECUTION_ID")
    stat = Path("/proc/self/stat")
    if not execution_id or not stat.is_file():
        raise CaptureError("live process identity requires /proc/self/stat and FT_D16_EXECUTION_ID")
    fields = stat.read_text().split()
    if len(fields) <= 21 or not fields[21].isdigit():
        raise CaptureError("cannot read process start ticks")
    return _identity({"pid": os.getpid(), "start_ticks": int(fields[21]), "execution_id": execution_id})


class QueryRegistry:
    """Query identity is bound before the engine is attached."""

    def __init__(self) -> None:
        self._queries: dict[object, dict] = {}

    def bind_query(self, uid: object, prompt_ids: list[int], event_identity: str) -> None:
        if uid in self._queries or not isinstance(prompt_ids, list) or not prompt_ids or not all(type(x) is int for x in prompt_ids):
            raise CaptureError("query binding requires a unique UID and nonempty integer prompt IDs")
        if not isinstance(event_identity, str) or not event_identity:
            raise CaptureError("query binding requires an event identity")
        self._queries[uid] = {"prompt_ids": list(prompt_ids), "prompt_sha256": _sha(_token_bytes(prompt_ids)), "event_identity": event_identity}

    def get(self, uid: object) -> dict:
        if uid not in self._queries:
            raise CaptureError("request UID has no query binding")
        return self._queries[uid]


class SamplerCapture:
    """A deliberately opt-in wrapper around one Engine and its one sampler."""

    def __init__(self, destination: Path | str, *, registry: QueryRegistry, process_identity: dict | None = None,
                 max_captures: int, max_bytes: int) -> None:
        if type(max_captures) is not int or max_captures <= 0 or type(max_bytes) is not int or max_bytes <= 0:
            raise CaptureError("max_captures and max_bytes must be positive explicit integers")
        self.destination = Path(destination)
        self.registry = registry
        self.process_identity = _self_identity() if process_identity is None else _identity(process_identity)
        self.max_captures, self.max_bytes = max_captures, max_bytes
        self.errors: list[str] = []
        self._current: list[dict] | None = None
        self._seen: set[tuple[object, int, str]] = set()
        self._attached = False
        self._captured_bytes = 0

    def _invalid(self, message: str) -> None:
        self.errors.append(message)
        self._current = None

    @staticmethod
    def _ids(req: object) -> tuple[list[int], int]:
        import torch
        value, device_len = getattr(req, "input_ids", None), getattr(req, "device_len", None)
        integer_dtypes = {torch.uint8, torch.int8, torch.int16, torch.int32, torch.int64}
        if (not isinstance(value, torch.Tensor) or value.device.type != "cpu" or value.ndim != 1
                or value.dtype not in integer_dtypes):
            raise CaptureError("request input_ids must be a one-dimensional integer CPU tensor")
        if type(device_len) is not int or device_len < 0 or value.numel() < device_len:
            raise CaptureError("request input_ids do not cover pre-device length")
        frozen = value[:device_len].detach().clone().contiguous()
        return [int(x) for x in frozen.tolist()], device_len

    def _before_forward(self, batch: object) -> None:
        reqs = getattr(batch, "reqs", None)
        if not isinstance(reqs, (list, tuple)) or not reqs:
            self._invalid("indeterminate: batch has no requests")
            return
        rows: list[dict] = []
        uids, contexts, prompts = set(), set(), set()
        try:
            for rowidx, req in enumerate(reqs):
                uid = getattr(req, "uid", None)
                if uid in uids:
                    raise CaptureError("indeterminate: duplicate UID in batch")
                uids.add(uid)
                ids, pre_len = self._ids(req)
                query = self.registry.get(uid)
                original = query["prompt_ids"]
                if pre_len < len(original) or ids[:len(original)] != original:
                    raise CaptureError("indeterminate: pre-device context does not begin with original prompt")
                if tuple(ids) in contexts and len(reqs) > 1:
                    raise CaptureError("indeterminate: multi-slot batch has equal prompt content")
                if tuple(original) in prompts and len(reqs) > 1:
                    raise CaptureError("indeterminate: multi-slot batch has equal original prompts")
                contexts.add(tuple(ids))
                prompts.add(tuple(original))
                generation = pre_len - len(original)
                key = (uid, generation, query["event_identity"])
                if key in self._seen:
                    raise CaptureError("indeterminate: duplicate UID/generation/event capture")
                rows.append({"row_index": rowidx, "uid": uid, "context_ids": ids,
                             "context_sha256": _sha(_token_bytes(ids)), "pre_device_len": pre_len,
                             "generation_index": generation, "original_prompt_ids": list(original),
                             "original_prompt_sha256": query["prompt_sha256"],
                             "event_identity": query["event_identity"], "key": key})
        except CaptureError as error:
            self._invalid(str(error))
            return
        self._current = rows

    def attach(self, engine: object) -> "SamplerCapture":
        if self._attached:
            raise CaptureError("capture is already attached")
        sampler = getattr(engine, "sampler", None)
        if not callable(getattr(engine, "forward_batch", None)) or not callable(getattr(sampler, "sample", None)):
            raise CaptureError("attach requires an Engine-like instance with sampler.sample")
        original_forward, original_sample = engine.forward_batch, sampler.sample

        def forward_wrapper(_engine: object, batch: object, *args: object, **kwargs: object):
            self._before_forward(batch)
            return original_forward(batch, *args, **kwargs)

        def sample_wrapper(_sampler: object, logits: object, args: object):
            # Clone the actual sampler input before native code can mutate it.  This is
            # observational only: the original tensor and arguments are passed through unchanged.
            prepared = self._prepare_logits(logits, args)
            try:
                sampled = original_sample(logits, args)
            except Exception:
                # A failed native sample cannot donate stale pre-forward context to a later call.
                self._current = None
                raise
            self._after_sample(prepared, sampled)
            return sampled

        engine.forward_batch = types.MethodType(forward_wrapper, engine)
        sampler.sample = types.MethodType(sample_wrapper, sampler)
        self._attached = True
        return self

    def _prepare_logits(self, logits: object, args: object) -> dict | None:
        import torch
        try:
            rows = self._current
            if rows is None:
                return None
            if not isinstance(logits, torch.Tensor) or logits.ndim != 2 or logits.shape[0] != len(rows):
                raise CaptureError("indeterminate: logits rows do not equal pre-forward request rows")
            if not torch.isfinite(logits).all().item():
                raise CaptureError("indeterminate: sampler logits contain nonfinite values")
            snapshot = logits.detach().to(device="cpu", dtype=torch.float32).clone().contiguous()
            return {"rows": rows, "snapshot": snapshot, "native_dtype": str(logits.dtype),
                    "native_shape": list(logits.shape[1:]), "greedy": getattr(args, "temperatures", object()) is None}
        except (CaptureError, OSError, RuntimeError, ValueError) as error:
            self.errors.append(str(error))
            return None

    def _after_sample(self, prepared: dict | None, sampled: object) -> None:
        import torch
        rows = self._current
        self._current = None
        if prepared is None or rows is None:
            return
        try:
            if not isinstance(sampled, torch.Tensor) or sampled.ndim != 1 or sampled.shape[0] != len(rows):
                raise CaptureError("indeterminate: sampled tokens do not equal request rows")
            if len(self._seen) + len(rows) > self.max_captures:
                raise CaptureError("indeterminate: capture count budget exceeded")
            for row in rows:
                row["sampled_token_id"] = int(sampled[row["row_index"]].detach().cpu().item())
                row["native_dtype"] = prepared["native_dtype"]
                row["native_shape"] = prepared["native_shape"]
            self._publish(prepared["snapshot"], rows, prepared["greedy"])
            self._seen.update(row["key"] for row in rows)
        except (CaptureError, OSError, RuntimeError, ValueError) as error:
            self.errors.append(str(error))

    def _manifest(self) -> dict:
        path = self.destination / "manifest.json"
        if not self.destination.exists():
            return {"schema": SCHEMA, "terminal": "open", "captures": [], "serialized_bytes": 0}
        if self.destination.is_symlink() or not path.is_file() or path.is_symlink():
            raise CaptureError("indeterminate: capture root has no terminal manifest")
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise CaptureError("indeterminate: capture manifest is unreadable") from error
        if (value.get("schema") != SCHEMA or value.get("terminal") not in {"open", "complete", "failed"}
                or not isinstance(value.get("captures"), list) or type(value.get("serialized_bytes")) is not int):
            raise CaptureError("indeterminate: capture manifest is invalid")
        return value

    def _publish(self, snapshot: object, rows: list[dict], greedy: bool) -> None:
        import torch
        parent = self.destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        new_root = not self.destination.exists()
        if new_root:
            self.destination.mkdir()  # exclusive root; readers reject it until manifest appears.
        manifest = {"schema": SCHEMA, "terminal": "open", "captures": [], "serialized_bytes": 0} if new_root else self._manifest()
        if manifest["terminal"] != "open":
            raise CaptureError("indeterminate: capture manifest is already terminal")
        capture_id = f"capture-{len(manifest['captures']) + 1:06d}"
        temporary = self.destination / (capture_id + ".tmp-" + uuid.uuid4().hex)
        try:
            temporary.mkdir()
            snapshot_path = temporary / "logits_fp32.pt"
            torch.save(snapshot, snapshot_path)
            snapshot_raw = snapshot_path.read_bytes()
            receipt = {"schema": SCHEMA, "admitted": False,
                       "scope": "greedy sampler input snapshot only" if greedy else "native sampler input diagnostic only",
                       "greedy_sampler_proof": greedy,
                       "sbatch_coverage": len(rows) > 1, "snapshot": {"path": "logits_fp32.pt", "sha256": _sha(snapshot_raw), "bytes": len(snapshot_raw), "fp32_bytes": snapshot.numel() * snapshot.element_size()},
                       "process_identity": self.process_identity, "capture_count": len(rows),
                       "rows": [{key: value for key, value in row.items() if key != "key"} for row in rows]}
            receipt_raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
            receipt_path = temporary / "receipt.json"; receipt_path.write_bytes(receipt_raw)
            serialized = len(snapshot_raw) + len(receipt_raw)
            if manifest["serialized_bytes"] + serialized > self.max_bytes:
                raise CaptureError("indeterminate: serialized capture byte budget exceeded")
            final = self.destination / capture_id
            os.rename(temporary, final)  # child publication point; never replaces an existing capture.
            next_manifest = {"schema": SCHEMA, "terminal": "open", "captures": manifest["captures"] + [{"id": capture_id,
                             "receipt_sha256": _sha(receipt_raw), "serialized_bytes": serialized,
                             "capture_count": len(rows)}], "serialized_bytes": manifest["serialized_bytes"] + serialized}
            manifest_tmp = self.destination / ("manifest.tmp-" + uuid.uuid4().hex)
            manifest_tmp.write_bytes((json.dumps(next_manifest, sort_keys=True, separators=(",", ":")) + "\n").encode())
            os.replace(manifest_tmp, self.destination / "manifest.json")
            self._captured_bytes = next_manifest["serialized_bytes"]
        except Exception:
            if temporary.exists():
                for item in temporary.iterdir():
                    item.unlink()
                temporary.rmdir()
            raise

    def finalize(self, expected: list[dict]) -> None:
        """Seal exactly the expected UID/generation/event set before a reader may admit it."""
        wanted: set[tuple[object, int, str]] = set()
        try:
            if not isinstance(expected, list):
                raise CaptureError("finalize requires expected capture bindings")
            for item in expected:
                if not isinstance(item, dict) or set(item) != {"uid", "generation_index", "event_identity"}:
                    raise CaptureError("expected capture binding is malformed")
                generation, event = item["generation_index"], item["event_identity"]
                if type(generation) is not int or generation < 0 or not isinstance(event, str) or not event:
                    raise CaptureError("expected capture binding is malformed")
                wanted.add((item["uid"], generation, event))
            if len(wanted) != len(expected) or wanted != self._seen or self.errors:
                raise CaptureError("capture set is incomplete or has indeterminate errors")
            terminal, failure = "complete", None
        except CaptureError as error:
            terminal, failure = "failed", str(error)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.destination.exists():
            self.destination.mkdir()
            manifest = {"schema": SCHEMA, "terminal": "open", "captures": [], "serialized_bytes": 0}
        elif (self.destination / "manifest.json").is_file():
            manifest = self._manifest()
        elif not self.destination.is_symlink() and not any(self.destination.iterdir()):
            manifest = {"schema": SCHEMA, "terminal": "open", "captures": [], "serialized_bytes": 0}
            terminal, failure = "failed", "capture root has no retained manifest"
        else:
            raise CaptureError("capture root has unbound bytes and no manifest")
        if manifest["terminal"] != "open":
            raise CaptureError("capture manifest is already terminal")
        sealed = dict(manifest); sealed["terminal"] = terminal
        if failure is not None: sealed["error"] = failure
        temporary = self.destination / ("manifest.tmp-" + uuid.uuid4().hex)
        temporary.write_bytes((json.dumps(sealed, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.replace(temporary, self.destination / "manifest.json")
        if terminal != "complete":
            raise CaptureError(failure or "capture finalization failed")


def _receipt_rows(receipt: dict, logits: object, snapshot_bytes: int) -> None:
    import torch
    if (receipt.get("schema") != SCHEMA or receipt.get("admitted") is not False
            or type(receipt.get("capture_count")) is not int or receipt["capture_count"] <= 0
            or not isinstance(receipt.get("rows"), list) or receipt["capture_count"] != len(receipt["rows"])
            or not isinstance(receipt.get("greedy_sampler_proof"), bool)):
        raise CaptureError("capture receipt has an invalid terminal contract")
    _identity(receipt.get("process_identity"))
    snapshot = receipt.get("snapshot")
    if not isinstance(logits, torch.Tensor) or logits.dtype != torch.float32 or logits.ndim != 2 or not torch.isfinite(logits).all().item():
        raise CaptureError("capture snapshot is not finite fp32 logits")
    if (not isinstance(snapshot, dict) or snapshot.get("path") != "logits_fp32.pt"
            or not _digest(snapshot.get("sha256")) or type(snapshot.get("bytes")) is not int or snapshot["bytes"] <= 0
            or snapshot["bytes"] != snapshot_bytes or type(snapshot.get("fp32_bytes")) is not int
            or snapshot["fp32_bytes"] != logits.numel() * logits.element_size()):
        raise CaptureError("capture receipt has an invalid snapshot binding")
    if logits.shape[0] != len(receipt["rows"]):
        raise CaptureError("capture rows do not match snapshot rows")
    keys: set[tuple[object, int, str]] = set()
    for index, row in enumerate(receipt["rows"]):
        ids = row.get("context_ids") if isinstance(row, dict) else None
        prompt = row.get("original_prompt_ids") if isinstance(row, dict) else None
        if (not isinstance(ids, list) or not ids or not all(type(value) is int for value in ids)
                or not isinstance(prompt, list) or not prompt or not all(type(value) is int for value in prompt)
                or "uid" not in row
                or row.get("row_index") != index or row.get("pre_device_len") != len(ids)
                or ids[:len(prompt)] != prompt or row.get("context_sha256") != _sha(_token_bytes(ids))
                or row.get("original_prompt_sha256") != _sha(_token_bytes(prompt))
                or type(row.get("generation_index")) is not int or row["generation_index"] < 0
                or row["generation_index"] != len(ids) - len(prompt)
                or not isinstance(row.get("event_identity"), str) or not row["event_identity"]
                or type(row.get("sampled_token_id")) is not int or not isinstance(row.get("native_dtype"), str)
                or row.get("native_shape") != list(logits[index].shape)):
            raise CaptureError("capture receipt row is malformed or no longer bound")
        key = (row["uid"], row["generation_index"], row["event_identity"])
        if key in keys:
            raise CaptureError("capture receipt has duplicate UID/generation/event")
        keys.add(key)
    if receipt["sbatch_coverage"] is not (len(receipt["rows"]) > 1):
        raise CaptureError("capture receipt has invalid S-batch coverage")


def read_logits_receipt(destination: Path | str, *, capture_id: str, receipt_sha256: str,
                        logits_probe: Path | str, logits_probe_sha256: str) -> dict:
    """Read one retained capture and use only pinned D03 metrics for self-metrics."""
    import torch
    root = Path(destination)
    try:
        if root.is_symlink() or not root.is_dir():
            raise CaptureError("capture directory is unavailable")
        manifest_path = root / "manifest.json"
        if not isinstance(capture_id, str) or not re.fullmatch(r"capture-[0-9]{6}", capture_id) or not _digest(receipt_sha256):
            raise CaptureError("reader requires an exact capture ID and pinned receipt SHA")
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise CaptureError("capture root has no terminal manifest")
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("schema") != SCHEMA or manifest.get("terminal") != "complete"
                or not isinstance(manifest.get("captures"), list) or type(manifest.get("serialized_bytes")) is not int):
            raise CaptureError("capture manifest is malformed")
        declared_ids: set[str] = set(); total = 0; selected = None; selected_receipt = selected_snapshot = None
        for entry in manifest["captures"]:
            if (not isinstance(entry, dict) or not re.fullmatch(r"capture-[0-9]{6}", str(entry.get("id")))
                    or entry["id"] in declared_ids or not _digest(entry.get("receipt_sha256"))
                    or type(entry.get("serialized_bytes")) is not int or entry["serialized_bytes"] <= 0
                    or type(entry.get("capture_count")) is not int or entry["capture_count"] <= 0):
                raise CaptureError("capture manifest entry is malformed")
            declared_ids.add(entry["id"])
            directory = root / entry["id"]
            if (not directory.is_dir() or directory.is_symlink()
                    or {path.name for path in directory.iterdir()} != {"receipt.json", "logits_fp32.pt"}):
                raise CaptureError("capture directory has unbound or missing bytes")
            receipt_entry, snapshot_entry = directory / "receipt.json", directory / "logits_fp32.pt"
            if directory.is_symlink() or any(path.is_symlink() or not path.is_file() for path in (receipt_entry, snapshot_entry)):
                raise CaptureError("capture manifest references missing bytes")
            raw_receipt, raw_snapshot = receipt_entry.read_bytes(), snapshot_entry.read_bytes()
            if _sha(raw_receipt) != entry["receipt_sha256"] or len(raw_receipt) + len(raw_snapshot) != entry["serialized_bytes"]:
                raise CaptureError("capture manifest does not bind retained bytes")
            document = json.loads(raw_receipt)
            if document.get("snapshot", {}).get("sha256") != _sha(raw_snapshot) or document.get("snapshot", {}).get("bytes") != len(raw_snapshot) or document.get("capture_count") != entry["capture_count"]:
                raise CaptureError("manifest capture receipt does not bind snapshot")
            total += entry["serialized_bytes"]
            if entry["id"] == capture_id: selected, selected_receipt, selected_snapshot = entry, document, raw_snapshot
        children = {path.name for path in root.iterdir()}
        if children != {"manifest.json", *declared_ids}:
            raise CaptureError("capture root has unmanifested or partial children")
        if total != manifest["serialized_bytes"] or selected is None or selected["receipt_sha256"] != receipt_sha256:
            raise CaptureError("requested capture is not pinned by terminal manifest")
        receipt_path, snapshot_path = root / capture_id / "receipt.json", root / capture_id / "logits_fp32.pt"
        if any(path.is_symlink() or not path.is_file() for path in (receipt_path, snapshot_path)):
            raise CaptureError("capture files are unavailable")
        receipt_raw, snapshot_raw = receipt_path.read_bytes(), snapshot_path.read_bytes()
        receipt = json.loads(receipt_raw)
        if _sha(receipt_raw) != receipt_sha256 or not _digest(receipt.get("snapshot", {}).get("sha256")) or _sha(snapshot_raw) != receipt["snapshot"]["sha256"]:
            raise CaptureError("capture receipt does not bind snapshot bytes")
        tool = Path(logits_probe)
        tool_raw = tool.read_bytes()
        if tool.is_symlink() or not _digest(logits_probe_sha256) or _sha(tool_raw) != logits_probe_sha256:
            raise CaptureError("pinned logits tool differs")
        spec = importlib.util.spec_from_file_location("sampler_capture_metrics_" + logits_probe_sha256[:12], tool)
        if spec is None or spec.loader is None:
            raise CaptureError("pinned logits tool is not importable")
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
        logits = torch.load(snapshot_path, map_location="cpu", weights_only=True)
        _receipt_rows(receipt, logits, len(snapshot_raw))
        # Self metrics intentionally prove only retained logits readability, never a D03 binding.
        return {"schema": SCHEMA, "admitted": False, "verdict": "recorded", "receipt_sha256": _sha(receipt_raw),
                "snapshot_sha256": _sha(snapshot_raw), "rows": int(logits.shape[0]), "scope": "self logits metrics only; no D03 binding",
                "metrics": module.metrics(logits, logits)}
    except (CaptureError, OSError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        return {"schema": SCHEMA, "admitted": False, "verdict": "indeterminate", "error": str(error)}
