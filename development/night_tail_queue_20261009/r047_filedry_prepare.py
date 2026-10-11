#!/usr/bin/env python3
"""Task-owned launcher for R047 v12's existing FILEdry implementation.

It imports the frozen R047 source read-only and delegates executor emission and
FILEdry to that source.  There is no service, HTTP, CUDA, lock or batch action
in this wrapper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "r047_runtime_v12" / "r047_prepare_v11.py"
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
ARMS = ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source():
    if SOURCE.is_symlink() or not SOURCE.is_file():
        raise RuntimeError("R047 v12 source is unavailable")
    spec = importlib.util.spec_from_file_location("night_r047_v12", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if module.CANDIDATE != CANDIDATE or tuple(module.FORMAL_PREDECESSORS)[-1] != ("E2-R044", "measured"):
        raise RuntimeError("R047 v12 identity or final predecessor differs")
    return module


def inspect() -> dict:
    module = load_source()
    argv = module.serve_argv(15000)
    return {
        "status": "CPU_PREPARED_PENDING_EXISTING_GATES",
        "rid": module.RID,
        "candidate_commit": module.CANDIDATE,
        "source": str(SOURCE),
        "source_sha256": sha256(SOURCE),
        "arms": list(ARMS),
        "service_arms": len(ARMS),
        "per_arm_requests": {"positive_streamed": 3, "negative": 1},
        "formal_predecessors": list(module.FORMAL_PREDECESSORS),
        "serve_baseline": {
            "memory_ratio": argv[argv.index("--memory-ratio") + 1],
            "kv_reserve_tokens": argv[argv.index("--kv-reserve-tokens") + 1],
            "max_seq_len_override": argv[argv.index("--max-seq-len-override") + 1],
        },
        "filedry_effects": {
            "service_started": False, "requests_sent": False,
            "gpu_lock_taken": False, "batch_allocated": False,
            "formal_rid_directory_created": False,
        },
    }


def emit(destination: Path) -> Path:
    return load_source().emit_review_executor(destination)


def file_dry(executor: Path, review_receipt: Path, worktree: Path, output_root: Path, directory: Path) -> None:
    if sys.platform != "linux":
        raise RuntimeError("R047 FILEdry must use the existing Linux gate/worktree environment")
    command = [sys.executable, str(executor), "--file-dry-run", str(directory),
               "--review-receipt", str(review_receipt), "--worktree", str(worktree), "--out", str(output_root)]
    subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--emit", type=Path)
    parser.add_argument("--file-dry", action="store_true")
    parser.add_argument("--executor", type=Path)
    parser.add_argument("--review-receipt", type=Path)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.inspect, args.emit, args.file_dry)) != 1:
        parser.error("select exactly one action")
    if args.inspect:
        print(json.dumps(inspect(), sort_keys=True))
        return 0
    if args.emit:
        print(emit(args.emit))
        return 0
    required = (args.executor, args.review_receipt, args.worktree, args.output_root, args.directory)
    if any(value is None for value in required):
        parser.error("--file-dry requires executor, review receipt, worktree, output root and directory")
    file_dry(*required)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
