import hashlib
import importlib.util
import json
import sys
import types
import urllib.request
from pathlib import Path

import pytest

SOURCE = Path(__file__).with_name("run_r044b_actual.py")
RETAINED = Path(__file__).parents[1] / "r044_capture_path_retry2_20261010" / "r044_prepare_v6.py"
STRICT = RETAINED.parent / "t16_full_tail_base_runner.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def messages(round_no):
    value = [{"role": "user", "content": f"retained-{round_no}"}]
    key = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return {"messages": value, "record": {"messages_sha": key}, "round": round_no}


class Process:
    def __init__(self, pid, arm, failed_ready=False):
        self.pid, self.arm, self.failed_ready = pid, arm, failed_ready

    def poll(self):
        return 1 if self.failed_ready else None


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def arrange(monkeypatch, tmp_path, *, failed_ready=False, unsafe_stop=False, mismatch=True,
            b2_args_drift=False, clock=None, idle_advance_s=0, replay_advance_s=0, cleanup_advance_s=0):
    runner = load(SOURCE, "r044b_actual_test")
    legacy = load(RETAINED, "r044b_retained_actual_test")
    root, output, worktree = tmp_path / "ft", tmp_path / "rounds", tmp_path / "wt"
    root.mkdir(); output.mkdir(); worktree.mkdir()
    packet = tmp_path / "packet"; packet.mkdir()
    (packet / "ROOT_ADMISSION_R044B.json").write_text(json.dumps({"bindings": {"runner": "pin"}}))
    monkeypatch.setenv("R044B_ROOT_AUTHORIZED", "1")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "PACKET", packet)
    monkeypatch.setattr(runner, "filedry", lambda: {"bindings": {"runner": "pin"}})

    legacy.ROOT, legacy.ROUNDS, legacy.WT, legacy.VENV = root, output, worktree, root / "venv"
    legacy.STRICT_READER = STRICT
    source_root = tmp_path / "sources"; source_root.mkdir()
    names = {
        "CAPTURE_STARTUP": "capture_startup.py", "LEGACY_CAPTURE": "legacy_capture.py",
        "REPLAY_SOURCE": "replay_client.py", "ORDINARY_ADAPTER": "ordinary_adapter.py",
        "ORDINARY_CLIENT": "ordinary_client.py", "PAIR_SOURCE": "pair.py",
    }
    for attr, name in names.items():
        path = source_root / name; path.write_text("# retained test source\n")
        setattr(legacy, attr, path)
    legacy.HERE = source_root
    suite = source_root / "equiv_suite"; suite.mkdir()
    for name in ("__init__.py", "service_capture_startup.py", "service_capture.py", "sampler_capture.py"):
        (suite / name).write_text("# capture observer\n")
    traces = {}
    for phase in ("cold", "warm"):
        path = tmp_path / f"{phase}.json"
        path.write_text(json.dumps({"rounds": [messages(i) for i in range(12)]}))
        traces[phase] = path
    legacy.TRACES = traces
    legacy.TRACE_SHA = {key: legacy.sha(value) for key, value in traces.items()}
    queue = tmp_path / "queue.json"; queue.write_text("{}")
    review = tmp_path / "sealed-review.json"; review.write_text("{}")

    calls = {"popen": [], "replay": [], "stop": [], "cleanup_started": [], "lock": [], "release": [], "reserve": [], "receipt": [], "telemetry": []}
    processes = {}

    class Owned:
        def verified_module(self, *_):
            return types.SimpleNamespace(next_batch=lambda _rounds: 73)

        def reserve_process(self, helper, batch, rid, argv, receipt_path, reserved):
            calls["reserve"].append((batch, rid, list(argv), dict(reserved)))
            receipt = {**reserved, "batch_pid": 701}
            receipt_path.write_text(json.dumps(receipt))
            return receipt

        def process_identity(self, pid):
            return {"pid": pid, "start_ticks": pid + 1000, "pgid": pid, "session": pid}

        def stop_owned_process(self, process, term_timeout=120, kill_timeout=30):
            calls["stop"].append(process.pid)
            calls.setdefault("cleanup_timeouts", []).append((term_timeout, kill_timeout))
            if clock is not None:
                calls["cleanup_started"].append(clock())
            if unsafe_stop:
                raise RuntimeError("controlled cleanup failure")
            if clock is not None:
                clock.advance(cleanup_advance_s)
            (process.arm / "worker_shutdown.json").write_text(json.dumps({
                "schema": "ft_t10_worker_shutdown/v3", "status": "complete", "scheduler_run_started": True,
                "pid": process.pid, "start_ticks": process.pid + 1000,
            }))

        def owned_group_alive(self, _pid):
            return False

    owned = Owned()

    class D07:
        LOCK = tmp_path / "gpu.lock"
        ATOMIC_HELPER_SHA = "a" * 64
        OWNED_PROTOCOL_SHA = "b" * 64

        def load_owned_lifecycle(self):
            return owned

        def process_birth(self):
            return {"pid": 600, "start_ticks": 1600, "execution_id": "600:1600"}

        def argv_sha256(self, argv):
            return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()

        def publish_child_binding(self, receipt_path, receipt, child, **_):
            value = {**receipt, "state": "launched", "child": child}
            receipt_path.write_text(json.dumps(value))
            return value

        def require_child_receipt(self, receipt, batch, wt, out, **kwargs):
            calls["receipt"].append((receipt, batch, wt, out, kwargs))
            assert receipt.is_file() and batch == 73 and wt == worktree and out == output

        def take_d07_gpu_lock(self, rid, batch):
            calls["lock"].append((rid, batch))
            return {"rid": rid, "batch": batch}

        def release_d07_gpu_lock(self, owner):
            calls["release"].append(owner)

        def require_gpu_idle(self):
            if clock is not None:
                clock.advance(idle_advance_s)
            return [{"gpu": 0, "memory_mib": 0}]

        def clean_environment(self, _wt, trace_dir=None):
            assert trace_dir is None
            return {"PATH": "/controlled/venv/bin", "VIRTUAL_ENV": str(root / "venv"), "CUDA_VISIBLE_DEVICES": ""}

        def serve_argv(self, port):
            return ["ft", "serve", "--port", str(port), "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--prefill-layer-major"]

    d07 = D07()
    class FakeTelemetry:
        def __init__(self, run, d, **_kwargs):
            self.run, self.d = run, d
            calls["telemetry"].append(("constructed", run))

        def start(self):
            calls["telemetry"].append(("started",))

        def bind_service(self, arm, process):
            calls["telemetry"].append(("bound", arm.name, process.pid))

        def stop(self):
            calls["telemetry"].append(("stopped",))

    monkeypatch.setattr(runner, "OwnedTelemetry", FakeTelemetry)
    monkeypatch.setattr(legacy, "load_d07", lambda: d07)
    monkeypatch.setattr(legacy, "require_queue", lambda _d: queue)
    monkeypatch.setattr(legacy, "packet", lambda _wt: {"old_33_36_evidence": {"sha256": "retained"}})
    monkeypatch.setattr(legacy, "require_startup_review", lambda: review)
    monkeypatch.setattr(legacy, "port_pair", lambda: {"api": 41000 + len(calls["popen"]) * 2, "tcpstore": 41001 + len(calls["popen"]) * 2})
    monkeypatch.setattr(legacy.sys, "platform", "linux")

    def fake_popen(argv, cwd, env, stdout, **_):
        arm = Path(stdout.name).parent; pid = 100 + len(calls["popen"])
        layer = "True" if "--prefill-layer-major" in argv else "False"
        port = argv[argv.index("--port") + 1]
        extend = "4097" if b2_args_drift and arm.name == "B2" else "4096"
        stdout.write("Parsed arguments ServerArgs(model_path='m', server_port=" + port + ", prefill_layer_major=" + layer + ", max_prefill_length=4096, max_extend_tokens=" + extend + ", mamba_host_slots=0, enable_cache_report=True, special_token_ckpt=True, _unique_suffix='.pid=" + str(pid) + "')\n")
        stdout.flush()
        process = Process(pid, arm, failed_ready=failed_ready)
        calls["popen"].append(process); processes[arm] = process
        return process

    class Health:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b'{"status":"ok"}'

    def write_capture(arm):
        process = processes[arm]; capture = legacy.capture_destination(arm); capture.mkdir(parents=True, exist_ok=True)
        sampler = capture / "sampler"; sampler.mkdir()
        (sampler / "manifest.json").write_text(json.dumps({"terminal": "complete", "captures": []}))
        admissions = [{"uid": uid, "receipt_sha256": f"receipt-{uid}"} for uid in range(24)]
        deliveries = [{"uid": uid, "generation_index": 0, "sampled_token_id": 7} for uid in range(24)]
        (capture / "service_delivery.json").write_text(json.dumps({
            "terminal": "complete", "errors": [], "process_identity": {"pid": process.pid, "start_ticks": process.pid + 1000},
            "admission_receipts": admissions, "deliveries": deliveries,
            "t10_terminal_cap": {"declared_max_tokens": 200, "actual_delivery_counts": {str(uid): 1 for uid in range(24)}},
        }))

    def fake_run(cmd, cwd, env, stdout, stderr, check, timeout=None):
        phase = cmd[cmd.index("--phase") + 1]; trace = Path(cmd[cmd.index("--trace") + 1]); out = Path(cmd[cmd.index("--out") + 1])
        arm = out.parent; rows = []
        for index, value in enumerate(legacy.trace_rows(trace).values()):
            text = f"reply-{index}" + ("-mismatch" if mismatch and arm.name == "B2" and phase == "cold" and index == 0 else "")
            rows.append({"round": index, "messages_sha": value["record"]["messages_sha"], "text": text, "parts": [text], "completion_tokens": 1, "cached_tokens": 0 if phase == "cold" else index, "finish_reason": "stop", "transport": "ordinary_sse_no_ft_dev_ack", "uid": index + (12 if phase == "warm" else 0)})
        out.write_text(json.dumps({"rounds": rows})); stdout.write("controlled replay side effect\n"); stdout.flush()
        calls["replay"].append((arm, phase, len(rows), timeout))
        if clock is not None:
            clock.advance(replay_advance_s)
        if phase == "warm": write_capture(arm)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(legacy.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(legacy.subprocess, "run", fake_run)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: Health())
    return runner, legacy, output, worktree, d07, calls


