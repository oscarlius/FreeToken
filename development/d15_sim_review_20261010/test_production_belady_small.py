"""Exercise run_stage0_review.belady itself against an independent exhaustive DP."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stage", HERE / "run_stage0_review.py")
stage = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(stage)
dp_spec = importlib.util.spec_from_file_location("dp", HERE / "test_belady_capacity_oracle.py")
dp = importlib.util.module_from_spec(dp_spec)
assert dp_spec.loader
dp_spec.loader.exec_module(dp)


def decode(layer_sets):
    # two layers, up to two routed experts/layer; duplicate padding is deduplicated.
    rows = []
    for experts in layer_sets:
        values = list(experts)
        rows.append((values + [values[-1]])[:2])
    return ("s", np.array(rows, dtype=np.int16).reshape(2, 1, 2))


def as_dp(ops):
    events = []
    for kind, ids in ops:
        if kind == "p":
            events.append(None)
        else:
            for layer in range(2):
                events.append(frozenset(layer * 3 + int(x) for x in np.unique(ids[layer])))
    return events


CASES = {
    "prefill_not_full": [("s", decode(((0,), (0,)))[1]), ("p", None), ("s", decode(((0, 1), (1,)))[1])],
    "layer_atomic": [("s", decode(((0, 1), (1, 2)))[1]), ("s", decode(((0,), (2,)))[1])],
    "consecutive_prefill": [("s", decode(((0, 1), (0, 2)))[1]), ("p", None), ("p", None), ("s", decode(((1,), (2,)))[1])],
}


def main():
    old = stage.kimi.NL, stage.kimi.E, stage.kimi.PF
    stage.kimi.NL, stage.kimi.E, stage.kimi.PF = 2, 3, 1
    try:
        for name, ops in CASES.items():
            events = as_dp(ops)
            got = stage.belady(ops, 4)["missing"]
            want = dp.exhaustive(events, 4, 1, 3)
            assert got == want, (name, got, want)
    finally:
        stage.kimi.NL, stage.kimi.E, stage.kimi.PF = old


if __name__ == "__main__":
    main()
