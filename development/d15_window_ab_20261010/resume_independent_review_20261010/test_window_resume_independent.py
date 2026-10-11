"""Review-owned CPU behavior checks for the one-service W128 resume wrapper."""
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).parent
SOURCE = HERE.parent / "window_resume.py"
spec = importlib.util.spec_from_file_location("review_window_resume", SOURCE)
resume = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resume
spec.loader.exec_module(resume)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def harness(tmp_path, monkeypatch, mismatch=False):
    starts, calls = [], []
    port, master = free_port(), free_port()
    seed = []
    for i in range(8):
        path = tmp_path / f"seed-{i}.json"
        path.write_text("{}")
        seed.append(path)

    class Proc:
        pid = 99991

    class Lifecycle:
        def stop_owned_process(self, *args, **kwargs):
            return None

        def owned_group_alive(self, *args):
            return False

    class Deps:
        root = tmp_path
        lifecycle = Lifecycle()
        active_process = None
        adapter = client = producer = object()
        sampler = None
        system_uptime = staticmethod(lambda: 1.0)
        gpu_idle = staticmethod(lambda: True)
        cleanup_safe = True

        @staticmethod
        def start(record, run, lifecycle, deadline):
            run.mkdir()
            starts.append(record["arm"])
            return Proc(), open(run / "serve.log", "w"), run / "observer", 0

        @staticmethod
        def frontend(payload):
            return [0] * 100223

        @staticmethod
        def slot_check(*args):
            return {"actual_slots": 2401}

        @staticmethod
        def window_payload(path):
            path.write_text(json.dumps({"max_tokens": 2048}))
            return path

        @staticmethod
        def next_b_payload(old, path, *args):
            path.write_text(json.dumps({"max_tokens": 2048}))
            return path

        @staticmethod
        def cold_payload(path):
            path.write_text(json.dumps({"max_tokens": 256}))
            return path

    Deps.seed_payloads = seed

    def invoke(*args, **kwargs):
        calls.append(args[3])
        token = "mismatch" if mismatch and len(calls) == 1 else "same"
        return ({"native_token_sha256": token, "completion_tokens": 2,
                 "decode_elapsed_s": 1.0, "cached_tokens": 0,
                 "min_free_gpu_mib": 1}, {})

    monkeypatch.setattr(resume.w, "invoke", invoke)
    packet = {"input_sha256": [resume.w.sha(p) for p in seed], "arms": [
        {"arm": "W98K", "port": 1, "master_port": 2, "window": 98304, "expected_auto_slots": 2700},
        {"arm": "W128K", "port": port, "master_port": master, "window": 131072, "expected_auto_slots": 2401},
    ]}
    previous = {"A": [{"native_token_sha256": "same", "completion_tokens": 2,
                       "decode_elapsed_s": 1.0} for _ in range(8)], "slots": {"actual_slots": 2700}}
    return packet, Deps(), previous, starts, calls


def test_resume_starts_only_w128_and_makes_13_calls(tmp_path, monkeypatch):
    packet, deps, previous, starts, calls = harness(tmp_path, monkeypatch)
    result = resume.measure(packet, {}, deps, previous, 10**12)
    assert starts == ["W128K"] and len(calls) == 13
    assert result["actual_new_services"] + result["previous_actual_services"] == 2
    assert len(result["W98K"]["A"]) == 8 and len(result["W128K"]["B"]) == 4


def test_resume_stops_after_first_native_mismatch(tmp_path, monkeypatch):
    packet, deps, previous, starts, calls = harness(tmp_path, monkeypatch, mismatch=True)
    with pytest.raises(RuntimeError, match="mismatch 1"):
        resume.measure(packet, {}, deps, previous, 10**12)
    assert starts == ["W128K"] and len(calls) == 1