def test_actual_retained_controller_child_stops_at_first_b1_b2_product_mismatch(monkeypatch, tmp_path):
    runner, legacy, output, worktree, d07, calls = arrange(monkeypatch, tmp_path)
    controller = runner.run(worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert controller["controller_child"] == {"pid": 701, "start_ticks": 1701, "execution_id": "701:1701"}
    batch, rid, argv, reserved = calls["reserve"][0]
    assert (batch, rid) == (73, runner.RID)
    assert argv == runner.child_argv(legacy, batch, output / f"launch_{runner.RID}_batch{batch}.json", worktree, output)
    assert reserved["argv_sha256"] == d07.argv_sha256(argv)

    receipt = output / f"launch_{runner.RID}_batch73.json"
    result = runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    first_key = next(iter(legacy.trace_rows(legacy.TRACES["cold"])))
    gate = result["r044b_product_gate"]
    assert gate["verdict"] == "not_met" and gate["product_acceptance"] is False
    assert {key: gate["first_failure"][key] for key in ("mode", "comparison", "left_arm", "right_arm", "round", "messages_sha", "same_fulltext", "same_sampled_token_ids")} == {"mode": "ordinary", "comparison": "cold_cold", "left_arm": "B1", "right_arm": "B2", "round": 0, "messages_sha": first_key, "same_fulltext": False, "same_sampled_token_ids": True}
    assert len(calls["popen"]) == len(calls["stop"]) == 2
    assert sum(rows for _arm, _phase, rows, _timeout in calls["replay"]) == 48
    assert len(calls["receipt"]) == 1 and len(calls["lock"]) == len(calls["release"]) == 1
    assert calls["telemetry"][-1] == ("stopped",)
    run = output / runner.RID
    gate_receipt = json.loads((run / "r044b_product_gate.json").read_text())
    assert gate_receipt["verdict"] == "not_met" and gate_receipt["raw_result_sha256"] == legacy.sha(run / "result.json")
    plans = list(run.glob("*/*/service_plan.json"))
    assert len(plans) == 2 and all(json.loads(path.read_text())["environment"]["FT_T10_CAPTURE_MAX_TOKENS"] == "200" for path in plans)
    parsed = [item["parsed"] for item in result["groups"]["ordinary"]["serve_identities"]]
    assert len(parsed) == 2 and all(row["max_extend_tokens"] == row["max_prefill_length"] == "4096" for row in parsed)
    assert all((path.parent / "worker_shutdown.json").is_file() for path in plans)


def test_actual_retained_child_completes_six_services_and_144_calls_when_stable(monkeypatch, tmp_path):
    runner, legacy, output, worktree, _d07, calls = arrange(monkeypatch, tmp_path, mismatch=False)
    receipt = output / "launch.json"; receipt.write_text("{}")
    result = runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert result["r044b_product_gate"] == {"verdict": "measured_pending_independent_review", "product_acceptance": False, "first_failure": None}
    assert len(calls["popen"]) == len(calls["stop"]) == 6
    assert sum(rows for _arm, _phase, rows, _timeout in calls["replay"]) == 144
    assert [row[0] for row in calls["telemetry"]].count("bound") == 6


def test_actual_startup_ready_failure_stops_owned_process_and_releases_lock(monkeypatch, tmp_path):
    runner, legacy, output, worktree, _d07, calls = arrange(monkeypatch, tmp_path, failed_ready=True)
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(RuntimeError, match="exited during startup"):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert len(calls["popen"]) == len(calls["stop"]) == len(calls["lock"]) == len(calls["release"]) == 1
    assert (output / runner.RID / "failed_harness.json").is_file()


def test_actual_unsafe_startup_cleanup_preserves_lock(monkeypatch, tmp_path):
    runner, legacy, output, worktree, _d07, calls = arrange(monkeypatch, tmp_path, failed_ready=True, unsafe_stop=True)
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(RuntimeError, match="preserve GPU lock"):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert len(calls["lock"]) == 1 and calls["release"] == []


def test_actual_controller_foreign_lock_stops_before_reservation(monkeypatch, tmp_path):
    runner, legacy, output, worktree, d07, calls = arrange(monkeypatch, tmp_path)
    d07.LOCK.write_text("foreign")
    with pytest.raises(RuntimeError, match="foreign GPU lock"):
        runner.run(worktree=worktree, output_root=output, legacy_loader=lambda: legacy)
    assert calls["reserve"] == [] and calls["lock"] == []


def test_load_legacy_uses_only_exact_retained_parent_for_queue_authorization(monkeypatch):
    runner = load(SOURCE, "r044b_actual_loader_test")
    monkeypatch.setattr(runner, "OLD", RETAINED.parent)
    monkeypatch.delitem(sys.modules, "queue_authorization", raising=False)
    before = list(sys.path)
    legacy = runner.load_legacy()
    assert legacy.__file__ == str(RETAINED)
    assert sys.path == before
    assert Path(sys.modules["queue_authorization"].__file__).resolve() == (RETAINED.parent / "queue_authorization.py").resolve()


def test_generation_deadline_caps_retained_client_subprocess_and_stops_later_services(monkeypatch, tmp_path):
    clock = Clock()
    runner, legacy, output, worktree, _d07, calls = arrange(
        monkeypatch, tmp_path, mismatch=False, clock=clock,
        replay_advance_s=1500,
    )
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(runner.DeadlineExpired, match="generation phase deadline"):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree,
                   output_root=output, legacy_loader=lambda: legacy, clock=clock)
    assert runner.GENERATION_PHASE_LIMIT_S == 1500
    assert len(calls["popen"]) == len(calls["stop"]) == 1
    assert len(calls["replay"]) == 1 and calls["replay"][0][3] == runner.GENERATION_PHASE_LIMIT_S
    failed = json.loads((output / runner.RID / "failed_harness.json").read_text())
    assert "generation phase deadline" in failed["error"]
    assert calls["release"] and not (output / runner.RID / "r044b_product_gate.json").exists()


