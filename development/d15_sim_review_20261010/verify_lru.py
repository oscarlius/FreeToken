#!/usr/bin/env python3
"""Independent, CPU-only D15 LRU calibration against E2-R046g route inputs.

This intentionally covers only the executable cache baseline.  It mirrors
flashlib lru_ensure's distinct-id accounting, hit-before-victim usage update,
and ascending (usage, slot) victim tie-break.  It does not simulate D15 online
adaptation because 8256553 has no live quiescent-publication proof for it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

E, LAYERS, SLOTS, PREFILL = 512, 48, 2700, 1024
GROUPS = ("G_seed12k", "G_seed_45k", "G_seed_real", "G_two")


class Lru:
    def __init__(self) -> None:
        self.slot_for = np.full(E * LAYERS, -1, np.int64)
        self.owner = np.full(SLOTS, -1, np.int64)
        self.usage = np.zeros(SLOTS, np.int64)
        self.slots = np.arange(SLOTS, dtype=np.int64)
        self.clock = self.missing = self.active = 0

    def prefill(self) -> None:
        old = self.owner[:PREFILL]
        self.slot_for[old[old >= 0]] = -1
        self.owner[:PREFILL] = -1
        self.usage[:PREFILL] = 0

    def ensure(self, layer: int, ids: np.ndarray) -> None:
        self.clock += 1
        routed = np.unique(ids)  # lru_ensure deduplicates before Stat.ACTIVE.
        flat = layer * E + routed
        cached = self.slot_for[flat]
        hits = cached >= 0
        self.usage[cached[hits]] = self.clock  # before choosing any victim.
        misses = flat[~hits]
        self.active += len(flat)
        self.missing += len(misses)
        priority = self.usage * 4096 + self.slots
        for expert in misses:  # np.unique is ascending, matching kernel order.
            victim = int(priority.argmin())
            previous = self.owner[victim]
            if previous >= 0:
                self.slot_for[previous] = -1
            self.owner[victim] = expert
            self.slot_for[expert] = victim
            self.usage[victim] = self.clock
            priority[victim] = self.clock * 4096 + victim


def d0_counts(d0: dict) -> tuple[int, int]:
    rows = d0["per_layer"]["per_layer"]
    # D0 retains per-step averages; the stored totals must be integral again.
    missing = sum(round(row["steps"] * row["missing_per_step"]) for row in rows)
    active = sum(round(row["steps"] * row["active_per_step"]) for row in rows)
    return missing, active


def replay(root: Path, group: str) -> dict:
    route = root / group / "route"
    cache, decode_step = Lru(), -1
    d0 = json.loads((root / group / "d0_decode.json").read_text())
    rows = d0["per_layer"]["per_layer"]
    full = min(int(row["steps"]) for row in rows)
    partial = [row["layer"] for row in rows if int(row["steps"]) == full + 1]
    assert all(int(row["steps"]) in {full, full + 1} for row in rows)
    for meta_path in sorted(route.glob("route-*.json")):
        meta = json.loads(meta_path.read_text())
        assert meta["phase"] in {"prefill", "decode"}
        if meta["phase"] == "prefill":
            cache.prefill()
            continue
        decode_step += 1
        if decode_step > full or (decode_step == full and not partial):
            break
        ids = np.load(route / meta["file"])["expert_ids"]
        assert ids.ndim == 3 and ids.shape[0] == LAYERS and ids.shape[2] == 10
        assert ids.shape[1] == sum(row["n_tokens"] for row in meta["reqs"])
        assert np.all((0 <= ids) & (ids < E))
        layers = partial if decode_step == full and partial else range(LAYERS)
        for layer in layers:
            cache.ensure(layer, ids[layer].reshape(-1))
    expected_missing, expected_active = d0_counts(d0)
    actual = cache.missing / cache.active
    return {
        "group": group,
        "replay_steps": full + (len(partial) / LAYERS if partial else 0),
        "sim_missing": cache.missing,
        "sim_active": cache.active,
        "sim_miss_rate": actual,
        "d0_missing": expected_missing,
        "d0_active": expected_active,
        "d0_miss_rate": d0["miss_rate"],
        "deviation_pp": (actual - d0["miss_rate"]) * 100,
        "pass": abs((actual - d0["miss_rate"]) * 100) <= 1,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [replay(args.root, group) for group in GROUPS]
    document = {
        "purpose": "independent LRU calibration only",
        "input_root": str(args.root),
        "groups": rows,
        "gate_pp": 1.0,
        "gate_pass": all(row["pass"] for row in rows),
    }
    (args.out / "independent_lru_calibration.json").write_text(json.dumps(document, indent=2) + "\n")
    for row in rows:
        print("{group}: sim={sim_miss_rate:.9f} d0={d0_miss_rate:.9f} dev={deviation_pp:+.6f}pp".format(**row))
    if not document["gate_pass"]:
        raise SystemExit("calibration gate failed")


if __name__ == "__main__":
    main()
