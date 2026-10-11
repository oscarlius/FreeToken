"""CPU-only packet builder for the final R067d retry.

This tooling derives the cold schedule from recorded hot observations.  It
never starts a service, opens HTTP, acquires a GPU lock, or loads model weights.
The later root-only runner must invoke ``boundary_gate`` immediately after the
cold donor dump and before it may execute the rewind/resume segment or emit a
token.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RETRY1 = HERE.parent / "r067d_short_tail_retry1_20261010"
RID = "E2-R067d-d20-short-tail-retry2"
REMOTE_DEV = f"/data2/FreeToken/development/{HERE.name}"
REMOTE_RUN = f"/data2/FreeToken/runs/dev_R067/{RID}"
HOT_RUN = "/data2/FreeToken/runs/dev_R067/E2-R067d-d20-short-tail-retry1/services"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def observations(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def observed_seed_schedule(rows: list[dict[str, Any]], prefix: int) -> list[dict[str, Any]]:
    """Extract the actual hot seed geometry; never infer a generic 4096 grid."""
    prefill = [row for row in rows if row.get("kind") == "prefill" and row.get("uid") == "0"]
    children = [row for row in rows if row.get("kind") == "layer-children" and row.get("uid") == "0"]
    assert len(prefill) >= 2 and len(children) == 1, "hot observation lacks seed or children"
    first, second = prefill[:2]
    assert first == {
        "cached_tokens": 0, "device_length": 512, "extend_tokens": 512,
        "first_child": {"cached_tokens": 0, "device_tokens": 512,
                        "fresh_state_indices": [12], "has_initial_state": False},
        "kind": "prefill", "layer_major": False, "reason": "anchor_cap", "uid": "0",
    }, "hot first seed segment drifted"
    assert second["cached_tokens"] == 512 and second["device_length"] == prefix + 1
    assert second["extend_tokens"] == prefix + 1 - 512 and second["layer_major"] is True
    actual = children[0]
    assert actual["outer_cached_tokens"] == 512
    child_pairs = [(x["cached_tokens"], x["device_tokens"]) for x in actual["children"]]
    assert child_pairs[0][0] == 512 and child_pairs[-1][1] == prefix + 1
    subchunks = [end - start for start, end in child_pairs]
    assert all(length > 0 for length in subchunks)
    return [
        {"start": 0, "end": 512, "mode": "ordinary", "subchunks": [512]},
        {"start": 512, "end": prefix + 1, "mode": "layer_major", "subchunks": subchunks},
        {"start": prefix, "end": prefix + 1, "mode": "ordinary", "subchunks": [1]},
    ]


def parse_schedule(schedule: list[dict[str, Any]]) -> None:
    previous = None
    for row in schedule:
        assert set(row) == {"start", "end", "mode", "subchunks"}
        assert row["mode"] in {"ordinary", "layer_major"}
        assert row["start"] >= 0 and row["end"] > row["start"]
        assert sum(row["subchunks"]) == row["end"] - row["start"]
        assert row["mode"] != "ordinary" or len(row["subchunks"]) == 1
        if previous is not None:
            assert row["start"] in {previous, previous - 1}
        previous = row["end"]


def state_tensor_hash(path: Path) -> str:
    """CPU-only bitwise hash; loading tensors via map_location='cpu' is explicit."""
    import torch
    value = torch.load(path, map_location="cpu", weights_only=False)
    assert isinstance(value, torch.Tensor)
    return sha_bytes(value.detach().contiguous().view(torch.uint8).numpy().tobytes())


def state_bundle_hash(directory: Path, *, prefix: str = "donate_0001_dev_") -> str:
    """Canonical logical donor hash over conv, GDN recurrent, and declared PLE slot states."""
    import torch
    digest = hashlib.sha256()
    names = ("conv_states", "recurrent_states", "ple_conv", "ple_ngram_ctx")
    for name in names:
        value = torch.load(directory / f"{prefix}{name}.pt", map_location="cpu", weights_only=False)
        assert isinstance(value, torch.Tensor), name
        state = value.detach().contiguous()
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(str(tuple(state.shape)).encode("ascii") + b"\0")
        digest.update(str(state.dtype).encode("ascii") + b"\0")
        digest.update(state.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def boundary_gate(hot_dump: Path, cold_dump: Path) -> dict[str, Any]:
    """Fail closed before resume/output when donor state differs at P."""
    hot, cold = state_tensor_hash(hot_dump), state_tensor_hash(cold_dump)
    result = {
        "schema": "ft_r067d_retry2_boundary_gate/v1",
        "hot_dump": str(hot_dump), "cold_dump": str(cold_dump),
        "hot_tensor_sha256": hot, "cold_tensor_sha256": cold,
        "equal": hot == cold,
        "verdict": "PASS" if hot == cold else "failed_harness",
        "resume_or_output_permitted": hot == cold,
    }
    if hot != cold:
        raise AssertionError(json.dumps(result, sort_keys=True))
    return result


def replay_prior_confounded_boundary(hot_dump: Path, cold_dump: Path) -> dict[str, Any]:
    """Preserve retry1's not_met record while recording why it cannot judge C3."""
    hot, cold = state_tensor_hash(hot_dump), state_tensor_hash(cold_dump)
    assert hot != cold, "retry1 replay no longer demonstrates the recorded confound"
    return {
        "prior_terminal_verdict": "not_met",
        "preserved_interpretation": "reference_confounded_before_tail",
        "hot_tensor_sha256": hot, "cold_tensor_sha256": cold,
        "equal": False,
    }