def test_late_startup_is_denied_before_frozen_900_second_health_loop(monkeypatch, tmp_path):
    clock = Clock()
    runner, legacy, output, worktree, _d07, calls = arrange(
        monkeypatch, tmp_path, mismatch=False, clock=clock,
        idle_advance_s=4196,
    )
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(runner.DeadlineExpired, match="startup budget exhausted"):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree,
                   output_root=output, legacy_loader=lambda: legacy, clock=clock)
    assert 4196 == runner.TOTAL_WALL_LIMIT_S - runner.CLEANUP_RESERVE_S - (runner.LEGACY_STARTUP_BOUND_S + runner.CLEANUP_RESERVE_S) + 1
    assert calls["popen"] == calls["stop"] == []
    assert len(calls["lock"]) == len(calls["release"]) == 1
    assert "startup budget exhausted" in json.loads((output / runner.RID / "failed_harness.json").read_text())["error"]


def test_b2_configuration_drift_is_failed_harness_before_product_comparison(monkeypatch, tmp_path):
    runner, legacy, output, worktree, _d07, calls = arrange(monkeypatch, tmp_path, mismatch=False, b2_args_drift=True)
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(ValueError):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree,
                   output_root=output, legacy_loader=lambda: legacy)
    run = output / runner.RID
    assert len(calls["popen"]) == len(calls["stop"]) == 2
    assert (run / "failed_harness.json").is_file() and not (run / "result.json").exists()
    assert not (run / "r044b_product_gate.json").exists()


