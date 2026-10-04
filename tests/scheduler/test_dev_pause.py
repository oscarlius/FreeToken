"""CPU seams for the D06 scheduler-owned development pause."""

from __future__ import annotations

from types import SimpleNamespace


def _scheduler():
    from freetoken.scheduler.scheduler import Scheduler

    sched = Scheduler.__new__(Scheduler)
    sched.config = SimpleNamespace(tp_info=SimpleNamespace(size=1))
    sched.prefill_manager = SimpleNamespace(runnable=False)
    sched.decode_manager = SimpleNamespace(runnable=False)
    sched._pending_rebuild = None
    sched._dev_pause_enabled = True
    sched._dev_pending_pauses = []
    sched._dev_deferred_msgs = []
    sched._dev_cancelled_pause_ids = set()
    sched._dev_pause_until = 0.0
    sched.receive_msg = lambda blocking=False: []
    sched.send_result = lambda result: sched.results.append(result)
    sched.results = []
    return sched


def test_dev_pause_rejects_invalid_seconds_and_tp():
    from freetoken.message import DevPauseBackendMsg
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    Scheduler._process_one_msg(sched, DevPauseBackendMsg("bad", 0.0, 1.0))
    assert sched.results[-1][0].status == "rejected"

    sched.config.tp_info.size = 2
    Scheduler._process_one_msg(sched, DevPauseBackendMsg("tp", 1.0, 1.0))
    assert sched.results[-1][0].status == "unsupported"


def test_pause_blocks_normal_loop_scheduling(monkeypatch):
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.message import DevPauseBackendMsg

    sched = _scheduler()
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "sleep", lambda interval: now.__setitem__(0, now[0] + interval))
    sched._dev_pending_pauses = [DevPauseBackendMsg("p", 0.02, 1.0)]
    scheduled = []
    sched._schedule_next_batch = lambda: scheduled.append(True)
    sched._process_last_data = lambda data: None
    sched._flush_abort_acks = lambda: None

    Scheduler._dev_normal_loop(sched)
    assert scheduled == []


def test_overlap_pause_drains_existing_forward_before_waiting(monkeypatch):
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.message import DevPauseBackendMsg

    sched = _scheduler()
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "sleep", lambda interval: now.__setitem__(0, now[0] + interval))
    sched._dev_pending_pauses = [DevPauseBackendMsg("p", 0.02, 1.0)]
    waits, drained, scheduled = [], [], []
    sched.stream = SimpleNamespace(wait_stream=lambda stream: waits.append(stream))
    sched.engine = SimpleNamespace(stream="engine")
    sched._process_last_data = lambda data: drained.append(data)
    sched._flush_abort_acks = lambda: None
    sched._schedule_next_batch = lambda: scheduled.append(True)

    assert Scheduler._dev_overlap_loop(sched, "inflight") is None
    assert waits == ["engine"]
    assert drained == ["inflight"]
    assert scheduled == []


def test_expired_pause_never_enters_idle_window(monkeypatch):
    from freetoken.message import DevPauseBackendMsg
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    monkeypatch.setattr(module.time, "monotonic", lambda: 10.0)
    sched._dev_pending_pauses = [DevPauseBackendMsg("late", 1.0, 9.0)]
    processed = []
    sched._process_one_msg = lambda msg: processed.append(msg)
    Scheduler._start_dev_pause(sched, None)
    assert sched.results[-1][0].status == "expired"
    assert processed == []


def test_drain_finishes_before_full_pause_interval_begins(monkeypatch):
    from freetoken.message import DevPauseBackendMsg
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "time", lambda: 1_000.0 + now[0])
    monkeypatch.setattr(module.time, "sleep", lambda interval: now.__setitem__(0, now[0] + interval))
    sched._dev_pending_pauses = [DevPauseBackendMsg("p", 2.0, 100.0)]
    sched.stream = SimpleNamespace(wait_stream=lambda stream: None)
    sched.engine = SimpleNamespace(stream="engine")
    sched._process_last_data = lambda data: now.__setitem__(0, 10.0)  # slow GPU/cache drain
    sched._flush_abort_acks = lambda: None

    Scheduler._start_dev_pause(sched, "inflight")
    reply = sched.results[-1][0]
    assert reply.pause_started_wallclock_s == 1_010.0
    assert reply.deadline_wallclock_s == 1_012.0
    assert now[0] == 12.0  # the full two idle seconds follow the drain


def test_concurrent_pause_requests_extend_serially(monkeypatch):
    from freetoken.message import DevPauseBackendMsg
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    monkeypatch.setattr(module.time, "sleep", lambda interval: now.__setitem__(0, now[0] + interval))
    sched._dev_pending_pauses = [
        DevPauseBackendMsg("one", 1.0, 100.0),
        DevPauseBackendMsg("two", 2.0, 100.0),
    ]

    Scheduler._start_dev_pause(sched, None)
    assert now[0] == 3.0
    assert [r[0].deadline_wallclock_s for r in sched.results] == [1.0, 3.0]


def test_cancel_active_pause_does_not_shorten_next_request(monkeypatch):
    from freetoken.message import DevPauseBackendMsg, DevPauseCancelBackendMsg
    from freetoken.scheduler import scheduler as module
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    monkeypatch.setattr(module.time, "sleep", lambda interval: now.__setitem__(0, now[0] + interval))
    sched._dev_pending_pauses = [
        DevPauseBackendMsg("cancel-me", 10.0, 100.0),
        DevPauseBackendMsg("keep-me", 2.0, 100.0),
    ]
    calls = [0]

    def receive(blocking=False):
        calls[0] += 1
        return [DevPauseCancelBackendMsg("cancel-me")] if calls[0] == 1 else []

    sched.receive_msg = receive
    Scheduler._start_dev_pause(sched, None)
    # First request starts then is cancelled; the second still receives its complete two seconds.
    assert now[0] == 2.0
    assert [r[0].request_id for r in sched.results] == ["cancel-me", "keep-me"]
    assert sched.results[-1][0].deadline_wallclock_s == 2.0


def test_pause_defers_non_control_messages_without_processing():
    from freetoken.scheduler.scheduler import Scheduler

    sched = _scheduler()
    ordinary = object()
    sched.receive_msg = lambda blocking=False: [ordinary]
    seen = []
    sched._process_one_msg = lambda msg: seen.append(msg)
    Scheduler._receive_dev_messages(sched, False)
    assert seen == []
    assert sched._dev_deferred_msgs == [ordinary]
