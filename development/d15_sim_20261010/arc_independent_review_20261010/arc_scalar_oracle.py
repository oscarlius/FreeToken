"""Small CPU oracle for reviewing the ARC supplement.

This is a review-side fixture, not a simulation result.  It checks the
Figure-4 Case-IV state transitions and the explicitly non-paper physical
extensions (a batched call and a physical prefill prefix).
"""
from collections import OrderedDict
import importlib.util
from pathlib import Path

import numpy as np


SOURCE = Path(__file__).parents[1] / "adaptive_arc_supplement" / "adaptive_arc.py"
spec = importlib.util.spec_from_file_location("reviewed_adaptive_arc", SOURCE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
ARC = module.ARC


def lists(cache):
    return {name: list(getattr(cache, name)) for name in ("t1", "t2", "b1", "b2")}


def assert_bounds(cache):
    state = lists(cache)
    assert len(state["t1"]) + len(state["b1"]) <= cache.n, state
    assert sum(map(len, state.values())) <= 2 * cache.n, state
    assert int((cache.ids >= 0).sum()) == len(state["t1"]) + len(state["t2"]), state


def case_iv_t1_full_discards_without_ghost():
    """Figure 4 Case IV: |T1|+|B1|=c and |T1|=c discards LRU(T1)."""
    cache = ARC(2)
    cache.ensure(0, np.array([0, 1]))
    cache.ensure(0, np.array([2]))
    assert lists(cache) == {"t1": [1, 2], "t2": [], "b1": [], "b2": []}
    assert_bounds(cache)


def case_iv_l1_full_discards_b1_then_replaces():
    """Figure 4 Case IV: |T1|+|B1|=c, |T1|<c discards LRU(B1), then REPLACE."""
    cache = ARC(2)
    # Valid scalar state: residents 10/11, one T1 history item and one B1 ghost.
    cache.ids[:] = [10, 11]
    cache.free_slots.clear()
    cache.slot_for_id[10], cache.slot_for_id[11] = 0, 1
    cache.t1, cache.t2 = OrderedDict([(10, None)]), OrderedDict([(11, None)])
    cache.b1, cache.b2 = OrderedDict([(20, None)]), OrderedDict()
    cache.ensure(0, np.array([12]))
    assert lists(cache) == {"t1": [12], "t2": [11], "b1": [10], "b2": []}, lists(cache)
    assert_bounds(cache)


def physical_extensions_are_explicit_and_safe():
    cache = ARC(4)
    cache.ensure(0, np.array([1, 2, 3, 4]))
    cache.ensure(0, np.array([1, 2, 5]))  # existing hits cannot be evicted by this call
    assert all(cache.slot_for_id[key] >= 0 for key in (1, 2, 5))
    cache.prefill()
    assert (cache.ids < 0).all()
    assert_bounds(cache)


def main():
    case_iv_t1_full_discards_without_ghost()
    case_iv_l1_full_discards_b1_then_replaces()
    physical_extensions_are_explicit_and_safe()
    print("ARC small scalar oracle: 3 passed")


if __name__ == "__main__":
    main()
