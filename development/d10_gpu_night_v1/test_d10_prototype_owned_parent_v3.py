import importlib.util
import json
import os
import socket
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("d10v3", Path(__file__).with_name("d10_prototype_owned_parent_v3.py"))
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return sock.getsockname()[1]


class Proc:
    pid = 12345
    def poll(self): return None


class Life:
    def __init__(self, gate): self.gate = gate; self.stopped = False
    def verified_module(self, *_): return self
    def next_batch(self, *_): return 7
    def reserve_process(self, _, batch, rid, argv, receipt, reserved):
        receipt.write_text(json.dumps(reserved | {"state": "launched", "batch_pid": 999}), encoding="utf-8")
        return {"batch_pid": 999}
    def stop_owned_process(self, *_): self.stopped = True
    def owned_group_alive(self, *_): return False


class Gate:
    ATOMIC_HELPER_SHA = "fake"; ROUNDS = Path("rounds")
    def __init__(self, root): self.root = root; self.LOCK = root / "gpu.lock"; self.life = Life(self); self.released = False
    def process_birth(self, pid=None): return {"pid": 999 if pid is None else pid, "start_ticks": 1}
    def process_identity(self, pid): return {"pid": pid, "start_ticks": 1}
    def argv_sha256(self, argv): return m.argv_sha(argv)
    def load_owned_lifecycle(self): return self.life
    def publish_child_binding(self, receipt, got, child, **_):
        value = json.loads(receipt.read_text()); value["child"] = child; receipt.write_text(json.dumps(value), encoding="utf-8"); return value
    def take_d07_gpu_lock(self, *_): self.LOCK.write_text("owned"); return "owner"
    def release_d07_gpu_lock(self, *_): self.released = True; self.LOCK.unlink()
    def clean_environment(self, *_): return {}
    def require_gpu_idle(self): return {"idle": True}
    def require_closed_round(self, rid, verdict):
        assert (rid, verdict) == ("E2-D10-T16-night-20261010", "kept")
        directory = self.root / "closed"; directory.mkdir(exist_ok=True)
        round_json = directory / "round.json"; manifest = directory / "MANIFEST.sha256"
        if not round_json.exists(): round_json.write_text('{"verdict":"kept"}'); manifest.write_text("round.json\n")
        return round_json


class Runner:
    def __init__(self, doc): self.doc = doc
    def require_admission(self, _): return self.doc


class Deps:
    def __init__(self, root, doc): self.root = root; self.gate = Gate(root); self.runner = Runner(doc); self.started = 0
    def validate_candidate(self): return {"head": m.CANDIDATE}
    def start(self, *_): self.started += 1; return Proc()
    def health(self, _): return {"status": "ok"}, object()
    def run_aiperf(self, _, __, output):
        output.mkdir();
        for index in range(4):
            (output / f"profile{index}.exit.json").write_text('{"exit_code": 0}')
            profile = output / f"profile{index}"; profile.mkdir()
            tokens = 64 if index < 2 else 256
            (profile / "raw.jsonl").write_text("\n".join(json.dumps({"completion_tokens": tokens}) for _ in range(2)))
        event = Path(self.event); event.write_text(json.dumps({"method": "Engine._forward_d10_staggered_decode", "entered": True, "eligible_lanes": 2, "candidate_commit": m.CANDIDATE, "service_pid": Proc.pid}))
    def stop(self, proc): self.gate.life.stop_owned_process(proc)
    def alive(self, _): return False
    def idle(self): return self.gate.require_gpu_idle()


def setup(tmp_path):
    api, tcp = free_port(), free_port(); output = tmp_path / "out"
    argv = ["/data2/FreeToken/venv/bin/python", "/data2/FreeToken/wt/d10-staggered-v1/python/freetoken/server/main.py", "--port", str(api), "--tcpstore-port", str(tcp), m.FLAG]
    doc = {"prototype_rid": m.RID, "candidate": m.CANDIDATE, "parent_commit": m.PARENT, "d10_flag": m.FLAG,
           "native_provenance_sha256": m.sha(m.PROVENANCE), "calls_max": 8, "services_max": 1,
           "service": {"argv": argv, "cwd": str(tmp_path), "endpoint": f"http://127.0.0.1:{api}", "api_port": api, "tcpstore_port": tcp},
           "prototype_output": str(output)}
    deps = Deps(tmp_path, doc); deps.event = output / "d10_branch_event.json"; admission = tmp_path / "admission.json"; admission.write_text("{}")
    round_json = deps.gate.require_closed_round("E2-D10-T16-night-20261010", "kept"); manifest = round_json.with_name("MANIFEST.sha256")
    doc["t16_closure"] = {"rid": "E2-D10-T16-night-20261010", "verdict": "kept", "round_json_sha256": m.sha(round_json), "manifest_sha256": m.sha(manifest)}
    os.chmod(admission, 0o444)
    return deps, admission, output


def test_actual_controller_child_body_completes_eight_call_prototype(tmp_path):
    deps, admission, output = setup(tmp_path)
    binding = m.controller(admission, deps)
    terminal = m.child(admission, binding["batch"], deps.root / "launch.json", deps)
    value = json.loads(terminal.read_text())
    assert deps.started == 1 and value["services"] == 1 and value["generation_calls_expected"] == 8
    assert value["source_branch_entered"] and value["post_cleanup_closed"] and deps.gate.released


def test_health_process_failure_cleans_owned_lock(tmp_path):
    deps, admission, _ = setup(tmp_path); binding = m.controller(admission, deps)
    deps.start = lambda *_: type("Dead", (), {"pid": 55, "poll": lambda self: 1})()
    with pytest.raises(RuntimeError, match="exited before health"):
        m.child(admission, binding["batch"], deps.root / "launch.json", deps)
    assert deps.gate.life.stopped and deps.gate.released


def test_wrong_receipt_rejects_before_service_start(tmp_path):
    deps, admission, _ = setup(tmp_path); binding = m.controller(admission, deps)
    receipt = deps.root / "launch.json"; value = json.loads(receipt.read_text()); value["candidate_commit"] = "wrong"; receipt.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="receipt binding"):
        m.child(admission, binding["batch"], receipt, deps)
    assert deps.started == 0 and not deps.gate.LOCK.exists()


def test_unsafe_actual_port_rebind_retains_lock(tmp_path, monkeypatch):
    deps, admission, _ = setup(tmp_path); binding = m.controller(admission, deps); original = m.reserve_pair; calls = []
    def fail_after_start(api, tcp):
        calls.append((api, tcp))
        if len(calls) > 1: raise OSError("actual service port cannot rebind")
        return original(api, tcp)
    monkeypatch.setattr(m, "reserve_pair", fail_after_start)
    with pytest.raises(RuntimeError, match="unsafe cleanup preserves GPU lock"):
        m.child(admission, binding["batch"], deps.root / "launch.json", deps)
    assert deps.gate.life.stopped and not deps.gate.released and deps.gate.LOCK.exists()
