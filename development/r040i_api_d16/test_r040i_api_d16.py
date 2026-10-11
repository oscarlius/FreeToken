"""CPU-only contract for the R040i preparation adapter."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("r040i", HERE / "r040i_api_d16.py")
mod = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(mod)


def test_final_argv_preserves_r040h_limits_and_removes_native_capture_env(monkeypatch):
    source = HERE / "fake_d07.py"
    source.write_text("def serve_argv(p): return ['ft','serve','--memory-ratio','0.88','--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','49152','--max-seq-len-override','49152']\n")
    try:
        with patch.object(mod, "D07", source):
            command = mod.argv(12345)
        assert command[:3] == ["numactl", "--cpunodebind=0,1", "--interleave=all"]
        assert [command[command.index(flag) + 1] for flag in ("--max-running-requests", "--cuda-graph-max-bs", "--kv-reserve-tokens", "--max-seq-len-override")] == ["4", "4", "98304", "98304"]
    finally: source.unlink(missing_ok=True)


def test_filedry_branch_never_calls_run(monkeypatch, capsys):
    value = {"candidate": {"commit": mod.CANDIDATE}, "serve_argv": ["ft"], "scope": "interleave6_services_8_calls_only"}
    monkeypatch.setattr(mod, "packet", lambda: value)
    monkeypatch.setattr(mod, "launch_owned", lambda: (_ for _ in ()).throw(AssertionError("launch called")))
    assert mod.main(["--filedry"]) == 0
    assert "no_rid_batch_lock_popen_or_request" in capsys.readouterr().out
