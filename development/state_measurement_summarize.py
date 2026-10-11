"""Read-only T04/T10/T11 measurement summarizer; it never changes a round."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ARMS = {"T04": ("R4096", "R8192", "RLM"), "T10": ("B1", "B2", "B3"), "T11": ("S_A_trace",)}
RID = {"T04": "E2-R002", "T10": "E2-R006", "T11": "E2-R011"}
EXPECTED_TAG = "E2-base@23f2e2c"
SERVER_TOKENIZER = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
LEN_LINE = re.compile(r"^len=.*$", re.MULTILINE)
T11_TARGET_TRACE_INDEX = 7
T11_HISTORICAL_UID = 8
T11_CACHED_TOKENS = 13376
T11_RECOMPUTED_TOKENS = 56
T11_RESUME = re.compile(r"GDN bank: resuming req (?P<uid>\d+) from host slot (?P<slot>\d+)")
T11_PREFILL = re.compile(r"Prefill batch, #new-seq: \d+, #new-token: (?P<new>\d+), #cached-token: (?P<cached>\d+)")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def finite_numbers(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_numbers(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_numbers(item) for key, item in value.items())
    return False


def state_eq(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^rc=(\d+)$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"state_eq rc is absent: {path}")
    return {"path": path.name, "sha256": sha256(path), "rc": int(match.group(1)),
            "length_lines": LEN_LINE.findall(text)}


def terminal_status(round_dir: Path, card: str) -> tuple[dict[str, Any], Path]:
    candidates = list(round_dir.glob("status_batch*.json"))
    if len(candidates) != 1:
        raise ValueError("exactly one status_batchN.json is required")
    path = candidates[0]
    match = re.fullmatch(r"status_batch(\d+)\.json", path.name)
    status = load(path)
    if not match or status.get("rid") != round_dir.name or status.get("card") != card:
        raise ValueError("status rid/card binding is invalid")
    if status.get("batch") != int(match.group(1)) or status.get("state") not in {"complete", "complete_measurements_pending_review"}:
        raise ValueError("status is not terminal for its exact batch")
    return status, path


def actual_identity(round_dir: Path, live: dict[str, Any], git_commit: str | None, git_tag: str | None) -> dict[str, str]:
    commit = git_commit
    tag = git_tag
    if commit is None:
        worktree = live.get("worktree")
        if not isinstance(worktree, str):
            raise ValueError("live_checks worktree is required to derive actual commit")
        commit = subprocess.check_output(["git", "-C", worktree, "rev-parse", "HEAD"], text=True).strip()
    if tag is None:
        worktree = live.get("worktree")
        tag = subprocess.check_output(["git", "-C", worktree, "describe", "--tags", "--exact-match"], text=True).strip()
    if not FULL_SHA.fullmatch(commit) or live.get("commit") != commit:
        raise ValueError("live_checks commit does not match actual full git HEAD")
    if tag != EXPECTED_TAG or live.get("code_version") != tag:
        raise ValueError("live_checks tag does not match E2-base admission tag")
    return {"commit": commit, "code_version": tag}


def admitted_trace(round_dir: Path, card: str, live: dict[str, Any], base: dict[str, str]) -> tuple[dict[str, Any], Path, dict[str, dict[str, Any]]]:
    path = round_dir / "admission.json"
    if not path.is_file():
        raise ValueError("admission.json is required")
    admission = load(path)
    required = {"rid": round_dir.name, "card": card, "commit": base["commit"], "code_version": base["code_version"]}
    if any(admission.get(key) != value for key, value in required.items()):
        raise ValueError("admission does not bind rid/card/full commit/tag")
    trace_name, trace_hash = live.get("trace"), live.get("trace_sha256")
    if not isinstance(trace_name, str) or not isinstance(trace_hash, str):
        raise ValueError("live_checks trace mapping is absent")
    trace = Path(trace_name)
    if not trace.is_file() or sha256(trace) != trace_hash:
        raise ValueError("live_checks trace SHA does not match its source path")
    if admission.get("trace") != trace_name or admission.get("trace_sha256") != trace_hash:
        raise ValueError("admission trace mapping differs from live_checks")
    return admission, trace, trace_messages(trace)


def arm_evidence(round_dir: Path, arms: tuple[str, ...]) -> tuple[str, dict[str, dict[str, str]]]:
    first_env: list[str] = []
    evidence: dict[str, dict[str, str]] = {}
    for arm in arms:
        arm_dir = round_dir / arm
        for name in ("ENV.txt", "SERVE_CMD.txt", "serve.log", "serve_args.txt"):
            path = arm_dir / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"missing arm evidence: {arm}/{name}")
        env_lines = (arm_dir / "ENV.txt").read_text(encoding="utf-8").splitlines()
        if not env_lines or not env_lines[0].strip():
            raise ValueError(f"missing first ENV time/source line: {arm}")
        try:
            datetime.fromisoformat(env_lines[0].split(maxsplit=1)[0])
        except ValueError as exc:
            raise ValueError(f"first ENV line must begin with an ISO timestamp: {arm}") from exc
        first_env.append(env_lines[0])
        evidence[arm] = {path.relative_to(arm_dir).as_posix(): sha256(path)
                         for path in arm_dir.rglob("*") if path.is_file()}
    # The runner writes the actual source/git record as ENV's first line.  Preserve it verbatim.
    return first_env[0], evidence


def trace_messages(path: Path) -> dict[str, int]:
    document = load(path)
    rows = document.get("rounds")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValueError(f"trace must contain exactly 12 rounds: {path}")
    mapped: dict[str, int] = {}
    source_rounds: set[int] = set()
    for index, row in enumerate(rows):
        record = row.get("record") if isinstance(row, dict) else None
        message_sha = record.get("messages_sha") if isinstance(record, dict) else None
        source_round = record.get("round") if isinstance(record, dict) else None
        # The remote-authoritative agent_trace stores the 16-hex prefix of the
        # canonical messages SHA-256.  Replay row.round addresses trace-list
        # position, even when record.round is reverse ordered.
        if (not isinstance(message_sha, str) or not re.fullmatch(r"[0-9a-f]{16}", message_sha)
                or type(source_round) is not int or source_round in source_rounds or message_sha in mapped):
            raise ValueError(f"invalid original trace messages_sha: {path}")
        mapped[message_sha] = index
        source_rounds.add(source_round)
    if source_rounds != set(range(12)):
        raise ValueError(f"original trace record.round values are not 0..11: {path}")
    return mapped


def valid_replay(path: Path, expected: dict[str, int]) -> dict[str, dict[str, Any]]:
    document = load(path)
    params = ((document.get("meta") or {}).get("params") or {})
    if params.get("dry_run") is not False:
        raise ValueError(f"replay metadata is not live: {path}")
    rows = document.get("rounds")
    if not isinstance(rows, list):
        raise ValueError(f"rounds missing: {path}")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        message_sha = row.get("messages_sha")
        if (not isinstance(message_sha, str) or message_sha != row.get("trace_messages_sha") or message_sha not in expected
                or type(row.get("round")) is not int or row["round"] != expected[message_sha]
                or not isinstance(row.get("text"), str) or not row["text"]
                or row.get("dry_run") is not False or row.get("error") is not None):
            raise ValueError(f"invalid replay row: {path}")
        if message_sha in mapped:
            raise ValueError(f"duplicate messages_sha: {path}")
        mapped[message_sha] = row
    if set(mapped) != set(expected):
        raise ValueError(f"replay does not bind one-to-one to original trace: {path}")
    return mapped


def first_difference(left: str, right: str) -> tuple[bool, int | None]:
    if left == right:
        return True, None
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return False, index
    return False, min(len(left), len(right))


def token_position(text: str, character: int, tokenizer: Any | None) -> int:
    if tokenizer is None:
        return character
    return len(tokenizer.encode(text[:character], add_special_tokens=False))


def maybe_tokenizer(model_path: str | None) -> Any | None:
    if model_path is None:
        return None
    from transformers import AutoTokenizer  # lazy: stdlib-only reader unless exact token positions are requested
    return AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)


def summarize_t04(round_dir: Path, diagnostics: dict[str, Any], results: dict[str, Any], expected_trace: dict[str, int]) -> None:
    diagnostics["replays"] = {arm: {"path": f"{arm}/replay.json", "sha256": sha256(round_dir / arm / "replay.json"),
                                    "messages_sha": sorted(valid_replay(round_dir / arm / "replay.json", expected_trace))}
                              for arm in ARMS["T04"]}
    required = ("eq_B_vs_R4096.txt", "eq_R4096_vs_R8192.txt")
    for name in required:
        path = round_dir / name
        if not path.is_file():
            raise ValueError(f"missing T04 state_eq: {name}")
        diagnostics[name] = state_eq(path)
    if diagnostics["eq_B_vs_R4096.txt"]["rc"] != 0:
        raise ValueError("T04 same-config B/R4096 determinism gate failed")
    optional = round_dir / "eq_R4096_vs_RLM.txt"
    nodump = round_dir / "RLM_NODUMP.txt"
    if optional.is_file():
        diagnostics[optional.name] = state_eq(optional)
    elif nodump.is_file():
        diagnostics[nodump.name] = {"sha256": sha256(nodump), "text": nodump.read_text(encoding="utf-8", errors="replace")}
    else:
        raise ValueError("T04 requires RLM state_eq or RLM_NODUMP")
    for name, payload in diagnostics.items():
        if name.startswith("eq_") and payload["rc"] not in (0, 1):
            raise ValueError(f"unexpected state_eq rc: {name}")
    pair_counts = {
        name.removesuffix(".txt"): len(payload["length_lines"])
        for name, payload in diagnostics.items()
        if name.startswith("eq_")
    }
    total_comparable = sum(pair_counts.values())
    # Keep the historical aggregate for diagnostics, but T04 card's >=6
    # admission gate specifically measures R4096 -> R8192, never other pairs.
    results["comparable_length_records"] = total_comparable
    results["comparable_length_records_by_pair"] = pair_counts
    gate_pair = "eq_R4096_vs_R8192"
    gate_observed = pair_counts[gate_pair]
    diagnostics["comparability_gate"] = {
        "pair": gate_pair,
        "minimum": 6,
        "observed": gate_observed,
        "met": gate_observed >= 6,
        "total_observed": total_comparable,
        "interpretation": "reported only; reviewer decides the outcome",
    }
    historical = round_dir.parent / "E1-R003-stateeq"
    refs = {}
    for name in ("dump_A", "dump_B"):
        index = historical / name / "index.jsonl"
        if index.is_file():
            refs[name] = {"index": str(index), "sha256": sha256(index)}
    diagnostics["historical_state_refs"] = refs


def t10_compare_artifacts(round_dir: Path) -> dict[str, dict[str, Any]]:
    compare_artifacts: dict[str, dict[str, Any]] = {}
    for left, right in (("B1", "B2"), ("B1", "B3"), ("B2", "B3")):
        stem = f"cmp_cold_{left}_{right}"
        result_path, log_path = round_dir / f"{stem}.json", round_dir / f"{stem}.log"
        if not result_path.is_file() or not log_path.is_file():
            raise ValueError(f"T10 compare artifact missing: {stem}")
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^rc=([0-9]+)$", log_text, re.MULTILINE)
        if not match or int(match.group(1)) not in (0, 1):
            raise ValueError(f"T10 compare log has invalid rc: {stem}")
        # Keep the independently produced compare result as evidence.  It is not
        # promoted into, or assumed equivalent to, replay-level localization.
        compare_artifacts[stem] = {"result_sha256": sha256(result_path), "result": load(result_path),
                                   "log_sha256": sha256(log_path), "rc": int(match.group(1))}
    return compare_artifacts


def summarize_t10(round_dir: Path, diagnostics: dict[str, Any], results: dict[str, Any], tokenizer: Any,
                  reverse_trace: dict[str, int], forward_trace: dict[str, int]) -> None:
    arms = ARMS["T10"]
    compare_artifacts = t10_compare_artifacts(round_dir)
    diagnostics["agent_trace_compare"] = compare_artifacts
    cold = {arm: valid_replay(round_dir / arm / "reversecold.json", reverse_trace) for arm in arms}
    warm = {arm: valid_replay(round_dir / arm / "forwardwarm.json", forward_trace) for arm in arms}
    expected = set(cold[arms[0]])
    if any(set(cold[arm]) != expected or set(warm[arm]) != expected for arm in arms):
        raise ValueError("T10 messages_sha input join mismatch")
    comparisons: list[dict[str, Any]] = []
    for left, right, kind in (("B1", "B2", "cross_cold"), ("B1", "B3", "cross_cold"), ("B2", "B3", "cross_cold"),
                              ("B1", "B1", "same_process_cold_warm"), ("B2", "B2", "same_process_cold_warm"), ("B3", "B3", "same_process_cold_warm")):
        left_rows, right_rows = cold[left], (warm[right] if kind.startswith("same") else cold[right])
        for message_sha in sorted(expected):
            a, b = left_rows[message_sha], right_rows[message_sha]
            text_a, text_b = str(a.get("text", "")), str(b.get("text", ""))
            same, char = first_difference(text_a, text_b)
            token = token_position(text_a, char, tokenizer) if char is not None else None
            comparisons.append({"kind": kind, "pair": f"{left}/{right}", "messages_sha": message_sha,
                                "round": a.get("round"), "same": same, "first_char": char,
                                "first_token_proxy": token,
                                "left_cached_tokens": a.get("cached_tokens"), "right_cached_tokens": b.get("cached_tokens"),
                                "left_text_sha256": hashlib.sha256(text_a.encode()).hexdigest(),
                                "right_text_sha256": hashlib.sha256(text_b.encode()).hexdigest()})
    results["comparison_count"] = len(comparisons)
    results["per_round_first_difference"] = [{"round": item["round"], "first_char": item["first_char"] if item["first_char"] is not None else -1,
                                               "first_token_proxy": item["first_token_proxy"] if item["first_token_proxy"] is not None else -1}
                                              for item in comparisons]
    if not finite_numbers(results):
        raise ValueError("T10 numeric results are incomplete or non-finite")
    diagnostics["input_comparisons"] = comparisons
    diagnostics["first_token_proxy"] = "AutoTokenizer token index over complete UTF text; null when text is equal"


def t11_target_evidence(round_dir: Path, arm: Path, rows: dict[str, dict[str, Any]], expected_trace: dict[str, int],
                        actual_worktree: str) -> dict[str, Any]:
    path = round_dir / "t11_target.json"
    if not path.is_file():
        raise ValueError("T11 source-bound target evidence is absent")
    target = load(path)
    target_messages = [message_sha for message_sha, index in expected_trace.items()
                       if index == T11_TARGET_TRACE_INDEX]
    if len(target_messages) != 1:
        raise ValueError("T11 trace target is not unique")
    message_sha = target_messages[0]
    required = {
        "trace_index": T11_TARGET_TRACE_INDEX,
        "messages_sha": message_sha,
        "cached_tokens": T11_CACHED_TOKENS,
        "recomputed_tokens": T11_RECOMPUTED_TOKENS,
        "historical_uid": T11_HISTORICAL_UID,
    }
    if any(target.get(key) != value for key, value in required.items()):
        raise ValueError("T11 target evidence does not bind the trace message and historical UID")
    actual_uid, host_slot = target.get("actual_uid"), target.get("host_slot")
    if type(actual_uid) is not int or actual_uid < 0 or type(host_slot) is not int or host_slot < 0:
        raise ValueError("T11 target actual UID/host slot is invalid")
    historical_replay = target.get("historical_replay")
    target_worktree = target.get("actual_worktree")
    if not isinstance(historical_replay, str) or target_worktree != actual_worktree:
        raise ValueError("T11 target source identities are absent")
    historical_path = Path(historical_replay)
    if (not historical_path.is_file() or target.get("historical_replay_sha256") != sha256(historical_path)
            or historical_replay == actual_worktree):
        raise ValueError("T11 historical and actual source evidence is invalid")
    replay = rows.get(message_sha)
    if replay is None or replay.get("cached_tokens") != T11_CACHED_TOKENS or replay.get("recomputed_tokens") != T11_RECOMPUTED_TOKENS:
        raise ValueError("T11 target replay does not reproduce cached=13376/recomputed=56")
    serve_log = arm / "serve.log"
    if target.get("serve_log_sha256") != sha256(serve_log):
        raise ValueError("T11 target evidence is not bound to the actual serve log")
    source_lines = serve_log.read_text(encoding="utf-8", errors="replace").splitlines()
    matches: list[str] = []
    for index, line in enumerate(source_lines):
        resume = T11_RESUME.search(line)
        if not resume or (int(resume["uid"]), int(resume["slot"])) != (actual_uid, host_slot):
            continue
        for candidate in source_lines[index + 1:]:
            if T11_RESUME.search(candidate):
                break
            prefill = T11_PREFILL.search(candidate)
            if prefill and (int(prefill["cached"]), int(prefill["new"])) == (T11_CACHED_TOKENS, T11_RECOMPUTED_TOKENS):
                matches.append(candidate)
                break
    if len(matches) != 1 or target.get("source_prefill_line") != matches[0]:
        raise ValueError("T11 target source prefill evidence is incomplete or mismatched")
    return target


def summarize_t11(round_dir: Path, diagnostics: dict[str, Any], results: dict[str, Any], expected_trace: dict[str, int],
                  actual_worktree: str) -> None:
    arm = round_dir / "S_A_trace"
    rows = valid_replay(arm / "replay.json", expected_trace)
    target = t11_target_evidence(round_dir, arm, rows, expected_trace, actual_worktree)
    target_row = rows[target["messages_sha"]]
    restore = load(round_dir / "restore_count.json").get("count")
    if not finite_numbers({"restore_count": restore, "target_cached": target_row.get("cached_tokens"),
                           "target_recomputed": target_row.get("recomputed_tokens")}):
        raise ValueError("T11 required numeric values absent")
    results.update({"restore_count": restore, "target_cached": target_row["cached_tokens"],
                    "target_recomputed": target_row["recomputed_tokens"]})
    diagnostics["t11_target"] = {
        "path": "t11_target.json",
        "sha256": sha256(round_dir / "t11_target.json"),
        "replay_path": "S_A_trace/replay.json",
        "replay_sha256": sha256(arm / "replay.json"),
        "historical_uid": T11_HISTORICAL_UID,
        "actual_uid": target["actual_uid"],
        "trace_index": T11_TARGET_TRACE_INDEX,
        "messages_sha": target["messages_sha"],
        "cached_tokens": T11_CACHED_TOKENS,
        "recomputed_tokens": T11_RECOMPUTED_TOKENS,
        "historical_replay": target["historical_replay"],
        "historical_replay_sha256": target["historical_replay_sha256"],
        "actual_worktree": target["actual_worktree"],
    }
    eq = round_dir / "eq_prevA_vs_new.txt"
    if eq.is_file():
        payload = state_eq(eq)
        if payload["rc"] not in (0, 1):
            raise ValueError("unexpected T11 state_eq rc")
        diagnostics[eq.name] = payload
    else:
        diagnostics.setdefault("gaps", []).append("historical A/new state_eq output absent")
    trace = round_dir / "t11_target_d3_trace.log"
    index = arm / "dump/index.jsonl"
    if trace.is_file():
        trace_lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
        diagnostics["d3_trace"] = {"sha256": sha256(trace), "lines": trace_lines, "positive_evidence": bool(trace_lines)}
        if not trace_lines:
            diagnostics.setdefault("gaps", []).append("D3 trace evidence is absent or empty")
    else:
        diagnostics.setdefault("gaps", []).append("D3 trace evidence is absent or empty")
    kinds: list[str] = []
    if index.is_file():
        for raw in index.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(raw)
                if isinstance(entry.get("kind"), str):
                    kinds.append(entry["kind"])
            except json.JSONDecodeError:
                diagnostics.setdefault("gaps", []).append("invalid dump index line")
                break
        diagnostics["dump_index"] = {"sha256": sha256(index), "kinds": sorted(set(kinds)), "entries": len(kinds)}
    else:
        diagnostics.setdefault("gaps", []).append("T11 dump index absent")
    diagnostics.setdefault("gaps", []).append(
        "finish-writeback coverage remains unresolved; absent donate/D3 output is not classified as H-hook or H-bug"
    )


def summarize(round_dir: Path, card: str, *, git_commit: str | None = None, git_tag: str | None = None, tokenizer_path: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if round_dir.name != RID[card]:
        raise ValueError("round id does not match card assignment")
    status, status_path = terminal_status(round_dir, card)
    live = load(round_dir / "live_checks.json")
    if live.get("rid") != round_dir.name or live.get("card") != card:
        raise ValueError("live_checks rid/card binding is invalid")
    if status.get("arms") != list(ARMS[card]):
        raise ValueError("terminal status does not contain the exact card arms")
    base = actual_identity(round_dir, live, git_commit, git_tag)
    admission, trace, original_trace = admitted_trace(round_dir, card, live, base)
    created_at, evidence = arm_evidence(round_dir, ARMS[card])
    results: dict[str, Any] = {"arm_count": len(ARMS[card])}
    diagnostics: dict[str, Any] = {"status": {"path": status_path.name, "batch": status["batch"], "state": status["state"]},
                                   "admission": {"sha256": sha256(round_dir / "admission.json"), "trace": str(trace),
                                                 "trace_sha256": sha256(trace), "messages_sha": sorted(original_trace)},
                                   "evidence_sha256": evidence}
    if card == "T04":
        summarize_t04(round_dir, diagnostics, results, original_trace)
    elif card == "T10":
        forward = trace.with_name("trace.json")
        if not forward.is_file():
            raise ValueError("T10 original forward trace is absent")
        forward_trace = trace_messages(forward)
        diagnostics["forward_trace"] = {"path": str(forward), "sha256": sha256(forward), "messages_sha": sorted(forward_trace)}
        summarize_t10(round_dir, diagnostics, results, maybe_tokenizer(tokenizer_path or SERVER_TOKENIZER), original_trace, forward_trace)
    else:
        worktree = live.get("worktree")
        if not isinstance(worktree, str):
            raise ValueError("live_checks worktree is required for T11 source binding")
        summarize_t11(round_dir, diagnostics, results, original_trace, worktree)
    if not finite_numbers(results):
        raise ValueError("results must contain only finite numeric values")
    summary = {"schema": "state_measurement_summary/v1", "round_id": round_dir.name, "card": card,
               "created_at": created_at, "base": base, "results": results, "diagnostics": diagnostics,
               "verdict": "pending_review", "proposed_verdict": None, "verdict_history": []}
    metadata = {"schema": "ft_round/v2", "round_id": round_dir.name, "epoch": 2, "card": card,
                "created_at": created_at, "base": base,
                "serve": {"arms": {arm: {"serve_cmd": f"{arm}/SERVE_CMD.txt", "serve_log": f"{arm}/serve.log",
                                            "serve_args": f"{arm}/serve_args.txt", "env": f"{arm}/ENV.txt"}
                                   for arm in ARMS[card]}}, "results": results, "first_shots": [],
                "verdict": "pending_review", "proposed_verdict": None, "verdict_history": [], "retractions": []}
    return summary, metadata


def self_test() -> None:
    assert finite_numbers({"x": [1, 2.0]}) and not finite_numbers({"x": True})
    assert first_difference("abc", "abd") == (False, 2)
    assert first_difference("abc", "abc") == (True, None)
    assert first_difference("ab", "abc") == (False, 2)
    assert token_position("abc", 2, None) == 2
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        trace = root / "trace_rev.json"
        digests = [f"{number:016x}" for number in range(12)]
        write_new(trace, {"rounds": [{"record": {"round": 11 - number, "messages_sha": digest}}
                                           for number, digest in enumerate(digests)]})
        round_dir = root / "E2-R002"
        round_dir.mkdir()
        write_new(round_dir / "status_batch9.json", {"rid": "E2-R002", "card": "T04", "batch": 9, "state": "complete", "arms": list(ARMS["T04"])})
        write_new(round_dir / "live_checks.json", {"rid": "E2-R002", "card": "T04", "commit": "a" * 40, "code_version": EXPECTED_TAG,
                                                     "worktree": "/not-used", "trace": str(trace), "trace_sha256": sha256(trace)})
        write_new(round_dir / "admission.json", {"rid": "E2-R002", "card": "T04", "commit": "a" * 40,
                                                   "code_version": EXPECTED_TAG, "trace": str(trace), "trace_sha256": sha256(trace)})
        for arm in ARMS["T04"]:
            arm_dir = round_dir / arm
            arm_dir.mkdir()
            (arm_dir / "ENV.txt").write_text("2026-10-04T00:00:00+08:00 source\n", encoding="utf-8")
            for name in ("SERVE_CMD.txt", "serve.log", "serve_args.txt"):
                (arm_dir / name).write_text("evidence\n", encoding="utf-8")
            write_new(arm_dir / "replay.json", {"meta": {"params": {"dry_run": False}}, "rounds": [
                {"round": number, "messages_sha": digest, "trace_messages_sha": digest, "text": "ok", "dry_run": False, "error": None}
                for number, digest in enumerate(digests)]})
        def eq_text(rc: int, count: int) -> str:
            return "rc={}\n{}".format(rc, "".join("len={} max_abs=0\n".format(number) for number in range(count)))

        (round_dir / "eq_B_vs_R4096.txt").write_text(eq_text(0, 12), encoding="utf-8")
        (round_dir / "eq_R4096_vs_R8192.txt").write_text(eq_text(1, 12), encoding="utf-8")
        (round_dir / "eq_R4096_vs_RLM.txt").write_text(eq_text(1, 12), encoding="utf-8")
        summary, metadata = summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        assert summary["created_at"].startswith("2026-10-04")
        assert summary["verdict"] == metadata["verdict"] == "pending_review"
        assert summary["proposed_verdict"] is None and metadata["verdict_history"] == []
        assert summary["diagnostics"]["eq_B_vs_R4096.txt"]["rc"] == 0
        assert summary["results"]["comparable_length_records"] == 36
        assert summary["results"]["comparable_length_records_by_pair"] == {
            "eq_B_vs_R4096": 12, "eq_R4096_vs_R8192": 12, "eq_R4096_vs_RLM": 12}
        assert summary["diagnostics"]["comparability_gate"] == {
            "pair": "eq_R4096_vs_R8192", "minimum": 6, "observed": 12, "met": True,
            "total_observed": 36, "interpretation": "reported only; reviewer decides the outcome"}
        # B and LM must not compensate for an insufficient R4096->R8192 sample.
        (round_dir / "eq_R4096_vs_R8192.txt").write_text(eq_text(1, 5), encoding="utf-8")
        short_summary, _ = summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        assert short_summary["results"]["comparable_length_records"] == 29
        assert short_summary["diagnostics"]["comparability_gate"]["observed"] == 5
        assert short_summary["diagnostics"]["comparability_gate"]["met"] is False
        (round_dir / "eq_R4096_vs_R8192.txt").write_text(eq_text(1, 6), encoding="utf-8")
        boundary_summary, _ = summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        assert boundary_summary["diagnostics"]["comparability_gate"]["observed"] == 6
        assert boundary_summary["diagnostics"]["comparability_gate"]["met"] is True
        (round_dir / "eq_B_vs_R4096.txt").write_text("rc=1\nlen=1 max_abs=1\n", encoding="utf-8")
        try:
            summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        except ValueError as exc:
            assert "same-config" in str(exc)
        else:
            raise AssertionError("same-config state_eq failure must reject")
        (round_dir / "eq_B_vs_R4096.txt").write_text("rc=0\nlen=1 max_abs=0\n", encoding="utf-8")
        (round_dir / "admission.json").unlink()
        try:
            summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        except ValueError as exc:
            assert "admission" in str(exc)
        else:
            raise AssertionError("missing admission must reject")
        write_new(round_dir / "admission.json", {"rid": "E2-R002", "card": "T04", "commit": "a" * 40,
                                                   "code_version": EXPECTED_TAG, "trace": str(trace), "trace_sha256": "0" * 64})
        try:
            summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        except ValueError as exc:
            assert "trace" in str(exc)
        else:
            raise AssertionError("wrong admission trace must reject")
        write_new(round_dir / "admission.fixed.json", {"rid": "E2-R002", "card": "T04", "commit": "a" * 40,
                                                         "code_version": EXPECTED_TAG, "trace": str(trace), "trace_sha256": sha256(trace)})
        (round_dir / "admission.json").unlink()
        (round_dir / "admission.fixed.json").rename(round_dir / "admission.json")
        for arm in ARMS["T04"]:
            write_new(round_dir / arm / "fake_replay.json", {"meta": {"params": {"dry_run": False}}, "rounds": [
                {"round": number, "messages_sha": f"{number + 100:016x}", "trace_messages_sha": f"{number + 100:016x}",
                 "text": "self-consistent fake", "dry_run": False, "error": None}
                for number in range(12)]})
            (round_dir / arm / "replay.json").unlink()
            (round_dir / arm / "fake_replay.json").rename(round_dir / arm / "replay.json")
        try:
            summarize(round_dir, "T04", git_commit="a" * 40, git_tag=EXPECTED_TAG)
        except ValueError as exc:
            assert "invalid replay" in str(exc) or "one-to-one" in str(exc)
        else:
            raise AssertionError("self-consistent replay fake must reject")
        t11 = root / "E2-R011" / "S_A_trace"
        (t11 / "dump").mkdir(parents=True)
        write_new(t11 / "replay.json", {"meta": {"params": {"dry_run": False}}, "rounds": [
            {"messages_sha": digest, "trace_messages_sha": digest, "text": "ok", "dry_run": False, "error": None,
             "round": number, "cached_tokens": 13376 if number == 7 else 0, "recomputed_tokens": 56 if number == 7 else 0}
            for number, digest in enumerate(digests)]})
        write_new(t11.parent / "restore_count.json", {"count": 1})
        serve_log = t11 / "serve.log"
        source_line = "Prefill batch, #new-seq: 1, #new-token: 56, #cached-token: 13376, token usage: 0.27"
        serve_log.write_text("GDN bank: resuming req 7 from host slot 22\n" + source_line + "\n", encoding="utf-8")
        write_new(t11.parent / "t11_target.json", {"trace_index": 7, "messages_sha": digests[7],
                  "cached_tokens": 13376, "recomputed_tokens": 56, "historical_uid": 8,
                  "actual_uid": 7, "host_slot": 22, "serve_log_sha256": sha256(serve_log),
                  "source_prefill_line": source_line, "historical_replay": str(trace),
                  "historical_replay_sha256": sha256(trace), "actual_worktree": "/new/e2base"})
        (t11.parent / "t11_target_d3_trace.log").write_text("", encoding="utf-8")
        (t11 / "dump/index.jsonl").write_text('{"kind":"state"}\n', encoding="utf-8")
        t11_diag, t11_results = {}, {}
        summarize_t11(t11.parent, t11_diag, t11_results, trace_messages(trace), "/new/e2base")
        assert t11_diag["t11_target"]["historical_uid"] == 8 and t11_diag["t11_target"]["actual_uid"] == 7
        assert t11_diag["t11_target"]["historical_replay"] == str(trace)
        assert "D3 trace evidence is absent or empty" in t11_diag["gaps"] and t11_diag["d3_trace"]["positive_evidence"] is False
        assert any("finish-writeback coverage remains unresolved" in gap for gap in t11_diag["gaps"])
        target_path = t11.parent / "t11_target.json"
        target_document = load(target_path)
        target_document["actual_worktree"] = "/intentionally-not-live-worktree"
        target_path.write_text(json.dumps(target_document), encoding="utf-8")
        try:
            t11_target_evidence(t11.parent, t11, valid_replay(t11 / "replay.json", trace_messages(trace)),
                                trace_messages(trace), "/new/e2base")
        except ValueError:
            pass
        else:
            raise AssertionError("T11 target accepted an arbitrary actual_worktree")
        t10 = root / "E2-R006"; t10.mkdir()
        for left, right in (("B1", "B2"), ("B1", "B3"), ("B2", "B3")):
            stem = f"cmp_cold_{left}_{right}"
            write_new(t10 / f"{stem}.json", {"independent": True})
            (t10 / f"{stem}.log").write_text("rc=1\ncomparison output\n", encoding="utf-8")
        assert set(t10_compare_artifacts(t10)) == {"cmp_cold_B1_B2", "cmp_cold_B1_B3", "cmp_cold_B2_B3"}
        (t10 / "cmp_cold_B1_B2.log").write_text("rc=2\n", encoding="utf-8")
        try:
            t10_compare_artifacts(t10)
        except ValueError as exc:
            assert "invalid rc" in str(exc)
        else:
            raise AssertionError("T10 compare rc outside 0/1 must reject")
    print("state_measurement_summarize SELFTEST PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("card", nargs="?", choices=ARMS)
    parser.add_argument("round", nargs="?", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--metadata-out", type=Path)
    parser.add_argument("--git-commit")
    parser.add_argument("--git-tag")
    parser.add_argument("--tokenizer-path", help="load the server tokenizer lazily for exact T10 token positions")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.card or not args.round or not args.out or not args.metadata_out:
        parser.error("card, round, --out and --metadata-out are required")
    if args.out.exists() or args.metadata_out.exists():
        parser.error("outputs must be new")
    summary, metadata = summarize(args.round, args.card, git_commit=args.git_commit, git_tag=args.git_tag,
                                  tokenizer_path=args.tokenizer_path)
    write_new(args.out, summary)
    write_new(args.metadata_out, metadata)


if __name__ == "__main__":
    main()
