"""R046a-only split of D07 service file preparation from process startup."""
from __future__ import annotations

import json
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path

ENV_RECORD_KEYS = ("CUDA_VISIBLE_DEVICES", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONDONTWRITEBYTECODE",
                   "PYTHONUNBUFFERED", "FT_DEV_ROUTE_TRACE", "FT_DEV_PAUSE_ENDPOINT")


def prepare_server_files(d07, directory: Path, worktree: Path, port: int, trace_dir: Path | None) -> dict:
    """Write the exact service inputs before either dry-run return or Popen."""
    env = d07.clean_environment(worktree, trace_dir=trace_dir)
    argv = d07.serve_argv(port)
    directory.mkdir(parents=True, exist_ok=True)
    recorded_env = {key: env[key] for key in ENV_RECORD_KEYS if key in env}
    if not recorded_env:
        raise RuntimeError("R046a service environment record is empty")
    (directory / "ENV.json").write_text(json.dumps(recorded_env, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "ENV.txt").write_text("".join(f"{key}={recorded_env[key]}\n" for key in sorted(recorded_env)), encoding="utf-8")
    (directory / "SERVE_CMD.txt").write_text(
        "env " + " ".join(f"{key}={shlex.quote(env[key])}" for key in sorted(env) if key in {"CUDA_VISIBLE_DEVICES", "FT_DEV_PAUSE_ENDPOINT", "FT_DEV_ROUTE_TRACE", "PYTHONPATH", "VIRTUAL_ENV"})
        + " " + shlex.join(argv) + "\n", encoding="utf-8")
    (directory / "serve.log").open("x", encoding="utf-8").close()
    return {"env": env, "argv": argv, "log": directory / "serve.log"}


def start_prepared_server(d07, directory: Path, worktree: Path, port: int, prepared: dict) -> subprocess.Popen:
    """Formal-only continuation after prepare_server_files; dry-run never calls this."""
    log = (directory / "serve.log").open("a", encoding="utf-8")
    process = subprocess.Popen(prepared["argv"], cwd=worktree, env=prepared["env"], stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        birth = d07.load_owned_lifecycle().process_identity(process.pid)
        if birth is None or birth.get("pgid") != process.pid or birth.get("session") != process.pid:
            raise RuntimeError("R046a owned service lacks a private process group/session")
        d07.write_new(directory / "owned_process.json", {"pid": process.pid, "pgid": process.pid, "port": port, "birth": birth})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"R046a owned service exited during startup: {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    d07.write_new(directory / "health.json", health)
                    text = (directory / "serve.log").read_text(encoding="utf-8", errors="replace")
                    position = text.find("Parsed arguments")
                    if position < 0:
                        raise RuntimeError("R046a service did not emit Parsed arguments")
                    parsed = "\n".join(text[position:].splitlines()[:2]).strip()
                    if not parsed:
                        raise RuntimeError("R046a Parsed arguments are empty")
                    (directory / "serve_args.txt").write_text(parsed + "\n", encoding="utf-8")
                    return process
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise TimeoutError("R046a owned service did not become healthy")
    except BaseException:
        try:
            d07.load_owned_lifecycle().stop_owned_process(process)
        except BaseException as cleanup_error:
            cleanup_error.owned_process = process
            cleanup_error.owned_cleanup_failed = True
            raise
        raise
