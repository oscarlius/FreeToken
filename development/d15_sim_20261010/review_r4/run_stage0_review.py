#!/usr/bin/env python3
"""Corrected D15 CPU stage-0 scan.

Uses preserved KIMI primitives plus corrections: G_two is truncated only for
LRU calibration but scanned through its complete route; PA is an implemented
candidate without GPU acceptance; PA-lag is theoretical; and the equal-layer
quota sensitivity is separate from the profile-quota pinned policy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HISTORICAL = HERE / "kimi_historical_20261010" / "sim_d15.py"
spec = importlib.util.spec_from_file_location("kimi_sim", HISTORICAL)
kimi = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(kimi)


class CorrectLagSim(kimi.CacheSim):
    """KIMI's PA-lag correction: the runtime clears recency when it publishes."""

    def boundary(self, seq: int) -> None:
        if self.pending is not None:
            copied = len(self.pending) * kimi.EXPERT_BYTES
            self._apply(self.pending)
            self.swap_bytes -= copied  # charged at plan/copy time below, not twice.
            self.pending = None
            self.recent[:] = 0
        if seq % self.every:
            return
        candidates = np.nonzero(self.recent)[0]
        candidates = candidates[self.slot_for_id[candidates] < kimi.PF]
        if not candidates.size:
            return
        order = np.lexsort((candidates, -self.recent[candidates]))[:self.swaps]
        priority = self.usage[kimi.PF:self.S] * 4096 + self.slots[kimi.PF:self.S]
        replacements = []
        for flat in candidates[order]:
            slot = kimi.PF + int(priority.argmin())
            priority[slot - kimi.PF] = np.iinfo(np.int64).max
            replacements.append((slot, int(flat)))
        # The lag model starts copies when it freezes a plan.  A final plan that
        # never publishes still consumed H2D bandwidth, so charge it here.
        self.swap_bytes += len(replacements) * kimi.EXPERT_BYTES
        self.pending = replacements


