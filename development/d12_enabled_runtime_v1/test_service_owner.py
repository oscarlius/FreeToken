"""Real Linux CPU lifecycle plus exact pre-Popen D12 plan forwarding.

Only the service Popen is replaced with a synthetic HTTP worker, and GPU-memory
readback is stubbed to zero. Native extension fingerprint subprocesses are real.
No model process, CUDA work, approval, or formal namespace caller is exercised.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires pinned Linux packages", allow_module_level=True)

import arm_plan
import service_owner
from service_owner import ServiceOwner
from test_arm_plan import options
from test_ordinary_evidence import BUNDLE, BUNDLE_SHA, CLIENT, LIFECYCLE, SERVER, SOURCE, WIRE, sha
from ordinary_evidence import collect_requests, record_stopped_worker


def make_plan(tmp_path):
    plan = arm_plan.build_plan(**options(tmp_path))
    path = tmp_path / "owner-plan.json"
    arm_plan._write(path, plan)
    return plan, path, sha(path)


def test_actual_four_arm_pre_popen_file_dry(tmp_path, monkeypatch):
    plan, path, digest = make_plan(tmp_path)
    original = subprocess.Popen

    def only_native_probe(argv, *args, **kwargs):
        assert argv[0] in {"git", arm_plan.PYTHON}, argv
        if argv[0] == arm_plan.PYTHON:
            assert argv[1] == "-c" and "_cpu_moe" in argv[2]
            assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", only_native_probe)
    monkeypatch.setenv("FT_DEV_ROUTE_TRACE", "/should-not-propagate")
    owner = ServiceOwner(path, digest, file_dry_run=True)
    for name, _, _ in arm_plan.ARMS:
        row = owner.service(name, lambda *_: pytest.fail("file-dry invoked operation"),
                            before_start=lambda *_: pytest.fail("file-dry invoked launch hook"))
        folder = Path(plan["arms"][name]["directory"])
        assert row["port_probe"] is None and row["file_dry_run"] is True
        assert row["formal_launch_authorized"] is False
        assert json.loads((folder / "argv.json").read_bytes()) == plan["arms"][name]["argv"]
        assert json.loads((folder / "environment.json").read_bytes()) == plan["arms"][name]["environment"]
        assert not (folder / "owned_process.json").exists() and not (folder / "health.json").exists()
        assert not (folder / "dev_D16").exists()
    assert owner.proc is None
    for row in owner.extensions.values():
        assert sha(Path(row["path"]).resolve()) == row["sha256"]
    assert {p.name for p in owner.root.iterdir() if p.is_dir()} == {a[0] for a in arm_plan.ARMS}
    before = sha(owner.root / "control/pre-popen.json")
    with pytest.raises(FileExistsError):
        owner.service("control", lambda *_: None)
    assert before == sha(owner.root / "control/pre-popen.json")


@pytest.mark.parametrize("fault", ["plan", "root", "new_source", "extension", "missing_hook"])
def test_pre_spawn_changes_fail_closed(tmp_path, monkeypatch, fault):
    plan, path, digest = make_plan(tmp_path)
    owner = ServiceOwner(path, digest, lifecycle=LIFECYCLE)
    if fault == "plan":
        value = copy.deepcopy(plan)
        value["arms"]["control"]["environment"]["FT_DEV_ROUTE_TRACE"] = "/changed"
        path.write_bytes(arm_plan._raw(value))
    elif fault == "root":
        owner.root.rename(owner.root.with_name("old-root"))
        owner.root.mkdir()
    elif fault == "new_source":
        original = arm_plan._sources
        monkeypatch.setattr(arm_plan, "_sources", lambda *args: {**original(*args), "/extra/source.py": "0" * 64})
    elif fault == "extension":
        owner.extensions = {"different": {}}
    calls = []
    def hook(*args): calls.append(args)
    with pytest.raises(ValueError):
        owner.service("control", lambda *_: pytest.fail("invalid owner called operation"),
                      before_start=None if fault == "missing_hook" else hook)
    assert not calls and owner.proc is None
    assert not (Path(plan["arms"]["control"]["directory"]) / "owned_process.json").exists()


def install_cpu_boundary(monkeypatch, owner, plan, *, health_error=False):
    original = subprocess.Popen
    seen = []
    born = []
    original_command = owner._r040a_private_gpu.protocol["command"]
    def command(argv, **kwargs):
        if argv == ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]:
            return "0"
        return original_command(argv, **kwargs)
    owner._r040a_private_gpu.protocol["command"] = command

    def cpu_popen(argv, *args, **kwargs):
        if argv[0] != "numactl":
            return original(argv, *args, **kwargs)
        arm = next(arm for arm in plan["arms"].values() if arm["argv"] == argv)
        assert kwargs["env"] == arm["environment"]
        assert kwargs["cwd"] == plan["candidate"]
        assert kwargs["start_new_session"] is kwargs["close_fds"] is True
        assert kwargs["stdin"] is subprocess.DEVNULL
        seen.append({"argv": argv, "environment": kwargs["env"]})
        server = SERVER.replace("self.send_response(200);self.send_header('Content-Length','0');self.end_headers()",
            "raw=b'{\"status\":\"ok\"}';self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)")
        server = server.replace("HTTPServer(('127.0.0.1',0),Handler)",
                                "HTTPServer(('127.0.0.1'," + str(arm["port"]) + "),Handler)")
        server = server.replace("import hashlib,json,os,subprocess,sys,time",
            "import hashlib,json,os,subprocess,sys,time,signal\nassert os.environ['CUDA_VISIBLE_DEVICES']==''\nsignal.signal(signal.SIGTERM,signal.SIG_DFL)")
        if health_error:
            server = server.replace('"status":"ok"', '"status":"error"')
        # This single replacement is explicitly CPU synthetic; all adapter
        # readiness, body capture, birth/PGID and D07 stop paths remain real.
        proc = original([sys.executable, "-c", server, arm["directory"], str(BUNDLE), arm["execution_id"]],
                        **{**kwargs, "env": {**kwargs["env"], "CUDA_VISIBLE_DEVICES": ""}})
        born.append(proc)
        return proc
    monkeypatch.setattr(subprocess, "Popen", cpu_popen)
    return seen, born


@pytest.mark.parametrize("fail_operation", [False, True])
def test_actual_health_only_three_requests_and_finally_stop(tmp_path, monkeypatch, fail_operation):
    plan, path, digest = make_plan(tmp_path)
    owner = ServiceOwner(path, digest, lifecycle=LIFECYCLE)
    seen, born = install_cpu_boundary(monkeypatch, owner, plan)
    hooks = []

    def operation(active, folder):
        arm = plan["arms"]["enabled"]
        assert active is owner
        assert not list(folder.glob("received-*.json")), "readiness sent a POST"
        value = collect_requests(active, capture=Path(arm["capture"]), execution_id=arm["execution_id"],
            input_root=BUNDLE, input_sha256=BUNDLE_SHA, output=folder / "wire",
            api_source=SOURCE / "python/freetoken/server/openai_api.py", ordinary_client=CLIENT, wire_root=WIRE, timeout=5)
        if fail_operation:
            raise RuntimeError("CPU injected operation failure")
        return value

    try:
        if fail_operation:
            with pytest.raises(RuntimeError, match="CPU injected"):
                owner.service("enabled", operation, before_start=lambda *args: hooks.append(args))
        else:
            result = owner.service("enabled", operation, before_start=lambda *args: hooks.append(args))
            assert list(result["responses"]) == ["0", "1", "2"]
        assert len(seen) == len(born) == len(hooks) == 1 and born[0].poll() is not None
        assert owner.proc is None and not LIFECYCLE.owned_group_alive(born[0].pid)
        folder = Path(plan["arms"]["enabled"]["directory"])
        assert len(list(folder.glob("received-*.json"))) == 3
        assert json.loads((folder / "health.json").read_bytes()) == {"status": "ok"}
        assert not (folder / "ready_sayok.json").exists()
        stopped = record_stopped_worker(LIFECYCLE, folder / "worker-stopped.json",
            collection_path=folder / "wire/collection.json", collection_sha256=sha(folder / "wire/collection.json"))
        assert stopped["worker_stopped_verified"] is True
        if fail_operation:
            with pytest.raises(ValueError, match="failed or busy"):
                owner.service("control", operation, before_start=lambda *_: None)
    finally:
        for proc in born:
            LIFECYCLE.stop_owned_process(proc, term_timeout=3, kill_timeout=5)


def test_callback_plan_mutation_rejected_at_last_boundary(tmp_path):
    plan, path, digest = make_plan(tmp_path)
    owner = ServiceOwner(path, digest, lifecycle=LIFECYCLE)
    def changed(*_): path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source SHA differs"):
        owner.service("control", lambda *_: pytest.fail("mutation launched operation"), before_start=changed)
    assert owner.proc is None
    assert not (owner.root / "control/owned_process.json").exists()


@pytest.mark.parametrize("fault", ["birth", "health", "gpu_release"])
def test_lifecycle_failures_escalate_without_success_receipt(tmp_path, monkeypatch, fault):
    plan, path, digest = make_plan(tmp_path)
    owner = ServiceOwner(path, digest, lifecycle=LIFECYCLE)
    seen, born = install_cpu_boundary(monkeypatch, owner, plan, health_error=fault == "health")
    identity = LIFECYCLE.process_identity
    if fault == "birth":
        monkeypatch.setattr(LIFECYCLE, "process_identity", lambda pid: None)
    if fault == "gpu_release":
        def failed_query(*args, **kwargs): raise RuntimeError("CPU injected GPU release readback failure")
        owner._r040a_private_gpu.protocol["command"] = failed_query
    try:
        with pytest.raises((RuntimeError, ValueError)) as raised:
            owner.service("control", lambda *_: None, before_start=lambda *_: None)
        assert len(seen) == 1
        if fault in ("birth", "gpu_release"):
            assert raised.value.owned_cleanup_failed is True
            assert raised.value.owned_process is born[0] and owner.proc is born[0]
            assert not (owner.root / "control/service-stopped.json").exists()
        else:
            assert "backend error" in str(raised.value)
            assert owner.proc is None and (owner.root / "control/service-stopped.json").exists()
        with pytest.raises(ValueError, match="failed or busy"):
            owner.service("repeat", lambda *_: None, before_start=lambda *_: None)
    finally:
        monkeypatch.setattr(LIFECYCLE, "process_identity", identity)
        # Unknown-birth cleanup belongs to the enclosing namespace in formal
        # use. This CPU test uses its retained Popen to remove only its fixture.
        for proc in born:
            LIFECYCLE.stop_owned_process(proc, term_timeout=3, kill_timeout=5)
            assert proc.poll() is not None and not LIFECYCLE.owned_group_alive(proc.pid)
