import importlib.util
import json
import math
import os
import socket
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("d10v7", HERE / "d10_prototype_owned_parent_v7.py")
m = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(m)
p = m.runner().parser()


def raw(request_id, completion=256, speed=31.0, ttft=1.0):
    return {"metadata": {"x_request_id": request_id}, "metrics": {"usage_completion_tokens": {"value": completion}, "output_token_count": {"value": completion}, "time_to_first_token": {"value": ttft}, "output_token_throughput_per_user": {"value": speed}}}


def profile(root, rows):
    root.mkdir(exist_ok=True); (root / "profile_export.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")


def test_parser_rejects_nan_empty_id_low_speed_and_short_fixed(tmp_path):
    profile(tmp_path / "nan", [raw("a", speed=math.nan), raw("b")])
    with pytest.raises(RuntimeError, match="non-finite"): p.fixed_gate(tmp_path / "nan")
    profile(tmp_path / "id", [raw(""), raw("b")])
    with pytest.raises(RuntimeError, match="invalid AIPerf"): p.fixed_gate(tmp_path / "id")
    profile(tmp_path / "slow", [raw("a", speed=1), raw("b", speed=1)])
    with pytest.raises(RuntimeError, match="decode speed"): p.fixed_gate(tmp_path / "slow")
    profile(tmp_path / "short", [raw("a", 1), raw("b", 256)])
    with pytest.raises(RuntimeError, match="exactly"): p.fixed_gate(tmp_path / "short")


def test_r045_fixture_is_only_known_gpu_fixture_and_does_not_fake_threshold():
    rows = p.parse_profile(HERE / "fixtures" / "wave1")
    assert [x["completion_tokens"] for x in rows] == [46, 58]
    with pytest.raises(RuntimeError, match="decode speed"): p.original_gate(HERE / "fixtures" / "wave1")


def readonly(path, value):
    path.write_text(json.dumps(value)); os.chmod(path, 0o444)
    return {"path": str(path), "sha256": m.sha(path), "verdict": value.get("verdict", "kept")}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); value = s.getsockname()[1]; s.close(); return value


def admission(tmp_path):
    api = free_port(); base = {"schema": "ft_d10_prototype_v7_admission/v1", "admit": True, "prototype_rid": m.RID, "candidate": m.CANDIDATE, "parent": m.PARENT, "d10_flag": m.FLAG, "calls_max": 8, "services_max": 1, "source_sha256": m.source_hashes(), "runner_source_sha256": m.runner().source_hashes(), "service": {"argv": ["ft", "serve", "--port", str(api), m.FLAG], "api_port": api, "tcpstore_port": api + 1, "endpoint": f"http://127.0.0.1:{api}", "cwd": str(tmp_path)}, "prototype_output": str(tmp_path / "out")}
    for name in ("t16_round", "t16_manifest", "t16_history", "d09_terminal", "d09_manifest", "d09_cleanup"):
        verdict = "failed_harness" if name == "d09_terminal" else "kept"
        base[name] = readonly(tmp_path / (name + ".json"), {"verdict": verdict})
    native_copy = tmp_path / "native_provenance.json"
    native_copy.write_bytes(m.NATIVE_PROVENANCE.read_bytes()); os.chmod(native_copy, 0o444)
    base["native_provenance"] = {"path": str(native_copy), "sha256": m.sha(native_copy), "verdict": "kept"}
    path = tmp_path / "admission.json"; readonly(path, base); return path, base


def test_admission_rejects_fake_t16_d09_and_input_source_drift(tmp_path):
    path, doc = admission(tmp_path)
    # Declaration-only values cannot replace hash-bound objects.
    altered = dict(doc); altered["t16_round"] = {"kept": True}; bad = tmp_path / "bad.json"; readonly(bad, altered)
    with pytest.raises(RuntimeError, match="binding is absent"): m.require_admission(bad)
    altered = dict(doc); altered["runner_source_sha256"] = {"inputs_r045_v7.jsonl": "0" * 64}; bad2 = tmp_path / "drift.json"; readonly(bad2, altered)
    with pytest.raises(RuntimeError, match="runtime source"): m.require_admission(bad2)
    assert m.require_admission(path)["d09_terminal"]["verdict"] == "failed_harness"