class EqualLayerSim(kimi.CacheSim):
    """Equal per-layer stable quotas plus volatile [0,2E) global LRU.

    With 1,676 stable slots and 48 layers, layers 0..46 own 34 slots and
    layer 47 owns the remaining 78, matching ExpertCache::layer_slot_range.
    """

    def __init__(self, size: int, ranked: np.ndarray) -> None:
        super().__init__(size, "lru", None)
        self.mode = "pinned"  # inherited ensure limits eviction to [0, PF).
        stable = size - kimi.PF
        q = stable // kimi.NL
        for layer in range(kimi.NL):
            lo = kimi.PF + layer * q
            hi = kimi.PF + (stable if layer == kimi.NL - 1 else (layer + 1) * q)
            choices = ranked[(ranked // kimi.E) == layer][:hi - lo]
            self.id_of_slot[lo:lo + choices.size] = choices
            self.slot_for_id[choices] = np.arange(lo, lo + choices.size)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(ops, size: int, mode: str, ranked: np.ndarray, *, every=0, swaps=0) -> dict:
    if mode == "fixed_layer":
        sim = EqualLayerSim(size, ranked)
    elif mode == "pa_lag1":
        sim = CorrectLagSim(size, "adapt", ranked, every, swaps, lag=1)
    else:
        sim = kimi.CacheSim(size, mode, ranked if mode in {"profile", "adapt", "pinned"} else None, every, swaps)
    step = -1
    for op in ops:
        if op[0] == "p":
            sim.prefill()
            continue
        step += 1
        for layer in range(kimi.NL):
            sim.ensure(layer, op[1][layer])
        if mode in {"adapt", "pa_lag1"}:
            sim.boundary(step + 1)
    return {"missing": sim.miss, "active": sim.active, "miss_rate": sim.miss / sim.active,
            "swap_bytes": sim.swap_bytes, "steps": step + 1}


def belady(ops, size: int) -> dict:
    """Capacity-constrained Belady relaxation with prefill capacity S-2E.

    A prefill may retain any S-2E resident pairs (free slot placement); this is
    an optimistic upper bound, not the exact fixed-slot FreeToken problem.
    Each layer's top-k is one atomic event and is protected from eviction.
    """
    events, occurrences = [], [[] for _ in range(kimi.NL * kimi.E)]
    for op in ops:
        if op[0] == "p":
            events.append(None)
            continue
        for layer in range(kimi.NL):
            event = layer * kimi.E + np.unique(op[1][layer]).astype(np.int64)
            occurrences_len = len(events)
            for flat in event:
                occurrences[int(flat)].append(occurrences_len)
            events.append(event)
    resident = np.zeros(kimi.NL * kimi.E, dtype=bool)
    next_use = np.full(kimi.NL * kimi.E, np.inf)
    cursor = np.zeros(kimi.NL * kimi.E, dtype=np.int64)
    heap, count, missing, active = [], 0, 0, 0
    # Give the oracle the same initial stable budget as P/PA, but let it choose
    # pairs with earliest future use.  This is a future-informed upper bound.
    initial = sorted((uses[0], flat) for flat, uses in enumerate(occurrences) if uses)[:size - kimi.PF]
    for _first, flat in initial:
        resident[flat] = True
        next_use[flat] = _first
        heapq.heappush(heap, (-_first, flat))
    count = len(initial)

    def evict_one(protected=frozenset()):
        deferred = []
        while heap:
            neg_next, flat = heapq.heappop(heap)
            if not resident[flat] or next_use[flat] != -neg_next:
                continue
            if flat in protected:
                deferred.append((neg_next, flat))
                continue
            resident[flat] = False
            for item in deferred:
                heapq.heappush(heap, item)
            return True
        for item in deferred:
            heapq.heappush(heap, item)
        return False

    for ordinal, event in enumerate(events):
        if event is None:
            while count > size - kimi.PF:
                assert evict_one()
                count -= 1
            continue
        active += event.size
        for flat in event:
            index = int(cursor[flat]) + 1
            cursor[flat] = index
            uses = occurrences[int(flat)]
            next_use[flat] = uses[index] if index < len(uses) else np.inf
            heapq.heappush(heap, (-next_use[flat], int(flat)))
        absent = event[~resident[event]]
        missing += absent.size
        resident[absent] = True
        count += absent.size
        protected = frozenset(int(flat) for flat in event)
        while count > size:
            assert evict_one(protected)
            count -= 1
    return {"missing": int(missing), "active": int(active), "miss_rate": missing / active,
            "swap_bytes": 0, "preload_bytes": count * 0 + len(initial) * kimi.EXPERT_BYTES,
            "steps": sum(1 for op in ops if op[0] == "s")}


def record(group, tag, kind, size, result, *, every=None, swaps=None, theoretical=False, in_sample=False, preload_bytes=0):
    row = {"group": group, "tag": tag, "kind": kind, "size": size, "every": every,
           "swaps": swaps, "theoretical": theoretical, "in_sample": in_sample,
           "preload_bytes": preload_bytes}
    row.update(result)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assert sha(args.profile) == kimi.STRP_SHA256
    ranked = kimi.read_strp_ranked(args.profile)
    streams = {}
    calibration = []
    for group in kimi.GROUPS:
        meta = kimi.prepare_group(args.root, group, args.out)
        import pickle
        streams[group] = pickle.loads((args.out / f"stream_{group}.pkl").read_bytes())
        base = kimi.run_job(args.out, {"group": group, "tag": "LRU@2700", "mode": "lru", "size": 2700})
        calibration.append({"group": group, "sim_miss_rate": base["miss_rate"], "d0_miss_rate": meta["d0_miss_rate"],
                            "deviation_pp": (base["miss_rate"] - meta["d0_miss_rate"]) * 100,
                            "pass": abs((base["miss_rate"] - meta["d0_miss_rate"]) * 100) <= 1,
                            "truncation": meta["trunc"]})
    assert all(row["pass"] for row in calibration)
    rows, grid = [], []
    for group, blob in streams.items():
        ops = blob["ops"]  # Full G_two (85 decode events) begins here, unlike calibration.
        base = replay(ops, 2700, "lru", ranked)
        rows.append(record(group, "LRU@2700", "lru", 2700, base, in_sample=group == kimi.IN_SAMPLE))
        preload = (2700 - kimi.PF) * kimi.EXPERT_BYTES
        for tag, mode, theory in (("P@2700", "profile", False), ("PROFILE_QUOTA_PINNED@2700", "pinned", False),
                                  ("EQUAL_LAYER_QUOTA@2700", "fixed_layer", False),
                                  ("NOINV@2700", "noinv", True)):
            rows.append(record(group, tag, mode, 2700, replay(ops, 2700, mode, ranked), theoretical=theory,
                               in_sample=group == kimi.IN_SAMPLE, preload_bytes=preload if mode != "noinv" else 0))
        rows.append(record(group, "BELADY@2700", "belady", 2700, belady(ops, 2700), theoretical=True,
                           in_sample=group == kimi.IN_SAMPLE))
        for every in (1, 4, 16, 64):
            for swaps in (1, 4, 16):
                row = record(group, f"PA_e{every}_s{swaps}@2700", "pa", 2700,
                             replay(ops, 2700, "adapt", ranked, every=every, swaps=swaps), every=every, swaps=swaps,
                             theoretical=False, in_sample=group == kimi.IN_SAMPLE, preload_bytes=preload)
                row["implementation_status"] = "candidate_unvalidated_gpu"
                rows.append(row)
                if group == kimi.IN_SAMPLE:
                    grid.append(row)
    selected = min(grid, key=lambda r: (r["miss_rate"], r["swap_bytes"] / r["steps"], -r["every"]))
    for group, blob in streams.items():
        rows.append(record(group, f"PA_LAG1_e{selected['every']}_s{selected['swaps']}@2700", "pa_lag1", 2700,
                           replay(blob["ops"], 2700, "pa_lag1", ranked, every=selected["every"], swaps=selected["swaps"]),
                           every=selected["every"], swaps=selected["swaps"], theoretical=True,
                           in_sample=group == kimi.IN_SAMPLE, preload_bytes=preload))
    for size in (3149, 3600):
        for group, blob in streams.items():
            for tag, mode in ((f"LRU@{size}", "lru"), (f"P@{size}", "profile")):
                rows.append(record(group, tag, mode, size, replay(blob["ops"], size, mode, ranked),
                                   in_sample=group == kimi.IN_SAMPLE,
                                   preload_bytes=(size - kimi.PF) * kimi.EXPERT_BYTES if mode == "profile" else 0))
    baselines = {(r["group"], r["size"]): r for r in rows if r["kind"] == "lru"}
    context_ktok = {"G_seed12k": 22.193, "G_seed_45k": 20.647, "G_seed_real": 90.955, "G_two": 0.675}
    for row in rows:
        row["delta_pp_vs_lru"] = (row["miss_rate"] - baselines[row["group"], row["size"]]["miss_rate"]) * 100
        row["swap_b_per_step"] = row["swap_bytes"] / row["steps"]
        row["L_ktok"] = context_ktok[row["group"]]
        swap_ms = row["swap_b_per_step"] / kimi.PCIE_BPS * 1000.0
        row["R_b1"] = kimi.speed(row["miss_rate"], row["swap_b_per_step"], row["L_ktok"], 1)
        row["R_b2"] = kimi.speed(row["miss_rate"], row["swap_b_per_step"], row["L_ktok"], 2)
    doc = {"candidate": "825655305d69df94d3d2f79c3f416234bfe890e6", "profile_sha256": sha(args.profile),
           "calibration": calibration, "calibration_pass": True, "selection_group": kimi.IN_SAMPLE,
           "pa_selected_candidate": {"every": selected["every"], "swaps": selected["swaps"]},
           "context_ktok": context_ktok,
           "g_two_policy_scan": "complete 85 decode events / 154 request tokens; calibration alone uses D0 snapshot truncation (79 full plus layer 0..10 of step 80)",
           "belady": "optimistic capacity-constrained upper bound: prefill retains any S-1024 pairs; each layer top-k is atomic and protected", "rows": rows}
    (args.out / "corrected_results.json").write_text(json.dumps(doc, indent=2) + "\n")
    with (args.out / "corrected_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"calibration_pass": True, "pa_selected_candidate": doc["pa_selected_candidate"],
                      "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
