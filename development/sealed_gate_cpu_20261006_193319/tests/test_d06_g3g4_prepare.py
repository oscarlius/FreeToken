import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    "d06_g3g4_prepare", Path(__file__).parents[1] / "d06_g3g4_prepare.py"
)
d06 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d06)


def test_receipt_write_failure_cleans_started_service(monkeypatch, tmp_path):
    stopped = []
    process = SimpleNamespace(pid=123)
    owned = SimpleNamespace(
        process_identity=lambda pid: {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1},
        stop_owned_process=lambda child: stopped.append(child.pid),
    )
    monkeypatch.setattr(d06, "environment", lambda *args: {key: "" for key in (
        "CUDA_VISIBLE_DEVICES", "FT_DEV_PAUSE_ENDPOINT", "FT_DEV_D0", "FT_DEV_D0_PATH",
        "FT_DEV_D0_TIMELINE", "FT_DEV_D0_TIMELINE_STEPS", "PYTHONPATH", "VIRTUAL_ENV"
    )})
    monkeypatch.setattr(d06.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(d06, "load_owned_lifecycle", lambda: owned)
    def fail_write(*args):
        raise OSError("receipt disk failure")
    monkeypatch.setattr(d06, "write_new", fail_write)
    with pytest.raises(OSError, match="receipt disk failure"):
        d06.start_server(tmp_path, tmp_path, 43001)
    assert stopped == [123]


def test_foreign_lock_is_preserved_and_cannot_produce_success(monkeypatch, tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.write_text("owned")
    monkeypatch.setattr(d06, "LOCK", lock)
    monkeypatch.setattr(d06, "LOCK_TOKEN", "owned")
    monkeypatch.setattr(d06, "LOCK_INODE", lock.stat().st_ino)
    lock.write_text("foreign")
    with pytest.raises(RuntimeError, match="foreign/replaced"):
        d06.release_gpu_lock()
    assert lock.read_text() == "foreign"
