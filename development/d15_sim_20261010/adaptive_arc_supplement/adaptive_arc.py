"""CPU-only ARC over the reviewed global physical-slot model.

Prefill physically clears slots ``[0, 1024)``.  Displaced identifiers enter
bounded ARC ghost lists; the reviewed production recipe has no such ghost
state, so this is an explicit exploratory modelling choice.
"""
from collections import OrderedDict
import heapq
import numpy as np

E, NL, PREFILL_SLOTS = 512, 48, 1024


class ARC:
    def __init__(self, slots):
        if slots <= 0:
            raise ValueError("slots must be positive")
        self.n = slots
        self.ids = np.full(slots, -1, dtype=np.int64)
        self.free_slots = list(range(slots))
        self.slot_for_id = np.full(NL * E, -1, dtype=np.int64)
        self.t1, self.t2 = OrderedDict(), OrderedDict()
        self.b1, self.b2 = OrderedDict(), OrderedDict()
        self.p = 0.0
        self.missing = self.active = 0

    @property
    def slots(self):  # compatibility with small correctness fixtures
        return self.slot_for_id

    def _bound_lists(self):
        """Published ARC bounds: L1 <= c and all four lists <= 2c."""
        while len(self.t1) + len(self.b1) > self.n:
            self.b1.popitem(last=False)
        while len(self.t1) + len(self.t2) + len(self.b1) + len(self.b2) > 2 * self.n:
            if self.b2:
                self.b2.popitem(last=False)
            else:
                self.b1.popitem(last=False)

    def _evict(self, queue, ghosts):
        victim, _ = queue.popitem(last=False)
        slot = int(self.slot_for_id[victim])
        if slot < 0:
            raise RuntimeError("ARC resident id has no physical slot")
        self.ids[slot] = -1
        heapq.heappush(self.free_slots, slot)
        self.slot_for_id[victim] = -1
        ghosts[victim] = None
        self._bound_lists()

    @staticmethod
    def _oldest_unprotected(queue, protected):
        for key in queue:
            if key not in protected:
                return key
        return None

    def _replace(self, incoming, protected):
        prefer_t1 = self.t1 and (len(self.t1) > self.p or (incoming in self.b2 and len(self.t1) == self.p))
        first, second = (self.t1, self.b1) if prefer_t1 else (self.t2, self.b2)
        fallback, fallback_ghost = (self.t2, self.b2) if prefer_t1 else (self.t1, self.b1)
        victim = self._oldest_unprotected(first, protected)
        if victim is None:
            victim = self._oldest_unprotected(fallback, protected)
            first, second = fallback, fallback_ghost
        if victim is not None:
            first.pop(victim)
            slot = int(self.slot_for_id[victim])
            self.ids[slot] = -1
            heapq.heappush(self.free_slots, slot)
            self.slot_for_id[victim] = -1
            second[victim] = None
            self._bound_lists()
        else:
            raise RuntimeError("ARC call protection leaves no replacement victim")

    def _drop_ghost(self, queue):
        if queue:
            queue.popitem(last=False)

    def _drop_t1_without_ghost(self, protected):
        victim = self._oldest_unprotected(self.t1, protected)
        if victim is None:
            raise RuntimeError("ARC Case IV needs an unprotected T1 victim")
        self.t1.pop(victim)
        slot = int(self.slot_for_id[victim])
        self.ids[slot] = -1
        heapq.heappush(self.free_slots, slot)
        self.slot_for_id[victim] = -1

    def prefill(self):
        for slot in range(min(PREFILL_SLOTS, self.n)):
            key = int(self.ids[slot])
            if key < 0:
                continue
            self.ids[slot] = -1
            heapq.heappush(self.free_slots, slot)
            self.slot_for_id[key] = -1
            if key in self.t1:
                self.t1.pop(key)
                self.b1[key] = None
            elif key in self.t2:
                self.t2.pop(key)
                self.b2[key] = None
            else:
                raise RuntimeError("ARC prefix slot absent from resident queues")
        self._bound_lists()

    def ensure(self, layer, routed):
        """Batch a layer call: refresh all hits, then protect its top-k on miss."""
        keys = [layer * E + int(expert) for expert in np.unique(routed).astype(int)]
        self.active += len(keys)
        protected = set()
        misses = []
        for key in keys:
            if key in self.t1:
                self.t1.pop(key)
                self.t2[key] = None
                protected.add(key)
            elif key in self.t2:
                self.t2.move_to_end(key)
                protected.add(key)
            else:
                misses.append(key)
        for key in misses:
            self.missing += 1
            if key in self.b1:
                self.p = min(float(self.n), self.p + max(1.0, len(self.b2) / len(self.b1)))
                if not self.free_slots:
                    self._replace(key, protected)
                self.b1.pop(key, None)
                self.t2[key] = None
            elif key in self.b2:
                self.p = max(0.0, self.p - max(1.0, len(self.b1) / len(self.b2)))
                if not self.free_slots:
                    self._replace(key, protected)
                self.b2.pop(key, None)
                self.t2[key] = None
            else:
                l1 = len(self.t1) + len(self.b1)
                total = l1 + len(self.t2) + len(self.b2)
                if l1 == self.n:
                    if len(self.t1) < self.n:
                        self._drop_ghost(self.b1)
                        if not self.free_slots:
                            self._replace(key, protected)
                    else:
                        self._drop_t1_without_ghost(protected)
                elif l1 < self.n and total >= self.n:
                    if total == 2 * self.n:
                        self._drop_ghost(self.b2)
                    if not self.free_slots:
                        self._replace(key, protected)
                self.t1[key] = None
            if not self.free_slots:
                raise RuntimeError("ARC physical slot accounting differs from resident queues")
            slot = heapq.heappop(self.free_slots)
            self.ids[slot] = key
            self.slot_for_id[key] = slot
            protected.add(key)
            self._bound_lists()


def replay(ops, slots, with_turns=False):
    cache, turns, turn = ARC(slots), [], 0
    for op, *rest in ops:
        if op == "p":
            cache.prefill()
            continue
        before_missing, before_active = cache.missing, cache.active
        for layer in range(NL):
            cache.ensure(layer, rest[0][layer])
        turn += 1
        if with_turns:
            turns.append({"turn": turn, "missing": cache.missing - before_missing,
                          "active": cache.active - before_active})
    return (cache.missing, cache.active, turns) if with_turns else (cache.missing, cache.active)
