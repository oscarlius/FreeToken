from __future__ import annotations

import json

from freetoken.scheduler.scheduler import _write_dev_oom_receipt


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
