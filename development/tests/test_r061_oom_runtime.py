"""CPU-only contracts for the R061 real fault runner.

The tests deliberately replace every network/GPU seam.  They prove the runner
will reject weak receipts rather than pretending a Python exception is API
evidence.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]


def load(name="r061_runtime"):
    spec = importlib.util.spec_from_file_location(name, DEV / "r061_oom_fault_prepare_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_fault_startup_uses_one_observer_directory_per_worker(tmp_path):
    module = load()
    value = module.write_fault_startup(tmp_path / "run")
    text = Path(value["startup"]).read_text(encoding="utf-8")
    assert '"workers",str(os.getpid())' in text
    assert "Engine.forward_batch" not in text
    assert "torch.cuda.OutOfMemoryError" not in text


def test_recovery_contract_requires_control_surface_when_present(tmp_path):
    module = load("r061_recovery")
    root = tmp_path / "wt" / "python" / "freetoken"
    (root / "server").mkdir(parents=True)
    (root / "engine").mkdir()
    (root / "server" / "api_server.py").write_text(
        'RESTART_READY_TIMEOUT_S = 900.0\nRESTART_QUEUE_MAX = 128\nmaintenance_state = "restarting"\nbackend_epoch += 1\n'
    )
    (root / "server" / "supervisor.py").write_text("restart_backend\nmax_restarts\n")
    (root / "engine" / "engine.py").write_text("def forward_batch(): pass\n")
    (root / "server" / "control_api.py").write_text('@app.get("/health")\nrestart_waiters\n')
    (root / "server" / "stats.py").write_text('"recovery"\nrestart_waiters\n')
    assert len(module.recovery_contract(tmp_path / "wt")) == 5
    (root / "server" / "stats.py").write_text('"recovery"\n')
    with pytest.raises(RuntimeError, match="control fields"):
        module.recovery_contract(tmp_path / "wt")


def test_file_dry_reuses_writer_and_never_reserves_service_or_round(tmp_path, monkeypatch):
    module = load("r061_dry")
    wt = tmp_path / "wt"
    (wt / "python" / "freetoken" / "server").mkdir(parents=True)
    (wt / "python" / "freetoken" / "engine").mkdir()
    (wt / "python" / "freetoken" / "server" / "api_server.py").write_text('maintenance_state = "restarting"\nbackend_epoch += 1\n')
    (wt / "python" / "freetoken" / "server" / "supervisor.py").write_text("restart_backend\nmax_restarts\n")
    (wt / "python" / "freetoken" / "engine" / "engine.py").write_text("def forward_batch(): pass\n")
    (wt / "python" / "freetoken" / "scheduler").mkdir()
    (wt / "python" / "freetoken" / "scheduler" / "scheduler.py").write_text("FT_DEV_OOM_INJECT FT_DEV_OOM_UID FT_DEV_OOM_POINT FT_DEV_OOM_RECEIPT_PATH before_forward _dev_oom_used torch.cuda.OutOfMemoryError")
    inputs = []
    for name in ("reference", "affected", "queued"):
        path = tmp_path / f"{name}.json"; path.write_text("{}", encoding="utf-8"); inputs.append(path)
    def writer(path, doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(doc, handle, sort_keys=True); handle.write("\n")
        path.chmod(0o600)
    fake = SimpleNamespace(candidate_binding=lambda *_: {}, private_port_pair=lambda: {"api": 31234, "tcpstore": 31235, "probe": "bind-only"}, PORT_PAIR=module.HERE / "ft_batch_port_pair_v1.py", write_new=writer)
    monkeypatch.setattr(module, "r060", lambda: fake)
    receipt = module.file_dry(tmp_path / "dry", "a" * 40, wt, *inputs)
    saved = tmp_path / "dry" / "receipt.json"
    assert receipt["service_started"] is False and receipt["requests_sent"] is False
    assert receipt["gpu_lock_taken"] is False and receipt["batch_allocated"] is False
    assert saved.stat().st_mode & 0o222 == 0
    assert set(receipt["output_probes"]) >= {"health.restarting.json", "affected.api.sse", "result.json"}
    if os.name != "nt":
        assert all(row["mode"] == "0o600" for row in receipt["source_copies"])


def test_restart_waiter_requires_live_thread_and_health_fields(monkeypatch):
    module = load("r061_waiter")
    class Thread:
        def is_alive(self): return True
    rows = iter((
        {"maintenance": "serving", "backend_epoch": 0, "restart_attempts": 0, "restart_waiters": 0},
        {"maintenance": "restarting", "backend_epoch": 1, "restart_attempts": 1, "restart_waiters": 1},
    ))
    monkeypatch.setattr(module, "_health", lambda _: next(rows))
    assert module._wait_for_restarting("http://127.0.0.1:1234/v1", Thread(), module.time.monotonic() + 1)["restart_waiters"] == 1


def test_raw_api_error_and_epoch_snapshots_reject_weak_evidence(tmp_path):
    module = load("r061_evidence")
    raw = tmp_path / "affected.sse"
    raw.write_text('data: {"error":{"message":"worker_restarting_after_oom"}}\n', encoding="utf-8")
    assert module._api_error(raw)["api_error"] == "worker_restarting_after_oom"
    raw.write_text('data: {"choices": []}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="API error"):
        module._api_error(raw)
    worker = tmp_path / "observer" / "workers" / "101"; worker.mkdir(parents=True)
    worker.joinpath("inputs.jsonl").write_text('{"uid": 7}\n', encoding="utf-8")
    worker.joinpath("tokens.jsonl").write_text('{"uid": 7}\n', encoding="utf-8")
    epoch = module._epoch_observer(tmp_path / "observer", 3, 7)
    assert epoch.name == "epoch-3" and epoch.joinpath("inputs.jsonl").is_file()
