from __future__ import annotations

from contextlib import contextmanager

import pytest
import torch

from freetoken.moe.staggered_decode import StaggeredDecodeLane, StaggeredDecodePrototype


class _Event:
    def __init__(self, log):
        self.log = log

    def record(self, stream):
        self.log.append(("record", stream.name))


class _Stream:
    def __init__(self, name, log):
        self.name, self.log = name, log

    def wait_event(self, event):
        self.log.append(("wait", self.name))


def _lanes(log, *, second_cache=(2, 3), second_state=(12,)):
    def lane(name, cache_slots, state_slots):
        return StaggeredDecodeLane(
            name=name,
            cache_slots=cache_slots,
            state_slots=state_slots,
            copy=lambda layer, slots: log.append(("copy", name, layer, slots)),
            compute=lambda layer, slots: log.append(("compute", name, layer, slots)),
        )

    return (lane("A", (0, 1), (10,)), lane("B", second_cache, second_state))


def test_disabled_by_default_and_cpu_cannot_enable():
    prototype = StaggeredDecodePrototype(torch.device("cpu"))
    with pytest.raises(RuntimeError, match="disabled"):
        prototype.run_step(1, _lanes([]))
    with pytest.raises(ValueError, match="CUDA"):
        StaggeredDecodePrototype(torch.device("cpu"), enabled=True)


@pytest.mark.parametrize("second_cache,second_state,match", [
    ((1, 2), (12,), "expert-cache"),
    ((2, 3), (10,), "decode state"),
])
def test_rejects_cross_lane_resource_aliasing(second_cache, second_state, match):
    prototype = StaggeredDecodePrototype(torch.device("cpu"))
    with pytest.raises(ValueError, match=match):
        prototype._validate_lanes(_lanes([], second_cache=second_cache, second_state=second_state))


def test_cuda_schedule_uses_independent_streams_events_and_lane_slots(monkeypatch):
    log = []
    streams = iter((_Stream("copy", log), _Stream("compute", log)))

    @contextmanager
    def use_stream(stream):
        log.append(("enter", stream.name))
        yield
        log.append(("exit", stream.name))

    monkeypatch.setattr(torch.cuda, "Stream", lambda *, device: next(streams))
    monkeypatch.setattr(torch.cuda, "Event", lambda: _Event(log))
    monkeypatch.setattr(torch.cuda, "stream", use_stream)
    monkeypatch.setattr(torch.cuda, "is_current_stream_capturing", lambda: False)

    prototype = StaggeredDecodePrototype(torch.device("cuda"), enabled=True)
    done = prototype.run_step(2, _lanes(log))

    assert isinstance(done, _Event)
    assert [x for x in log if x[0] == "copy"] == [
        ("copy", "A", 0, (0, 1)), ("copy", "B", 0, (2, 3)),
        ("copy", "A", 1, (0, 1)), ("copy", "B", 1, (2, 3)),
    ]
    assert [x for x in log if x[0] == "compute"] == [
        ("compute", "A", 0, (10,)), ("compute", "B", 0, (12,)),
        ("compute", "A", 1, (10,)), ("compute", "B", 1, (12,)),
    ]
    # Submission order is the D10 stagger: B's transfer is submitted only
    # after A's compute work, allowing the two CUDA streams to overlap.
    assert log.index(("compute", "A", 0, (10,))) < log.index(("copy", "B", 0, (2, 3)))
    # Four compute waits consume copy-ready events; four copy waits consume
    # prepare-ready events before each copy reads the lane's route descriptors.
    assert len([x for x in log if x == ("wait", "compute")]) == 4
    assert len([x for x in log if x == ("wait", "copy")]) == 4
    assert log[-1] == ("record", "compute")


def test_rejects_whole_forward_cuda_graph_capture(monkeypatch):
    prototype = object.__new__(StaggeredDecodePrototype)
    prototype.enabled = True
    prototype.copy_stream = object()
    prototype.compute_stream = object()
    monkeypatch.setattr(torch.cuda, "is_current_stream_capturing", lambda: True)
    with pytest.raises(RuntimeError, match="CUDA graph capture"):
        prototype.run_step(1, _lanes([]))