def render_packet(hot_observation_files: dict[int, Path], hot_dump_files: dict[int, Path]) -> dict[str, Any]:
    base = json.loads((RETRY1 / "R067D_RETRY1_CONFIG_CPU_ONLY.json").read_text())
    assert len(base["services"]) == 10 and base["budget"] == {"services": 10, "generation_calls": 14}
    schedules: dict[str, Any] = {}
    for prefix in (8192, 8256):
        source = hot_observation_files[prefix]
        assert source.is_file(), source
        schedule = observed_seed_schedule(observations(source), prefix)
        parse_schedule(schedule)
        key = f"p{prefix}"
        schedules[key] = {
            "source_observations": str(source), "source_observations_sha256": sha_file(source),
            "schedule": schedule, "schedule_sha256": sha_bytes(json.dumps(schedule, separators=(",", ":")).encode()),
            "hot_donor_dump": str(hot_dump_files[prefix]), "hot_donor_file_sha256": sha_file(hot_dump_files[prefix]),
        }
    return {
        "schema": "ft_r067d_retry2_cpu_packet/v1", "rid": RID,
        "scope": {"services": 10, "generation_calls": 14, "new_reference_fix": "cold schedule is derived from recorded hot seed observations"},
        "base_retry1_config_sha256": sha_file(RETRY1 / "R067D_RETRY1_CONFIG_CPU_ONLY.json"),
        "constraints": {"cache_type": "hybrid_radix", "mamba_host_slots": 0, "forbid_naive": True,
                        "no_gpu": True, "no_http": True, "no_model_init": True},
        "schedules": schedules,
        "runtime_gate": {"phase": "after cold donor state dump at P and before rewind/resume/output",
                         "function": "boundary_gate", "on_mismatch": "failed_harness_stop_no_output"},
        "root_only_execution": {"start_argv_source": "base retry1 config; root must render a fresh RID-specific argv",
                                "service_call_budget": "10 services / 14 generation calls", "estimated_duration": "root to estimate after load preflight",
                                "mutable_paths": [REMOTE_DEV, REMOTE_RUN], "gpu_admission": False},
    }


def write_packet(destination: Path, hot_observation_files: dict[int, Path], hot_dump_files: dict[int, Path]) -> dict[str, Any]:
    packet = render_packet(hot_observation_files, hot_dump_files)
    assert not destination.exists(), destination
    destination.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet


def main() -> None:
    """Make exactly one CPU/FILEdry receipt from immutable retry1 sources."""
    sources = {
        8192: Path(f"{HOT_RUN}/hot_p8192/observations.jsonl"),
        8256: Path(f"{HOT_RUN}/hot_p8256/observations.jsonl"),
    }
    hot_dumps = {
        prefix: Path(f"{HOT_RUN}/hot_p{prefix}/state_dump/donate_0001_dev_conv_states.pt")
        for prefix in sources
    }
    old_cold = Path(f"{HOT_RUN}/cold_A_p8192_t1/state_dump/donate_0001_dev_conv_states.pt")
    output = HERE / "CPU_FILEDRY_RECEIPT.json"
    assert not output.exists(), output
    doc = render_packet(sources, hot_dumps)
    doc["prior_retry1_replay"] = replay_prior_confounded_boundary(hot_dumps[8192], old_cold)
    doc["cpu_filedry"] = {
        "source_consumed": True, "source_sha256_verified": True,
        "gpu_started": False, "service_started": False, "http_generation": False,
        "model_initialized": False, "cpu_bound": "nice19/taskset single core supplied by caller",
    }
    output.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
