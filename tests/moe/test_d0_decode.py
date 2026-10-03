from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from freetoken.moe.d0_decode import D0DecodeRecorder, read_sm_clock_mhz


def _batch(*uids, padded=None):
    reqs = [SimpleNamespace(uid=uid) for uid in uids]
    return SimpleNamespace(reqs=reqs, size=len(reqs), padded_size=padded or len(reqs))


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_step_deltas_freeze_real_rids_and_optional_padded_size(tmp_path):
    recorder = D0DecodeRecorder(tmp_path / "d0", device=None)
    recorder.begin(_batch(4, 9, padded=4), [10, 20], [4, 7])
    recorder.finish([13, 25], [5, 10], expert_row_bytes=16)

    assert _rows(tmp_path / "d0_decode_steps.jsonl") == [{
        "step": 0, "t": pytest.approx(_rows(tmp_path / "d0_decode_steps.jsonl")[0]["t"]),
        "bs": 2, "padded_bs": 4, "rids": [4, 9], "missing_per_layer": [3, 5],
        "missing_total": 8, "h2d_bytes": 64,
    }]


def test_hybrid_cpu_experts_and_warmup_baseline(tmp_path):
    recorder = D0DecodeRecorder(tmp_path / "d0", device=None)
    recorder.begin(_batch(1), [100, 200], [50, 100])
    recorder.finish([100, 200], [50, 100], expert_row_bytes=8, hybrid=True)
    recorder.begin(_batch(1), [100, 200], [50, 100])
    recorder.finish([105, 207], [52, 104], expert_row_bytes=8, hybrid=True)

    first, second = _rows(tmp_path / "d0_decode_steps.jsonl")
    assert first["missing_total"] == first["h2d_bytes"] == first["cpu_experts"] == 0
    assert second["missing_per_layer"] == [5, 7]
    assert second["h2d_bytes"] == 48
    assert second["cpu_experts_per_layer"] == [3, 3]
    assert second["cpu_experts"] == 6


def test_off_timeline_never_creates_events(tmp_path):
    def unexpected_event():
        raise AssertionError("timeline event should not be created")

    recorder = D0DecodeRecorder(tmp_path / "d0", None, event_factory=unexpected_event)
    recorder.begin(_batch(1), [0], [0])
    recorder.mark(0, "copy_start")
    recorder.finish([1], [1], expert_row_bytes=1)
    assert not (tmp_path / "d0_decode_timeline.jsonl").exists()


class _Event:
    def __init__(self, clock):
        self.clock = clock
        self.at = None
        self.synced = False

    def record(self):
        self.at = self.clock[0]
        self.clock[0] += 1

    def synchronize(self):
        self.synced = True

    def elapsed_time(self, other):
        return (other.at - self.at) * 2.5


def test_timeline_cap_and_complete_events(tmp_path):
    clock = [0]
    recorder = D0DecodeRecorder(tmp_path / "d0", None, timeline=True, timeline_steps=1,
                                event_factory=lambda: _Event(clock))
    recorder.begin(_batch(3), [0], [0])
    for name in ("copy_start", "copy_end", "compute_start", "compute_end"):
        recorder.mark(0, name)
    recorder.finish([2], [1], expert_row_bytes=4)
    recorder.begin(_batch(3), [2], [1])
    recorder.mark(0, "copy_start")
    recorder.finish([3], [2], expert_row_bytes=4)

    timeline = _rows(tmp_path / "d0_decode_timeline.jsonl")
    assert len(timeline) == 1
    assert timeline[0]["layers"] == [{
        "copy_start_ms": 2.5, "copy_end_ms": 5.0,
        "compute_start_ms": 7.5, "compute_end_ms": 10.0, "layer": 0,
    }]


def test_timeline_rejects_incomplete_or_illegal_events(tmp_path):
    recorder = D0DecodeRecorder(tmp_path / "d0", None, timeline=True, event_factory=lambda: _Event([0]))
    recorder.begin(_batch(1), [0], [0])
    with pytest.raises(ValueError, match="unknown"):
        recorder.mark(0, "bad")
    recorder.mark(0, "copy_start")
    with pytest.raises(ValueError, match="incomplete"):
        recorder.finish([1], [1], expert_row_bytes=1)


def test_timeline_end_precedes_counter_and_file_io_delays(tmp_path, monkeypatch):
    clock = [0]
    recorder = D0DecodeRecorder(tmp_path / "d0", None, timeline=True,
                                event_factory=lambda: _Event(clock))
    recorder.begin(_batch(1), [0], [0])
    for name in ("copy_start", "copy_end", "compute_start", "compute_end"):
        recorder.mark(0, name)
    recorder.seal_timeline()
    clock[0] += 1000  # counter read and host file I/O must not widen the GPU step
    recorder.finish([1], [1], expert_row_bytes=4)
    row = _rows(tmp_path / "d0_decode_timeline.jsonl")[0]
    assert row["step_ms"] == 12.5


def test_bad_batch_counts_and_append_failures_are_not_silenced(tmp_path, monkeypatch):
    recorder = D0DecodeRecorder(tmp_path / "d0", None)
    bad = SimpleNamespace(reqs=[SimpleNamespace(uid=1)], size=2, padded_size=2)
    with pytest.raises(ValueError, match="rids"):
        recorder.begin(bad, [0], [0])

    recorder.begin(_batch(1), [3], [1])
    with pytest.raises(ValueError, match="backwards"):
        recorder.finish([2], [1], expert_row_bytes=1)
    recorder.begin(_batch(1), [3], [1])
    monkeypatch.setattr(recorder, "_append", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        recorder.finish([4], [2], expert_row_bytes=1)


def test_clock_failure_returns_none(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("no nvidia-smi")

    monkeypatch.setattr("freetoken.moe.d0_decode.subprocess.run", fail)
    assert read_sm_clock_mhz(SimpleNamespace(index=0)) is None
