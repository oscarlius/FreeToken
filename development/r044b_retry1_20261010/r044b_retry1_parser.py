"""R044b retry1 strict ServerArgs identity adapter.

The predecessor B1 raw log contains the server canonical max_extend_tokens
field. The frozen command vocabulary calls the same setting
max_prefill_length. This adapter preserves the raw parsed map, adds the alias
only to the comparison map, and refuses a missing or contradictory alias.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

PREDECESSOR_RID = "E2-R044b-20261010"
RETRY1_RID = "E2-R044b-retry1-20261010"
RAW_REQUIRED = {
    "model_path", "server_port", "prefill_layer_major", "max_extend_tokens",
    "mamba_host_slots", "enable_cache_report", "special_token_ckpt", "_unique_suffix",
}
STRICT_REQUIRED = RAW_REQUIRED | {"max_prefill_length"}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load_parser(path: Path):
    spec = importlib.util.spec_from_file_location("r044b_retry1_raw_serverargs", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load raw ServerArgs parser: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse

def normalize_alias(raw: dict[str, str]) -> dict[str, str]:
    missing = RAW_REQUIRED - set(raw)
    if missing:
        raise ValueError("actual serve.log lacks required raw ServerArgs: " + ",".join(sorted(missing)))
    normalized = dict(raw)
    raw_extend = raw["max_extend_tokens"]
    raw_prefill = raw.get("max_prefill_length")
    if raw_prefill is not None and raw_prefill != raw_extend:
        raise ValueError("actual serve.log prefill/extend alias differs")
    normalized["max_prefill_length"] = raw_extend
    if STRICT_REQUIRED - set(normalized):
        raise ValueError("normalized strict ServerArgs incomplete")
    return normalized

def serve_identity(serve_log: Path, owned_process: Path, layer_major: bool, parser_path: Path) -> dict[str, Any]:
    raw = load_parser(parser_path)(serve_log)
    normalized = normalize_alias(raw)
    owned = json.loads(owned_process.read_text(encoding="utf-8"))
    if str(raw["server_port"]) != str(owned["port"]):
        raise ValueError("actual serve.log port differs from owned process")
    if str(raw["prefill_layer_major"]) != str(layer_major):
        raise ValueError("actual serve.log layer-major differs from declared service")
    try:
        suffix = ast.literal_eval(raw["_unique_suffix"])
    except (SyntaxError, ValueError) as exc:
        raise ValueError("actual serve.log PID suffix is not a ServerArgs string literal") from exc
    if suffix != ".pid=" + str(owned["pid"]):
        raise ValueError("actual serve.log PID suffix differs from owned process")
    normalized["server_port"] = "<dynamic-port>"
    normalized["_unique_suffix"] = "<dynamic-pid>"
    return {
        "raw_parsed": raw, "normalized": normalized, "serve_log_sha256": sha256(serve_log),
        "owned_process": owned,
        "alias": {"normalized_key": "max_prefill_length", "raw_key": "max_extend_tokens", "value": raw_extend(raw)},
    }

def raw_extend(raw: dict[str, str]) -> str:
    return raw["max_extend_tokens"]


