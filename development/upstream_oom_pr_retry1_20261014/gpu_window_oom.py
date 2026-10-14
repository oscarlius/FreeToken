"""One-shot OOM recovery GPU window. Inert unless explicitly invoked with --run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
ACTIVE_PATH = Path("/data2/FreeToken/run/production.active.json")
RESTORE_ID = "UPSTREAM-OOM-PR-RESTORE-E3-20261014-02"
RESTORE_RESERVE_SECONDS = 2100
RESTORE_ADAPTERS = {
    "approved_attempt.py", "start_approved_release.py", "wait_release_and_smoke.py",
    "run_exclusive_smoke.py", "stop_approved_restore.py", "deploy_conditional.py",
}
ARMS = ("candidate_off", "candidate_on")
CALL_CAPS = {"candidate_off": 3, "candidate_on": 4}
OLDPY = "/data2/FreeToken/venv/bin/python"
NEWPY = "/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_authorization() -> dict:
    path = ROOT / "WINDOW_AUTHORIZATION.json"
    if not path.is_file():
        raise RuntimeError("missing root WINDOW_AUTHORIZATION.json")
    auth = json.loads(path.read_text())
    if auth.get("authorized") is not True:
        raise RuntimeError("inert: root authorization is not true")
    if not auth.get("independent_controller_review"):
        raise RuntimeError("missing independent controller review")
    if not auth.get("source_sha256_pins"):
        raise RuntimeError("missing source SHA pins")
    return auth


def client_argv(arm: str, arm_dir: Path, deadline_unix: float) -> list[str]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    return [
        "gpu_http_check.py", "--arm", arm, "--base-url", "http://127.0.0.1:8095",
        "--out", str(arm_dir), "--deadline-unix", str(deadline_unix),
        "--inputs", str(ROOT / "inputs.json"),
    ]


def phase_event(event: str, **fields) -> None:
    with (ROOT / "window_events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": time.time(), "event": event, **fields}) + "\n")


def load_external_baseline(auth: dict) -> dict:
    """Main-arm receipts from the sealed first window; retry never reruns main."""
    raw = auth.get("baseline_main_summary")
    expected = auth.get("baseline_main_summary_sha256")
    if not raw or not expected:
        raise RuntimeError("missing pinned external main baseline")
    path = Path(raw)
    if not path.is_file() or path.is_symlink() or sha(path) != expected:
        raise RuntimeError("external main baseline hash differs")
    return verify_summary_document("main", json.loads(path.read_text()), expected_calls=3)


def verify_summary_document(arm: str, summary: dict, *, expected_calls: int) -> dict:
    if summary.get("classification") != "kept":
        raise RuntimeError(f"{arm} not kept")
    refs = summary.get("refs") or {}
    if set(refs) != {"short512", "long8257"}:
        raise RuntimeError(f"{arm} lacks canonical refs")
    if summary.get("calls") != expected_calls or any(not isinstance(ids, list) or len(ids) != 128 for ids in refs.values()):
        raise RuntimeError(f"{arm} call ledger or native ID length differs")
    return refs


def verify_summary(arm: str, arm_dir: Path, baseline: dict | None = None) -> dict:
    expected_calls = 3 if arm == "main" else CALL_CAPS[arm]
    refs = verify_summary_document(arm, json.loads((arm_dir / "SUMMARY.json").read_text()), expected_calls=expected_calls)
    if baseline and refs != baseline:
        raise RuntimeError(f"{arm} native IDs differ from baseline")
    return refs


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def active_owner_is_live(helper, active: dict) -> bool:
    """Require the active pointer to name the same still-live production owner."""
    try:
        for name in ("supervisor", "service"):
            expected = active[name]
            live = helper.process_identity(expected["pid"])
            if not live or any(live.get(key) != expected.get(key) for key in ("pid", "start_ticks", "pgid", "session")):
                return False
    except (KeyError, TypeError):
        return False
    return True


def snapshot_environment(path: Path) -> None:
    """Use the frozen window snapshot format for before/after arm evidence."""
    ready = load_module(
        ROOT.parent / "upstream_layer_major_pr_20261014" / "gpu_window_ready.py",
        "oom_window_snapshot",
    )
    ready.snapshot(path)


def bounded_deadline(window_deadline: float, seconds: float = 120) -> float:
    return min(window_deadline, time.time() + seconds)


def verify_restore_package() -> Path:
    """Bind the copied restore package to the frozen source before stopping production."""
    package = ROOT / "restore_e3"
    source = ROOT.parent / "upstream_layer_major_pr_20261014" / "restore_e3"
    manifest_path = package / "SOURCE_MANIFEST.json"
    approval_path = package / "DEPLOYMENT_APPROVAL.json"
    if not manifest_path.is_file() or not approval_path.is_file() or not source.is_dir():
        raise RuntimeError("missing source-bound restore_e3 package")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("identity") != RESTORE_ID:
        raise RuntimeError("restore package identity differs")
    files = manifest.get("files") or {}
    if set(files) != RESTORE_ADAPTERS:
        raise RuntimeError("restore package adapter set differs")
    for name, expected in files.items():
        packaged, original = package / name, source / name
        if (not packaged.is_file() or packaged.is_symlink() or not original.is_file()
                or original.is_symlink() or sha(packaged) != expected or sha(packaged) != sha(original)):
            raise RuntimeError(f"restore adapter differs from pinned source: {name}")
    approval = json.loads(approval_path.read_text())
    if approval.get("approval_id") != RESTORE_ID:
        raise RuntimeError("restore approval identity differs")
    return package


def verify_restore_admission(package: Path) -> dict:
    """Verify the approved restore control and its frozen source before production stop."""
    approval = json.loads((package / "DEPLOYMENT_APPROVAL.json").read_text())
    guard_path = ROOT / "recovery_guard.py"
    frozen_guard = ROOT.parent / "upstream_layer_major_pr_20261014" / "recovery_guard.py"
    if (not guard_path.is_file() or guard_path.is_symlink() or not frozen_guard.is_file()
            or frozen_guard.is_symlink() or sha(guard_path) != sha(frozen_guard)):
        raise RuntimeError("source-pinned recovery_guard.py differs")
    gate = load_module(package / "deploy_conditional.py", "oom_restore_gate")
    gate.require_root_final_review(approval)
    load_module(guard_path, "oom_recovery_guard").verify_sources(approval)
    return approval


def stop_owned_service(lifecycle, service) -> None:
    """Do not re-stop a leader that has already exited; its group cleanup already ran."""
    if service is not None and service.poll() is None:
        lifecycle.stop_owned_process(service, 120, 30)


def verify_pins(auth: dict) -> None:
    """Verify root-staged archives, sources, and native allowlist before any stop action."""
    for raw, expected in (auth.get("source_sha256_pins") or {}).items():
        path = Path(raw)
        if not path.is_file() or path.is_symlink() or sha(path) != expected:
            raise RuntimeError(f"source SHA pin failed: {path}")
    for key in ("main", "candidate"):
        for suffix in ("source", "archive", "commit"):
            if not auth.get(f"{key}_{suffix}"):
                raise RuntimeError(f"missing {key}_{suffix}")
    if not isinstance(auth.get("native_modules"), dict):
        raise RuntimeError("missing native module allowlist")
    verifier = load_module(ROOT.parent / "upstream_layer_major_pr_20261014" / "gpu_window_ready.py", "source_verifier")
    for name in ("main", "candidate"):
        archive, source = Path(auth[f"{name}_archive"]), Path(auth[f"{name}_source"])
        verifier.verify_tree(archive, source, sha(archive), auth[f"{name}_commit"], auth["native_modules"])


def wait_gpu_idle(deadline: float) -> None:
    """Bounded post-stop idle proof; never release the owned lock over foreign compute."""
    last = "no nvidia-smi sample"
    while time.time() < deadline:
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"], text=True, timeout=5,
            ).strip()
            memory = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=5,
            ).strip()
            last = f"compute={output!r}; memory={memory!r}"
            if not output and all(int(x.strip()) < 512 for x in memory.splitlines() if x.strip()):
                return
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            last = repr(exc)
            phase_event("gpu_idle_query_retry", diagnostic=last)
        time.sleep(min(1, max(0, deadline - time.time())))
    raise RuntimeError(f"GPU did not become idle before absolute deadline: {last}")


def service_argv(source: Path, *, oom_recovery: bool, python: str = NEWPY) -> list[str]:
    argv = ["taskset", "-c", "1,3-47", python, "-m", "freetoken.cli", "serve", "--model-path",
            "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay", "--host", "127.0.0.1",
            "--port", "8095", "--served-model-name", "Qwen3.8-Flash-Next-NVFP4", "--memory-ratio", "0.88", "--moe-cache-auto", "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
            "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2",
            "--cuda-graph-max-bs", "2", "--kv-reserve-tokens", "98304",
            "--max-seq-len-override", "98304", "--max-prefill-length", "4096", "--enable-cache-report"]
    if oom_recovery:
        argv.append("--oom-recovery")
    return argv


def wait_ready(service, deadline: float) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.time() < deadline:
        if service.poll() is not None:
            raise RuntimeError("owned service exited before readiness")
        try:
            with opener.open("http://127.0.0.1:8095/health", timeout=3) as response:
                health = json.load(response)
            if health.get("status") == "ok" and health.get("maintenance") == "serving": return
        except OSError: pass
        time.sleep(1)
    raise TimeoutError("service readiness deadline reached")


def run_command(argv: list[str], *, env: dict, cwd: Path, deadline: float, log: Path) -> None:
    with log.open("xb") as handle:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            proc.wait(timeout=max(1, deadline - time.time()))
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, 15)
                proc.wait(timeout=10)
        if proc.returncode:
            raise RuntimeError(f"command failed: {argv[0]} rc={proc.returncode}")


def run() -> None:
    auth = load_authorization()
    verify_pins(auth)
    baseline = load_external_baseline(auth)
    restore = verify_restore_package()
    verify_restore_admission(restore)
    consumed = ROOT / "WINDOW_RUN_CONSUMED.json"
    if consumed.exists() or (ROOT / "GPU_WINDOW_TERMINAL.json").exists():
        raise RuntimeError("one-shot window already consumed")
    with consumed.open("x") as handle: json.dump({"at": time.time(), "authorization_sha256": sha(ROOT / "WINDOW_AUTHORIZATION.json")}, handle)
    frozen_ops = auth["frozen_ops"]
    helper_path = Path(frozen_ops.get("helper_path") or Path(frozen_ops["path"]).parent / "d07_g3g4_prepare.py")
    helper = load_module(helper_path, "frozen_d07_helper")
    lifecycle = helper.load_owned_lifecycle()
    active_path = ACTIVE_PATH
    active = json.loads(active_path.read_text())
    if active != auth["active_snapshot"]:
        raise RuntimeError("active production identity changed")
    if not active_owner_is_live(helper, active):
        raise RuntimeError("active production identity changed")
    window_seconds = float(auth.get("window_seconds", 3600))
    if not 0 < window_seconds <= 3600:
        raise RuntimeError("window_seconds must be positive and no more than 3600")
    deadline = time.time() + window_seconds
    measurement_deadline = min(deadline - RESTORE_RESERVE_SECONDS, time.time() + 1500)
    if measurement_deadline <= time.time():
        raise RuntimeError("window leaves no bounded measurement period after restoration reserve")
    result = {"classification": "failed_harness", "arms": [], "restored": False}
    lock = None
    stopped = False
    services = []
    test_python = auth.get("test_python")
    if test_python != NEWPY:
        raise RuntimeError("authorization test_python does not pin the validated main-venv")
    previous_handlers = {}

    def _interrupt(signum, _frame) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    stop_signals = (signal.SIGINT, signal.SIGTERM)
    if hasattr(signal, "SIGHUP"):
        stop_signals += (signal.SIGHUP,)
    for signum in stop_signals:
        previous_handlers[signum] = signal.signal(signum, _interrupt)
    try:
        phase_event("window_start", deadline=deadline, measurement_deadline=measurement_deadline)
        stopped = True
        phase_event("production_stop_attempt")
        run_command([OLDPY, auth["old_stop_adapter"]], env=os.environ.copy(), cwd=ROOT,
                    deadline=min(deadline, time.time() + 300), log=ROOT / "stop_e3.log")
        wait_gpu_idle(bounded_deadline(deadline))
        lock = helper.take_d07_gpu_lock("UPSTREAM-OOM-PR-20261014", 0)
        for arm in ARMS:
            if time.time() >= measurement_deadline:
                raise TimeoutError("measurement deadline reached before service start")
            source = Path(auth["main_source"] if arm == "main" else auth["candidate_source"])
            arm_dir = ROOT / "gpu_results" / arm
            arm_dir.mkdir(parents=True, exist_ok=False)
            env = {k:v for k,v in os.environ.items() if not k.startswith("FT_") and k not in {"PYTHONPATH","CUDA_VISIBLE_DEVICES","MASTER_PORT"}}
            env.update(PYTHONPATH=":".join((str(ROOT / "fault_site"), str(ROOT), str(source / "python"))),
                FT_PR_OOM_ARTIFACTS=str(arm_dir / "native"), FT_UPSTREAM_NATIVE_IDS=str(arm_dir / "native"),
                CUDA_VISIBLE_DEVICES="0", MASTER_PORT="8096", CUDA_HOME="/usr/local/cuda-13.0",
                PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
            if arm == "candidate_on": env["FT_PR_OOM_INJECT"] = "1"
            with (arm_dir / "serve.log").open("xb") as log:
                service = subprocess.Popen(service_argv(source, oom_recovery=arm == "candidate_on", python=test_python), cwd=source,
                    env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            services.append(service)
            try:
                phase_event("arm_start", arm=arm)
                wait_ready(service, min(measurement_deadline, time.time() + 600))
                snapshot_environment(arm_dir / "environment_before.json")
                # Root client owns readiness/fault/queue assertions and emits canonical SUMMARY.
                run_command([OLDPY, str(ROOT / "gpu_http_check.py"), *client_argv(arm, arm_dir, measurement_deadline)[1:]],
                    env=env, cwd=arm_dir, deadline=measurement_deadline, log=arm_dir / "client.log")
                verify_summary(arm, arm_dir, baseline)
                snapshot_environment(arm_dir / "environment_after.json")
                result["arms"].append({"arm": arm, "calls": CALL_CAPS[arm], "classification": "kept"})
                phase_event("arm_terminal", arm=arm, classification="kept")
            finally:
                stop_owned_service(lifecycle, service)
                wait_gpu_idle(bounded_deadline(deadline))
        result["classification"] = "kept"
    except BaseException as exc:
        result["error"] = repr(exc)
        phase_event("measurement_error", error=result["error"])
        (ROOT / "WINDOW_PHASE_ERROR.json").write_text(json.dumps({"at": time.time(), "error": result["error"]}) + "\n")
        summaries = [ROOT / "gpu_results" / arm / "SUMMARY.json" for arm in ARMS]
        if any(path.is_file() and json.loads(path.read_text()).get("classification") == "not_met" for path in summaries):
            result["classification"] = "not_met"
        else:
            result["classification"] = "not_met" if isinstance(exc, ValueError) else "failed_harness"
    finally:
        for service in services:
            try:
                if lifecycle is not None:
                    stop_owned_service(lifecycle, service)
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(repr(exc))
        try:
            if stopped:
                active_now = json.loads(active_path.read_text()) if active_path.is_file() else None
                if active_now == active and active_owner_is_live(helper, active):
                    # An external recovery already brought back the exact original owner. Do not
                    # wait for its legitimate compute to become idle, and do not start another.
                    result["restored"] = True
                    result["production_already_live"] = True
                    if lock is not None:
                        helper.release_d07_gpu_lock(lock)
                        lock = None
                elif active_now is None:
                    # No production process remains. Prove idle after our owned cleanup, then
                    # release only our exact lock before the approved restore needs to acquire it.
                    wait_gpu_idle(bounded_deadline(deadline))
                    if lock is not None:
                        helper.release_d07_gpu_lock(lock)
                        lock = None
                    run_command([OLDPY, str(restore / "start_approved_release.py")], env=os.environ.copy(), cwd=ROOT,
                        deadline=deadline, log=ROOT / "restore_start.log")
                    run_command([OLDPY, str(restore / "wait_release_and_smoke.py")], env=os.environ.copy(), cwd=ROOT,
                        deadline=deadline, log=ROOT / "restore_smoke.log")
                    result["restored"] = True
                else:
                    raise RuntimeError("foreign active production identity; refusing restoration")
            elif lock is not None:
                wait_gpu_idle(bounded_deadline(deadline))
                helper.release_d07_gpu_lock(lock)
                lock = None
        except BaseException as exc:
            result["restoration_error"] = repr(exc)
        finally:
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
        (ROOT / "GPU_WINDOW_TERMINAL.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["classification"] != "kept" or not result["restored"]:
        raise RuntimeError(json.dumps(result))



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("Inert: supply --run only for the authorized GPU window")
    run()