class Life:
    def stop_owned_process(self, *_): pass
    def owned_group_alive(self, *_): return False


class Gate:
    def __init__(self, root, *, idle=True, receipt=True): self.root=root; self.LOCK=root/"gpu.lock"; self.idle=idle; self.receipt=receipt; self.released=False
    def require_child_receipt(self, *_args, **_kwargs):
        if not self.receipt: raise RuntimeError("wrongbirth")
    def take_d07_gpu_lock(self, *_): self.LOCK.write_text("owned"); return {"owned": True}
    def release_d07_gpu_lock(self, *_): self.released=True; self.LOCK.unlink()
    def require_gpu_idle(self):
        if not self.idle: raise RuntimeError("GPU is not idle")
    def clean_environment(self, *_): return {}
    def load_owned_lifecycle(self): return Life()


class Proc:
    pid = 123
    def poll(self): return None


class Deps:
    def __init__(self, root, doc, *, mode="success", idle=True, receipt=True, cleanup=True): self.gate=Gate(root, idle=idle, receipt=receipt); self.run=m.runner(); self.doc=doc; self.mode=mode; self.cleanup=cleanup; self.dispatched=[]
    def start(self, *_): return Proc()
    def health(self, *_): return {"status": "ok"}
    def dispatch(self, _endpoint, output, index):
        self.dispatched.append(index)
        if self.mode == "dispatch" and index == 1: raise RuntimeError("tooling missing raw")
        target=output/f"profile{index}"; target.mkdir(); tokens=64 if index < 2 else 256; speed=31 if self.mode != "slow" else 1
        profile(target, [raw(f"{index}a", tokens, speed), raw(f"{index}b", tokens, speed)])
        event=Path(self.doc["prototype_output"])/"d10_branch_event.json"; event.write_text(json.dumps({"actual_batch_reqs": 2 if self.mode != "partial" else 1, "actual_can_use_d10_staggered": True}))
    def stop(self, *_):
        if not self.cleanup: raise RuntimeError("cleanupfail")
    def alive(self, *_): return False


@pytest.mark.parametrize("mode,expected,calls", [("success", "measured_pending_independent_review", 8), ("slow", "not_met", 8), ("partial", "not_met", 8), ("dispatch", "failed_harness", 4)])
def test_same_body_child_truth_and_budget(tmp_path, mode, expected, calls):
    path, doc = admission(tmp_path); receipt=tmp_path/"launch.json"; readonly(receipt, {"state": "launched"}); deps=Deps(tmp_path, doc, mode=mode)
    if expected == "measured_pending_independent_review": terminal=m.child(path, 4, receipt, deps)
    else:
        with pytest.raises(RuntimeError): m.child(path, 4, receipt, deps)
        terminal=Path(doc["prototype_output"])/"terminal.json"
    result=json.loads(terminal.read_text()); assert result["verdict"] == expected and result["actual_generation_calls"] == calls and deps.gate.released


def test_busy_gpu_wrong_birth_and_cleanup_failure_do_not_unlock(tmp_path):
    path, doc=admission(tmp_path); receipt=tmp_path/"launch.json"; readonly(receipt,{"state":"launched"})
    for mode, kwargs, released in (("busy", {"idle":False}, True), ("birth", {"receipt":False}, False), ("cleanup", {"cleanup":False}, False)):
        target=tmp_path/mode; target.mkdir(); changed=dict(doc); changed["prototype_output"]=str(target/"out"); ad=target/"a.json"; readonly(ad,changed); deps=Deps(target,changed,**kwargs)
        with pytest.raises(RuntimeError): m.child(ad, 4, receipt, deps)
        assert deps.gate.released is released
