"""CPU regression for the R046 draft; imports the actual candidate scheduler source."""
import os
import sys
import types
from pathlib import Path

import pytest

CANDIDATE = Path(os.environ.get("FT_CANDIDATE_SCHEDULER", ""))
OLD = '''    def _receive_dev_messages(self, blocking: bool) -> None:
        """Only pause controls are acted on until the pause window ends."""
        for msg in self.receive_msg(blocking=blocking):
            if isinstance(msg, (DevPauseBackendMsg, DevPauseCancelBackendMsg)):
                self._process_one_msg(msg)
            else:
                self._dev_deferred_msgs.append(msg)
'''
NEW = '''    def _receive_dev_messages(self, blocking: bool) -> None:
        """Process ordinary work unless a requested or active pause owns the gate."""
        messages = list(self.receive_msg(blocking=blocking))
        controls = []
        ordinary = []
        for msg in messages:
            if isinstance(msg, (DevPauseBackendMsg, DevPauseCancelBackendMsg)):
                controls.append(msg)
            else:
                ordinary.append(msg)
        # Process controls first so a pause received in the same batch gates every
        # ordinary message, regardless of wire ordering.
        for msg in controls:
            self._process_one_msg(msg)
        if self._dev_pause_active() or self._dev_pending_pauses:
            self._dev_deferred_msgs.extend(ordinary)
            return
        for msg in ordinary:
            self._process_one_msg(msg)
'''


def patched_scheduler():
    if not CANDIDATE.is_file():
        pytest.skip("FT_CANDIDATE_SCHEDULER required")
    source = CANDIDATE.read_text()
    assert source.count(OLD) == 1
    module = types.ModuleType("freetoken.scheduler.scheduler_r046_draft")
    module.__package__ = "freetoken.scheduler"
    sys.modules[module.__name__] = module
    exec(compile(source.replace(OLD, NEW), str(CANDIDATE), "exec"), module.__dict__)
    return module.Scheduler, module.DevPauseBackendMsg, module.DevPauseCancelBackendMsg


def harness(cls, incoming):
    obj = cls.__new__(cls)
    obj._dev_pending_pauses = []
    obj._dev_deferred_msgs = []
    obj._dev_pause_until = 0.0
    processed = []
    obj.receive_msg = lambda blocking: incoming
    def process(msg):
        processed.append(msg)
        if hasattr(msg, "seconds"):
            obj._dev_pending_pauses.append(msg)
    obj._process_one_msg = process
    return obj, processed


def test_no_pause_processes_ordinary_user_message():
    cls, _, _ = patched_scheduler()
    user = object(); obj, processed = harness(cls, [user])
    cls._receive_dev_messages(obj, True)
    assert processed == [user]
    assert obj._dev_deferred_msgs == []


def test_pause_batch_defers_ordinary_independent_of_wire_order():
    cls, Pause, _ = patched_scheduler()
    user = object(); pause = Pause("p", 1.0, 9999999999.0)
    obj, processed = harness(cls, [user, pause])
    cls._receive_dev_messages(obj, True)
    assert processed == [pause]
    assert obj._dev_deferred_msgs == [user]


def test_release_after_pause_processes_deferred_once():
    cls, _, _ = patched_scheduler()
    first, second = object(), object(); obj, processed = harness(cls, [])
    obj._dev_deferred_msgs = [first, second]
    cls._release_deferred_dev_messages(obj)
    cls._release_deferred_dev_messages(obj)
    assert processed == [first, second]
    assert obj._dev_deferred_msgs == []


def test_active_pause_window_holds_ordinary_message():
    cls, _, _ = patched_scheduler()
    user = object(); obj, processed = harness(cls, [user])
    import time
    obj._dev_pause_until = time.monotonic() + 5.0
    cls._receive_dev_messages(obj, False)
    assert processed == [] and obj._dev_deferred_msgs == [user]


def _pause_lifecycle_subject(cls, incoming, deferred, pending):
    obj = cls.__new__(cls)
    obj._dev_pause_enabled = True
    obj.config = types.SimpleNamespace(tp_info=types.SimpleNamespace(size=1))
    obj.prefill_manager = types.SimpleNamespace(runnable=False)
    obj.decode_manager = types.SimpleNamespace(runnable=False)
    obj._dev_pending_pauses = list(pending)
    obj._dev_deferred_msgs = list(deferred)
    obj._dev_cancelled_pause_ids = set()
    obj._dev_pause_until = 0.0
    replies=[]; released=[]; queue=list(incoming)
    obj._reply_dev_pause = lambda *args, **kwargs: replies.append(args[1])
    obj.receive_msg = lambda blocking: [queue.pop(0)] if queue else []
    def process(msg):
        if msg.__class__.__name__ in {"DevPauseBackendMsg", "DevPauseCancelBackendMsg"}:
            return cls._process_one_msg(obj, msg)
        released.append(msg)
    obj._process_one_msg = process
    return obj, replies, released


def test_real_cancel_control_releases_deferred_exactly_once():
    cls, Pause, Cancel = patched_scheduler()
    import time
    user = object(); pause = Pause("p", 1.0, time.monotonic() + 10.0)
    obj, replies, released = _pause_lifecycle_subject(cls, [Cancel("p")], [user], [pause])
    cls._start_dev_pause(obj, None)
    assert released == [user]
    assert obj._dev_deferred_msgs == []
    assert "p" not in obj._dev_cancelled_pause_ids


def test_expired_pause_releases_preserved_ordinary_message():
    cls, Pause, _ = patched_scheduler()
    user = object(); expired = Pause("late", 1.0, 0.0)
    obj, replies, released = _pause_lifecycle_subject(cls, [], [user], [expired])
    cls._start_dev_pause(obj, None)
    assert replies == ["expired"]
    assert released == [user]
    assert obj._dev_deferred_msgs == []
