"""Prepare, validate, and describe a future HC GEMM replay; never launch it here."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any


POSITIONS = list(range(4608, 4672))
M_BY_ARM = {"warm": 3585, "cold": 3649}
ROLES = {"down": ("hc_down_input", "hc_down_output"), "up": ("hc_up_input", "hc_up_output"),
         "gdn": ("gdn_qkv_input", "gdn_qkv_output")}
RAW_PREFIX = "model.language_model.layers.0.attn_hyper_connection."
GDN_PREFIX = "model.language_model.layers.0.linear_attn."
OVERLAY = Path('/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay')
BASE = Path('/data2/model/Qwen3.8-Flash-Next-NVFP4')
SPECS = {
    "down": (RAW_PREFIX, {"hc_norm.weight": ("BF16", [10240]), "input_mix_weight_down.weight": ("BF16", [320, 10240]),
                            "block_inject_weight.weight": ("BF16", [4, 10240]), "input_mix_weight_up.weight": ("BF16", [10240, 320])}),
    "up": (RAW_PREFIX, {"hc_norm.weight": ("BF16", [10240]), "input_mix_weight_down.weight": ("BF16", [320, 10240]),
                          "block_inject_weight.weight": ("BF16", [4, 10240]), "input_mix_weight_up.weight": ("BF16", [10240, 320])}),
    "gdn": (GDN_PREFIX, {"in_proj_qkv.weight": ("BF16", [10240, 2560]), "in_proj_z.weight": ("BF16", [6144, 2560]),
                           "in_proj_b.weight": ("BF16", [48, 2560]), "in_proj_a.weight": ("BF16", [48, 2560])}),
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 << 20):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file(): raise ValueError(f"{label} must be a regular file")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict): raise ValueError(f"{label} must be a JSON object")
    return value


def under(root: Path, path: Path) -> bool:
    return not path.is_symlink() and root.resolve() in path.resolve().parents


def _header(path: Path) -> dict:
    if path.is_symlink() or not path.is_file(): raise ValueError("checkpoint shard must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(8)
        if len(raw) != 8: raise ValueError("invalid safetensors header length")
        size = struct.unpack("<Q", raw)[0]
        if size > 128 << 20: raise ValueError("unreasonable safetensors header")
        raw = stream.read(size)
        return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _resolved_declared(declared: Path, expected_target: Path | None, label: str) -> Path:
    resolved = declared.resolve(strict=True)
    if declared.is_symlink() and (expected_target is None or resolved != expected_target):
        raise ValueError(f"{label} symlink target differs")
    if resolved.is_symlink() or not resolved.is_file(): raise ValueError(f"{label} resolved target must be regular")
    return resolved


def checkpoint_metadata(checkpoint_root: Path, *, operator: str = "down", expected_config_sha: str, expected_index_sha: str,
                        expected_shard_sha: str, expected_header_sha: str) -> dict:
    """Read only the declared index and one header, never a tensor payload."""
    declared_root = checkpoint_root
    root = checkpoint_root.resolve(strict=True)
    declared_config, declared_index = root / "config.json", root / "model.safetensors.index.json"
    overlay = root == OVERLAY
    config = _resolved_declared(declared_config, BASE / 'config.json.qwen4_exp.orig' if overlay else None, 'checkpoint config')
    index = _resolved_declared(declared_index, BASE / 'model.safetensors.index.json' if overlay else None, 'checkpoint index')
    if sha(config) != expected_config_sha or sha(index) != expected_index_sha: raise ValueError("checkpoint config/index binding differs")
    weight_map = load_json(index, "checkpoint index").get("weight_map")
    if not isinstance(weight_map, dict): raise ValueError("checkpoint index has no weight_map")
    if operator not in SPECS: raise ValueError("operator must be down, up, or gdn")
    prefix, expected = SPECS[operator]
    names = {name: weight_map.get(prefix + name) for name in expected}
    if any(not isinstance(value, str) for value in names.values()): raise ValueError("decoder-0 HC checkpoint key missing")
    if len(set(names.values())) != 1: raise ValueError("bounded replay requires one declared HC shard")
    declared_shard = root / next(iter(names.values())); shard = declared_shard.resolve(strict=True)
    if declared_shard.is_symlink() and shard.parent != BASE:
        raise ValueError("overlay shard symlink target differs")
    if shard.is_symlink() or not shard.is_file() or sha(shard) != expected_shard_sha:
        raise ValueError("checkpoint shard binding differs")
    header, digest = _header(shard)
    if digest != expected_header_sha: raise ValueError("raw checkpoint header binding differs")
    selected = {short: header[prefix + short] for short in names}
    for name, (dtype, shape) in expected.items():
        if selected[name].get("dtype") != dtype or selected[name].get("shape") != shape:
            raise ValueError("unexpected decoder-0 HC tensor metadata: " + name)
    return {"declared_root": str(declared_root), "root": str(root), "declared_config": str(declared_config), "config": str(config),
            "declared_index": str(declared_index), "index": str(index), "config_sha256": expected_config_sha, "index_sha256": expected_index_sha,
            "declared_shard": str(declared_shard), "shard": str(shard), "shard_sha256": expected_shard_sha, "header_sha256": expected_header_sha,
            "shard_integrity_read": "full-file SHA256; no tensor payload decoded during metadata validation",
            "operator": operator, "raw_prefix": prefix,
            "tensors": {name: {key: selected[name][key] for key in ("dtype", "shape", "data_offsets")} for name in selected},
            "merged_down": {"raw_parts": ["input_mix_weight_down.weight", "block_inject_weight.weight"],
                            "zero_pad_rows": 12, "shape": [336, 10240]} if operator == "down" else None}


def _validate_leaf(role: dict) -> None:
    leaf = role.get("leaf_operator")
    if not isinstance(leaf, dict): raise ValueError("HC receipt omits leaf operator metadata")
    if leaf.get("quant_method_class", "").split(".")[-1] != "UnquantizedLinearMethod":
        raise ValueError("HC replay requires observed UnquantizedLinearMethod")
    kernel = leaf.get("quant_kernel")
    if kernel != "TorchLinearKernel" and (not isinstance(kernel, str) or not kernel.endswith(".TorchLinearKernel")):
        raise ValueError("HC replay requires observed TorchLinearKernel")
    if leaf.get("quant_requested") != "auto": raise ValueError("HC replay requires the observed auto kernel request")
    weight = leaf.get("weight")
    if not isinstance(weight, dict) or weight.get("dtype") != "torch.bfloat16" or weight.get("device") != "cuda:0":
        raise ValueError("HC replay requires observed BF16 CUDA leaf weight")


def observation(arm: Path, uid: int | str, arm_name: str, operator: str) -> dict:
    """Validate a real terminal HC receipt, without loading its tensors yet."""
    if operator not in ROLES or arm_name not in M_BY_ARM: raise ValueError("explicit operator/arm required")
    root = arm / "hc"; final = load_json(root / ("final_" + str(uid) + ".json"), "HC final")
    if final.get("valid") is not True or str(final.get("uid")) != str(uid): raise ValueError("HC terminal receipt is invalid")
    receipt_path = root / final.get("receipt_file", "")
    if not under(root, receipt_path) or sha(receipt_path) != final.get("receipt_sha256"): raise ValueError("HC receipt hash/path differs")
    record = load_json(receipt_path, "HC receipt")
    expected_m = M_BY_ARM[arm_name]
    if (record.get("schema") != "t17_hc_observe/v1" or str(record.get("uid")) != str(uid)
            or record.get("cached_tokens") != 4608 or record.get("extend_tokens") != expected_m
            or record.get("device_tokens") != 4608 + expected_m or record.get("positions") != POSITIONS):
        raise ValueError("HC receipt coordinates differ")
    input_role, output_role = ROLES[operator]; roles = record.get("roles")
    if not isinstance(roles, dict) or not all(name in roles for name in (input_role, output_role)):
        raise ValueError("selected HC roles missing")
    selected = {}
    for name in (input_role, output_role):
        role = roles[name]
        if any(role.get(key) != record.get(key) for key in ("uid", "slot", "cached_tokens", "device_tokens", "extend_tokens", "positions")):
            raise ValueError("HC role identity differs: " + name)
        path = root / role.get("file", "")
        if not under(root, path) or sha(path) != role.get("sha256"): raise ValueError("HC tensor hash/path differs: " + name)
        if role.get("shape", [None])[0] != 64 or not role.get("dtype") or not role.get("stride"):
            raise ValueError("HC tensor metadata is incomplete: " + name)
        if name.endswith("output"): _validate_leaf(role)
        selected[name] = {"file": str(path), "sha256": role["sha256"], "shape": role["shape"], "dtype": role["dtype"], "stride": role["stride"], "operation": role.get("operation"), "leaf_operator": role.get("leaf_operator")}
    return {"arm": arm_name, "uid": str(uid), "receipt_sha256": sha(receipt_path), "coordinates": {key: record[key] for key in ("slot", "cached_tokens", "device_tokens", "extend_tokens", "positions")}, "roles": selected}


def verify_torch_linear_source(path: Path, expected_sha: str) -> dict:
    if path.is_symlink() or not path.is_file() or sha(path) != expected_sha: raise ValueError("TorchLinearKernel source binding differs")
    text = path.read_text(encoding="utf-8")
    required = ("class TorchLinearKernel", "class UnquantizedLinearMethod", "return F.linear(x, w, b)")
    if not all(fragment in text for fragment in required): raise ValueError("source does not prove the declared F.linear path")
    return {"path": str(path), "sha256": expected_sha, "kernel": "TorchLinearKernel", "operation": "F.linear(x, w, b)"}


def plan(operator: str, warm: dict, cold: dict, checkpoint: dict, kernel: dict, *, include_m4096: bool = False,
         include_m1_oracle: bool = False) -> dict:
    if operator not in ROLES: raise ValueError("operator must be down, up, or gdn")
    if warm["arm"] != "warm" or cold["arm"] != "cold": raise ValueError("warm/cold observation binding differs")
    input_role, output_role = ROLES[operator]
    return {"schema": "ft_t17_hc_gemm_replay_plan/v1", "diagnostic_only": True, "operator": operator,
            "input_role": input_role, "output_role": output_role, "positions": POSITIONS,
            "arms": {"warm": warm, "cold": cold}, "checkpoint": checkpoint, "kernel": kernel,
            "runs": [{"name": "warm_full_m", "M": 3585, "artificial_rows": 3521},
                     {"name": "cold_full_m", "M": 3649, "artificial_rows": 3585}]
                    + ([{"name": "matched_m_4096", "M": 4096, "artificial_rows": 4032}] if include_m4096 else [])
                    + ([{"name": "m1_oracle", "M": 1, "artificial_rows": 0}] if include_m1_oracle else []),
            "limitations": ["Only the selected 64 real rows are supplied; remaining full-M rows are artificial zeros.",
                            "Checkpoint index/header binding does not establish a checksum of loaded runtime weights.",
                            "Replay is diagnostic only and cannot select a fix or relax T17."]}


def write_plan(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream: json.dump(value, stream, sort_keys=True, indent=2); stream.write("\n")


def validate_external_ownership(proof: dict, *, rid: str) -> dict:
    """Root driver gate: this module never acquires or releases the GPU lock."""
    required = ("rid", "pid", "start_ticks", "lock_owner", "lock_token", "global_lock_path", "lock_inode")
    if not isinstance(proof, dict) or any(not proof.get(key) for key in required):
        raise ValueError("external replay ownership proof is incomplete")
    if proof["rid"] != rid or proof["lock_owner"] != rid:
        raise ValueError("external replay RID/lock ownership differs")
    if not isinstance(proof["pid"], int) or not isinstance(proof["start_ticks"], int):
        raise ValueError("external replay PID/birth proof differs")
    return {key: proof[key] for key in required}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator", choices=sorted(ROLES), required=True); parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.run:
        raise RuntimeError("GPU replay execution is delegated to the externally owned launcher/lock/RID; this tool prepares only")
    print(json.dumps({"schema": "ft_t17_hc_gemm_replay_prepare/v1", "operator": args.operator, "gpu_started": False}))


if __name__ == "__main__": main()
