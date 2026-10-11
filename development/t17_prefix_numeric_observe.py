"""Test-only first-GDN prefix observer for the T17 numerical isolation."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import types


FIELDS = ("conv_in", "q", "k", "v", "g", "beta")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _item(value) -> int:
    return int(value.item()) if hasattr(value, "item") else int(value)


def _slice_absolute(value, start: int, end: int, cached: int):
    """Copy only [start,end) from a token-major value whose local offset is cached."""
    return value[:, start - cached:end - cached].detach().to("cpu").clone()


class PrefixObserver:
    def __init__(self, pool, output_dir, boundary=8192, prefix_start=512, sink=lambda row: None):
        self.pool = pool
        self.out = Path(output_dir)
        self.boundary, self.prefix_start, self.sink = int(boundary), int(prefix_start), sink
        if not 0 <= self.prefix_start < self.boundary:
            raise ValueError("invalid common-prefix interval")
        self.by_uid = {}
        self.errors = []
        self._sequence = 0
        self._armed = None
        self.source = {}
        self.first_gdn_quantization = {}

    def _row(self, uid):
        return self.by_uid.setdefault(str(uid), {"segments": [], "h": None, "errors": []})

    def _save(self, uid, kind, tensor, metadata):
        import torch
        self.out.mkdir(parents=True, exist_ok=True)
        self._sequence += 1
        name = "prefix_%s_%04d_%s.pt" % (uid, self._sequence, kind)
        path = self.out / name
        if path.exists():
            raise ValueError("refusing to replace observer evidence")
        torch.save(tensor, path)
        return {"file": name, "sha256": _sha(path), "shape": list(tensor.shape),
                "dtype": str(tensor.dtype), **metadata}

    def _batch(self):
        if self._get_batch is not None:
            return self._get_batch()
        from freetoken.core import get_global_ctx
        return get_global_ctx().batch

    def _identity(self, batch):
        if len(batch.reqs) != 1:
            raise ValueError("first-GDN observer requires singleton prefill")
        req = batch.reqs[0]
        if not getattr(batch, "is_prefill", True):
            raise ValueError("first-GDN observer received non-prefill batch")
        return str(req.uid), int(req.cached_len), int(req.device_len), int(req.extend_len)

    def capture_conv(self, conv_in):
        uid, cached, device, extend = self._identity(self._batch())
        if self._armed is not None:
            raise ValueError("first-GDN kernel was not reached before the next conv prefill")
        start, end = max(cached, self.prefix_start), min(device, self.boundary)
        self._armed = (uid, cached, device)
        if start >= end:
            return
        if conv_in.shape[0] != extend:
            raise ValueError("conv input length is not the scheduled extension")
        row = self._row(uid)
        fields = {"conv_in": self._save(uid, "conv_in", _slice_absolute(conv_in.unsqueeze(0), start, end, cached), {
            "absolute_start": start, "absolute_end": end, "cached_tokens": cached,
            "device_tokens": device, "extend_tokens": extend})}
        row["segments"].append({"absolute_start": start, "absolute_end": end,
                                "cached_tokens": cached, "device_tokens": device,
                                "extend_tokens": extend, "fields": fields})
        self.sink({"kind": "prefix-conv", "uid": uid, "absolute_start": start,
                   "absolute_end": end, "cached_tokens": cached, "device_tokens": device})

    def capture_gdn_inputs(self, q, k, v, g, beta):
        armed = self._armed
        if armed is None:
            return False
        uid, cached, device, extend = self._identity(self._batch())
        if armed != (uid, cached, device):
            raise ValueError("first-GDN kernel coordinates differ from its conv prefill")
        start, end = max(cached, self.prefix_start), min(device, self.boundary)
        row = self._row(uid)
        if start < end:
            segment = next((x for x in reversed(row["segments"])
                            if x["cached_tokens"] == cached and x["device_tokens"] == device), None)
            if segment is None:
                raise ValueError("GDN capture has no matching raw conv input")
            for kind, value in zip(("q", "k", "v", "g", "beta"), (q, k, v, g, beta)):
                if value.shape[1] != extend:
                    raise ValueError("GDN argument length is not the scheduled extension: " + kind)
                segment["fields"][kind] = self._save(uid, kind, _slice_absolute(value, start, end, cached), {
                    "absolute_start": start, "absolute_end": end, "cached_tokens": cached,
                    "device_tokens": device, "extend_tokens": extend})
        return True

    def capture_gdn_result(self, result):
        armed = self._armed
        if armed is None:
            return
        self._armed = None
        uid, cached, device = armed
        actual_uid, actual_cached, actual_device, _extend = self._identity(self._batch())
        if (uid, cached, device) != (actual_uid, actual_cached, actual_device):
            raise ValueError("first-GDN result coordinates differ from its conv prefill")
        row = self._row(uid)
        if not (cached < self.boundary < device):
            return
        fla = getattr(self._batch(), "fla_metadata", None)
        if fla is None or fla.track_h_row is None:
            raise ValueError("target boundary lacks the existing tracked h metadata")
        if not isinstance(result, tuple) or len(result) != 2:
            raise ValueError("tracked GDN prefill did not return (output, h)")
        h = result[1]
        boundary_row = self.boundary - cached
        absolute_boundary = self.boundary
        if boundary_row <= 0 or boundary_row % 64:
            raise ValueError("target boundary is not a completed 64-token boundary")
        from freetoken.kernel.fla.chunk import CHUNK_SIZE
        from freetoken.kernel.fla.index import prepare_chunk_offsets
        if CHUNK_SIZE != 64:
            raise ValueError("observer proof is pinned to the GDN 64-token h contract")
        offsets = prepare_chunk_offsets(fla.cu_seqlens, CHUNK_SIZE)
        expected = _item(offsets[0]) + boundary_row // CHUNK_SIZE
        if expected < 0 or expected >= h.shape[1]:
            raise ValueError("target h row is outside the original kernel result")
        observed = _item(fla.track_h_row[0])
        actual_track_boundary_row = _item(fla.track_boundary_row[0])
        if row["h"] is not None:
            raise ValueError("duplicate first-GDN boundary h capture")
        row["h"] = self._save(uid, "h_8192", h[:, expected:expected + 1].detach().to("cpu").clone(), {
            "absolute_boundary": absolute_boundary, "target_boundary_row": boundary_row,
            "actual_track_boundary_row": actual_track_boundary_row,
            "actual_track_absolute_boundary": cached + actual_track_boundary_row,
            "actual_track_h_row": observed, "computed_h_row": expected,
            "cached_tokens": cached, "device_tokens": device})
        self.sink({"kind": "prefix-h", "uid": uid, "absolute_boundary": absolute_boundary,
                   "track_h_row": observed})

    def has_uid(self, uid) -> bool:
        row = self.by_uid.get(str(uid))
        if row is None or row["h"] is None:
            return False
        segments = sorted(row["segments"], key=lambda x: x["absolute_start"])
        cursor = self.prefix_start
        for segment in segments:
            if segment["absolute_start"] != cursor or set(segment["fields"]) != set(FIELDS):
                return False
            cursor = segment["absolute_end"]
        return cursor == self.boundary

    def finalize(self, uid):
        uid = str(uid)
        if not self.has_uid(uid):
            raise ValueError("first-GDN prefix evidence is incomplete")
        row = self.by_uid[uid]
        receipt = {"schema": "t17_first_gdn_prefix/v1", "uid": uid,
                   "absolute_interval": [self.prefix_start, self.boundary],
                   "segments": row["segments"], "h": row["h"],
                   "source": self.source,
                   "first_gdn_quantization": self.first_gdn_quantization}
        path = self.out / ("prefix_%s_receipt.json" % uid)
        if path.exists():
            raise ValueError("refusing to replace observer receipt")
        with path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
        return {**receipt, "receipt_file": path.name, "receipt_sha256": _sha(path)}


def install(model, pool, *, output_dir, boundary=8192, prefix_start=512, sink=lambda row: None, get_batch=None):
    """Install a one-call wrapper on the first decoder GDN and its kernel symbol."""
    layers = getattr(getattr(model, "layers", None), "op_list", None)
    if layers is None:
        layers = model.model.layers.op_list
    first_layer = next((layer for layer in layers if getattr(layer, "_is_linear", False)), None)
    target = None if first_layer is None else first_layer.linear_attn
    if target is None or getattr(target, "_t17_prefix_numeric_observed", False):
        raise ValueError("first GDN is absent or already observed")
    observer = PrefixObserver(pool, output_dir, boundary, prefix_start, sink)
    observer._get_batch = get_batch
    original_conv = target._conv_prefill
    module = inspect.getmodule(type(target))
    original_kernel = module.gdn_prefill_chunk_fla

    def conv_wrapped(this, conv_in, *args, **kwargs):
        observer.capture_conv(conv_in)
        return original_conv(conv_in, *args, **kwargs)

    def kernel_wrapped(q, k, v, g, beta, *args, **kwargs):
        armed = observer.capture_gdn_inputs(q, k, v, g, beta)
        result = original_kernel(q, k, v, g, beta, *args, **kwargs)
        if armed:
            observer.capture_gdn_result(result)
        return result

    target._conv_prefill = types.MethodType(conv_wrapped, target)
    target._t17_prefix_numeric_observed = True
    module.gdn_prefill_chunk_fla = kernel_wrapped
    for candidate in (module, inspect.getmodule(original_kernel)):
        filename = getattr(candidate, "__file__", None)
        if filename:
            path = Path(filename).resolve()
            observer.source[str(path)] = _sha(path)
    for name in ("in_proj_qkvz", "in_proj_ba"):
        projection = getattr(target, name, None)
        method = getattr(projection, "quant_method", None)
        kernel = getattr(method, "kernel", None)
        scheme = getattr(method, "scheme", None)
        observer.first_gdn_quantization[name] = {
            "quant_method_class": None if method is None else type(method).__module__ + "." + type(method).__qualname__,
            "kernel_name": getattr(kernel, "name", None),
            "kernel_class": None if kernel is None else type(kernel).__module__ + "." + type(kernel).__qualname__,
            "requested": getattr(method, "requested", None),
            "scheme": None if scheme is None else str(scheme),
        }
    return observer
