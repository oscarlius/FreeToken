"""Pure-Python protocol tests for the opt-in D12 segment-state observer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import segment_capture


def test_native_linear_state_pool_dump_roundtrip(tmp_path, monkeypatch):
    source = os.environ.get("FT_D12_NATIVE_SOURCE")
    if not source:
        pytest.skip("requires the actual Linux D12 candidate package")
    import importlib
    import torch

    monkeypatch.syspath_prepend(str(Path(source) / "python"))
    native = importlib.import_module("freetoken.kvcache.linear_state_pool")
    assert Path(native.__file__).resolve() == Path(source).resolve() / "python/freetoken/kvcache/linear_state_pool.py"
    monkeypatch.setattr(native, "DUMP_PATH", str(tmp_path))
    pool = native.LinearStatePool.__new__(native.LinearStatePool)
    pool.conv_states = torch.arange(40, dtype=torch.bfloat16).reshape(2, 5, 4)
    pool.recurrent_states = torch.arange(60, dtype=torch.float32).reshape(2, 5, 2, 3)
    pool.slot_states = {
        "ple_conv": torch.arange(30, dtype=torch.float32).reshape(2, 5, 3),
        "ple_ngram_ctx": torch.arange(20, dtype=torch.int64).reshape(2, 5, 2),
    }
    tensors = {"conv_states": pool.conv_states, "recurrent_states": pool.recurrent_states,
               **{"slot:" + key: tensor for key, tensor in pool.slot_states.items()}}
    before = {key: tensor.clone() for key, tensor in tensors.items()}
    outer = batch([request(slot=3)])
    engine = SimpleNamespace(linear_state_pool=pool, ctx=SimpleNamespace(batch=outer))
    calls = []

    def forward(current):
        calls.append(current)
        for tensor in tensors.values():
            tensor[:, 3].add_(10)
        return "native-dump-fixture"

    engine.forward_batch = forward
    records = []
    _, restore = segment_capture.install_prefill_segment_capture(SimpleNamespace(engine=engine), tmp_path, records.append)
    try:
        assert engine.forward_batch(outer) == "native-dump-fixture"
        assert calls == [outer] and len(records) == 1
        record = records[0]
        assert record["admitted"] is False
        assert set(record["role_files"]) == set(tensors)
        assert len({item["path"] for item in record["role_files"].values()}) == 4
        for role, tensor in tensors.items():
            info = record["role_files"][role]
            path = tmp_path / info["path"]
            saved = torch.load(path, map_location="cpu", weights_only=True)
            assert saved.dtype == tensor.dtype
            assert torch.equal(saved, tensor[:, [3]])
            assert torch.equal(tensor[:, 0], before[role][:, 0])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]
        assert not torch.cuda.is_initialized()
    finally:
        restore()
    assert engine.forward_batch is forward


class Pool:
    def __init__(self, root, roles=segment_capture._ROLES):
        self.root = Path(root)
        self.roles = tuple(roles)
        self.calls = []

    def dump_state(self, kind, *, dev_slots=None, host_slots=None, length=None, uid=None, note=""):
        self.calls.append((kind, dev_slots, host_slots, length, uid, note))
        self.root.mkdir(parents=True, exist_ok=True)
        seq = len(self.calls)
        files = {}
        for role in self.roles:
            name = "%s_%04d_%s.pt" % (kind, seq, role.replace(":", "_"))
            (self.root / name).write_bytes((role + ":" + str(dev_slots)).encode())
            files[role] = name
        row = {"seq": seq, "kind": kind, "length": length, "uid": uid, "note": note,
               "dev_slots": [dev_slots], "host_slots": host_slots, "files": files}
        with (self.root / "index.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")


def request(uid=0, *, start=10, end=20, slot=3):
    return SimpleNamespace(uid=uid, cached_len=start, device_len=end, linear_slot_idx=slot)


def batch(reqs, *, prefill=True, start=10, end=20):
    return SimpleNamespace(reqs=reqs, is_prefill=prefill, seg_start=start, seg_end=end)


def fixture(tmp_path, monkeypatch, *, roles=segment_capture._ROLES):
    monkeypatch.setattr(segment_capture, "_configured_dump_path", lambda: str(tmp_path))
    pool = Pool(tmp_path, roles)
    engine = SimpleNamespace(linear_state_pool=pool, ctx=SimpleNamespace(batch=None))
    calls = []

    def forward(outer, *args, **kwargs):
        calls.append(outer)
        return "ok"

    engine.forward_batch = forward
    scheduler = SimpleNamespace(engine=engine)
    records = []
    provider, restore = segment_capture.install_prefill_segment_capture(scheduler, tmp_path, records.append)
    return scheduler, pool, calls, records, provider, restore


def test_capture_calls_original_once_dumps_all_roles_and_restores(tmp_path, monkeypatch):
    scheduler, pool, calls, records, _, restore = fixture(tmp_path, monkeypatch)
    outer = batch([request()])
    assert scheduler.engine.forward_batch(outer, "args") == "ok"
    assert calls == [outer]
    assert pool.calls == [("d12_post_prefill", 3, None, 20, "0", "d12 outer=0 start=10 end=20")]
    assert records[0]["admitted"] is False
    assert records[0]["outer"] == {"uid": 0, "outer_segment_index": 0, "start": 10, "end": 20, "linear_slot_idx": 3}
    assert set(records[0]["role_files"]) == set(segment_capture._ROLES)
    for item in records[0]["role_files"].values():
        blob = (tmp_path / item["path"]).read_bytes()
        assert item["bytes"] == len(blob) and item["sha256"] == hashlib.sha256(blob).hexdigest()
    original = calls  # prove cleanup changes the bound method, not an unrelated class.
    restore()
    assert scheduler.engine.forward_batch(outer) == "ok"
    assert calls == [outer, outer] and original is calls


def test_provider_reads_actual_child_extent_across_layers(tmp_path, monkeypatch):
    scheduler, _, _, _, provider, restore = fixture(tmp_path, monkeypatch)
    outer = batch([request(start=100, end=400, slot=7)], start=100, end=400)
    child_a = batch([request(start=100, end=164, slot=7)], start=100, end=400)
    child_b = batch([request(start=164, end=397, slot=7)], start=100, end=400)

    def forward(_outer):
        scheduler.engine.ctx.batch = child_a
        assert provider() == {"uid": 0, "outer_segment_index": 0, "child_start": 100, "child_end": 164, "child_tokens": 64}
        scheduler.engine.ctx.batch = child_b
        assert provider() == {"uid": 0, "outer_segment_index": 0, "child_start": 164, "child_end": 397, "child_tokens": 233}
        return "ok"

    restore()
    # Reinstall against a purpose-built engine method.  The first fixture wrapper
    # is removed before replacing the bound instance method.
    scheduler.engine.forward_batch = forward
    provider, restore = segment_capture.install_prefill_segment_capture(scheduler, tmp_path, lambda _: None)
    assert scheduler.engine.forward_batch(outer) == "ok"
    restore()


@pytest.mark.parametrize("foreign", [3, 9])
def test_foreign_uid_and_multirequest_pass_through(tmp_path, monkeypatch, foreign):
    scheduler, pool, calls, records, _, restore = fixture(tmp_path, monkeypatch)
    one = batch([request(foreign)])
    two = batch([request(0), request(1)])
    assert scheduler.engine.forward_batch(one) == "ok"
    assert scheduler.engine.forward_batch(two) == "ok"
    assert calls == [one, two] and pool.calls == records == []
    restore()


def test_decode_passes_through_once_without_capture(tmp_path, monkeypatch):
    scheduler, pool, calls, records, _, restore = fixture(tmp_path, monkeypatch)
    decode = batch([request()], prefill=False)
    assert scheduler.engine.forward_batch(decode) == "ok"
    assert calls == [decode] and pool.calls == records == []
    restore()


def test_outer_coordinates_come_from_request_when_optional_batch_fields_are_absent(tmp_path, monkeypatch):
    scheduler, pool, _, records, _, restore = fixture(tmp_path, monkeypatch)
    outer = SimpleNamespace(reqs=[request(start=64, end=297)], is_prefill=True)
    assert scheduler.engine.forward_batch(outer) == "ok"
    assert pool.calls[0][3] == 297 and records[0]["outer"]["start"] == 64
    restore()


def test_exception_never_dumps_or_emits(tmp_path, monkeypatch):
    scheduler, pool, _, records, _, restore = fixture(tmp_path, monkeypatch)

    def boom(*_):
        raise RuntimeError("product failed")

    restore()
    scheduler.engine.forward_batch = boom
    _, restore = segment_capture.install_prefill_segment_capture(scheduler, tmp_path, records.append)
    with pytest.raises(RuntimeError, match="product failed"):
        scheduler.engine.forward_batch(batch([request()]))
    assert pool.calls == records == []
    restore()


def test_missing_native_role_is_rejected_after_original(tmp_path, monkeypatch):
    scheduler, _, calls, records, _, restore = fixture(tmp_path, monkeypatch, roles=segment_capture._ROLES[:-1])
    with pytest.raises(ValueError, match="missing required device roles"):
        scheduler.engine.forward_batch(batch([request()]))
    assert len(calls) == 1 and records == []
    restore()


def test_provider_rejects_foreign_or_outside_child_and_restore_ownership(tmp_path, monkeypatch):
    scheduler, _, _, _, provider, restore = fixture(tmp_path, monkeypatch)
    outer = batch([request(start=10, end=20)], start=10, end=20)

    def forward(_outer):
        scheduler.engine.ctx.batch = batch([request(uid=1, start=10, end=12)])
        with pytest.raises(ValueError, match="UID"):
            provider()
        scheduler.engine.ctx.batch = batch([request(start=9, end=12)])
        with pytest.raises(ValueError, match="outside"):
            provider()
        return "ok"

    restore()
    scheduler.engine.forward_batch = forward
    provider, restore = segment_capture.install_prefill_segment_capture(scheduler, tmp_path, lambda _: None)
    assert scheduler.engine.forward_batch(outer) == "ok"
    scheduler.engine.forward_batch = lambda *_: None
    with pytest.raises(RuntimeError, match="ownership changed"):
        restore()
