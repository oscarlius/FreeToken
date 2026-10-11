#!/usr/bin/env python3
"""CPU-only source freeze and FILEdry packet for E2-R067-d20-short-tail."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
D20 = Path(os.environ.get("R067_D20_WORKTREE", HERE.parent / "d20_short_tail_v1"))
BASE = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
D20_COMMIT = "d50be0f8f84ab1105f788be8f1354773ad539b63"
RID = "E2-R067-d20-short-tail"
PREFIXES = (8192, 8256)
TAILS = (1, 30, 63, 64)
SAMPLING = {"max_tokens": 128, "temperature": 0, "top_p": 1, "ignore_eos": True}
CLEANUP_FAILED = "/data2/FreeToken/run/production.cleanup_failed.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(D20), *args], text=True).strip()


def segments(prefix: int, tail: int) -> list[dict[str, object]]:
    donor_end = prefix + 1
    chunks = [4096, 4096, donor_end - 8192]
    return [
        {"start": 0, "end": donor_end, "mode": "layer_major", "subchunks": chunks},
        {"start": prefix, "end": prefix + tail, "mode": "ordinary", "subchunks": [tail]},
    ]


def plan() -> dict[str, object]:
    services: list[dict[str, object]] = []
    for prefix in PREFIXES:
        services.append({
            "name": f"hot_p{prefix}", "kind": "hot", "worktree_commit": BASE,
            "seed": {"token_range": [0, prefix + 1], "calls": 1},
            "queries": [{"tail": tail, "cached_tokens": prefix, "new_tokens": tail,
                         "tail_content": f"r067-hot-{prefix}-{tail}"} for tail in TAILS],
        })
        for arm in ("A", "B"):
            services.append({
                "name": f"cold_{arm}_p{prefix}", "kind": "cold", "arm": arm,
                "worktree_commit": D20_COMMIT, "cache": "disabled",
                "queries": [{"tail": tail, "cached_tokens": 0,
                             "segments": segments(prefix, tail)} for tail in TAILS],
                "schedule_consumptions_required": 4,
            })
    calls = sum(service["seed"]["calls"] if service["kind"] == "hot" else 0 for service in services)
    calls += sum(len(service["queries"]) for service in services)
    return {
        "schema": "ft_r067_d20_plan/v1", "rid": RID,
        "scope": {"services": len(services), "generation_calls": calls,
                  "limits": {"services": 6, "generation_calls": 28}},
        "sampling": SAMPLING, "services": services,
        "comparison": {"compare": ["token_ids", "full_text"], "a_not_equal_b": "failed_harness",
                       "hot_different": "not_met_stop", "tooling_retries_max": 2},
        "admission_interlocks": {"gpu_lock_required": True, "dynamic_ports_only": True,
                                 "reject_ports": [8095, 8096],
                                 "reject_if_exists": CLEANUP_FAILED,
                                 "cold_rearm": "R067-only hook; idle, UID and input-SHA bound"},
    }


def source_freeze() -> dict[str, object]:
    if git("rev-parse", "HEAD") != D20_COMMIT:
        raise RuntimeError("D20 worktree is not at the frozen commit")
    if git("status", "--porcelain"):
        raise RuntimeError("D20 worktree is not clean")
    changed = git("diff", "--name-only", f"{BASE}..{D20_COMMIT}").splitlines()
    runtime_changed = [p for p in changed if p.startswith("python/")]
    if runtime_changed != ["python/freetoken/engine/engine.py"]:
        raise RuntimeError(f"unexpected runtime changes: {runtime_changed}")
    engine = D20 / runtime_changed[0]
    text = engine.read_text(encoding="utf-8")
    method_start = text.index("    def _forward_dev_prefill_schedule")
    method_end = text.index("\n    def ", method_start + 5)
    diff = git("diff", "--unified=0", f"{BASE}..{D20_COMMIT}", "--", runtime_changed[0])
    if "index: following.start" not in diff or "rewind_after.get(index)" not in diff:
        raise RuntimeError("D20 same-end segment-index fix absent")
    prefill = D20 / "python/freetoken/scheduler/prefill.py"
    one_shot = "self.dev_prefill_schedule = None" in prefill.read_text(encoding="utf-8")
    if not one_shot:
        raise RuntimeError("expected one-shot schedule guard absent; re-review required")
    return {
        "base_commit": BASE, "d20_commit": D20_COMMIT, "worktree": str(D20),
        "changed_paths": changed, "runtime_changed_paths": runtime_changed,
        "engine_sha256": digest(engine), "prefill_sha256": digest(prefill),
        "changed_method": "_forward_dev_prefill_schedule",
        "method_source_sha256": hashlib.sha256(text[method_start:method_end].encode()).hexdigest(),
        "normal_scheduler_source_changed": False,
        "one_shot_schedule_source": str(prefill), "one_shot_schedule": True,
    }


def packet() -> dict[str, object]:
    current_plan = plan()
    return {
        "schema": "ft_r067_d20_filedry/v1", "rid": RID, "source": source_freeze(),
        "plan": current_plan, "cpu_only": True, "gpu_started": False,
        "popen": False, "http_requests": False, "gpu_lock_taken": False,
        "cold_matrix_admission": {
            "admittable": "pending_root_admission_and_independent_review",
            "one_shot_schedule": True,
            "rearm_design": "cold-only R067 hook before original Scheduler._process_one_msg",
            "rearm_requirements": ["idle_drained", "one_pending_via_original_guard", "UID_bound", "actual_input_SHA_bound", "frozen_schedule_SHA_bound", "cache_type_naive"],
        },
    }


def write_packet(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    target = out / "r067_filedry.json"
    target.write_text(json.dumps(packet(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filedry", type=Path, required=True)
    args = parser.parse_args(argv)
    print(write_packet(args.filedry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
