"""CPU-only R067e retry2 packet for the Engine donor-hash domain.

This tool never starts a process, contacts HTTP, imports the candidate runtime,
or writes a source packet.  It reads archived hot state dumps on CPU and emits
a new, unapproved plan whose cold expected hash uses the exact Engine labels.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
RID = "E2-R067e-20261010-retry2"
ENGINE_SHA256 = "0675eae434f3e17f12b33c1a56ec42e8fb308b6cd9c827fda044978ef3405e21"
PARENT_PACKET = PARENT / "R067E_ROOT_PACKET.json"
HOT_RUN = Path("/data2/FreeToken/runs/dev_R067/E2-R067d-d20-short-tail-retry1/services")
STATE_NAMES = ("conv_states", "recurrent_states", "ple_conv", "ple_ngram_ctx")
ENGINE_NAMES = ("conv_states", "recurrent_states", "slot_states/ple_conv", "slot_states/ple_ngram_ctx")


def _load(directory: Path, name: str, prefix: str = "donate_0001_dev_"):
    import torch
    value = torch.load(directory / f"{prefix}{name}.pt", map_location="cpu", weights_only=False)
    if not isinstance(value, torch.Tensor):
        raise TypeError(f"{name} is not a Tensor")
    return value.detach().contiguous()


def _digest(directory: Path, labels: tuple[str, ...], prefix: str = "donate_0001_dev_") -> str:
    digest = hashlib.sha256()
    for name, label in zip(STATE_NAMES, labels, strict=True):
        state = _load(directory, name, prefix)
        digest.update(label.encode("utf-8") + b"\0")
        digest.update(str(tuple(state.shape)).encode("ascii") + b"\0")
        digest.update(str(state.dtype).encode("ascii") + b"\0")
        digest.update(state.view(__import__("torch").uint8).numpy().tobytes())
    return digest.hexdigest()


def plain_hash(directory: Path) -> str:
    """The legacy packet domain; retained only to prove it differs."""
    return _digest(directory, STATE_NAMES)


def engine_canonical_hash(directory: Path) -> str:
    """Byte-for-byte label/order contract of Engine._verify_dev_cold_donor_guard."""
    return _digest(directory, ENGINE_NAMES)


def component_raw_hashes(directory: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in STATE_NAMES:
        state = _load(directory, name)
        raw = state.view(__import__("torch").uint8).numpy().tobytes()
        out[name] = {"shape": list(state.shape), "dtype": str(state.dtype), "raw_sha256": hashlib.sha256(raw).hexdigest()}
    return out


def build_unapproved_packet(parent_packet: Path = PARENT_PACKET, hot_run: Path = HOT_RUN) -> dict[str, Any]:
    parent = json.loads(parent_packet.read_text(encoding="utf-8"))
    services = copy.deepcopy(parent["services"])
    donor: dict[str, Any] = {}
    for boundary in (8192, 8256):
        dump = hot_run / f"hot_p{boundary}" / "state_dump"
        plain, canonical = plain_hash(dump), engine_canonical_hash(dump)
        donor[str(boundary)] = {
            "hot_dump": str(dump), "plain_hash": plain, "engine_canonical_hash": canonical,
            "components": component_raw_hashes(dump),
        }
    for service in services:
        if service["kind"] != "cold":
            continue
        boundary = str(int(service["name"].split("_p", 1)[1].split("_", 1)[0]))
        service["env"]["FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256"] = donor[boundary]["engine_canonical_hash"]
        service["env"]["FT_DEV_COLD_DONOR_HASH_DOMAIN"] = "engine-v1/conv,recurrent,slot_states-sorted/shape,dtype,rawbytes"
    if len(services) != 10 or sum(len(x.get("requests", [x.get("request")])) for x in services) != 14:
        raise RuntimeError("parent plan no longer has the frozen 10-service/14-call scope")
    return {
        "schema": "ft_r067e_retry2_hash_domain_cpu_packet/v1",
        "rid": RID,
        "status": "CPU_READY_PENDING_NONAUTHOR_REVIEW_AND_GPU_ADMISSION",
        "parent_packet": {"path": str(parent_packet), "sha256": hashlib.sha256(parent_packet.read_bytes()).hexdigest()},
        "engine_contract": {"source_sha256": ENGINE_SHA256, "names": list(ENGINE_NAMES), "algorithm": "SHA256(label\\0, shape\\0, dtype\\0, rawbytes) in listed order"},
        "donor": donor,
        "budget": {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1},
        "services": services,
        "stop_rules": ["any donor hash mismatch is failed_harness before rewind/tail/output", "first valid product not_met stops remaining arms"],
        "pre_guard_observation": {"implemented": False, "reason": "external tooling cannot read the live cold pool before Engine raises", "future_requirement": "a separately reviewed candidate Engine hook must emit the exact canonical digest before the guard comparison"},
        "limits": ["no runtime source change in this packet", "no D12 action", "no GPU authorization"],
    }


def main() -> None:
    print(json.dumps(build_unapproved_packet(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
