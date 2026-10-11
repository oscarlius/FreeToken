import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "d07_g3g4_prepare.py"
SPEC = importlib.util.spec_from_file_location("d07_g3g4_prepare", PATH)
d07 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d07)


def test_ephemeral_port_is_never_the_shared_service_port():
    port = d07.dynamic_fixture_port()
    assert 1024 <= port <= 65535
    assert port != 8095


def test_g3_requires_utf8_text_equality(tmp_path):
    off, on = tmp_path / "off.json", tmp_path / "on.json"
    record = {"cold_id": "same", "finish_reason": "stop", "built_tokens": 32052, "completion_tokens": 4}
    off.write_text(json.dumps({"record": record, "text": "逐字相同"}), encoding="utf-8")
    on.write_text(json.dumps({"record": record, "text": "逐字相同"}), encoding="utf-8")
    got = d07.g3_compare(off, on)
    assert got["byte_identical"] is True
    assert got["text_utf8_sha256"] == hashlib.sha256("逐字相同".encode()).hexdigest()
    on.write_text(json.dumps({"record": record, "text": "不同"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="G3 failed"):
        d07.g3_compare(off, on)


def test_prepared_packet_labels_cpu_guard_and_non_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(d07, "checked_worktree", lambda path: {"worktree": str(path), "commit": d07.CANDIDATE, "tracked_clean": True})
    monkeypatch.setattr(d07, "verify_d07_tools", lambda path: {"verified": True})
    monkeypatch.setattr(d07, "verify_frozen_cold_helpers", lambda path: {"frozen": True})
    monkeypatch.setattr(d07, "dynamic_fixture_port", lambda: 43001)
    packet = d07.prepared_packet(tmp_path)
    assert packet["fixture_port"] == 43001
    assert packet["cuda_visible_devices_cpu_guard"] == ""
    assert packet["run_requires"] == ["explicit --run", "Linux host", "R041 D04 kept", "T20 E2-R040 D04 kept", "atomic D07 O_EXCL lock", "GPU idle gate"]
    assert packet["timing"].startswith("not a performance")


def test_g3_rejects_different_ids_and_missing_response_fields(tmp_path):
    off, on = tmp_path / "off.json", tmp_path / "on.json"
    good = {"record": {"cold_id": "off", "finish_reason": "stop", "built_tokens": 32052, "completion_tokens": 1}, "text": "x"}
    off.write_text(json.dumps(good), encoding="utf-8")
    on.write_text(json.dumps({**good, "record": {**good["record"], "cold_id": "on"}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="IDs differ"):
        d07.g3_compare(off, on)
    on.write_text(json.dumps({"record": {"cold_id": "off"}, "text": ""}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete"):
        d07.g3_compare(off, on)


def test_candidate_frozen_companion_hash_mismatch_fails_before_gpu(tmp_path):
    scripts = tmp_path / "scripts"; scripts.mkdir()
    (scripts / "agent_trace.py").write_text('_SHA256 = "' + "0" * 64 + '"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_text("changed\n", encoding="utf-8")
    (scripts / "route_analyze.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="frozen companion hash mismatch"):
        d07.verify_d07_tools(tmp_path)


def test_linux_rejects_normalized_only_companion_binding(monkeypatch, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    companion = b"pass\r\n"
    expected = hashlib.sha256(b"pass\n").hexdigest()
    (scripts / "agent_trace.py").write_text('_SHA256 = "' + expected + '"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_bytes(companion)
    (scripts / "route_analyze.py").write_bytes(b"pass\n")
    monkeypatch.setattr(d07.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="frozen companion hash mismatch"):
        d07.verify_d07_tools(tmp_path)


def test_candidate_frozen_companion_accepts_crlf_checkout_when_lf_pin_matches(tmp_path):
    scripts = tmp_path / "scripts"; scripts.mkdir()
    payload = b"one\ntwo\n"
    digest = hashlib.sha256(payload).hexdigest()
    (scripts / "agent_trace.py").write_text(f'_SHA256 = "{digest}"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_bytes(payload.replace(b"\n", b"\r\n"))
    (scripts / "route_analyze.py").write_text("pass\n", encoding="utf-8")
    assert d07.verify_d07_tools(tmp_path)["frozen_companion_lf_sha256"] == digest


def test_cold_adapter_preloads_owned_probe_before_raw_cold_import(monkeypatch, tmp_path):
    helpers = tmp_path / "helpers/raw"; helpers.mkdir(parents=True)
    probe = helpers / "probe_ft_cold32k.py"
    probe.write_text('URL="live-url"\n', encoding="utf-8")
    cold = helpers / "cold_eq.py"
    cold.write_text(
        'import json,sys\nsys.path.insert(0,"/definitely-not-live")\nfrom probe_ft_cold32k import URL\n'
        'json.dump({"url":URL},open(sys.argv[2],"w"))\n', encoding="utf-8"
    )
    monkeypatch.setattr(d07, "verify_frozen_cold_helpers", lambda _: {"verified": True})
    out = tmp_path / "cold.json"
    d07.invoke_cold_eq(tmp_path, 43001, "cold", out, tmp_path)
    assert json.loads(out.read_text(encoding="utf-8"))["url"] == "http://127.0.0.1:43001/v1/chat/completions"


def test_startup_failure_stops_entire_owned_process_group(monkeypatch, tmp_path):
    class Process:
        pid = 123
        returncode = None
        def poll(self): return None
    stopped = []
    class Owned:
        def stop_owned_process(self, process): stopped.append(process.pid)
        def process_identity(self, pid): return {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1}
    monkeypatch.setattr(d07.subprocess, "Popen", lambda *_, **__: Process())
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: Owned())
    ticks = iter((0, 901))
    monkeypatch.setattr(d07.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(d07, "clean_environment", lambda *_1, **_2: {})
    with pytest.raises(TimeoutError):
        d07.start_server(tmp_path, tmp_path, 43001, None)
    assert stopped == [123]


def test_process_receipt_failure_also_cleans_owned_group(monkeypatch, tmp_path):
    from types import SimpleNamespace
    process = SimpleNamespace(pid=123)
    stopped = []
    owned = SimpleNamespace(
        process_identity=lambda pid: {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1},
        stop_owned_process=lambda child: stopped.append(child.pid),
    )
    monkeypatch.setattr(d07.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: owned)
    monkeypatch.setattr(d07, "clean_environment", lambda *_1, **_2: {})
    def fail_write(*args):
        raise OSError("receipt disk failure")
    monkeypatch.setattr(d07, "write_new", fail_write)
    with pytest.raises(OSError, match="receipt disk failure"):
        d07.start_server(tmp_path, tmp_path, 43001, None)
    assert stopped == [123]


def test_d07_lock_is_exclusive_bound_and_refuses_foreign_release(monkeypatch, tmp_path):
    lock = tmp_path / "gpu.lock"
    monkeypatch.setattr(d07, "LOCK", lock)
    monkeypatch.setattr(d07, "process_birth", lambda: {"pid": 7, "start_ticks": 8, "execution_id": "7:8"})
    owner = d07.take_d07_gpu_lock("E2-R043", 69)
    assert json.loads(lock.read_text(encoding="utf-8"))["batch"] == 69
    with pytest.raises(RuntimeError, match="foreign GPU lock"):
        d07.take_d07_gpu_lock("E2-R043", 70)
    d07.release_d07_gpu_lock(owner)
    assert not lock.exists()
    lock.write_text("foreign", encoding="utf-8")
    with pytest.raises(RuntimeError, match="foreign/replaced"):
        d07.release_d07_gpu_lock(owner)


def test_failed_cleanup_preserves_lock_when_owned_group_is_live(monkeypatch, tmp_path):
    from types import SimpleNamespace
    closure = tmp_path / "kept.json"
    closure.write_text('{}')
    released = []
    monkeypatch.setattr(d07.sys, "platform", "linux")
    monkeypatch.setattr(d07, "require_r041_kept", lambda _: closure)
    monkeypatch.setattr(d07, "require_t20_kept", lambda: closure)
    owned = SimpleNamespace(
        verified_module=lambda *args: SimpleNamespace(next_batch=lambda _: 77),
        owned_group_alive=lambda _: True,
    )
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: owned)
    monkeypatch.setattr(d07, "take_d07_gpu_lock", lambda *args: {"batch": 77})
    monkeypatch.setattr(d07, "release_d07_gpu_lock", lambda owner: released.append(owner))
    monkeypatch.setattr(d07, "require_gpu_idle", lambda: [4])
    monkeypatch.setattr(d07, "prepared_packet", lambda _: {})
    def fail_start(*args):
        failure = RuntimeError("cleanup failed")
        failure.owned_process = SimpleNamespace(pid=123)
        raise failure
    monkeypatch.setattr(d07, "start_server", fail_start)
    with pytest.raises(RuntimeError, match="preserve GPU lock"):
        d07.execute(tmp_path, tmp_path / "runs")
    assert released == []
    assert not list((tmp_path / "runs").glob("*/owned_cleanup.json"))


