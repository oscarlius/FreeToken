"""Read-only, CPU recomputation audit for the eight-arm R032 D14 schedule gate."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

RID = "E2-R032-gate-D14"
BATCH = 60
DIRECTORY = Path("/data2/_shared/runs/ft_rounds") / RID
RECEIPT = Path("/data2/FreeToken/runs/dev_D14/launch_" + RID + ".json")
PARENT = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
BATCH_PID, BATCH_START_TICKS = 907150, 123278676
RUNNER_SHA = "0ba84245224aedf56a8252b1972a6dd12aefa4220cf837fd3b70e3fdc2ba5364"
ADAPTER_SHA = "0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8"
BASE_SHA = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"
WRAPPER_SHA = "06d48e07f7c712a12349a89dafd1ac9784950f92f7423a386686daf9d7620b89"
CPU_STAGE_SHA = "458553a9db361c00ff4f1056604fc6c8807c086f27b66a1b363122c1b542736c"
ARMS = tuple(f"{prefix}{name}_b{BATCH}" for prefix in ("", "CHUNK_")
             for name in ("PARENT", "NEW", "PARENT_P", "NEW_P"))
LAYER_ARMS, CHUNK_ARMS = ARMS[:4], ARMS[4:]
PID_RE = re.compile(r"['\"]?\.pid=(\d+)['\"]?")
CONTROL = ("round.json", "round_history", "MANIFEST.sha256", "initial_metadata.json")
ARGS_PARSER = Path("/data2/FreeToken/scripts/serve_args_diff.py")
HELPERS = Path(__file__).with_name("t16_r022_review.py")
HELPERS_SHA = "d212243e709d521ad93c91893103eb202ae9497c736c38692480c340e68662ec"


def _import(path: Path, expected: str, name: str):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("pinned source bytes differ: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


_helpers = _import(HELPERS, HELPERS_SHA, "ft_r032_pinned_helpers")
sha, require, load, guarded, terminal, owned = (_helpers.sha, _helpers.require, _helpers.load,
                                                  _helpers.guarded, _helpers.terminal, _helpers.owned)
import_pinned = _helpers.import_pinned


def mode_for_arm(arm: str) -> str:
    if arm in LAYER_ARMS:
        return "layer_major"
    if arm in CHUNK_ARMS:
        return "non_layer_major"
    raise ValueError("unexpected R032 arm: " + arm)


def cases_for_mode(mode: str):
    if mode == "layer_major":
        return [("det", "", 32052, 128)]
    if mode == "non_layer_major":
        return [("short", "", 2000, 128), ("chunked", "", 32052, 128)]
    raise ValueError("unexpected R032 mode: " + mode)


def service(directory: Path, arm: str) -> int:
    mode = mode_for_arm(arm)
    path = directory / arm
    names = ["SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt", "prefill_seq.txt"]
    names += [case[0] + ".json" for case in cases_for_mode(mode)]
    if "_P_" not in arm:
        names += ["d0_prefill.jsonl", "prefill_while_alive.json"]
    if any(not (path / name).exists() for name in names):
        raise ValueError("incomplete service evidence: " + arm)
    for name in names:
        require(path / name)
    ids = PID_RE.findall((path / "serve_args.txt").read_text(encoding="utf-8"))
    if len(ids) != 1 or not terminal(int(ids[0])):
        raise ValueError("live or ambiguous owned service PID: " + arm)
    expected = PARENT if "PARENT" in arm else CANDIDATE
    if expected not in (path / "ENV.txt").read_text(encoding="utf-8"):
        raise ValueError("wrong source commit: " + arm)
    if "_P_" not in arm:
        live = load(path / "prefill_while_alive.json")
        if live.get("service_pid") != int(ids[0]) or live.get("process_alive") is not True or live.get("includes_terminal_prefill") is not True:
            raise ValueError("actual terminal prefill evidence differs: " + arm)
    elif list(path.glob("d0*")):
        raise ValueError("production arm leaks D0 evidence: " + arm)
    return int(ids[0])


def _parser() -> dict:
    source = require(ARGS_PARSER).read_bytes()
    if hashlib.md5(source).hexdigest() != "ce123cb0af201d99baac91f7f8e4f8c7":
        raise ValueError("reviewed parsed-args reader differs")
    scope = {"__file__": str(ARGS_PARSER), "__name__": "ft_r032_args"}
    exec(compile(source, str(ARGS_PARSER), "exec"), scope)
    return scope


def _verify_stage(receipt: dict, frozen: Path) -> dict:
    stage = guarded(Path(receipt["source_stage"]))
    for origin in (stage, frozen.parent):
        owned(origin)
        for path in (origin, *origin.rglob("*")):
            if path.stat().st_mode & 0o222:
                raise ValueError("writable frozen stage/runtime path: " + str(path))
    report = load(stage / "cpu_validation.json")
    if sha(stage / "cpu_validation.json") != CPU_STAGE_SHA or receipt.get("cpu_stage_sha256") != CPU_STAGE_SHA:
        raise ValueError("CPU stage binding differs")
    if report.get("schema") != "ft_t16_d14_schedule_stage/v1" or report.get("verdict") != "PASS" or report.get("gpu_started") is not False or report.get("requests_sent") is not False or report.get("passed") != 75:
        raise ValueError("CPU stage report differs")
    files = report.get("files")
    if not isinstance(files, dict) or files != receipt.get("source_files") or len(files) != 29:
        raise ValueError("frozen 29-source map differs")
    if "tests/test_d18_client_params.py" not in files:
        raise ValueError("D18 test source is absent from frozen stage")
    for name, digest in files.items():
        for root in (stage, frozen.parent):
            path = require(root / name)
            if sha(path) != digest or path.stat().st_mode & 0o222:
                raise ValueError("frozen runtime/CPU source changed: " + name)
    if set(report.get("steps", {})) != {"regression", "d18_binding"}:
        raise ValueError("CPU stage step set differs")
    for name, step in report["steps"].items():
        log = require(stage / (name + ".log"))
        if step.get("returncode") != 0 or sha(log) != step.get("log_sha256"):
            raise ValueError("CPU stage log differs: " + name)
    cpu = load(stage / "d14_schedule_cpu_receipt.json")
    proof = require(Path(cpu["stage"]) / "cpu_validation.json")
    if proof.stat().st_mode & 0o222 or sha(proof) != cpu.get("report_sha256") or load(proof) != cpu.get("report"):
        raise ValueError("embedded engine CPU proof differs from immutable report")
    engine = cpu["report"]
    if engine.get("candidate_commit") != CANDIDATE or engine.get("tree") != "09068014ec70359cb20919669be43e2dc56c9cba" or engine.get("verdict") != "PASS":
        raise ValueError("embedded engine candidate proof differs")
    return report


def verify_d18_archives(directory: Path, schedule) -> dict:
    # Historical replay uses only the frozen D18 receipt/test map and archived
    # round bytes; it deliberately never opens a mutable live probe or client.
    frozen_receipt = require(schedule.D18)
    frozen_log = require(schedule.D18_LOG)
    if (sha(directory / "d18_independent_cpu_receipt.json") != sha(frozen_receipt)
            or sha(directory / "d18_independent_cpu_receipt.log") != sha(frozen_log)):
        raise ValueError("D18 archives differ from frozen CPU-tested sources")
    receipt = load(frozen_receipt)
    sources = receipt.get("source_files")
    if (receipt.get("schema") != "ft_d18_independent_cpu/v1" or receipt.get("returncode") != 0
            or receipt.get("gpu_started") is not False or receipt.get("requests_sent") is not False
            or not isinstance(sources, dict)):
        raise ValueError("D18 archived receipt differs")
    if sources.get("tests/test_d18_client_params.py") != sha(require(schedule.D18_TEST)):
        raise ValueError("D18 test source differs from frozen CPU proof")
    expected = {"receipt_sha256": sha(directory / "d18_independent_cpu_receipt.json"),
                "log_sha256": sha(directory / "d18_independent_cpu_receipt.log"),
                "probe_sha256": sha(directory / "d18_probe_ft_cold32k.py"),
                "probe_md5": hashlib.md5(require(directory / "d18_probe_ft_cold32k.py").read_bytes()).hexdigest(),
                "benchmark_sha256": sources.get("../_shared/benchmark_client.py"),
                "test_sha256": sources.get("tests/test_d18_client_params.py")}
    if expected["probe_sha256"] != schedule.PROBE_SHA or expected["probe_md5"] != schedule.PROBE_MD5:
        raise ValueError("D18 frozen probe differs")
    if receipt.get("log_sha256") != expected["log_sha256"] or sources.get("scripts/probe_ft_cold32k.py") != expected["probe_sha256"]:
        raise ValueError("D18 archived receipt/log/probe differs")
    binding = load(directory / "d18_binding.json")
    if binding != expected:
        raise ValueError("D18 archived binding differs")
    return binding


def validate_status(status: dict) -> None:
    expected = {"rid": RID, "batch": BATCH, "candidate_case": "D14-schedule",
                "state": "complete_measurements_pending_review", "batch_pid": BATCH_PID}
    if any(status.get(key) != value for key, value in expected.items()):
        raise ValueError("terminal status identity differs")
    if "batch_start_ticks" in status and status["batch_start_ticks"] != BATCH_START_TICKS:
        raise ValueError("status birth differs")


def audit(directory: Path = DIRECTORY, receipt_path: Path = RECEIPT, *, allow_review: bool = False) -> dict:
    directory = guarded(directory)
    if directory != DIRECTORY:
        raise ValueError("exact canonical R032 round required")
    prohibited = CONTROL + (() if allow_review else (f"review_batch{BATCH}.json",))
    if any((directory / name).exists() for name in prohibited):
        raise ValueError("unsealed unreviewed round required")
    owned(directory)
    raw_files = {path.relative_to(directory).as_posix(): sha(path) for path in directory.rglob("*")
                 if path.is_file() and path.relative_to(directory).parts[0] not in CONTROL
                 and path.name != f"review_batch{BATCH}.json"}
    status = load(directory / f"status_batch{BATCH}.json")
    validate_status(status)
    receipt = load(receipt_path)
    required = {"schema": "ft_t16_d14_schedule_launch/v1", "state": "launched", "rid": RID, "batch": BATCH, "card": "D14", "case": "D14-schedule", "parent_commit": PARENT, "candidate_commit": CANDIDATE, "runner_sha256": RUNNER_SHA, "batch_pid": BATCH_PID, "batch_pgid": BATCH_PID, "wrapper_sha256": WRAPPER_SHA}
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError("launch receipt identity differs")
    identity = receipt.get("process_identity", {})
    if any(identity.get(key) != value for key, value in {"pid": BATCH_PID, "pgid": BATCH_PID, "session": BATCH_PID, "start_ticks": BATCH_START_TICKS}.items()):
        raise ValueError("launch process identity differs")
    if not terminal(BATCH_PID, BATCH_START_TICKS):
        raise ValueError("batch remains live")
    frozen = guarded(Path(receipt.get("frozen_runner", "")))
    if sha(frozen) != RUNNER_SHA:
        raise ValueError("frozen runner differs")
    schedule = import_pinned(frozen, RUNNER_SHA, "ft_r032_schedule_adapter")
    adapter = frozen.with_name("t16_candidate_runner_full_tail.py")
    module = import_pinned(adapter, ADAPTER_SHA, "ft_r032_shared_adapter")
    if sha(require(frozen.with_name("t16_full_tail_base_runner.py"))) != BASE_SHA:
        raise ValueError("frozen base runner differs")
    _verify_stage(receipt, frozen)
    if sha(require(directory / f"runner_batch{BATCH}.py")) != RUNNER_SHA or sha(require(directory / f"base_runner_batch{BATCH}.py")) != BASE_SHA or sha(require(directory / f"batch{BATCH}.sh")) != WRAPPER_SHA:
        raise ValueError("archived runner/base/wrapper differs")
    binding = load(directory / "candidate_binding.json")
    need = {"case": "D14-schedule", "card": "D14", "parent_wt": "e2d14", "new_wt": "e2d14-schedule", "parent_commit": PARENT, "new_commit": CANDIDATE, "ordinary_prefill": True, "candidate_runner_sha256": RUNNER_SHA, "base_runner_sha256": BASE_SHA}
    if any(binding.get(key) != value for key, value in need.items()):
        raise ValueError("candidate binding differs")
    verify_d18_archives(directory, schedule)
    service_pids = {arm: service(directory, arm) for arm in ARMS}
    parser = _parser()
    replay = object.__new__(module.CandidateRunner)
    replay.parser = parser["parse"]
    recomputed = {}
    for mode, arms in (("layer_major", LAYER_ARMS), ("non_layer_major", CHUNK_ARMS)):
        recomputed[mode] = json.loads(json.dumps(module.CandidateRunner.compare(replay, *(directory / arm for arm in arms), cases=cases_for_mode(mode)), allow_nan=False))
        for side in ("D0", "PROD"):
            if set(recomputed[mode][side]["args"]) != {"_unique_suffix"}:
                raise ValueError("only PID suffix may differ: " + mode + "/" + side)
            for case, _, target, tokens in cases_for_mode(mode):
                records = recomputed[mode][side][case]["records"]
                if len(records) != 2 or any(r.get("built_tokens") != target or r.get("completion_tokens") != tokens for r in records):
                    raise ValueError("full text/token evidence differs: " + mode + "/" + case)
    raw = load(directory / f"gate_batch{BATCH}.json")
    if raw.get("arms") != list(ARMS) or raw.get("gate") != "D14" or raw.get("candidate_case") != "D14-schedule" or raw.get("parent_commit") != PARENT or raw.get("new_commit") != CANDIDATE:
        raise ValueError("raw gate identity differs")
    if any(raw.get(mode) != value for mode, value in recomputed.items()):
        raise ValueError("recomputed evidence differs from raw gate")
    if Path("/data2/_shared/gpu.lock").exists():
        raise ValueError("R032 audit requires released GPU lock")
    return {"schema": "ft_independent_raw_review/v1", "scope": "CPU_RAW_RECOMPUTATION; fresh raw map only, not formal acceptance", "verdict": "PASS", "formal_verdict": "pending_review", "rid": RID, "batch": BATCH, "parent_commit": PARENT, "candidate_commit": CANDIDATE, "gate_sha256": sha(directory / f"gate_batch{BATCH}.json"), "receipt_sha256": sha(receipt_path), "raw_files": raw_files, "service_pids": service_pids, "recomputed": recomputed, "checks": {"eight_arms": True, "terminal_owned_batch_and_services": True, "fulltext_and_128_token_count": True, "pid_only_args": True, "frozen_29_sources": True, "d18_binding": True}}


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
