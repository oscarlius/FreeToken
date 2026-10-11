"""Independently recompute the terminal D14 T16 gate before it is sealed."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import ModuleType

RID = "E2-R021-gate-D14"
BATCH = 49
DIRECTORY = Path("/data2/_shared/runs/ft_rounds") / RID
RECEIPT = Path("/data2/FreeToken/runs/dev_D14/launch_" + RID + ".json")
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
BATCH_PID = 120974
BATCH_START_TICKS = 121621035
RUNNER_SHA = "55677170b0f6625cfdebd2ea81bd945ef003e700bcc0afb7b602202e32bae592"
ADAPTER_SHA = "d29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1"
BASE_SHA = "66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125"
WRAPPER_SHA = "d399d38607d841d32977793f7790dc5ad6a0b95f423f043ca0d950e7ddfbb8c2"
ARMS = ("PARENT_b49", "NEW_b49", "PARENT_P_b49", "NEW_P_b49")
PID_RE = re.compile(r"['\"]?\.pid=(\d+)['\"]?")
CONTROL = ("round.json", "round_history", "MANIFEST.sha256", "initial_metadata.json")
ARGS_PARSER = Path("/data2/FreeToken/scripts/serve_args_diff.py")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(path: Path) -> Path:
    path = Path(path)
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError("missing actual artifact: " + str(path))
    return path


def load(path: Path) -> dict:
    try:
        value = json.loads(require(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON: " + str(path)) from exc
    if not isinstance(value, dict):
        raise ValueError("JSON object required: " + str(path))
    return value


def guarded(path: Path) -> Path:
    raw = Path(os.path.abspath(path))
    for ancestor in (raw, *raw.parents):
        if ancestor.is_symlink():
            raise ValueError("symlink path or ancestor rejected: " + str(ancestor))
    return raw.resolve(strict=True)


def terminal(pid: int, start_ticks: int | None = None) -> bool:
    if type(pid) is not int or pid <= 0:
        raise ValueError("positive PID required")
    stat = Path("/proc") / str(pid) / "stat"
    if not stat.exists():
        return True
    fields = stat.read_text().rpartition(") ")[2].split()
    if len(fields) < 20:
        raise ValueError("invalid proc stat: " + str(pid))
    if start_ticks is not None and int(fields[19]) != start_ticks:
        raise ValueError("PID was reused: " + str(pid))
    return fields[0] == "Z"


def owned(directory: Path) -> None:
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    for path in (directory, *directory.rglob("*")):
        if path.is_symlink() or (uid is not None and path.stat().st_uid != uid):
            raise ValueError("foreign owner or symlink rejected: " + str(path))


def import_pinned(path: Path, expected: str, name: str) -> ModuleType:
    path = require(path)
    if sha(path) != expected:
        raise ValueError("pinned source bytes differ: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def service(directory: Path, arm: str) -> int:
    path = directory / arm
    for name in ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt", "det.json", "prefill_seq.txt", "d0_prefill.jsonl"):
        require(path / name)
    ids = PID_RE.findall((path / "serve_args.txt").read_text(encoding="utf-8"))
    if len(ids) != 1 or not terminal(int(ids[0])):
        raise ValueError("live or ambiguous owned service PID: " + arm)
    expected = PARENT if arm.startswith("PARENT") else CANDIDATE
    if expected not in (path / "ENV.txt").read_text(encoding="utf-8"):
        raise ValueError("wrong source commit: " + arm)
    return int(ids[0])


def audit(directory: Path = DIRECTORY, receipt_path: Path = RECEIPT, *, allow_review: bool = False) -> dict:
    directory = guarded(directory)
    if directory != DIRECTORY:
        raise ValueError("exact canonical R021 round required")
    prohibited = CONTROL + (() if allow_review else (f"review_batch{BATCH}.json",))
    if any((directory / name).exists() for name in prohibited):
        raise ValueError("unsealed unreviewed round required")
    owned(directory)
    status = load(directory / f"status_batch{BATCH}.json")
    expected_status = {"rid": RID, "batch": BATCH, "candidate_case": "D14",
                       "state": "complete_measurements_pending_review", "batch_pid": BATCH_PID}
    if any(status.get(key) != value for key, value in expected_status.items()):
        raise ValueError("terminal status identity differs")
    status_ticks = status.get("batch_start_ticks", BATCH_START_TICKS)
    if status_ticks != BATCH_START_TICKS or not terminal(BATCH_PID, BATCH_START_TICKS):
        raise ValueError("batch process is not terminal with its owned start time")
    receipt = load(receipt_path)
    receipt_need = {"schema": "ft_t16_d14_launch/v1", "state": "launched", "rid": RID, "batch": BATCH,
                    "card": "D14", "parent_commit": PARENT, "candidate_commit": CANDIDATE,
                    "runner_sha256": RUNNER_SHA, "base_runner_sha256": BASE_SHA,
                    "batch_pid": BATCH_PID, "batch_pgid": BATCH_PID, "wrapper_sha256": WRAPPER_SHA}
    if any(receipt.get(key) != value for key, value in receipt_need.items()):
        raise ValueError("launch receipt identity differs")
    frozen = guarded(Path(receipt.get("frozen_runner", "")))
    if sha(frozen) != RUNNER_SHA:
        raise ValueError("frozen runner differs")
    adapter = frozen.with_name("t16_candidate_runner_full_tail.py")
    base = frozen.with_name("t16_full_tail_base_runner.py")
    module = import_pinned(adapter, ADAPTER_SHA, "ft_r021_archived_adapter")
    if sha(require(base)) != BASE_SHA:
        raise ValueError("frozen base runner differs")
    runner_archive = require(directory / f"runner_batch{BATCH}.py")
    base_archive = require(directory / f"base_runner_batch{BATCH}.py")
    wrapper = require(directory / f"batch{BATCH}.sh")
    if sha(runner_archive) != RUNNER_SHA or sha(base_archive) != BASE_SHA or sha(wrapper) != WRAPPER_SHA:
        raise ValueError("archived runner/base/wrapper differs")
    binding = load(directory / "candidate_binding.json")
    binding_need = {"case": "D14", "card": "D14", "parent_wt": "e2base", "new_wt": "e2d14",
                    "parent_commit": PARENT, "new_commit": CANDIDATE, "ordinary_prefill": False,
                    "candidate_runner_sha256": RUNNER_SHA, "base_runner_sha256": BASE_SHA}
    if any(binding.get(key) != value for key, value in binding_need.items()):
        raise ValueError("candidate binding differs")
    arms = [directory / arm for arm in ARMS]
    service_pids = {arm: service(directory, arm) for arm in ARMS}
    parser = ARGS_PARSER
    parser_source = require(parser).read_bytes()
    if hashlib.md5(parser_source).hexdigest() != "ce123cb0af201d99baac91f7f8e4f8c7":
        raise ValueError("reviewed parsed-args reader differs")
    parser_scope: dict = {"__file__": str(parser), "__name__": "ft_r021_args"}
    exec(compile(parser_source, str(parser), "exec"), parser_scope)
    replay = object.__new__(module.CandidateRunner)
    replay.parser = parser_scope["parse"]
    recomputed = module.CandidateRunner.compare(replay, *arms)
    raw = load(directory / f"gate_batch{BATCH}.json")
    if raw.get("arms") != list(ARMS) or raw.get("gate") != "D14" or raw.get("candidate_case") != "D14":
        raise ValueError("raw gate identity differs")
    if raw.get("parent_commit") != PARENT or raw.get("new_commit") != CANDIDATE or raw.get("layer_major") != recomputed:
        raise ValueError("recomputed evidence differs from raw gate")
    prefill = recomputed["prefill"]
    if (prefill.get("parent_rows"), prefill.get("new_rows"), prefill.get("all_prefill_events")) != (13, 13, 13):
        raise ValueError("complete 13-row D0 evidence required")
    for side in ("D0", "PROD"):
        record = recomputed[side]["det"]["records"]
        if len(record) != 2 or any(item["completion_tokens"] != 128 for item in record):
            raise ValueError("fulltext 128-token evidence required")
        if set(recomputed[side]["args"]) != {"_unique_suffix"}:
            raise ValueError("only PID suffix may differ")
    return {"schema": "ft_independent_raw_review/v1", "reviewer": "D14 independent archival reviewer",
            "scope": "raw recomputation and source integrity; not formal acceptance", "verdict": "PASS",
            "formal_verdict": "pending_review", "rid": RID, "batch": BATCH, "batch_pid": BATCH_PID,
            "batch_start_ticks": BATCH_START_TICKS, "parent_commit": PARENT, "candidate_commit": CANDIDATE,
            "gate_sha256": sha(directory / f"gate_batch{BATCH}.json"),
            "candidate_binding_sha256": sha(directory / "candidate_binding.json"),
            "receipt_sha256": sha(receipt_path), "runner_sha256": RUNNER_SHA, "adapter_sha256": ADAPTER_SHA,
            "base_runner_sha256": BASE_SHA, "wrapper_sha256": WRAPPER_SHA, "frozen_runner": str(frozen),
            "service_pids": service_pids, "recomputed": recomputed,
            "checks": {"fulltext_and_128_tokens": True, "pid_only_arg_difference": True,
                       "exact_prefill_sequence_and_final_row": True, "raw_gate_matches": True,
                       "terminal_owned_batch_and_services": True}}


def review(directory: Path = DIRECTORY, receipt_path: Path = RECEIPT) -> dict:
    result = audit(directory, receipt_path)
    out = directory / f"review_batch{BATCH}.json"
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return {"review_path": str(out), "review_sha256": sha(out), **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", action="store_true")
    options = parser.parse_args()
    if not options.review or sys.platform != "linux":
        parser.error("--review on the actual Linux host required")
    print(json.dumps(review(), sort_keys=True, allow_nan=False))
