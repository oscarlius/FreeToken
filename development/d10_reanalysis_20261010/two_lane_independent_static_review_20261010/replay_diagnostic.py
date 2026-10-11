"""CPU-only instrumentation of the existing D10 two-lane script; no strategy changes."""
import importlib.util
import json
import pickle
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
SOURCE = HERE.parent / "two_lane_share_sim.py"
spec = importlib.util.spec_from_file_location("d10_original", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def replay(steps, mode, size, prefills):
    caches = [mod.LRU(size // 2), mod.LRU(size // 2)] if mode == "partition" else [mod.LRU(size)]
    data = {"misses": [0, 0], "active": [0, 0], "calls": [0, 0], "combined_misses": 0, "combined_active": 0, "combined_calls": 0}
    for t, st in enumerate(steps):
        if t in prefills:
            for cache in caches:
                cache.clear_prefill()
        nl = len(st[0])
        for layer in range(mod.NL):
            if mode == "batched":
                ids = np.concatenate(st[layer]) + layer * mod.E
                data["combined_misses"] += caches[0].ensure(ids, False)
                data["combined_active"] += np.unique(ids).size
                data["combined_calls"] += 1
            elif mode == "partition":
                for lane in range(nl):
                    ids = st[layer][lane] + layer * mod.E
                    data["misses"][lane] += caches[lane].ensure(ids, False)
                    data["active"][lane] += np.unique(ids).size
                    data["calls"][lane] += 1
            else:
                ids = st[layer][0] + layer * mod.E
                data["misses"][0] += caches[0].ensure(ids, True)
                data["active"][0] += np.unique(ids).size
                data["calls"][0] += 1
                if nl > 1:
                    lb = (layer + mod.NL // 2) % mod.NL
                    src = st if lb >= mod.NL // 2 else (steps[t - 1] if t > 0 else None)
                    if src is not None and len(src[lb]) > 1:
                        ids = src[lb][1] + lb * mod.E
                        data["misses"][1] += caches[0].ensure(ids, True)
                        data["active"][1] += np.unique(ids).size
                        data["calls"][1] += 1
    return data


def fixtures():
    cache = mod.LRU(4)
    cache.ensure(np.array([0]), True)
    old = cache.prev.copy(); cache.clear_prefill()
    stale = bool(old.size and cache.id_of[int(old[0])] == -1 and cache.prev.size)
    one = [[[np.arange(10), np.arange(10, 20)] for _ in range(mod.NL)]]
    stagger = replay(one, "stagger", 2700, set())
    with tempfile.TemporaryDirectory() as temp:
        a, b = Path(temp) / "a.pkl", Path(temp) / "b.pkl"
        payload = {"ops": [("p",), ("s", np.zeros((mod.NL, 10), np.int16)), ("p",), ("s", np.zeros((mod.NL, 10), np.int16))]}
        for path in (a, b):
            path.write_bytes(pickle.dumps(payload))
        _, pre = mod.load_pair(a, b)
    return {"prefill_stale_prev": stale, "stagger_one_step_calls": stagger["calls"], "stagger_one_step_expected_complete": [48, 48], "load_pair_prefills_from_two_each": [2, 2], "load_pair_prefills_result": sorted(pre)}


def main():
    root = Path("freetoken/development/d15_sim_20261010/review_r4")
    sets = {"G_two": mod.load_two(root / "stream_G_two.pkl"), "seed_real_x_seed12k": mod.load_pair(root / "stream_G_seed_real.pkl", root / "stream_G_seed12k.pkl")}
    out = {"fixtures": fixtures(), "sets": {}}
    for name, (steps, prefills) in sets.items():
        n = len(steps)
        lane_events = sum(len(step[0]) for step in steps)
        nominal = lane_events * 480
        out["sets"][name] = {"steps": n, "lane_events": lane_events, "single_lane_steps": sum(len(step[0]) == 1 for step in steps), "two_lane_steps": sum(len(step[0]) == 2 for step in steps), "prefills": sorted(prefills), "author_nominal_denominator": nominal,
            "batched": replay(steps, "batched", 2700, prefills), "stagger": replay(steps, "stagger", 2700, prefills), "partition": replay(steps, "partition", 2700, prefills)}
    print(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main()
