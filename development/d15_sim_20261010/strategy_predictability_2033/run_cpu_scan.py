"""CPU-only D15 replacement and route-persistence descriptive scan.

This script deliberately reuses the read-only stage-0 replay streams.  It
reproduces the LRU `ensure` semantics used by the historical simulator: one
call per (decode step, layer), unique routed experts, hit refresh before
misses, ascending routed-id insertion, and prefill clears slots [0, 1024).
It reports cache misses, not GPU speed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

E, NL, PREFILL_SLOTS = 512, 48, 1024
GROUPS = ("G_seed12k", "G_seed_45k", "G_seed_real", "G_two")
HALF_LIVES = (96, 192, 384, 768, 1536)
SIZE = 2401
CALIBRATION_SIZE = 2700
EXPECTED_LRU_2700 = {
    "G_seed12k": (579863, 1545120),
    "G_seed_45k": (670309, 1885920),
    "G_seed_real": (208366, 540000),
    "G_two": (29955, 70334),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replay(ops, size: int, policy: str) -> tuple[int, int]:
    """Return `(missing, active)` for LRU, cycle tie-break, or lrfuH."""
    id_of_slot = np.full(size, -1, dtype=np.int64)
    slot_for_id = np.full(NL * E, -1, dtype=np.int64)
    last_call = np.zeros(size, dtype=np.int64)
    last_step = np.full(size, -1, dtype=np.int64)
    crf = np.zeros(size, dtype=np.float64)
    slots = np.arange(size, dtype=np.int64)
    half_life = int(policy[4:]) if policy.startswith("lrfu") else None
    alpha = np.log(2.0) / half_life if half_life else 0.0
    # The historical/reviewed replay starts its call clock at zero; retaining
    # that origin preserves the production LRU `(usage, slot)` tie order.
    clock, step = 0, -1
    missing = active = 0

    for kind, *payload in ops:
        if kind == "p":
            old = id_of_slot[:PREFILL_SLOTS]
            slot_for_id[old[old >= 0]] = -1
            id_of_slot[:PREFILL_SLOTS] = -1
            last_call[:PREFILL_SLOTS] = 0
            last_step[:PREFILL_SLOTS] = -1
            crf[:PREFILL_SLOTS] = 0.0
            continue
        step += 1
        ids = payload[0]
        for layer in range(NL):
            clock += 1
            routed = np.unique(ids[layer]).astype(np.int64)
            base = layer * E
            resident = slot_for_id[base + routed]
            hit = resident >= 0
            hit_slots = resident[hit]
            if half_life:
                crf[hit_slots] = 1.0 + crf[hit_slots] * np.exp(
                    -alpha * (clock - last_call[hit_slots])
                )
            last_call[hit_slots] = clock
            last_step[hit_slots] = step
            active += routed.size
            misses = routed[~hit]
            missing += misses.size
            if not misses.size:
                continue

            if policy == "lru":
                key = last_call * 4096 + slots
            elif policy == "cycle":
                resident_layer = np.where(id_of_slot >= 0, id_of_slot // E, -1)
                visited = (resident_layer <= layer).astype(np.int64)
                missed = step - last_step - (1 - visited)
                distance = np.mod(resident_layer - layer, NL)
                distance = np.where(distance == 0, NL, distance)
                key = -(missed * 64 + distance)
                key = np.where(id_of_slot < 0, -(1 << 60), key)
            elif half_life:
                key = crf * np.exp(-alpha * (clock - last_call))
                key = np.where(id_of_slot < 0, -1.0, key)
            else:
                raise ValueError(policy)
            key = key.copy()
            key[hit_slots] = np.inf if half_life else (1 << 60)
            for expert in misses:
                victim = int(key.argmin())
                old_id = id_of_slot[victim]
                if old_id >= 0:
                    slot_for_id[old_id] = -1
                id_of_slot[victim] = base + expert
                slot_for_id[base + expert] = victim
                last_call[victim] = clock
                last_step[victim] = step
                crf[victim] = 1.0
                key[victim] = np.inf if half_life else (1 << 60)
    return missing, active


def per_layer_top10(ops) -> list[set[int]]:
    counts = [Counter() for _ in range(NL)]
    for kind, *payload in ops:
        if kind == "s":
            for layer, ids in enumerate(payload[0]):
                counts[layer].update(int(x) for x in ids)
    return [set(x for x, _ in layer.most_common(10)) for layer in counts]


def predictability(ops, frequency_top10: list[set[int]]) -> dict[str, float | int]:
    """Adjacent-step recall; a prefill between steps removes the transition."""
    previous = None
    transitions = 0
    previous_hits = frequency_hits = targets = 0
    for kind, *payload in ops:
        if kind == "p":
            previous = None
            continue
        current = [set(int(x) for x in layer) for layer in payload[0]]
        if previous is not None:
            transitions += NL
            for layer, target in enumerate(current):
                targets += len(target)
                previous_hits += len(previous[layer] & target)
                frequency_hits += len(frequency_top10[layer] & target)
        previous = current
    return {
        "layer_transitions": transitions,
        "target_unique_experts": targets,
        "previous_step_recall": previous_hits / targets if targets else 0.0,
        "seed12k_top10_frequency_recall": frequency_hits / targets if targets else 0.0,
    }


def row(group, policy, missing, active, role) -> dict:
    return {
        "group": group,
        "role": role,
        "slots": SIZE,
        "policy": policy,
        "missing": missing,
        "active": active,
        "miss_rate": missing / active,
        "miss_rate_pct": 100 * missing / active,
    }


def main() -> None:
    here = Path(__file__).resolve().parent
    streams = here.parent / "review_r4"
    source = here.parent / "main_session_check_20261010_2018" / "turn_sim.py"
    blobs = {group: pickle.loads((streams / f"stream_{group}.pkl").read_bytes()) for group in GROUPS}
    calibration = []
    for group, blob in blobs.items():
        got = replay(blob["ops"], CALIBRATION_SIZE, "lru")
        expected = EXPECTED_LRU_2700[group]
        calibration.append({"group": group, "got": got, "expected": expected, "pass": got == expected})
    if not all(item["pass"] for item in calibration):
        raise AssertionError(f"LRU calibration failed: {calibration}")

    selection = []
    for half_life in HALF_LIVES:
        missing, active = replay(blobs["G_seed12k"]["ops"], SIZE, f"lrfu{half_life}")
        selection.append(row("G_seed12k", f"lrfu{half_life}", missing, active, "in_sample_selection"))
    selected = min(selection, key=lambda item: (item["missing"], int(item["policy"][4:])))
    selected_policy = selected["policy"]

    results = []
    roles = {"G_seed12k": "in_sample_selection", "G_seed_real": "independent_heldout", "G_seed_45k": "same_source_diagnostic", "G_two": "short_trace_diagnostic"}
    for group, blob in blobs.items():
        for policy in ("lru", "cycle", selected_policy):
            missing, active = replay(blob["ops"], SIZE, policy)
            results.append(row(group, policy, missing, active, roles[group]))
    for group in GROUPS:
        baseline = next(item["miss_rate_pct"] for item in results if item["group"] == group and item["policy"] == "lru")
        for item in results:
            if item["group"] == group:
                item["delta_pp_vs_lru"] = item["miss_rate_pct"] - baseline

    frequency_top10 = per_layer_top10(blobs["G_seed12k"]["ops"])
    prediction = {group: predictability(blob["ops"], frequency_top10) for group, blob in blobs.items()}
    inputs = {f"stream_{group}.pkl": sha256(streams / f"stream_{group}.pkl") for group in GROUPS}
    report = {
        "purpose": "CPU cache miss and descriptive route-persistence scan; no GPU speed claim",
        "semantics_source": str(source.relative_to(here.parent.parent.parent.parent)),
        "semantics_source_sha256": sha256(source),
        "input_sha256": inputs,
        "parameters": {"slots": SIZE, "policies": ["lru", "cycle", *[f"lrfu{x}" for x in HALF_LIVES]], "selection_group": "G_seed12k", "selected_policy": selected_policy},
        "calibration_lru_2700": calibration,
        "lrfu_selection": selection,
        "replacement_results": results,
        "route_predictability": prediction,
        "limitations": [
            "G_seed_real is the only independent heldout trace; one session does not establish a general performance result.",
            "G_seed_45k shares source with seed12k and G_two has only 85 steps; both are diagnostics, not performance evidence.",
            "Previous-step and static-frequency recall are descriptive route overlap, not a trained predictor or a cache policy benefit.",
            "No adaptive ARC-style grid or preregistered acceptance criterion was present in the archived 20:30 instruction.",
        ],
    }
    (here / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    fields = list(results[0])
    with (here / "replacement_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(results)
    print(json.dumps({"selected_policy": selected_policy, "calibration_pass": True, "rows": len(results)}, indent=2))


if __name__ == "__main__":
    main()
