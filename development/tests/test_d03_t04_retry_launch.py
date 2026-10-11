from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "d03_t04_retry_launch.py"
SPEC = importlib.util.spec_from_file_location("d03_t04_retry_launch_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_r015_launcher_is_inert_until_root_freezes_bundle(monkeypatch):
    monkeypatch.setattr(launcher, "FROZEN_RETRY_BUNDLE", None)
    with pytest.raises(RuntimeError, match="TODO: root must freeze"):
        launcher.verify_reviewed_sources()


def test_missing_reviewed_retry_tool_fails_closed(monkeypatch, tmp_path):
    bundle = {
        "t04_logits_retry.py": "0" * 64,
        "t04_capture_controlled.py": launcher.sha256(launcher.CONTROLLED_CLIENT),
    }
    monkeypatch.setattr(launcher, "FROZEN_RETRY_BUNDLE", bundle)
    monkeypatch.setattr(launcher, "RETRY_RUNNER", tmp_path / "missing_retry.py")
    with pytest.raises(ValueError, match="absent"):
        launcher.verify_reviewed_sources()


def test_cli_without_linux_run_never_calls_launch(monkeypatch):
    launched = []
    monkeypatch.setattr(launcher, "launch", lambda: launched.append(True))
    monkeypatch.setattr(launcher.sys, "argv", [str(MODULE_PATH), "--run"])
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    with pytest.raises(SystemExit):
        launcher.main()
    assert launched == []


def test_receipt_is_exclusive_then_atomically_published_with_inode_binding(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "DEV", tmp_path)
    path, inode = launcher.reserve_receipt(44)
    assert path.exists()
    assert __import__("json").loads(path.read_text())["state"] == "reserved"
    launcher.publish_receipt(path, inode, {"state": "launched", "rid": "E2-R015"})
    assert __import__("json").loads(path.read_text()) == {"state": "launched", "rid": "E2-R015"}
    with pytest.raises(FileExistsError):
        launcher.reserve_receipt(44)


def test_preflight_validates_selfcheck_raw_binding_and_gate_before_reservation(monkeypatch, tmp_path):
    token_path = tmp_path / "tokens.json"
    binding_path = tmp_path / "binding.json"
    trace_path = tmp_path / "trace.json"
    for path in (token_path, binding_path, trace_path):
        path.write_text("{}")
    monkeypatch.setattr(
        launcher,
        "arguments",
        lambda batch: [
            "--g4-token-file", str(token_path), "--raw-binding-manifest", str(binding_path),
            "--trace", str(trace_path),
        ],
    )
    calls = []

    class Inherited:
        @staticmethod
        def read_token_record(path, max_k):
            calls.append("token")
            return {"token": True}

        @staticmethod
        def verify_g4_source(sc, token, binding, trace, candidate):
            calls.append("selfcheck")

        @staticmethod
        def read_binding(path, token):
            calls.append("binding")
            return {"trace_sha256": "trace", "messages_sha": "messages", "request_sha256": "request"}

        @staticmethod
        def sha256(path):
            return "trace"

    class Selfcheck:
        LEGACY_REPLAY = tmp_path / "legacy.json"

        @staticmethod
        def trace_record(path):
            calls.append("trace")
            return {}, {"messages_sha": "messages"}, {}

        @staticmethod
        def historical_payload(document, messages, legacy):
            return {"request": True}

        @staticmethod
        def request_sha(payload):
            return "request"

    Selfcheck.LEGACY_REPLAY.write_text("{}")

    class Runner:
        def __init__(self, args):
            self.inherited = Inherited()
            self.phase = type("Phase", (), {"sc": Selfcheck()})()

        def gate(self):
            calls.append("gate")

    extra = launcher.preflight(type("Module", (), {"RetryPhase2": Runner}), 44)
    assert extra[1] == str(token_path)
    assert calls == ["token", "selfcheck", "binding", "trace", "gate"]
