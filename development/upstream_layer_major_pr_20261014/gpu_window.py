"""One-shot, three-arm GPU-window controller.  It is inert until --run is supplied."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


HELPER_SHA256 = "c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0"
MEASUREMENT_SECONDS = 1800
RESTORE_RESERVE_SECONDS = 900
PORT = 8095


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _remaining(deadline: float, what: str) -> float:
    value = deadline - time.time()
    if value <= 0:
        raise RuntimeError(f"window deadline expired before {what}")
    return value


def _health(deadline: float, service) -> None:
    while True:
        _remaining(deadline, "service health")
        if service.poll() is not None:
            raise RuntimeError(f"service exited early with code {service.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("status") == "ok" and health.get("maintenance") == "serving":
                return
        except OSError:
            pass
        time.sleep(1)


def _snapshot(path: Path) -> None:
    path.write_text(json.dumps({"unix": time.time(), "nvidia_smi": subprocess.getoutput("nvidia-smi")}, indent=2) + "\n")


def _native_ids(arm_dir: Path) -> dict[str, list[int]]:
    records = {}
    for line in (arm_dir / "receipts.jsonl").read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("label") in records or not isinstance(value.get("native_token_ids"), list):
            raise RuntimeError(f"invalid native receipt in {arm_dir}")
        records[value["label"]] = value["native_token_ids"]
    if len(records) != 9:
        raise RuntimeError(f"{arm_dir} does not contain nine native receipts")
    return records


def _service_command(python: str, source: Path, model: str, candidate_on: bool) -> list[str]:
    command = [python, "-m", "freetoken.cli", "serve", model, "--host", "127.0.0.1", "--port", str(PORT),
               "--served-model-name", model, "--moe-strategy", "offload", "--ple-backend", "pinned",
               "--max-prefill-length", "4096", "--max-seq-len", "98304", "--num-tokens", "98304",
               "--mem-fraction-static", "0.88", "--moe-cache-auto", "--moe-prefill-hit-d2d",
               "--cuda-graph-max-bs", "2", "--max-running-requests", "2", "--enable-cache-report",
               "--quant-backend", "moe.nvfp4=triton"]
    if candidate_on:
        command.append("--prefill-layer-major")
    return command


def run(args) -> None:
    authorization = json.loads(Path(args.authorization).read_text())
    if authorization.get("authorized") is not True:
        raise RuntimeError("WINDOW_AUTHORIZATION.json does not authorize this window")
    helper_path = Path(args.d07_helper)
    if _sha256(helper_path).lower() != HELPER_SHA256:
        raise RuntimeError("pinned D07 helper hash differs")
    helper = _load_module(helper_path, "window_d07")
    guard = _load_module(Path(args.recovery_guard), "window_recovery_guard")
    active = json.loads(Path(args.active_snapshot).read_text())
    guard.verify_sources(authorization)
    guard.verify_active(authorization["active_snapshot"], active)
    lifecycle = helper.load_owned_lifecycle(Path(args.lifecycle_source))
    lock = helper.take_d07_gpu_lock("upstreamLM-20261014", 0)
    production_stopped = False
    try:
        helper.require_gpu_idle()
        lifecycle.stop_owned_process(json.loads(Path(args.production_receipt).read_text()), 120, 30)
        production_stopped = True
        start = time.time()
        measurement_deadline, window_deadline = start + MEASUREMENT_SECONDS, start + MEASUREMENT_SECONDS + RESTORE_RESERVE_SECONDS
        root = Path(args.output); root.mkdir(parents=True, exist_ok=False)
        for arm, source, enabled in (("main", Path(args.main_source), False), ("candidate_off", Path(args.candidate_source), False), ("candidate_on", Path(args.candidate_source), True)):
            _remaining(measurement_deadline, f"start {arm}")
            arm_dir = root / arm; arm_dir.mkdir()
            env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(source), str(Path(args.observer_dir)), env.get("PYTHONPATH", "")))
            with (arm_dir / "service.log").open("wb") as log:
                service = subprocess.Popen(_service_command(args.measurement_python, source, args.model, enabled), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                _health(min(measurement_deadline, time.time() + 180), service)
                _snapshot(arm_dir / "before.json")
                client = [args.controller_python, str(Path(args.client)), "run-arm", "--base-url", f"http://127.0.0.1:{PORT}", "--model", args.model, "--inputs", args.inputs, "--output", str(root), "--arm", arm, "--native-dir", str(arm_dir / "native"), "--deadline-unix", str(measurement_deadline)]
                subprocess.run(client, check=True, timeout=_remaining(measurement_deadline, f"measure {arm}"))
                _snapshot(arm_dir / "after.json")
            finally:
                lifecycle.stop_owned_process({"pid": service.pid}, 120, 30)
                helper.require_gpu_idle()
        main_ids = _native_ids(root / "main")
        for arm in ("candidate_off", "candidate_on"):
            candidate_ids = _native_ids(root / arm)
            if candidate_ids != main_ids:
                raise RuntimeError(f"{arm} native token IDs differ from main")
        if time.time() > measurement_deadline:
            raise RuntimeError("measurement exceeded 30 minute limit")
    finally:
        helper.release_d07_gpu_lock(lock)
        if production_stopped:
            subprocess.run([args.controller_python, args.restore_start], check=True, timeout=_remaining(window_deadline, "restore start"))
            subprocess.run([args.controller_python, args.restore_wait], check=True, timeout=_remaining(window_deadline, "restore smoke"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    for name in ("authorization", "d07-helper", "recovery-guard", "active-snapshot", "lifecycle-source", "production-receipt", "controller-python", "measurement-python", "main-source", "candidate-source", "model", "inputs", "client", "observer-dir", "output", "restore-start", "restore-wait"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("refusing to control services without --run")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
