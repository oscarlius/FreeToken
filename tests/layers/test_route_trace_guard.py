"""CPU collector lifecycle checks; CUDA transfer handling is covered on Linux."""
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
from freetoken.route_trace import RouteTraceCollector


class Req:
    def __init__(self, uid, extend_len=1): self.uid, self.extend_len = uid, extend_len


class Batch:
    is_prefill = True
    phase = "prefill"
    def __init__(self): self.reqs = [Req(3)]


def test_default_guard_never_constructs_collector_or_allocates_buffer(monkeypatch,tmp_path):
    import freetoken.route_trace as trace
    monkeypatch.delenv('FT_DEV_ROUTE_TRACE',raising=False)
    monkeypatch.setattr(trace,'_collector',None)
    def forbidden(*args,**kwargs):
        pytest.fail('default path attempted route allocation or writer construction')
    monkeypatch.setattr(trace,'RouteTraceCollector',forbidden)
    monkeypatch.setattr(trace.torch,'empty',forbidden)
    monkeypatch.setattr(trace.threading,'Thread',forbidden)
    assert trace.route_trace_enabled() is False
    assert trace.get_route_tracer() is None
    assert trace._collector is None and list(tmp_path.iterdir())==[]


def capture_one(collector, values=None):
    collector.begin(Batch())
    values = torch.arange(10, dtype=torch.int16).reshape(1, 10) if values is None else values
    collector.capture(7, values)
    values.fill_(99)
    collector.end()


def test_cpu_snapshot_flush_close_and_closed_guard(tmp_path):
    collector = RouteTraceCollector(tmp_path)
    capture_one(collector)
    collector.flush()
    data = __import__("numpy").load(tmp_path / "route-00000000.npz")["expert_ids"]
    assert data[0, 0].tolist() == list(range(10))
    assert json.loads((tmp_path / "route-00000000.json").read_text())["reqs"] == [{"rid": 3, "n_tokens": 1}]
    collector.close(); collector.close()
    with pytest.raises(RuntimeError, match="closed"): collector.begin(Batch())
    with pytest.raises(RuntimeError, match="closed"): collector.capture(7, torch.zeros((1, 10), dtype=torch.int16))


def test_writer_failure_propagates_and_close_stops_thread(tmp_path, monkeypatch):
    collector = RouteTraceCollector(tmp_path)
    monkeypatch.setattr("freetoken.route_trace.np.savez_compressed", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    capture_one(collector)
    with pytest.raises(RuntimeError, match="writer failed"): collector.flush()
    with pytest.raises(RuntimeError, match="writer failed"): collector.close()
    assert not collector._thread.is_alive()


class FakeEvent:
    def __init__(self, fail=False): self.called, self.fail = False, fail
    def synchronize(self):
        self.called = True
        if self.fail: raise RuntimeError("event failed")


def test_abort_synchronizes_unqueued_async_capture(tmp_path):
    collector = RouteTraceCollector(tmp_path)
    event = FakeEvent()
    collector._current = {"layers": {7: (torch.zeros((1, 10), dtype=torch.int16), event)}}
    collector.abort()
    assert event.called
    collector.close()


def test_end_queue_full_synchronizes_unqueued_async_capture(tmp_path, monkeypatch):
    collector = RouteTraceCollector(tmp_path)
    event = FakeEvent()
    collector._current = {"seq": 0, "layers": {7: (torch.zeros((1, 10), dtype=torch.int16), event)}}
    monkeypatch.setattr(collector._queue, "put_nowait", lambda value: (_ for _ in ()).throw(__import__("queue").Full()))
    with pytest.raises(RuntimeError, match="queue is full"):
        collector.end()
    assert event.called
    with pytest.raises(RuntimeError, match="writer failed"):
        collector.close()
    assert not collector._thread.is_alive()


def test_async_sync_failure_is_retained_and_reported(tmp_path):
    collector = RouteTraceCollector(tmp_path)
    event = FakeEvent(fail=True)
    collector._current = {"layers": {7: (torch.zeros((1, 10), dtype=torch.int16), event)}}
    with pytest.raises(RuntimeError, match="async route trace"):
        collector.abort()
    assert event.called and collector._retired
    with pytest.raises(RuntimeError): collector.close()


def test_writer_sync_failure_retains_buffer_and_close_aborts_current(tmp_path):
    collector = RouteTraceCollector(tmp_path)
    copied = (torch.zeros((1, 10), dtype=torch.int16), FakeEvent(fail=True))
    collector._queue.put(({"seq": 0, "file": "never.npz"}, [copied]))
    with pytest.raises(RuntimeError, match="writer failed"):
        collector.flush()
    assert any(item is copied for item in collector._retired)
    current_event = FakeEvent()
    collector._current = {"layers": {7: (torch.zeros((1, 10), dtype=torch.int16), current_event)}}
    with pytest.raises(RuntimeError):
        collector.close()
    assert current_event.called and not collector._thread.is_alive()


@pytest.mark.skipif(not torch.cuda.is_available(), reason="serial GPU gate owns CUDA D2H abort")
def test_cuda_capture_abort_retains_until_event_completes(tmp_path):
    collector = RouteTraceCollector(tmp_path)
    collector.begin(Batch())
    collector.capture(7, torch.arange(10, device="cuda", dtype=torch.int16).reshape(1, 10))
    collector.abort()
    collector.close()


def test_source_has_opt_in_queue_and_cuda_event_guard():
    source = Path("python/freetoken/route_trace.py").read_text(encoding="utf-8")
    assert "queue.Queue(maxsize=_QUEUE_SIZE)" in source and "pin_memory=True" in source
    assert "raw.to(dtype=torch.int16).clone()" in source and "event.synchronize()" in source
