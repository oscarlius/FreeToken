"""Test-only first-GDN hyper-connection observer for the R027 M-shape diagnosis.

The observer wraps existing instance methods.  It does not alter a batch, model
state, arguments, or return values; it retains only rows 4608..4671 on CPU.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import types
from typing import Any, Callable


TARGET_CACHED = 4608
TARGET_START = 4608
TARGET_COUNT = 64
TARGET_STOP = TARGET_START + TARGET_COUNT
TARGET_DEVICES = (8193, 8257)
SCHEMA = "t17_hc_observe/v1"
ROLES = (
    "embedding_output", "hc_mix_input", "hc_down_input", "hc_down_output",
    "hc_up_input", "hc_up_output", "hc_mix_output", "gdn_qkv_input",
    "gdn_qkv_output",
)


def _class_name(value: Any) -> str:
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _source_binding(owner: Any, method_name: str) -> dict:
    cls = type(owner)
    source = inspect.getsourcefile(cls)
    if not source or not Path(source).is_file():
        raise ValueError(f"cannot bind source for {_class_name(owner)}")
    method = getattr(cls, method_name, None)
    if method is None:
        raise ValueError(f"missing class method {cls.__qualname__}.{method_name}")
    method_source = inspect.getsource(method)
    path = Path(source)
    return {
        "module": cls.__module__, "class": cls.__qualname__, "method": method_name,
        "method_qualname": getattr(method, "__qualname__", method_name),
        "source_file": str(path), "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "method_sha256": hashlib.sha256(method_source.encode("utf-8")).hexdigest(),
    }


def _tensor_meta(value: Any) -> dict:
    result = {"shape": list(value.shape), "dtype": str(value.dtype)}
    if hasattr(value, "stride"):
        result["stride"] = list(value.stride())
    return result


def _leaf_metadata(module: Any) -> dict:
    """Metadata only: never copy parameter values or scales."""
    result = {"runtime_class": _class_name(module)}
    for name in ("prefix", "in_features", "out_features", "full_input_size", "full_output_size"):
        if hasattr(module, name):
            value = getattr(module, name)
            result[name] = value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
    quant = getattr(module, "quant_method", None)
    result["quant_method_class"] = None if quant is None else _class_name(quant)
    for name in ("scheme", "requested", "kernel"):
        if quant is not None and hasattr(quant, name):
            value = getattr(quant, name)
            result[f"quant_{name}"] = None if value is None else (
                _class_name(value) if name == "kernel" else str(value))
        else:
            result[f"quant_{name}"] = "unknown"
    weight = getattr(module, "weight", None)
    if weight is None:
        result["weight"] = "unknown"
    elif hasattr(weight, "shape"):
        result["weight"] = {"shape": list(weight.shape), "dtype": str(weight.dtype),
                            "device": str(getattr(weight, "device", "unknown"))}
    else:
        result["weight"] = "unknown"
    return result


class HCObserver:
    def __init__(self, output_dir: str | Path, *, sink: Callable[[dict], None] = lambda _row: None):
        self.output_dir = Path(output_dir)
        self.sink = sink
        self.identity: dict | None = None
        self.captures: dict[str, tuple[Any, dict]] = {}
        self.errors: list[str] = []
        self.selection: dict | None = None
        self._terminal_seen = False

    def _target(self, batch: Any) -> tuple[dict, list[int]] | None:
        # Decode and unrelated child/later-hit callbacks must be ignored before
        # requesting or validating any coordinates.
        if bool(getattr(batch, "is_decode", False)):
            return None
        reqs = getattr(batch, "reqs", None)
        if not reqs:
            return None
        candidates = [req for req in reqs if getattr(req, "cached_len", None) == TARGET_CACHED]
        if not candidates:
            return None
        if len(reqs) != 1 or len(candidates) != 1:
            raise ValueError("target second layer-major child is not a singleton request")
        req = candidates[0]
        try:
            cached, device, extend = int(req.cached_len), int(req.device_len), int(req.extend_len)
            slot, uid = int(req.linear_slot_idx), str(req.uid)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("target request lacks concrete identity or coordinates") from exc
        if device not in TARGET_DEVICES or extend != device - cached:
            raise ValueError("target second layer-major child has unexpected coordinates")
        if extend not in (3585, 3649):
            raise ValueError("target second layer-major child has unexpected logical M")
        identity = {"uid": uid, "slot": slot, "cached_tokens": cached,
                    "device_tokens": device, "extend_tokens": extend,
                    "positions": list(range(TARGET_START, TARGET_STOP))}
        return identity, list(range(TARGET_COUNT))

    def capture(self, role: str, value: Any, batch: Any, owner: Any, method_name: str,
                *, leaf: Any | None = None) -> None:
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
                raise ValueError("target UID/slot/coordinates drifted between captures")
            if role in self.captures:
                raise ValueError(f"duplicate target capture: {role}")
            if not hasattr(value, "shape") or len(value.shape) < 1:
                raise ValueError(f"{role} is not a token-row tensor")
            if int(value.shape[0]) != identity["extend_tokens"]:
                raise ValueError(f"{role} row count does not equal actual logical M")
            snapshot = value[rows].detach().to("cpu").clone()
            if int(snapshot.shape[0]) != TARGET_COUNT:
                raise ValueError(f"{role} did not retain exactly {TARGET_COUNT} rows")
            meta = {**identity, "role": role, **_tensor_meta(snapshot),
                    "operation": _source_binding(owner, method_name)}
            if leaf is not None:
                meta["leaf_operator"] = _leaf_metadata(leaf)
            self.captures[role] = (snapshot, meta)
            self.sink({"kind": "hc-capture", **meta})
        except Exception as exc:
            self.errors.append(str(exc))

    def finalize(self, uid: Any) -> dict:
        if self._terminal_seen:
            raise ValueError("HC observer received more than one terminal event")
        self._terminal_seen = True
        if self.errors:
            raise ValueError("; ".join(self.errors))
        if self.identity is None:
            raise ValueError("target second layer-major child was never observed")
        if str(uid) != self.identity["uid"]:
            raise ValueError("terminal UID does not bind to captured target")
        missing = [role for role in ROLES if role not in self.captures]
        if missing:
            raise ValueError("missing HC observation: " + ", ".join(missing))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        import torch
        roles = {}
        for role in ROLES:
            tensor, meta = self.captures[role]
            filename = f"hc_{self.identity['uid']}_{role}.pt"
            path = self.output_dir / filename
            try:
                with path.open("xb") as stream:
                    torch.save(tensor, stream)
            except FileExistsError as exc:
                raise ValueError(f"refusing to replace HC snapshot: {filename}") from exc
            roles[role] = {**meta, "file": filename,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        receipt = {"schema": SCHEMA, **self.identity, "selection": self.selection, "roles": roles}
        receipt_path = self.output_dir / f"hc_{self.identity['uid']}_receipt.json"
        try:
            with receipt_path.open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, sort_keys=True, indent=2)
                stream.write("\n")
        except FileExistsError as exc:
            raise ValueError("refusing to replace HC receipt") from exc
        receipt.update(receipt_file=receipt_path.name,
                       receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest())
        self.sink({"kind": "hc-receipt", **receipt})
        return receipt


def _replace_forward(module: Any, wrapper: Callable[..., Any], marker: str) -> None:
    if getattr(module, marker, False):
        raise ValueError(f"observer already installed on {_class_name(module)}")
    original = module.forward
    def wrapped(this: Any, *args: Any, **kwargs: Any) -> Any:
        return wrapper(original, *args, **kwargs)
    module.forward = types.MethodType(wrapped, module)
    setattr(module, marker, True)


def _replace_method(owner: Any, name: str, wrapper: Callable[..., Any], marker: str) -> None:
    if getattr(owner, marker, False):
        raise ValueError(f"observer already installed on {_class_name(owner)}.{name}")
    original = getattr(owner, name)
    if not inspect.ismethod(original):
        raise ValueError(f"expected bound method {_class_name(owner)}.{name}")
    def wrapped(this: Any, *args: Any, **kwargs: Any) -> Any:
        return wrapper(original, *args, **kwargs)
    setattr(owner, name, types.MethodType(wrapped, owner))
    setattr(owner, marker, True)


def install(model: Any, get_batch: Callable[[], Any], *, output_dir: str | Path,
            sink: Callable[[dict], None] = lambda _row: None,
            parsed_ple_layer_ids: tuple[int, ...] | None = None) -> HCObserver:
    """Install exactly-once observation wrappers on decoder 0 and validate PLE decoder 1."""
    try:
        layers = model.layers.op_list
        gdn_owner, ple_owner = layers[0], layers[1]
        hc, gdn, embedding = gdn_owner.attn_hyper_connection, gdn_owner.linear_attn, model.embed_tokens
        ple = ple_owner.ple
        qkv = gdn.in_proj_qkvz if getattr(gdn, "_split_in_proj", False) else gdn.in_proj
        down = getattr(hc, "input_mix_weight_down", None)
        if down is None:
            down = hc.input_mix_weight_down_block_inject
        up = hc.input_mix_weight_up
    except (AttributeError, IndexError) as exc:
        raise ValueError("unexpected Qwen4Exp first-GDN hyper-connection structure") from exc
    config_ids = tuple(parsed_ple_layer_ids if parsed_ple_layer_ids is not None
                       else getattr(model._config.qwen4_args, "ple_layer_ids"))
    ple_owners = [index for index, layer in enumerate(layers) if getattr(layer, "ple", None) is not None]
    if (not getattr(gdn_owner, "_is_linear", False) or int(gdn_owner._layer_id) != 0
            or not getattr(ple_owner, "_is_linear", False) or ple is None
            or int(ple_owner._layer_id) != 1 or int(ple.layer_id) != 1
            or ple_owners != [1] or config_ids != (1,)):
        raise ValueError("expected GDN decoder 0 and uniquely mapped PLE decoder 1")
    observer = HCObserver(output_dir, sink=sink)
    observer.selection = {
        "gdn": {"decoder_index": 0, "decoder_layer_id": 0, "class": _class_name(gdn_owner)},
        "ple": {"decoder_index": 1, "decoder_layer_id": 1, "ple_layer_id": 1,
                "class": _class_name(ple_owner)},
        "parsed_ple_layer_ids": list(config_ids),
    }
    def batch() -> Any:
        active = get_batch()
        if active is None:
            raise ValueError("observer has no active batch")
        return active
    _replace_forward(embedding, lambda original, ids, *a, **kw: _after(
        observer, "embedding_output", original(ids, *a, **kw), batch(), embedding, "forward"),
        "_t17_hc_embedding")
    def mix_wrapper(original: Callable[..., Any], hidden: Any, *a: Any, **kw: Any) -> Any:
        active = batch(); observer.capture("hc_mix_input", hidden, active, hc, "mix")
        result = original(hidden, *a, **kw)
        if not isinstance(result, tuple) or not result:
            observer.errors.append("HC mix did not return its expected tuple")
        else:
            observer.capture("hc_mix_output", result[0], active, hc, "mix")
        return result
    _replace_method(hc, "mix", mix_wrapper, "_t17_hc_mix")
    def down_wrapper(original: Callable[..., Any], rn: Any, *a: Any, **kw: Any) -> Any:
        observer.capture("hc_down_input", rn, batch(), hc, "_down")
        return original(rn, *a, **kw)
    _replace_method(hc, "_down", down_wrapper, "_t17_hc_down")
    _replace_forward(down, lambda original, value, *a, **kw: _after(
        observer, "hc_down_output", original(value, *a, **kw), batch(), down, "forward", leaf=down),
        "_t17_hc_down_leaf")
    def up_wrapper(original: Callable[..., Any], value: Any, *a: Any, **kw: Any) -> Any:
        active = batch(); observer.capture("hc_up_input", value, active, up, "forward", leaf=up)
        result = original(value, *a, **kw)
        observer.capture("hc_up_output", result, active, up, "forward", leaf=up)
        return result
    _replace_forward(up, up_wrapper, "_t17_hc_up_leaf")
    def qkv_wrapper(original: Callable[..., Any], value: Any, *a: Any, **kw: Any) -> Any:
        active = batch(); observer.capture("gdn_qkv_input", value, active, qkv, "forward", leaf=qkv)
        result = original(value, *a, **kw)
        observer.capture("gdn_qkv_output", result, active, qkv, "forward", leaf=qkv)
        return result
    _replace_forward(qkv, qkv_wrapper, "_t17_hc_gdn_qkv")
    return observer


def _after(observer: HCObserver, role: str, result: Any, batch: Any, owner: Any,
           method: str, *, leaf: Any | None = None) -> Any:
    observer.capture(role, result, batch, owner, method, leaf=leaf)
    return result
