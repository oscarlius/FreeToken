from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import torch

from freetoken.scheduler.scheduler import ForwardInput, Scheduler, _write_dev_oom_receipt


def test_dev_oom_receipt_is_opt_in_and_binds_uid_epoch_and_point(tmp_path, monkeypatch) -> None:
    path = tmp_path / "receipt.json"
    _write_dev_oom_receipt(uid=3, epoch=2, point="before_forward")
    assert not path.exists()
    monkeypatch.setenv("FT_DEV_OOM_RECEIPT_PATH", str(path))
    _write_dev_oom_receipt(uid=3, epoch=2, point="before_forward")
    assert not path.exists()
    monkeypatch.setenv("FT_DEV_OOM_INJECT", "1")
    _write_dev_oom_receipt(uid=3, epoch=2, point="before_forward")
    payload = json.loads(path.read_text())
    assert payload["schema"] == "ft_dev_oom_receipt/v1"
    assert payload["uid"] == 3 and payload["epoch"] == 2
    assert payload["point"] == "before_forward" and payload["count"] == 1
    assert isinstance(payload["pid"], int) and payload["monotonic_ns"] > 0


def test_scheduler_before_forward_injection_writes_matched_uid_epoch_then_raises(tmp_path, monkeypatch) -> None:
    receipt = tmp_path / "receipt.json"
    matched = SimpleNamespace(uid=17, epoch=23)
    batch = SimpleNamespace(reqs=[SimpleNamespace(uid=4, epoch=5), matched])
    scheduler = object.__new__(Scheduler)
    monkeypatch.setenv("FT_DEV_OOM_INJECT", "1")
    monkeypatch.setenv("FT_DEV_OOM_UID", "17")
    monkeypatch.setenv("FT_DEV_OOM_POINT", "before_forward")
    monkeypatch.setenv("FT_DEV_OOM_RECEIPT_PATH", str(receipt))

    with pytest.raises(torch.cuda.OutOfMemoryError, match="uid=17 point=before_forward"):
        scheduler._forward(ForwardInput(batch, None, None, None))

    payload = json.loads(receipt.read_text())
    assert payload["uid"] == 17
    assert payload["epoch"] == 23
    assert payload["point"] == "before_forward"
    assert scheduler._dev_oom_used is True


def test_scheduler_default_forward_does_not_enter_dev_injection(tmp_path, monkeypatch) -> None:
    receipt = tmp_path / "receipt.json"
    batch = SimpleNamespace(reqs=[SimpleNamespace(uid=17, epoch=23)], is_prefill=True)
    engine = SimpleNamespace(forward_batch=lambda got_batch, got_args: SimpleNamespace(next_tokens_gpu="next"))
    decode = SimpleNamespace(filter_reqs=lambda reqs: None)
    scheduler = object.__new__(Scheduler)
    scheduler.engine = engine
    scheduler.decode_manager = decode
    scheduler.token_pool = {0: "input"}
    scheduler.toolcall_anchor_id = None
    monkeypatch.setenv("FT_DEV_OOM_INJECT", "0")
    monkeypatch.setenv("FT_DEV_OOM_UID", "17")
    monkeypatch.setenv("FT_DEV_OOM_POINT", "before_forward")
    monkeypatch.setenv("FT_DEV_OOM_RECEIPT_PATH", str(receipt))

    output = scheduler._forward(ForwardInput(batch, None, 0, 1))

    assert output.next_tokens_gpu == "next"
    assert batch.input_ids == "input"
    assert scheduler.token_pool[1] == "next"
    assert not receipt.exists()
    assert not hasattr(scheduler, "_dev_oom_used")
