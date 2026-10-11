"""Scheduled references never consume their first request with SayOK."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import t17_d14_gpu as runner


def test_health_readiness_has_no_generation_request(tmp_path, monkeypatch):
    urls = []

    def request(url, **kwargs):
        urls.append(url)
        return io.BytesIO(json.dumps({"status": "ok"}).encode())

    monkeypatch.setattr(runner.urllib.request, "urlopen", request)
    run = object.__new__(runner.Run)
    run.proc = SimpleNamespace(poll=lambda: None)
    run.ready_health(tmp_path)
    assert urls == ["http://127.0.0.1:8095/health"]
    assert not (tmp_path / "ready_sayok.json").exists()
    assert json.loads((tmp_path / "health.json").read_text()) == {"status": "ok"}


def test_backend_error_stops_before_any_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.urllib.request, "urlopen",
                        lambda *args, **kwargs: io.BytesIO(b'{"status":"error"}'))
    run = object.__new__(runner.Run)
    run.proc = SimpleNamespace(poll=lambda: None)
    with pytest.raises(RuntimeError, match="backend error"):
        run.ready_health(tmp_path)


def test_schedule_cannot_use_generation_readiness_or_mutable_file(tmp_path):
    run = object.__new__(runner.Run)
    schedule = tmp_path / "schedule.json"
    schedule.write_text("[]")
    with pytest.raises(ValueError, match="health-only"):
        run.service("reference", lambda arm: None, schedule=schedule)
    with pytest.raises(ValueError, match="frozen"):
        run.service("reference", lambda arm: None, schedule=schedule, health_only=True)
