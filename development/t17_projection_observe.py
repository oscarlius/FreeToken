"""Test-only projection observer for the 8192..8256 continuation rows.

It wraps existing Python ``forward`` methods once, copies only six selected 65-row
CPU tensors, and never changes inputs, batches, metadata, model state, or returns.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import types
from typing import Any, Callable

TARGET_START = 8192
TARGET_COUNT = 65
TARGET_STOP = TARGET_START + TARGET_COUNT
SCHEMA = "t17_projection_observe/v1"


class ProjectionObserver:
    """Fail-closed recorder for one singleton prefill segment spanning 8192..8256."""

    def __init__(self, output_dir: str | Path, *, sink: Callable[[dict], None] = lambda _row: None):
        self.output_dir = Path(output_dir)
        self.sink = sink
        self.identity: dict | None = None
        self.captures: dict[str, tuple[Any, dict]] = {}
        self.errors: list[str] = []
        self.receipt: dict | None = None
        self._terminal_seen = False
        self.selection: dict | None = None
        self.role_context: dict[str, dict] = {}

    @staticmethod
    def _source_binding(module: Any, method_name: str | None = None) -> dict:
        cls = type(module)
        source = inspect.getsourcefile(cls)
        if not source:
            raise ValueError(f"cannot bind source for {cls.__module__}.{cls.__qualname__}")
        path = Path(source)
        if not path.is_file():
            raise ValueError(f"module source is not a file: {path}")
        binding = {
            "module": cls.__module__,
            "class": cls.__qualname__,
            "source_file": str(path),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if method_name is not None:
            method = getattr(cls, method_name, None)
            if method is None:
                raise ValueError(f"owner {cls.__qualname__} has no method {method_name}")
            binding.update(
                method=method_name,
                method_qualname=getattr(method, "__qualname__", method_name),
            )
        return binding

    def _target(self, batch: Any) -> tuple[dict, list[int]] | None:
        if bool(getattr(batch, "is_decode", False)):
            return None
        try:
            reqs = batch.reqs
        except AttributeError as exc:
            raise ValueError("batch has no reqs for absolute-position binding") from exc
        if not reqs:
            raise ValueError("batch has no requests")
        target_candidates = []
        for req in reqs:
            try:
                cached = int(req.cached_len)
                device = int(req.device_len)
                extend = int(req.extend_len)
            except AttributeError as exc:
                raise ValueError("request lacks cached/device/extend coordinates") from exc
            if device < cached or extend < 0 or device - cached != extend:
                raise ValueError("request has incoherent cached/device/extend coordinates")
            if cached < TARGET_STOP and device > TARGET_START:
                target_candidates.append(req)
        if not target_candidates:
            return None
        # Donors end at 8193 and deliberately do not contain the 65-row continuation.
        # They are non-target observations; a segment that reaches 8257 but starts after
        # 8192 is instead a malformed partial target and must fail closed.
        if all(int(req.device_len) < TARGET_STOP for req in target_candidates):
            return None
        if len(reqs) != 1 or len(target_candidates) != 1:
            raise ValueError("target absolute-position range is not a singleton request")
        req = target_candidates[0]
        cached, device, extend = int(req.cached_len), int(req.device_len), int(req.extend_len)
        if cached > TARGET_START or device < TARGET_STOP:
            raise ValueError("prefill segment only partially covers required 8192..8256 rows")
        positions = list(range(TARGET_START, TARGET_STOP))
        local_rows = [position - cached for position in positions]
        if local_rows[0] < 0 or local_rows[-1] >= extend:
            raise ValueError("absolute-position mapping falls outside actual prefill rows")
        try:
            slot = int(req.linear_slot_idx)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("target request lacks a concrete linear slot") from exc
        identity = {
            "uid": str(req.uid),
            "slot": slot,
            "cached_tokens": cached,
            "device_tokens": device,
            "extend_tokens": extend,
            "positions": positions,
        }
        return identity, local_rows

    def capture(self, kind: str, value: Any, batch: Any, module: Any,
                method_name: str | None = None) -> None:
        """Immediately make a CPU clone of the selected real rows, or retain failure."""
        if self.errors:
            return
        try:
            selected = self._target(batch)
            if selected is None:
                return
            identity, rows = selected
            if self.identity is None:
                self.identity = identity
            elif self.identity != identity:
                raise ValueError("target request identity or coordinates drifted")
            if kind in self.captures:
                raise ValueError(f"duplicate target capture: {kind}")
            if not hasattr(value, "shape") or len(value.shape) < 1:
                raise ValueError(f"{kind} is not a token-row tensor")
            if int(value.shape[0]) != identity["extend_tokens"]:
                raise ValueError(f"{kind} row count does not equal actual extend_tokens")
            tensor = value[rows].detach().to("cpu").clone()
            if int(tensor.shape[0]) != TARGET_COUNT:
                raise ValueError(f"{kind} did not retain exactly {TARGET_COUNT} rows")
            meta = {**identity, "kind": kind, **self.role_context.get(kind, {}),
                    "module_binding": self._source_binding(module, method_name),
                    "shape": list(tensor.shape), "dtype": str(tensor.dtype)}
            self.captures[kind] = (tensor, meta)
            self.sink({"kind": "projection-capture", **meta})
        except Exception as exc:
            self.errors.append(str(exc))

    def finalize(self, uid: Any) -> dict:
        """Called exactly once for the target request's terminal reply."""
        if self._terminal_seen:
            raise ValueError("projection observer received more than one terminal event")
        self._terminal_seen = True
        if self.errors:
            raise ValueError("; ".join(self.errors))
        if self.identity is None:
            raise ValueError("target 8192..8256 prefill segment was never observed")
        if str(uid) != self.identity["uid"]:
            raise ValueError("terminal UID does not bind to the captured target request")
        required = (
            "embedding_output", "ple_input", "ple_value_projection_output",
            "ple_conv_output", "gdn_qkv_input", "gdn_qkv_output",
        )
        missing = [kind for kind in required if kind not in self.captures]
        if missing:
            raise ValueError("missing target projection capture: " + ", ".join(missing))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        import torch

        roles = {}
        for kind in required:
            tensor, meta = self.captures[kind]
            filename = f"projection_{self.identity['uid']}_{kind}.pt"
            path = self.output_dir / filename
            try:
                with path.open("xb") as stream:
                    torch.save(tensor, stream)
            except FileExistsError as exc:
                raise ValueError(f"refusing to replace projection snapshot: {filename}") from exc
            roles[kind] = {**meta, "file": filename,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if self.selection is None:
            raise ValueError("projection observer has no frozen decoder selection")
        receipt = {"schema": SCHEMA, **self.identity, "selection": self.selection, "roles": roles}
        receipt_path = self.output_dir / f"projection_{self.identity['uid']}_receipt.json"
        if receipt_path.exists():
            raise ValueError("refusing to replace projection receipt")
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
        receipt.update(receipt_file=receipt_path.name,
                       receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
        self.receipt = receipt
        self.sink({"kind": "projection-receipt", **receipt})
        return receipt


def _replace_bound_method(owner: Any, method_name: str, wrapper: Callable[..., Any], marker: str) -> None:
    """Wrap a bound instance method; unlike an OP, it has no ``.forward`` attribute."""
    if getattr(owner, marker, False):
        raise ValueError(f"observer already installed on {type(owner).__name__}.{method_name}")
    original = getattr(owner, method_name)
    if not inspect.ismethod(original):
        raise ValueError(f"expected bound method {type(owner).__name__}.{method_name}")

    def wrapped(this: Any, *args: Any, **kwargs: Any) -> Any:
        return wrapper(original, *args, **kwargs)

    setattr(owner, method_name, types.MethodType(wrapped, owner))
    setattr(owner, marker, True)


def _replace_forward(module: Any, wrapper: Callable[..., Any], marker: str) -> None:
    if getattr(module, marker, False):
        raise ValueError(f"observer already installed on {type(module).__name__}")
    original = module.forward

    def wrapped(this: Any, *args: Any, **kwargs: Any) -> Any:
        return wrapper(original, *args, **kwargs)

    module.forward = types.MethodType(wrapped, module)
    setattr(module, marker, True)


def install(model: Any, get_batch: Callable[[], Any], *, output_dir: str | Path,
            sink: Callable[[dict], None] = lambda _row: None,
            source_ple_layer_ids: tuple[int, ...] | None = None) -> ProjectionObserver:
    """Install runtime-only wrappers on the exact Qwen4Exp GDN/PLE paths.

    Required model structure is intentionally strict: GDN decoder 0 and the
    unique PLE owner decoder 1 are distinct model components. The caller passes
    candidate-parser zero-based ids, never raw one-based HF ids.
    """
    try:
        layers = model.layers.op_list
        gdn_owner = layers[0]
        ple_owners = [(index, layer) for index, layer in enumerate(layers) if layer.ple is not None]
        if len(ple_owners) != 1:
            raise ValueError("expected exactly one PLE owner in the loaded decoder list")
        ple_index, ple_owner = ple_owners[0]
        if ple_index != 1:
            raise ValueError(f"expected PLE owner at decoder index 1, got {ple_index}")
        if source_ple_layer_ids is not None and tuple(source_ple_layer_ids) != (ple_index,):
            raise ValueError("loaded source config PLE layer ids do not bind the PLE owner")
        ple = ple_owner.ple
        gdn = gdn_owner.linear_attn
        qkv = gdn.in_proj_qkvz if getattr(gdn, "_split_in_proj", False) else gdn.in_proj
        embedding = model.embed_tokens
        value_projection = ple.value_proj
    except (AttributeError, IndexError) as exc:
        raise ValueError("unexpected Qwen4Exp first-decoder PLE/GDN projection structure") from exc
    if (not getattr(gdn_owner, "_is_linear", False) or not getattr(ple_owner, "_is_linear", False)
            or int(getattr(gdn_owner, "_layer_id")) != 0
            or int(getattr(ple_owner, "_layer_id")) != ple_index
            or int(getattr(ple, "layer_id")) != int(getattr(ple_owner, "_layer_id"))):
        raise ValueError("loaded decoder indices and source layer identities do not bind")

    observer = ProjectionObserver(output_dir, sink=sink)
    def owner_context(index: int, owner: Any) -> dict:
        return {"decoder_index": index, "decoder_layer_id": int(owner._layer_id),
                "decoder_class": type(owner).__qualname__}
    observer.selection = {
        "gdn": owner_context(0, gdn_owner),
        "ple": owner_context(ple_index, ple_owner),
        "ple_layer_id": int(ple.layer_id),
    }
    observer.role_context = {
        "embedding_output": {"embedding_owner": type(model).__qualname__},
        "gdn_qkv_input": observer.selection["gdn"],
        "gdn_qkv_output": observer.selection["gdn"],
        "ple_input": observer.selection["ple"],
        "ple_value_projection_output": observer.selection["ple"],
        "ple_conv_output": observer.selection["ple"],
    }

    def batch() -> Any:
        result = get_batch()
        if result is None:
            raise ValueError("global context has no active batch")
        return result

    _replace_forward(
        embedding,
        lambda original, input_ids, *args, **kwargs: _capture_after(
            observer, "embedding_output", original(input_ids, *args, **kwargs), batch(), embedding),
        "_t17_projection_embedding_observed",
    )
    _replace_forward(
        ple,
        lambda original, hidden, *args, **kwargs: _ple_forward(
            observer, original, hidden, batch(), ple, *args, **kwargs),
        "_t17_projection_ple_observed",
    )
    _replace_forward(
        value_projection,
        lambda original, hidden, *args, **kwargs: _capture_after(
            observer, "ple_value_projection_output", original(hidden, *args, **kwargs), batch(), value_projection),
        "_t17_projection_ple_value_observed",
    )
    _replace_bound_method(
        ple,
        "_short_conv",
        lambda original, value, *args, **kwargs: _capture_after(
            observer, "ple_conv_output", original(value, *args, **kwargs), batch(), ple,
            method_name="_short_conv"),
        "_t17_projection_ple_conv_observed",
    )

    def qkv_wrapper(original: Callable[..., Any], hidden: Any, *args: Any, **kwargs: Any) -> Any:
        active = batch()
        observer.capture("gdn_qkv_input", hidden, active, qkv)
        result = original(hidden, *args, **kwargs)
        observer.capture("gdn_qkv_output", result, active, qkv)
        return result

    _replace_forward(qkv, qkv_wrapper, "_t17_projection_gdn_qkv_observed")
    return observer


def _capture_after(observer: ProjectionObserver, kind: str, result: Any, batch: Any, module: Any,
                   method_name: str | None = None) -> Any:
    observer.capture(kind, result, batch, module, method_name)
    return result


def _ple_forward(observer: ProjectionObserver, original: Callable[..., Any], hidden: Any,
                 batch: Any, module: Any, *args: Any, **kwargs: Any) -> Any:
    observer.capture("ple_input", hidden, batch, module)
    return original(hidden, *args, **kwargs)


