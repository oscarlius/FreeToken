#!/usr/bin/env python3
"""D15 phase-0: CPU replay of the FreeToken MoE expert slot cache (commit 8256553 semantics).

Replays D07 route traces (route-*.npz/json) through a host model of
OffloadMoeCache + flashlib lru_ensure and scores decode miss rates for the
D15 policy family. CPU-only; never touches a GPU.

Mirrored cache semantics (python/freetoken/moe/offload_cache.py,
offload_kernels.py, venv flashlib/kernels/slot_cache/triton/lru_ensure.py):
  * one slot holds one (layer, expert) instance; flat id = layer*E + expert
  * one ensure call = one (layer, decode step): routed ids are deduped;
    hits bump usage to the per-call clock BEFORE victim selection (a slot
    touched this call sorts last and cannot be evicted by this call);
    misses in ascending id order take victims by ascending (usage, slot);
    D0 stats count DISTINCT active / distinct missing ids per call
    (Stat.ACTIVE = sum(first), Stat.MISS = num_missing in lru_ensure.py)
  * a prefill event invalidates slots [0, 2E): ids dropped, usage zeroed
    (prefill double buffers borrow them; prefill routing never enters the
    slot map, so the whole prefill effect on the map is this clear)
  * profile preload: ranked[:S-2E] -> slots [2E, S), usage left at 0
    (so untouched profile slots are the first eviction victims, in slot
    order = profile rank order)
  * profile+adapt: policy_recent += 1 per raw routed position (duplicates
    across a bs>1 call count); at decode boundary seq % every == 0, plan
    up to `swaps` replacements: candidates by (-recent, flat id), skipping
    already stable-resident (slot >= 2E); victims by (usage, slot) over
    [2E, S) excluding already-planned; applied between decode steps (the
    step that just ran is unaffected); usage[victim] = current clock;
    policy_recent zeroed when the plan is made. PA-lag1 queues the plan at
    boundary s and publishes it at boundary s+1 (recents zeroed at plan).
  * swap cost: EXPERT_BYTES per applied replacement (nvfp4 H=2560 I=640).

Calibration target: each group's d0_decode.json miss_rate. G_two's
d0_decode.json is a mid-run snapshot (d0_decode_steps.jsonl has 85 steps
but the json shows 80 steps for layers 0-10 and 79 for 11-47), so G_two is
replayed truncated: 79 full steps + step 79 restricted to layers 0-10.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import json
import pickle
import struct
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

E, NL, PF = 512, 48, 1024                 # experts/layer, layers, prefill region [0, 2E)
EXPERT_BYTES = 2_772_480                  # nvfp4 banks per (layer, expert)
PCIE_BPS = 24.3e9
MISS_MS = 54.77                           # S_tok(1.331 GB) / B_P(24.3 GB/s), ms
T0_MS, K_MS_PER_KTOK, TREQ_MS = 13.1, 0.032, 5.3
GROUPS = ("G_seed12k", "G_seed_45k", "G_seed_real", "G_two")
IN_SAMPLE = "G_seed12k"
STRP_SHA256 = "8fd705d5556c43d94d9a74b963b7942332b2ae05d3e02bc7b3292dca457c206e"


def read_strp_ranked(path: Path) -> np.ndarray:
    """STRP -> flat ids (layer*E+expert), hottest first (expert_profile.read_profile)."""
    blob = Path(path).read_bytes()
    assert blob[:4] == b"STRP", "bad STRP magic"
    ver, layers, experts, _slots, n = struct.unpack_from("<5I", blob, 4)
    assert (ver, layers, experts) == (1, NL, E), (ver, layers, experts)
    pairs = np.frombuffer(blob, dtype="<u2", count=2 * n, offset=24).reshape(n, 2).astype(np.int64)
    return pairs[:, 0] * E + pairs[:, 1]


def prepare_group(root: Path, group: str, out: Path) -> dict:
    """Build the replay program (prefill clear ops + per-step (48, K) routed ids) and meta."""
    route = root / group / "route"
    metas = [json.loads(p.read_text()) for p in sorted(route.glob("route-*.json"))]
    ops, ctxs = [], []
    rid_len, rid_state = {}, {}
    n_dec = 0
    for m in metas:
        if m["phase"] == "prefill":
            for r in m["reqs"]:
                rid = r["rid"]
                if rid_state.get(rid) == "decode":
                    rid_len[rid] = 0            # new request reuses the slot
                rid_state[rid] = "prefill"
                rid_len[rid] = rid_len.get(rid, 0) + r["n_tokens"]
            ops.append(("p",))
            continue
        ids = np.load(route / m["file"])["expert_ids"]          # (48, t, 10) int16
        t = ids.shape[1]
        assert t == sum(r["n_tokens"] for r in m["reqs"]), (group, m["file"])
        assert all(r["n_tokens"] == 1 for r in m["reqs"]), (group, m["file"])
        ops.append(("s", ids.reshape(NL, t * 10).copy()))
        n_dec += 1
        for r in m["reqs"]:
            ctxs.append(rid_len.get(r["rid"], 0))
            rid_len[r["rid"]] = rid_len.get(r["rid"], 0) + 1
            rid_state[r["rid"]] = "decode"
    d0 = json.loads((root / group / "d0_decode.json").read_text())
    per_layer = d0["per_layer"]["per_layer"]
    steps_l = [int(p["steps"]) for p in per_layer]
    full = min(steps_l)
    partial = [p["layer"] for p in per_layer if p["steps"] == full + 1]
    assert all(s in (full, full + 1) for s in steps_l), steps_l
    trunc = None if (full == n_dec and not partial) else (full, partial)
    d0_missing = sum(round(p["steps"] * p["missing_per_step"]) for p in per_layer)
    d0_active = sum(round(p["steps"] * p["active_per_step"]) for p in per_layer)
    meta = {
        "group": group,
        "decode_events": n_dec,
        "prefill_events": sum(1 for op in ops if op[0] == "p"),
        "steps_replay": full + (len(partial) / NL if trunc else 0.0),
        "trunc": trunc,
        "L_ktok": float(np.median(ctxs) / 1000.0),
        "d0_miss_rate": d0["miss_rate"],
        "d0_missing": d0_missing,
        "d0_active": d0_active,
        "d0_layer_calls": d0["layer_calls"],
    }
    with open(out / f"stream_{group}.pkl", "wb") as f:
        pickle.dump({"ops": ops, "meta": meta}, f, protocol=4)
    return meta


class CacheSim:
    """lru / profile / adapt / pinned / noinv replay of the slot map."""

    def __init__(self, size: int, mode: str, ranked: np.ndarray | None, every=0, swaps=0, lag=0):
        self.S, self.mode = size, mode
        self.every, self.swaps, self.lag = every, swaps, lag
        self.slot_for_id = np.full(NL * E, -1, np.int64)
        self.id_of_slot = np.full(size, -1, np.int64)
        self.usage = np.zeros(size, np.int64)
        self.slots = np.arange(size)
        self.clock = 0
        self.recent = np.zeros(NL * E, np.int64)
        self.swap_bytes = 0
        self.miss = 0
        self.active = 0
        self.pending = None
        if mode in ("profile", "adapt", "pinned"):
            flat = ranked[: size - PF]
            self.id_of_slot[PF : PF + flat.size] = flat
            self.slot_for_id[flat] = np.arange(PF, PF + flat.size)
            # usage stays 0: _initialize_expert_profile only writes the maps

    def prefill(self) -> None:
        if self.mode == "noinv":
            return
        old = self.id_of_slot[:PF]
        self.slot_for_id[old[old >= 0]] = -1
        self.id_of_slot[:PF] = -1
        self.usage[:PF] = 0

    def ensure(self, layer: int, raw: np.ndarray) -> None:
        self.clock += 1
        clk = self.clock
        d = np.unique(raw)                        # distinct; ascending id = miss rank order
        base = layer * E
        s = self.slot_for_id[base + d]
        hit = s >= 0
        self.usage[s[hit]] = clk                  # hit bump precedes victim selection
        self.active += d.size
        misses = d[~hit]
        self.miss += misses.size
        if self.mode == "adapt":
            np.add.at(self.recent, base + raw.astype(np.int64), 1)   # raw positions, dupes count
        if misses.size == 0:
            return
        lo, hi = (0, PF) if self.mode == "pinned" else (0, self.S)
        us = self.usage
        pk = us[lo:hi] * 4096 + self.slots[lo:hi]  # (usage, slot) in one int64; usage==clk sorts last
        sid, ios = self.slot_for_id, self.id_of_slot
        for e in misses:
            v = lo + int(pk.argmin())
            old = ios[v]
            if old >= 0:
                sid[old] = -1
            ios[v] = base + e
            sid[base + e] = v
            us[v] = clk
            pk[v - lo] = clk * 4096 + v

    def boundary(self, seq: int) -> None:
        if self.mode != "adapt":
            return
        if self.pending is not None:              # PA-lag1: publish the previous plan now
            self._apply(self.pending)
            self.pending = None
        if seq % self.every:
            return
        cand = np.nonzero(self.recent)[0]         # plan_profile_adaptation, offload_cache.py:976-995
        cand = cand[self.slot_for_id[cand] < PF]  # skip already stable-resident
        if cand.size == 0:
            return
        order = np.lexsort((cand, -self.recent[cand]))[: self.swaps]  # (-count, layer, expert)
        pk = self.usage[PF : self.S] * 4096 + self.slots[PF : self.S]
        repl = []
        for f in cand[order]:
            v = PF + int(pk.argmin())
            pk[v - PF] = np.iinfo(np.int64).max   # planned_slots exclusion
            repl.append((v, int(f)))
        if not repl:
            return
        self.recent[:] = 0                        # zeroed at plan time (apply time when lag=0)
        if self.lag:
            self.pending = repl
        else:
            self._apply(repl)

    def _apply(self, repl) -> None:               # apply_profile_adaptation, offload_cache.py:1040-1061
        for v, f in repl:
            old = self.id_of_slot[v]
            if old >= 0:
                self.slot_for_id[old] = -1
            olds = self.slot_for_id[f]
            if olds >= 0 and olds != v:
                self.id_of_slot[olds] = -1        # promoted expert's volatile slot is released
            self.slot_for_id[f] = v
            self.id_of_slot[v] = f
            self.usage[v] = self.clock
            self.swap_bytes += EXPERT_BYTES


def run_belady(ops, trunc, size: int):
    """Optimal replacement over a set-model cache of `size` slots; each prefill event
    sheds the 2E resident ids with the farthest next use (the constrained optimum).
    Consecutive prefill events (chunked prefill with no decode in between) share one
    2E shed budget: the real clear empties the volatile region, so a second chunk
    with no intervening decode has nothing left to clear."""
    steps = [ids for op in ops if op[0] == "s" for ids in [op[1]]]
    n_replay = trunc[0] + (1 if trunc and trunc[1] else 0) if trunc else len(steps)
    steps = steps[:n_replay]
    occ = [[] for _ in range(NL * E)]
    for si, ids in enumerate(steps):
        layers = trunc[1] if (trunc and si == trunc[0] and trunc[1]) else range(NL)
        for l in layers:
            for e in np.unique(ids[l]):
                occ[l * E + e].append(si)
    occ = [np.array(o, dtype=np.int64) for o in occ]
    resident = np.zeros(NL * E, bool)
    nu = np.full(NL * E, np.inf)
    ptr = np.zeros(NL * E, np.int64)
    heap, cnt, miss, active = [], 0, 0, 0
    shed = PF
    si = -1
    for op in ops:
        if op[0] == "p":
            for _ in range(min(shed, cnt)):        # shed farthest-next-use residents
                while heap:
                    negnu, f = heapq.heappop(heap)
                    if resident[f] and nu[f] == -negnu:
                        resident[f] = False
                        cnt -= 1
                        break
            shed = 0                               # volatile region now empty until next decode
            continue
        shed = PF
        si += 1
        if si >= len(steps):
            break
        ids = op[1]
        layers = trunc[1] if (trunc and si == trunc[0] and trunc[1]) else range(NL)
        for l in layers:
            d = np.unique(ids[l]).astype(np.int64)
            fs = l * E + d
            active += d.size
            for f in fs:                          # consume this use; nu = next use after si
                p = ptr[f] + 1
                ptr[f] = p
                o = occ[f]
                nu[f] = o[p] if p < o.size else np.inf
                heapq.heappush(heap, (-nu[f], f))  # refresh validity on every activation
            m = fs[~resident[fs]]
            miss += m.size
            for f in m:
                resident[f] = True
                cnt += 1
                if cnt > size:
                    while heap:
                        negnu, g = heapq.heappop(heap)
                        if resident[g] and nu[g] == -negnu:
                            resident[g] = False
                            cnt -= 1
                            break
    return miss, active


def speed(m: float, swap_b_per_step: float, L_ktok: float, B: int) -> float:
    swap_ms = swap_b_per_step / PCIE_BPS * 1000.0
    return 1000.0 / (T0_MS + K_MS_PER_KTOK * L_ktok + TREQ_MS * (B - 1) + B * (m * MISS_MS + swap_ms))


def run_job(prep: Path, job: dict) -> dict:
    with open(prep / f"stream_{job['group']}.pkl", "rb") as f:
        blob = pickle.load(f)
    ops, meta = blob["ops"], blob["meta"]
    trunc = tuple(meta["trunc"]) if meta["trunc"] else None
    t0 = time.time()
    if job["mode"] == "belady":
        miss, active = run_belady(ops, trunc, job["size"])
        swap_bytes = 0
    else:
        ranked = None
        if job["mode"] in ("profile", "adapt", "pinned"):
            ranked = read_strp_ranked(job["profile"])
        sim = CacheSim(job["size"], job["mode"], ranked, job.get("every", 0), job.get("swaps", 0), job.get("lag", 0))
        si = -1
        for op in ops:
            if op[0] == "p":
                sim.prefill()
                continue
            si += 1
            if trunc and si > trunc[0]:
                break
            layers = trunc[1] if (trunc and si == trunc[0] and trunc[1]) else range(NL)
            ids = op[1]
            for l in layers:
                sim.ensure(l, ids[l])
            if not (trunc and si == trunc[0] and trunc[1]):
                sim.boundary(si + 1)              # boundary_seq starts at 1 (seal_decode_boundary)
        miss, active, swap_bytes = sim.miss, sim.active, sim.swap_bytes
    m = miss / active
    steps = meta["steps_replay"]
    sb_step = swap_bytes / steps
    return {
        **job, "steps": steps, "missing": miss, "active": active, "miss_rate": m,
        "swap_bytes": swap_bytes, "swap_b_per_step": sb_step,
        "L_ktok": meta["L_ktok"], "R_b1": speed(m, sb_step, meta["L_ktok"], 1),
        "R_b2": speed(m, sb_step, meta["L_ktok"], 2),
        "d0_miss_rate": meta["d0_miss_rate"], "wall_s": round(time.time() - t0, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default="/data2/_shared/runs/ft_rounds/E2-R046g")
    ap.add_argument("--profile", type=Path, default="/data2/_shared/runs/ft_rounds/E2-R049c/seed12k_only.strp")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--calibrate-only", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import hashlib
    assert hashlib.sha256(args.profile.read_bytes()).hexdigest() == STRP_SHA256, "profile sha256 mismatch"

    metas = {}
    for g in GROUPS:
        pkl = args.out / f"stream_{g}.pkl"
        metas[g] = prepare_group(args.root, g, args.out) if not pkl.exists() else pickle.loads(pkl.read_bytes())["meta"]
        print("prepare", json.dumps(metas[g], default=str))
    if args.prepare_only:
        return

    def jobs_base():
        for g in GROUPS:
            yield {"group": g, "tag": "LRU@2700", "mode": "lru", "size": 2700, "profile": str(args.profile)}

    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            calib = list(ex.map(run_job, [args.out] * 4, [j for j in jobs_base()]))
    else:
        calib = [run_job(args.out, j) for j in jobs_base()]
    gate = {}
    for r in calib:
        dev_pp = (r["miss_rate"] - r["d0_miss_rate"]) * 100.0
        gate[r["group"]] = {
            "sim_miss_rate": r["miss_rate"], "d0_miss_rate": r["d0_miss_rate"],
            "deviation_pp": dev_pp, "pass": abs(dev_pp) <= 1.0,
            "sim_missing": r["missing"], "sim_active": r["active"],
            "d0_missing": metas[r["group"]]["d0_missing"], "d0_active": metas[r["group"]]["d0_active"],
            "trunc": metas[r["group"]]["trunc"], "steps_replay": r["steps"],
        }
        print("calib", r["group"], f"sim={r['miss_rate']:.6f} d0={r['d0_miss_rate']:.6f} dev={dev_pp:+.3f}pp")
    calib_doc = {"semantics": __doc__.split("Mirrored cache semantics")[1].split("Calibration target")[0].strip(),
                 "gate_threshold_pp": 1.0, "groups": gate,
                 "gate_pass": all(v["pass"] for v in gate.values())}
    with open(args.out / "calibration.json", "w") as f:
        json.dump(calib_doc, f, indent=2)
    if not calib_doc["gate_pass"] or args.calibrate_only:
        print("CALIBRATION GATE:", "PASS" if calib_doc["gate_pass"] else "FAIL")
        return

    # ---- strategy scan ----
    jobs = []
    for g in GROUPS:
        jobs += [
            {"group": g, "tag": "P@2700", "mode": "profile", "size": 2700, "profile": str(args.profile)},
            {"group": g, "tag": "PINNED@2700", "mode": "pinned", "size": 2700, "profile": str(args.profile)},
            {"group": g, "tag": "NOINV@2700", "mode": "noinv", "size": 2700, "profile": str(args.profile)},
            {"group": g, "tag": "BELADY@2700", "mode": "belady", "size": 2700, "profile": str(args.profile)},
        ]
    for every in (1, 4, 16, 64):
        for swaps in (1, 4, 16):
            for g in GROUPS:
                jobs.append({"group": g, "tag": f"PA_e{every}_s{swaps}@2700", "mode": "adapt",
                             "size": 2700, "every": every, "swaps": swaps, "lag": 0, "profile": str(args.profile)})
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        rows = calib + list(ex.map(run_job, [args.out] * len(jobs), jobs))

    # PA parameter selection on seed12k only: lowest miss, then fewer swap bytes/step, then larger every
    grid = [r for r in rows if r["mode"] == "adapt" and r["group"] == IN_SAMPLE and r.get("lag") == 0]
    sel = min(grid, key=lambda r: (r["miss_rate"], r["swap_b_per_step"], -r["every"]))
    sel_every, sel_swaps = sel["every"], sel["swaps"]
    print(f"PA selected on {IN_SAMPLE}: every={sel_every} swaps={sel_swaps} miss={sel['miss_rate']:.6f}")

    lag_jobs, sweep_jobs = [], []
    for g in GROUPS:
        lag_jobs.append({"group": g, "tag": f"PA-lag1_e{sel_every}_s{sel_swaps}@2700", "mode": "adapt",
                         "size": 2700, "every": sel_every, "swaps": sel_swaps, "lag": 1, "profile": str(args.profile)})
    # best realizable on seed12k among P / PINNED / PA-selected
    cands = {r["mode"]: r for r in rows if r["group"] == IN_SAMPLE and r["tag"] in
             ("P@2700", "PINNED@2700", f"PA_e{sel_every}_s{sel_swaps}@2700")}
    best_mode = min(cands, key=lambda m: cands[m]["miss_rate"])
    best_name = {"profile": "P", "pinned": "PINNED", "adapt": "PA"}[best_mode]
    for size in (3149, 3600):
        for g in GROUPS:
            sweep_jobs.append({"group": g, "tag": f"LRU@{size}", "mode": "lru", "size": size, "profile": str(args.profile)})
            jb = {"group": g, "tag": f"{best_name}@{size}", "mode": best_mode, "size": size, "profile": str(args.profile)}
            if best_mode == "adapt":
                jb.update({"every": sel_every, "swaps": sel_swaps, "lag": 0})
            sweep_jobs.append(jb)
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        rows += list(ex.map(run_job, [args.out] * (len(lag_jobs) + len(sweep_jobs)), lag_jobs + sweep_jobs))

    lru = {(r["group"], r["size"]): r for r in rows if r["mode"] == "lru"}
    for r in rows:
        base = lru[(r["group"], r["size"])]
        r["delta_pp_vs_lru"] = (r["miss_rate"] - base["miss_rate"]) * 100.0
        r["selected"] = bool(r["mode"] == "adapt" and not r.get("lag") and
                             r["every"] == sel_every and r["swaps"] == sel_swaps and r["size"] == 2700)
        r["in_sample"] = r["group"] == IN_SAMPLE
        r["swap_ms_per_step"] = r["swap_b_per_step"] / PCIE_BPS * 1000.0
    doc = {"pa_selected": {"every": sel_every, "swaps": sel_swaps},
           "best_realizable_on_seed12k": best_name, "rows": rows}
    with open(args.out / "results.json", "w") as f:
        json.dump(doc, f, indent=2)
    cols = ["group", "tag", "mode", "size", "every", "swaps", "lag", "selected", "in_sample", "steps",
            "missing", "active", "miss_rate", "d0_miss_rate", "delta_pp_vs_lru", "swap_bytes",
            "swap_b_per_step", "swap_ms_per_step", "L_ktok", "R_b1", "R_b2"]
    write_header = not (args.out / "results.csv").exists()
    with open(args.out / "results.csv", "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerows(rows)
    for r in sorted(rows, key=lambda r: (r["group"], r["tag"])):
        print(f"{r['group']:12s} {r['tag']:26s} m={r['miss_rate']:.6f} d={r['delta_pp_vs_lru']:+7.3f}pp "
              f"swB/step={r['swap_b_per_step']:9.0f} R1={r['R_b1']:.2f} R2={r['R_b2']:.2f}")


if __name__ == "__main__":
    main()
