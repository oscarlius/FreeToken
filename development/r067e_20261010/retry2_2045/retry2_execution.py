"""Inert, task-owned execution packet for the approved R067e final retry.

This module changes no candidate source.  It derives the 10-service/14-call
plan from the sealed parent packet, swaps only the expected donor hash to the
Engine's canonical label domain, and binds a task-owned pre-guard observer.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
RID = "E2-R067e-20261010-retry2"
PARENT_PACKET = PARENT / "R067E_ROOT_PACKET.json"
NATIVE_PROOF = PARENT / "NATIVE_ABI_CPU_PROOF.json"
STATE_FILES = ("conv_states", "recurrent_states", "ple_conv", "ple_ngram_ctx")
ENGINE_LABELS = ("conv_states", "recurrent_states", "slot_states/ple_conv", "slot_states/ple_ngram_ctx")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def engine_donor_hash(directory: Path) -> str:
    """Exact Engine._verify_dev_cold_donor_guard labels/order on CPU bytes."""
    import torch
    digest = hashlib.sha256()
    for filename, label in zip(STATE_FILES, ENGINE_LABELS, strict=True):
        tensor = torch.load(directory / f"donate_0001_dev_{filename}.pt", map_location="cpu", weights_only=False)
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f"{filename} is not a Tensor")
        value = tensor.detach().contiguous()
        digest.update(label.encode("utf-8") + b"\0")
        digest.update(str(tuple(value.shape)).encode("ascii") + b"\0")
        digest.update(str(value.dtype).encode("ascii") + b"\0")
        digest.update(value.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def source_manifest() -> dict[str, str]:
    names = ("retry2_execution.py", "retry2_effects.py", "retry2_runner.py", "retry2_startup.py")
    parent_names = ("r067e_actual.py", "r067e_owned.py", "r067e_runner.py", "r067e_packet.py", "r067e_startup.py")
    result = {f"task_owned/{name}": sha(HERE / name) for name in names}
    result.update({f"parent/{name}": sha(PARENT / name) for name in parent_names})
    result["parent/NATIVE_ABI_CPU_PROOF.json"] = sha(NATIVE_PROOF)
    return result


def _cold_boundary(name: str) -> int:
    return int(name.split("_p", 1)[1].split("_", 1)[0])


def build_plan(parent_packet: Path = PARENT_PACKET, hot_root: Path | None = None) -> dict[str, Any]:
    """Derive an inert launch plan; this function has no process/API/GPU effects."""
    parent = json.loads(parent_packet.read_text(encoding="utf-8"))
    if len(parent["services"]) != 10 or parent["budget"] != {"services": 10, "generation_calls": 14}:
        raise RuntimeError("parent scope differs from the approved 10-service/14-call budget")
    hot_root = hot_root or Path("/data2/FreeToken/runs/dev_R067/E2-R067d-d20-short-tail-retry1/services")
    donors = {str(prefix): engine_donor_hash(hot_root / f"hot_p{prefix}" / "state_dump") for prefix in (8192, 8256)}
    services = copy.deepcopy(parent["services"])
    adapter_sha = sha(HERE / "retry2_startup.py")
    for service in services:
        # Every spawned service imports the task-owned startup wrapper; only
        # cold services additionally activate its pre-guard receipt path.
        service["env"]["FT_DEV_R067E_STARTUP_SHA256"] = adapter_sha
        if service["kind"] != "cold":
            continue
        boundary = str(_cold_boundary(service["name"]))
        arm = Path(service["service_dir"])
        service["env"].update({
            "FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256": donors[boundary],
            "FT_DEV_COLD_DONOR_HASH_DOMAIN": "engine-v1/conv,recurrent,slot_states-sorted/shape,dtype,rawbytes",
            "FT_DEV_COLD_DONOR_PRE_GUARD_RECEIPT": str(arm / "cold_preguard_engine_hash.json"),
            "FT_DEV_R067E_RETRY2_ADAPTER_SHA256": adapter_sha,
        })
    return {
        "schema": "ft_r067e_retry2_execution_packet/v1",
        "rid": RID,
        "status": "INERT_CPU_READY_PENDING_INDEPENDENT_REVIEW_AND_ROOT_GPU_ADMISSION",
        "parent_packet": {"path": str(parent_packet), "sha256": sha(parent_packet)},
        "native_proof": {"path": str(NATIVE_PROOF), "sha256": sha(NATIVE_PROOF)},
        "source_manifest": source_manifest(),
        "engine_hash_domain": {"labels": list(ENGINE_LABELS), "algorithm": "SHA256(label\\0,shape\\0,dtype\\0,rawbytes)"},
        "donor_at_p": donors,
        "input_binding": copy.deepcopy(parent["input_binding"]),
        "worktree": parent["commit"] and parent["services"][0]["worktree"],
        "commit": parent["commit"],
        "engine_sha256": parent["engine_sha256"],
        "budget": {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1},
        "services": services,
        "required_effect_sequence": "materialize -> start -> readiness -> exact-ID request -> evidence -> cleanup",
        "stop_rules": ["cold pre-guard receipt mismatch fails_harness before Engine guard/replay/tail/output", "first valid product not_met stops remaining arms"],
        "side_effects": {"packet_build": "CPU/file read only", "gpu": False, "service": False, "http": False, "candidate_source_modified": False},
    }


def filedry(parent_packet: Path = PARENT_PACKET, hot_root: Path | None = None) -> dict[str, Any]:
    """CPU/file-dry validation used before root creates a launch receipt."""
    plan = build_plan(parent_packet, hot_root)
    binding = Path(plan["input_binding"]["path"])
    if binding.is_symlink() or not binding.is_file() or sha(binding) != plan["input_binding"]["sha256"]:
        raise RuntimeError("exact-ID input binding differs")
    for service in plan["services"]:
        if service["kind"] == "cold":
            env = service["env"]
            if not env.get("FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256") or not env.get("FT_DEV_COLD_DONOR_PRE_GUARD_RECEIPT"):
                raise RuntimeError("cold service lacks canonical pre-guard binding")
    return plan
