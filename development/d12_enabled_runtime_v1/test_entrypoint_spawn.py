"""Actual CLI parsing and Python spawn entry; no API service or model load."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SOURCE = os.environ.get("FT_D12_NATIVE_SOURCE")
if not SOURCE:
    pytest.skip("requires the Linux candidate CLI dependencies", allow_module_level=True)

from test_replay_binding import BUNDLE, BUNDLE_SHA


def environment(tmp_path):
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1",
           "FT_D12_DIAGNOSTIC": "1", "FT_D12_CAPTURE_POLICY": "natural-terminal-v1",
           "FT_D12_REPLAY_INPUT_DIR": str(BUNDLE), "FT_D12_REPLAY_INPUT_SHA256": BUNDLE_SHA,
           "FT_D16_SERVICE_CAPTURE_DIR": str(tmp_path / "dev_D16/capture"),
           "FT_D12_MAX_EVENTS": "1024", "FT_D12_MAX_EVENT_BYTES": "1000000",
           "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), str(Path(SOURCE) / "python"),
                                        str(Path(SOURCE) / "scripts")])}
    for key in ("FT_DEV_STATE_DUMP", "FT_DEV_ROUTE_TRACE", "FT_D16_CACHE_INIT", "FT_D16_PARK_RESTORE",
                "FT_D16_SERVICE_CAPTURE_EXPECTED_JSON"):
        env.pop(key, None)
    return env


def retain(tmp_path, result):
    (tmp_path / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (tmp_path / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_cli_help_reaches_candidate_argument_parser_without_capture(tmp_path):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("worker_capture.py")), "serve", "--help"],
                            env=environment(tmp_path), capture_output=True, text=True, timeout=45)
    retain(tmp_path, result)
    assert "--moe-prefill-routed-only-max-tokens" in result.stdout
    assert "--disable-moe-prefill-overlap" in result.stdout
    assert not (tmp_path / "dev_D16/capture").exists()


def test_main_module_worker_target_survives_real_spawn_and_reaches_its_guard(tmp_path):
    # Substitute the CLI dispatch at its boundary so the actual main script can
    # register its __main__.run_scheduler target, then spawn that exact target.
    # A TP=2 argument deliberately stops inside D12 before any model/CUDA owner.
    probe = tmp_path / "spawn_probe.py"
    worker = Path(__file__).with_name("worker_capture.py")
    probe.write_text('''import json, multiprocessing as mp, os, runpy, sys
from pathlib import Path
from types import SimpleNamespace
from freetoken import cli
from freetoken.server import launch

def dispatch(argv=None):
    target = launch._run_scheduler
    assert target.__name__ == "run_scheduler" and target.__module__ == "__main__"
    child = mp.get_context("spawn").Process(target=target, args=(SimpleNamespace(tp_info=SimpleNamespace(size=2)), None))
    child.start()
    child.join(20)
    if child.is_alive():
        child.terminate(); child.join(5)
        raise RuntimeError("owned spawn guard probe timed out")
    assert child.exitcode == 1
    print(json.dumps({"target_module": target.__module__, "target_name": target.__name__,
                      "child_pid": child.pid, "child_exitcode": child.exitcode,
                      "scope": "spawn target import and TP guard only; no API/model/GPU"}))
    return 0

if __name__ == "__main__":
    cli.main = dispatch
    sys.argv = [os.environ["D12_ENTRY_WORKER"], "serve"]
    runpy.run_path(os.environ["D12_ENTRY_WORKER"], run_name="__main__")
''', encoding="utf-8")
    env = {**environment(tmp_path), "D12_ENTRY_WORKER": str(worker)}
    result = subprocess.run([sys.executable, str(probe)], env=env, capture_output=True, text=True, timeout=45)
    retain(tmp_path, result)
    assert "ValueError: D12 initial diagnostic is TP=1 only" in result.stderr
    assert "ImportError" not in result.stderr and "PicklingError" not in result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["target_module"] == "__main__" and report["child_exitcode"] == 1
    assert not (tmp_path / "dev_D16/capture").exists()
    (tmp_path / "spawn_result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
