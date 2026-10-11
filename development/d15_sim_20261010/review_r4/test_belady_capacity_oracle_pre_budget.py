#!/usr/bin/env python3
"""Exhaustive small-state validation for the capacity-drop Belady upper bound."""
from __future__ import annotations

import itertools
import json
from functools import lru_cache


def greedy(events, capacity, prefill_slots):
    """Same set-cache rule as run_stage0_review.belady, for tiny integer ids."""
    uses = {x: [] for event in events if event is not None for x in event}
    for at, event in enumerate(events):
        if event is not None:
            for x in event:
                uses[x].append(at)
    position = {x: 0 for x in uses}
    resident, misses = set(), 0
    for at, event in enumerate(events):
        if event is None:
            while len(resident) > capacity - prefill_slots:
                resident.remove(max(resident, key=lambda x: (uses[x][position[x]] if position[x] < len(uses[x]) else float("inf"), x)))
            continue
        event = set(event)
        misses += len(event - resident)
        resident |= event
        for x in event:
            position[x] += 1
        while len(resident) > capacity:
            candidates = resident - event
            assert candidates
            resident.remove(max(candidates, key=lambda x: (uses[x][position[x]] if position[x] < len(uses[x]) else float("inf"), x)))
    return misses


def exhaustive(events, capacity, prefill_slots):
    universe = sorted({x for event in events if event is not None for x in event})

    def subsets(pool, limit, required=frozenset()):
        extra = sorted(set(pool) - set(required))
        for count in range(min(limit - len(required), len(extra)) + 1):
            for picked in itertools.combinations(extra, count):
                yield frozenset(set(required) | set(picked))

    @lru_cache(None)
    def solve(at, resident):
        resident = frozenset(resident)
        if at == len(events):
            return 0
        event = events[at]
        if event is None:
            return min(solve(at + 1, nxt) for nxt in subsets(resident, capacity - prefill_slots))
        needed = frozenset(event)
        base = resident | needed
        misses = len(needed - resident)
        return misses + min(solve(at + 1, nxt) for nxt in subsets(base, capacity, needed))

    return solve(0, frozenset())


CASES = {
    "prefill_before_full": ([frozenset({0}), None, frozenset({0, 1}), frozenset({0})], 3, 1),
    "same_step_layers_atomic": ([frozenset({0, 1}), frozenset({2, 3}), frozenset({0, 1})], 3, 1),
    "consecutive_prefill": ([frozenset({0, 1, 2}), None, None, frozenset({0, 1}), frozenset({2})], 4, 2),
}


def main():
    result = {}
    for name, (events, capacity, prefill_slots) in CASES.items():
        got, want = greedy(events, capacity, prefill_slots), exhaustive(events, capacity, prefill_slots)
        assert got == want, (name, got, want)
        result[name] = {"greedy_misses": got, "exhaustive_min_misses": want}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
