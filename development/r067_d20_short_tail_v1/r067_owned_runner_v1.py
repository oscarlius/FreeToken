#!/usr/bin/env python3
"""Admission-gated R067 controller.  FILEdry never starts a process or takes a lock."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
WT_D20 = ROOT / "wt/d20_short_tail_v1"
WT_RELEASE = ROOT / "wt/e2oom-protocol-restart"
RID = "E2-R067-d20-short-tail"
BASE = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
D20 = "d50be0f8f84ab1105f788be8f1354773ad539b63"
LIMITS = {"services": 6, "generation_calls": 28}
CLEANUP_FAILED = ROOT / "run/production.cleanup_failed.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def service_rows() -> list[dict[str, object]]:
    rows = []
    for prefix in (8192, 8256):
        rows.append({"name": f"hot_p{prefix}", "kind": "hot", "worktree": str(WT_RELEASE),
                     "commit": BASE, "calls": 5, "seed": [0, prefix + 1], "tails": [1, 30, 63, 64],
                     "wrapper": None, "FT_DEV_PREFILL_SCHEDULE": None})
        for arm in ("A", "B"):
            rows.append({"name": f"cold_{arm}_p{prefix}", "kind": "cold", "worktree": str(WT_D20),
                         "commit": D20, "calls": 4, "cache_type": "naive", "tails": [1, 30, 63, 64],
                         "wrapper": "r067_cold_startup.py", "rearm": "uid+input_sha+schedule_sha+idle"})
    return rows


def candidate(path: Path, commit: str) -> dict[str, str]:
    if path.is_symlink() or subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip() != commit:
        raise RuntimeError("R067 worktree commit differs")
    if subprocess.check_output(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise RuntimeError("R067 worktree is dirty")
    return {"worktree": str(path), "commit": commit}


def source_map() -> dict[str, str]:
    paths = {name: HERE / name for name in ("r067_owned_runner_v1.py", "r067_prepare.py", "r067_cold_hook.py", "r067_cold_startup.py", "r067_wire.py", "test_cpu.py")}
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise RuntimeError("R067 source closure unavailable")
    return {name: sha(path) for name, path in paths.items()}


def plan() -> dict[str, object]:
    rows = service_rows()
    calls = sum(int(row["calls"]) for row in rows)
    if len(rows) != LIMITS["services"] or calls != 26 or calls > LIMITS["generation_calls"]:
        raise RuntimeError("R067 service/call budget differs")
    return {"schema": "ft_r067_owned_plan/v1", "rid": RID, "candidates": [candidate(WT_RELEASE, BASE), candidate(WT_D20, D20)],
            "scope": {"services": 6, "generation_calls": 26, "upper_generation_calls": 28},
            "sampling": {"max_tokens": 128, "temperature": 0, "top_p": 1, "ignore_eos": True},
            "services": rows, "ports": {"dynamic_only": True, "reject": [8095, 8096]},
            "interlocks": {"shared_gpu_lock": True, "reject_cleanup_failed": str(CLEANUP_FAILED),
                           "root_admission_required": True, "independent_review_required": True},
            "stop": {"A_not_equal_B": "failed_harness_first_divergence", "hot_difference": "not_met_first_divergence",
                     "probe_invalid": "continue_remaining_valid_cells_no_full_pass"}, "source_sha256": source_map()}


def freeze(out: Path) -> dict[str, str]:
    runtime = out / "runtime_sources"; runtime.mkdir()
    hashes = {}
    for name in source_map():
        target = runtime / name; shutil.copyfile(HERE / name, target); target.chmod(0o444); hashes[name] = sha(target)
    write_new(out / "source_manifest.json", {"schema": "ft_r067_source_manifest/v1", "files": hashes})
    (out / "source_manifest.json").chmod(0o444)
    return hashes


def filedry(out_root: Path) -> dict[str, object]:
    out = out_root / ("r067_filedry_" + time.strftime("%Y%m%d_%H%M%S")); out.mkdir(parents=True)
    package = plan(); freeze(out); write_new(out / "preflight.json", package)
    for row in package["services"]:
        directory = out / row["name"]; directory.mkdir()
        write_new(directory / "no_start.json", {"filedry": True, "popen": False, "request": False, "gpu_lock_taken": False,
                                                  "dynamic_port_required": True, "service": row})
    write_new(out / "filedry.json", {"schema": "ft_r067_filedry/v1", "rid": RID, "output": str(out),
                                      "no_formal_rid_batch_lock_popen_or_request": True, "admission_required_before_run": True})
    return {"output": str(out), "filedry_sha256": sha(out / "filedry.json"), "source_manifest_sha256": sha(out / "source_manifest.json"), "preflight_sha256": sha(out / "preflight.json")}


def require_admission(path: Path | None) -> dict[str, object]:
    if CLEANUP_FAILED.exists():
        raise RuntimeError("production cleanup-failed isolation marker exists")
    if path is None or path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("immutable root admission required")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("rid") != RID or doc.get("scope") != {"services": 6, "generation_calls": 26} or not doc.get("approved"):
        raise RuntimeError("R067 root admission differs")
    if doc.get("source_sha256") != source_map():
        raise RuntimeError("R067 admission source map stale")
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--filedry", type=Path); parser.add_argument("--run", action="store_true"); parser.add_argument("--admission", type=Path)
    args = parser.parse_args(argv)
    if bool(args.filedry) == args.run:
        parser.error("choose --filedry or --run")
    if args.filedry:
        print(json.dumps(filedry(args.filedry), sort_keys=True)); return 0
    # The subsequent owned reserve/publish child is intentionally unavailable
    # until the FILEdry and independent review bind this exact source package.
    require_admission(args.admission)
    raise RuntimeError("R067 admitted launch child has not been sealed into this source package")


if __name__ == "__main__":
    raise SystemExit(main())