def test_final_cleanup_starts_with_reserved_time_and_finishes_at_absolute_end(monkeypatch, tmp_path):
    clock = Clock()
    runner, legacy, output, worktree, _d07, calls = arrange(
        monkeypatch, tmp_path, mismatch=False, clock=clock,
        idle_advance_s=4000, replay_advance_s=1250, cleanup_advance_s=150,
    )
    receipt = output / "launch.json"; receipt.write_text("{}")
    with pytest.raises(runner.DeadlineExpired, match="work deadline"):
        runner.run(owned_child=True, batch=73, launch_receipt=receipt, worktree=worktree,
                   output_root=output, legacy_loader=lambda: legacy, clock=clock)
    assert len(calls["popen"]) == len(calls["stop"]) == 1
    assert len(calls["replay"]) == 1 and calls["replay"][0][3] == 1250
    assert calls["cleanup_started"] == [runner.TOTAL_WALL_LIMIT_S - runner.CLEANUP_RESERVE_S]
    assert calls["cleanup_timeouts"] == [(115, 30)]
    assert clock() == runner.TOTAL_WALL_LIMIT_S
    assert "work deadline" in json.loads((output / runner.RID / "failed_harness.json").read_text())["error"]
    assert len(calls["release"]) == 1


def test_owned_telemetry_seals_raw_sidecars_and_leaves_no_monitor_process(monkeypatch, tmp_path):
    runner = load(SOURCE, "r044b_actual_telemetry_test")
    nvidia, vmstat, diskstats = tmp_path / "nvidia-smi", tmp_path / "vmstat", tmp_path / "diskstats"
    for path in (nvidia, vmstat):
        path.write_text("tool")
    diskstats.write_text("8 0 sda 1 2 3 4\n")
    monkeypatch.setattr(runner, "NVIDIA_SMI", nvidia)
    monkeypatch.setattr(runner, "VMSTAT", vmstat)
    monkeypatch.setattr(runner, "PROC_DISKSTATS", diskstats)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None if name == "iostat" else str(tmp_path / name))

    class Sidecar:
        def __init__(self, pid):
            self.pid, self.state = pid, None

        def poll(self):
            return self.state

        def terminate(self):
            self.state = -15

        def kill(self):
            self.state = -9

        def wait(self, timeout):
            assert timeout == 2
            return self.state

    launches, sidecars = [], []

    def fake_popen(argv, **kwargs):
        launches.append((list(argv), kwargs))
        sidecar = Sidecar(900 + len(launches))
        sidecars.append(sidecar)
        return sidecar

    lifecycle = types.SimpleNamespace(process_identity=lambda pid: {"pid": pid, "start_ticks": pid + 1, "pgid": pid})
    d = types.SimpleNamespace(load_owned_lifecycle=lambda: lifecycle)
    telemetry = runner.OwnedTelemetry(tmp_path / "run", d, popen=fake_popen)
    telemetry.start()
    service = types.SimpleNamespace(pid=77)
    telemetry.bind_service(tmp_path / "run" / "ordinary" / "B1", service)
    telemetry.stop()

    raw = tmp_path / "run" / "telemetry"
    manifest = json.loads((raw / "telemetry_manifest.json").read_text())
    assert manifest["streams"]["disk"] == {"iostat": "unavailable (/usr/bin/iostat absent)", "fallback": "proc_diskstats_fallback", "raw": "proc_diskstats.jsonl"}
    assert [entry[0] for entry in launches] == [
        [str(nvidia), "dmon", "-s", "umt", "-d", "1", "-i", "0", "-o", "DT"],
        [str(vmstat), "-n", "-t", "1"],
    ]
    assert all(entry[1]["start_new_session"] is True for entry in launches)
    assert all(entry[1]["stdout"] is not None for entry in launches)
    assert all(entry[1]["stderr"] is runner.subprocess.STDOUT for entry in launches)
    assert all(item["birth"]["pgid"] == item["birth"]["pid"] for item in manifest["sidecars"])
    assert all(sidecar.poll() is not None for sidecar in sidecars)
    assert telemetry.thread is not None and not telemetry.thread.is_alive()
    binding = json.loads((raw / "service_bindings.jsonl").read_text().strip())
    assert binding["service_birth"] == {"pid": 77, "start_ticks": 78, "pgid": 77}
    assert json.loads((raw / "telemetry_terminal.json").read_text())["sidecars_stopped"] is True
    assert all((raw / name).stat().st_mode & 0o222 == 0 for name in ("nvidia_dmon_raw.txt", "vmstat_raw.txt", "proc_diskstats.jsonl", "service_bindings.jsonl", "telemetry_manifest.json", "telemetry_terminal.json"))

