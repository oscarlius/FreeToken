#!/usr/bin/env python3
"""Bind and run eight official-SDK loopback tests without touching the candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
EVAL = Path("/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python")
SERVER = Path("/data2/FreeToken/venv/bin/python")
CANDIDATE = Path("/data2/FreeToken/wt/e2oom-protocol-restart")
COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_dir
    if root.exists():
        raise RuntimeError("artifact directory already exists")
    if subprocess.check_output(["git", "-C", str(CANDIDATE), "rev-parse", "HEAD"], text=True).strip() != COMMIT:
        raise RuntimeError("candidate commit differs")
    if subprocess.check_output(["git", "-C", str(CANDIDATE), "status", "--porcelain"], text=True):
        raise RuntimeError("candidate worktree is not clean")
    root.mkdir(mode=0o700, parents=True)
    command = [str(EVAL), "-m", "pytest", "-q", str(HERE / "test_public_sdk.py"), "--junitxml", str(root / "junit.xml")]
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "FT_SDK_ARTIFACT_DIR": str(root), "FT_SDK_SERVER_PYTHON": str(SERVER), "FT_SDK_CANDIDATE": str(CANDIDATE)}
    for key in ("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "http_proxy", "https_proxy"):
        env.pop(key, None)
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    completed = subprocess.run(command, text=True, capture_output=True, env=env)
    (root / "pytest.stdout.log").write_text(completed.stdout)
    (root / "pytest.stderr.log").write_text(completed.stderr)
    receipt = {
        "schema": "ft_r061_public_sdk_cpu/v1", "candidate_commit": COMMIT, "candidate": str(CANDIDATE),
        "command": command, "returncode": completed.returncode,
        "sources": {path.name: sha(path) for path in (HERE / "fixture_server.py", HERE / "test_public_sdk.py", HERE / "run_public_sdk_cpu.py")},
        "stdout_sha256": sha(root / "pytest.stdout.log"), "stderr_sha256": sha(root / "pytest.stderr.log"),
        "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"], "gpu_used": False,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
