from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from freetoken.moe.adaptation_boundary import AdaptationBoundary, AdaptationBoundaryResult
from freetoken.scheduler.scheduler import Scheduler


class FakeStream:
    def __init__(self, name, calls):
        self.name = name
        self.device = "cpu"
        self.calls = calls

    def synchronize(self):
        self.calls.append(f"sync:{self.name}")

    def query(self):
        self.calls.append(f"query:{self.name}")
        return True


class FakeEvent:
    device = "cpu"

    def __init__(self, calls):
        self.calls = calls

    def synchronize(self):
        self.calls.append("drain:copy_done")

    def query(self):
        self.calls.append("query:copy_done")
        return True


class FakeCoordinator:
    def __init__(self, calls):
        self.calls = calls

    def close_launch_gate(self, generation, event):
        self.calls.append(f"gate:{generation}")
        return object()

    def mark_last_data_drained(self, gate, event):
        self.calls.append("mark:event")
        return event.query()

    def mark_streams_drained(self, gate, streams):
        self.calls.append("mark:streams")
        return all(stream.query() for stream in streams)

    def issue_proof(self, gate):
        assert gate is not None
        self.calls.append("issue")
        return object()


class FakeCache:
    def __init__(self, calls, result="verified"):
        self.calls = calls
        self.result = result
        self.prefill_copy_stream = FakeStream("prefill", calls)
        self._locked = False

    def adaptation_pending(self):
        return True

    def adaptation_launch_blocked(self):
        return self._locked

    def _register_adaptation_boundary(self, owner, scheduler, identity, streams, *, cpu_test_scope):
        assert cpu_test_scope
        self.calls.append(f"coordinator:{identity}")
        return FakeCoordinator(self.calls)

    def next_adaptation_launch_generation(self):
        return 17

    def plan_profile_adaptation(self, proof):
        self.calls.append("plan")
        return SimpleNamespace(status="verified")

    def apply_profile_adaptation(self, plan, proof):
        self.calls.append("apply")
        if self.result == "locked":
            self._locked = True
        return SimpleNamespace(status=self.result)


def test_boundary_drains_prior_batch_before_all_streams_and_publication():
    calls = []
    cache = FakeCache(calls)
    boundary = AdaptationBoundary("scheduler:test", cpu_test_scope=True)
    last_data = (object(), SimpleNamespace(copy_done_event=FakeEvent(calls)))

    def drain(data):
        assert data is last_data
        data[1].copy_done_event.synchronize()

    result = boundary.run(cache, last_data, drain, FakeStream("scheduler", calls), FakeStream("engine", calls))

    assert result == AdaptationBoundaryResult("verified", drained_last_data=True)
    assert calls.index("drain:copy_done") < calls.index("sync:engine") < calls.index("issue") < calls.index("apply")
    assert calls.index("sync:scheduler") < calls.index("issue")
    assert calls.index("sync:prefill") < calls.index("issue")


def test_scheduler_default_policy_does_not_touch_boundary_or_streams():
    calls = []

    class LruCache:
        def adaptation_launch_blocked(self):
            return False

        def adaptation_pending(self):
            calls.append("pending")
            return False

    scheduler = SimpleNamespace(
        engine=SimpleNamespace(moe_offload_cache=LruCache()),
        _adaptation_boundary=AdaptationBoundary("scheduler:test", cpu_test_scope=True),
    )
    assert Scheduler._run_moe_adaptation_boundary(scheduler, None) is None
    assert calls == ["pending"]


def test_scheduler_blocks_next_launch_after_locked_transaction():
    calls = []
    cache = FakeCache(calls, result="locked")
    scheduler = SimpleNamespace(
        engine=SimpleNamespace(moe_offload_cache=cache, stream=FakeStream("engine", calls)),
        stream=FakeStream("scheduler", calls),
        _adaptation_boundary=AdaptationBoundary("scheduler:test", cpu_test_scope=True),
        _process_last_data=lambda data: data[1].copy_done_event.synchronize(),
        _flush_abort_acks=lambda: calls.append("flush"),
        _last_data=None,
    )
    with pytest.raises(RuntimeError, match="launch gate remains closed"):
        Scheduler._run_moe_adaptation_boundary(scheduler, None)
    assert "apply" in calls
    assert cache.adaptation_launch_blocked()
