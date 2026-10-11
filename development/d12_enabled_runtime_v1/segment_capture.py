"""Opt-in D12 post-prefill linear-state diagnostic.

This module is intentionally an instance wrapper, not a product hook.  A
diagnostic launcher installs it on one Engine and must also configure the
native ``FT_DEV_STATE_DUMP`` before importing the engine's state pool.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path


_ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")


def _configured_dump_path() -> str:
    """Read the state-pool module's import-time diagnostic destination."""
    module = importlib.import_module("freetoken.kvcache.linear_state_pool")
    return getattr(module, "DUMP_PATH", "")


def _require_int(value, name: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError("invalid " + name)
    return value


def _read_new_record(root: Path, before: bytes, *, uid: int, slot: int, length: int) -> dict:
    index = root / "index.jsonl"
    if not index.is_file():
        raise ValueError("native state dump did not create index.jsonl")
    raw = index.read_bytes()
    if not raw.startswith(before):
        raise ValueError("native state dump rewrote its existing index")
    appended = raw[len(before):]
    lines = appended.splitlines()
    if len(lines) != 1:
        raise ValueError("native state dump did not append exactly one record")
    try:
        record = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise ValueError("native state dump appended invalid JSON") from error
    if (record.get("kind") != "d12_post_prefill" or record.get("uid") != str(uid)
            or record.get("length") != length or record.get("dev_slots") != [slot]
            or record.get("host_slots") is not None):
        raise ValueError("native state dump record identity differs")
    files = record.get("files")
    if not isinstance(files, dict) or set(files) != set(_ROLES):
        raise ValueError("native state dump is missing required device roles")
    role_files = {}
    for role in _ROLES:
        name = files[role]
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("native state dump role filename is invalid")
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("native state dump role file is unavailable")
        blob = path.read_bytes()
        role_files[role] = {"path": name, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
    return {"native_record": record, "role_files": role_files}


def _read_d0_append(path, before, outer, cache):
    if path.resolve() != path.absolute() or not path.is_file():
        raise ValueError("D12 native D0 file is unavailable")
    raw = path.read_bytes()
    appended = raw[len(before):]
    if not raw.startswith(before) or not appended.endswith(b"\n") or len(appended.splitlines()) != 1:
        raise ValueError("D12 native D0 did not append exactly one unchanged-prefix record")
    record = json.loads(appended)
    if (record.get("chunk") != outer["index"] or record.get("start") != outer["start"]
            or record.get("end") != outer["end"] or getattr(cache, "_d0_prefill_active", True)):
        raise ValueError("D12 native D0 outer identity or completion differs")
    return {"path": path.name, "byte_offset": len(before), "bytes": len(appended),
            "sha256": hashlib.sha256(appended).hexdigest(), "record": record,
            "device_type": cache.device.type,
            "cache_num_layers": cache.num_layers,
            "routed_only_threshold": cache.prefill_routed_only_max_tokens,
            "prefill_overlap": cache.prefill_overlap,
            "eager_prefill": True}


def install_prefill_segment_capture(scheduler, dump_root, emit, allowed_uids=(0, 1, 2), *, d0_path=None):
    """Wrap one engine's ``forward_batch`` and return ``(context_provider, restore)``.

    Successful admitted outer prefills append one native state-pool record after
    the original forward returns.  The returned provider is for the routed-bank
    observer: while an admitted forward is active it reads the model's current
    layer-major child batch, never substitutes the outer segment geometry.
    """
    if not callable(emit):
        raise ValueError("emit must be callable")
    if (not isinstance(allowed_uids, tuple) or not allowed_uids
            or any(type(uid) is not int for uid in allowed_uids)
            or len(set(allowed_uids)) != len(allowed_uids)):
        raise ValueError("allowed_uids must be a non-empty tuple of unique ints")
    root = Path(dump_root)
    if _configured_dump_path() != str(root):
        raise ValueError("FT_DEV_STATE_DUMP does not equal dump_root")
    engine = getattr(scheduler, "engine", None)
    original = getattr(engine, "forward_batch", None)
    if not callable(original):
        raise ValueError("scheduler has no Engine.forward_batch")
    if getattr(original, "_d12_segment_capture", False):
        raise ValueError("D12 segment capture already installed")
    d0 = Path(d0_path).absolute() if d0_path is not None else None
    cache = getattr(engine, "moe_offload_cache", None)
    if d0 is not None:
        if (d0.resolve() != d0 or d0.parent != root.absolute().parent or d0.exists()
                or not getattr(cache, "_d0_on", False) or getattr(cache, "_d0_prefill_path", None) != str(d0)
                or getattr(cache, "_d0_chunk_idx", None) != 0
                or getattr(cache, "_d0_prefill_active", False) or cache.prefill_overlap):
            raise ValueError("D12 requires a fresh native D0 path and non-overlap cache")

    active_outer = None
    next_outer_index = 0

    def context_provider():
        if active_outer is None:
            raise ValueError("D12 capture has no active outer prefill")
        batch = engine.ctx.batch
        if (not getattr(batch, "is_prefill", False) or len(getattr(batch, "reqs", ())) != 1):
            raise ValueError("D12 capture current batch is not a single prefill child")
        request = batch.reqs[0]
        uid = _require_int(getattr(request, "uid", None), "child uid")
        if uid != active_outer["uid"]:
            raise ValueError("D12 capture child UID differs from outer prefill")
        start = _require_int(getattr(request, "cached_len", None), "child start", minimum=0)
        end = _require_int(getattr(request, "device_len", None), "child end", minimum=0)
        if not active_outer["start"] <= start < end <= active_outer["end"]:
            raise ValueError("D12 capture child extent lies outside outer prefill")
        return {"uid": uid, "outer_segment_index": active_outer["index"],
                "child_start": start, "child_end": end, "child_tokens": end - start}

    def wrapped(batch, *args, **kwargs):
        nonlocal active_outer, next_outer_index
        reqs = getattr(batch, "reqs", ())
        if not getattr(batch, "is_prefill", False) or len(reqs) != 1:
            return original(batch, *args, **kwargs)
        request = reqs[0]
        uid = getattr(request, "uid", None)
        if type(uid) is not int or uid not in allowed_uids:
            return original(batch, *args, **kwargs)
        if d0 is not None and (getattr(batch, "is_decode", False)
                               or getattr(batch, "dev_prefill_schedule", None) is not None):
            raise ValueError("D12 D0 coverage requires an ordinary eager prefill")
        # Ordinary PrefillManager batches do not populate the optional D0
        # ``seg_start``/``seg_end`` fields.  Req geometry is the production
        # coordinate source; scheduled development segments may additionally
        # provide batch fields, which must agree rather than replace it.
        start = _require_int(getattr(request, "cached_len", None), "outer start", minimum=0)
        end = _require_int(getattr(request, "device_len", None), "outer end", minimum=0)
        batch_start = getattr(batch, "seg_start", None)
        batch_end = getattr(batch, "seg_end", None)
        if ((batch_start is not None and batch_start != start)
                or (batch_end is not None and batch_end != end)):
            raise ValueError("outer batch and request extents differ")
        if end <= start:
            raise ValueError("outer prefill extent is empty")
        slot = _require_int(getattr(request, "linear_slot_idx", None), "linear slot", minimum=0)
        pool = getattr(engine, "linear_state_pool", None)
        if pool is None or not callable(getattr(pool, "dump_state", None)):
            raise ValueError("D12 segment capture requires LinearStatePool.dump_state")
        if active_outer is not None:
            raise RuntimeError("D12 segment capture nested outer prefill")
        outer = {"uid": uid, "index": next_outer_index, "start": start, "end": end, "slot": slot}
        next_outer_index += 1
        before = (root / "index.jsonl").read_bytes() if (root / "index.jsonl").is_file() else b""
        d0_before = b""
        if d0 is not None and d0.exists():
            if d0.resolve() != d0 or not d0.is_file():
                raise ValueError("D12 native D0 path changed")
            d0_before = d0.read_bytes()
        active_outer = outer
        try:
            result = original(batch, *args, **kwargs)
        except BaseException:
            raise
        else:
            d0_evidence = _read_d0_append(d0, d0_before, outer, cache) if d0 is not None else None
            pool.dump_state("d12_post_prefill", dev_slots=slot, length=end, uid=str(uid),
                            note="d12 outer=%d start=%d end=%d" % (outer["index"], start, end))
            evidence = _read_new_record(root, before, uid=uid, slot=slot, length=end)
            emit({"schema": "ft_d12_post_prefill_state/v1", "admitted": False,
                  "outer": {"uid": uid, "outer_segment_index": outer["index"],
                            "start": start, "end": end, "linear_slot_idx": slot},
                  **evidence, **({"native_d0": d0_evidence} if d0_evidence is not None else {})})
            return result
        finally:
            active_outer = None

    wrapped._d12_segment_capture = True
    engine.forward_batch = wrapped

    def restore():
        if engine.forward_batch is not wrapped:
            raise RuntimeError("D12 segment capture ownership changed before cleanup")
        engine.forward_batch = original

    return context_provider, restore
