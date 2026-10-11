#!/usr/bin/env python3
"""Fail-closed GPU runner for the executable portions of T04, T10, and T11.

It is deliberately inert unless invoked with ``--run`` on the Linux test host.
The default ``--self-test`` covers only pure input/argument/trace validation.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path("/data2/FreeToken")
RUNS = Path("/data2/_shared/runs/ft_rounds")
FT = "/data2/FreeToken/venv/bin/ft"
PY = "/data2/FreeToken/venv/bin/python"
SCRIPTS = ROOT / "scripts"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
PORT = 8095
EXPECTED_E2_COMMIT = "23f2e2c"
EXPECTED_E2_TAG = "E2-base"
EXPECTED_ROUNDS = 12
ASSIGNED_RIDS = {"T04": "E2-R002", "T10": "E2-R006", "T11": "E2-R011"}
T11_TARGET_TRACE_INDEX = 7
T11_HISTORICAL_UID = 8
T11_CACHED_TOKENS = 13376
T11_RECOMPUTED_TOKENS = 56
T11_RESUME = re.compile(r"GDN bank: resuming req (?P<uid>\d+) from host slot (?P<slot>\d+)")
T11_PREFILL = re.compile(r"Prefill batch, #new-seq: \d+, #new-token: (?P<new>\d+), #cached-token: (?P<cached>\d+)")


@dataclass(frozen=True)
class Card:
    worktree: Path
    commit: str
    trace: Path
    flags: tuple[str, ...]
    arms: tuple[tuple[str, tuple[str, ...], dict[str, str]], ...]


CARDS = {
    "T04": Card(
        ROOT / "wt/e1r003sd", "97bc62c", RUNS / "E1-R003-v2/trace_rev.json",
        ("--enable-special-token-ckpt", "--mamba-host-slots", "0"),
        (
            ("R4096", ("--max-prefill-length", "4096"), {"FT_DEV_STATE_DUMP": "dump"}),
            ("R8192", ("--max-prefill-length", "8192"), {"FT_DEV_STATE_DUMP": "dump"}),
            ("RLM", ("--max-prefill-length", "4096", "--prefill-layer-major"), {"FT_DEV_STATE_DUMP": "dump"}),
        ),
    ),
    "T10": Card(
        ROOT / "wt/e1r003", "c721c74", RUNS / "E1-R003-v2/trace_rev.json",
        ("--enable-special-token-ckpt", "--max-prefill-length", "4096", "--mamba-host-slots", "0"),
        (("B1", (), {}), ("B2", (), {}), ("B3", (), {})),
    ),
    "T11": Card(
        ROOT / "wt/e1r003sd", "97bc62c", RUNS / "E1-R003-v2/trace_rev.json",
        ("--enable-special-token-ckpt", "--enable-cache-report", "--max-prefill-length", "4096", "--mamba-host-slots", "32"),
        (("S_A_trace", (), {"FT_DEV_STATE_DUMP": "dump", "FT_D3_TRACE": "1"}),),
    ),
}


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        timeout: int | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, env=env, timeout=timeout, check=True,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        if isinstance(value, (dict, list)):
            json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.write("\n")
        else:
            out.write(str(value))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed_args(log: Path) -> dict[str, str]:
    text = log.read_text(encoding="utf-8", errors="replace")
    marker = "ServerArgs("
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"Parsed arguments absent: {log}")
    depth, quote, escaped = 0, None, False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                raw = text[start + len(marker):index]
                break
    else:
        raise ValueError(f"unterminated ServerArgs: {log}")
    result: dict[str, str] = {}
    for match in re.finditer(r"(?:^|, )([A-Za-z_]\w*)=", raw):
        key, value_start = match.group(1), match.end()
        next_match = re.search(r", [A-Za-z_]\w*=", raw[value_start:])
        value_end = value_start + next_match.start() if next_match else len(raw)
        result[key] = raw[value_start:value_end]
    if not result:
        raise ValueError(f"empty parsed arguments: {log}")
    return result


def pid_value(value: str) -> bool:
    try:
        return bool(re.fullmatch(r"\.pid=\d+", ast.literal_eval(value)))
    except (ValueError, SyntaxError):
        return False


def strict_args(before: dict[str, str], after: dict[str, str], allowed: dict[str, str]) -> dict[str, tuple[str | None, str | None]]:
    differences = {key: (before.get(key), after.get(key)) for key in sorted(set(before) | set(after))
                   if before.get(key) != after.get(key)}
    for key, (old, new) in differences.items():
        if key == "_unique_suffix" and old is not None and new is not None and pid_value(old) and pid_value(new):
            continue
        if allowed.get(key) == new and old is not None:
            continue
        raise ValueError(f"unexpected parsed-argument difference {key}: {old!r} -> {new!r}")
    return differences


def require_t11_cache_report(parsed: dict[str, str]) -> None:
    if parsed.get("enable_cache_report") != "True":
        raise ValueError("T11 requires --enable-cache-report")


def trace_map(trace: Path) -> dict[str, int]:
    document = json.loads(trace.read_text(encoding="utf-8"))
    rounds = document.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != EXPECTED_ROUNDS:
        raise ValueError(f"trace must contain exactly {EXPECTED_ROUNDS} rounds")
    result: dict[str, int] = {}
    trace_rounds: set[int] = set()
    for index, item in enumerate(rounds):
        record = item.get("record") if isinstance(item, dict) else None
        digest = record.get("messages_sha") if isinstance(record, dict) else None
        source_round = record.get("round") if isinstance(record, dict) else None
        # agent_trace.messages_digest() deliberately stores the first 16 hex
        # chars of the canonical messages SHA-256, not a full 64-char digest.
        # Replay indexes the trace list, which may be reverse-ordered.
        if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{16}", digest)
                or type(source_round) is not int or source_round in trace_rounds):
            raise ValueError("trace round lacks a valid record.messages_sha")
        if digest in result:
            raise ValueError("duplicate trace messages_sha")
        result[digest] = index
        trace_rounds.add(source_round)
    if trace_rounds != set(range(EXPECTED_ROUNDS)):
        raise ValueError("trace record.round values are not exactly 0..11")
    return result


def validate_replay(trace: Path, replay: Path) -> dict[str, Any]:
    expected = trace_map(trace)
    document = json.loads(replay.read_text(encoding="utf-8"))
    params = ((document.get("meta") or {}).get("params") or {})
    if params.get("dry_run") is not False:
        raise ValueError("replay metadata does not prove a live (non-dry-run) request")
    rounds = document.get("rounds")
    if not isinstance(rounds, list) or len(rounds) != EXPECTED_ROUNDS:
        raise ValueError(f"replay must contain exactly {EXPECTED_ROUNDS} rounds")
    actual: dict[str, dict[str, Any]] = {}
    for item in rounds:
        digest, trace_digest = item.get("messages_sha"), item.get("trace_messages_sha")
        if (not isinstance(digest, str) or digest != trace_digest or type(item.get("round")) is not int):
            raise ValueError("replay messages_sha does not equal trace_messages_sha")
        if digest not in expected or digest in actual:
            raise ValueError("replay messages hash is not a one-to-one trace join")
        if item["round"] != expected[digest]:
            raise ValueError("replay round index does not match the original trace entry")
        if not isinstance(item.get("text"), str) or not item["text"]:
            raise ValueError("replay round has empty text")
        if item.get("error"):
            raise ValueError(f"replay API error: {item['error']}")
        if item.get("dry_run") is not False:
            raise ValueError("replay row is dry-run evidence")
        actual[digest] = item
    if set(actual) != set(expected):
        raise ValueError("replay/trace messages_sha sets differ")
    return {"rounds": len(actual), "messages_sha": sorted(actual), "trace_sha256": sha256(trace),
            "replay_sha256": sha256(replay)}


def t11_target_proof(trace: Path, replay: Path, serve_log: Path) -> dict[str, Any]:
    """Bind T11's historical uid=8 case to this replay's trace message and UID."""
    trace_by_message = trace_map(trace)
    targets = [message_sha for message_sha, index in trace_by_message.items()
               if index == T11_TARGET_TRACE_INDEX]
    if len(targets) != 1:
        raise ValueError("T11 trace has no unique target message at index 7")
    target_message = targets[0]
    replay_document = json.loads(replay.read_text(encoding="utf-8"))
    replay_rows = replay_document.get("rounds")
    if not isinstance(replay_rows, list):
        raise ValueError("T11 replay rounds are absent")
    target_rows = [row for row in replay_rows if isinstance(row, dict)
                   and row.get("messages_sha") == target_message]
    if len(target_rows) != 1:
        raise ValueError("T11 target message is not uniquely present in replay")
    target = target_rows[0]
    if (target.get("trace_messages_sha") != target_message
            or target.get("round") != T11_TARGET_TRACE_INDEX
            or target.get("cached_tokens") != T11_CACHED_TOKENS
            or target.get("recomputed_tokens") != T11_RECOMPUTED_TOKENS):
        raise ValueError("T11 target replay does not report cached=13376/recomputed=56")

    lines = serve_log.read_text(encoding="utf-8", errors="replace").splitlines()
    observed: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        resume = T11_RESUME.search(line)
        if not resume:
            continue
        for candidate in lines[index + 1:]:
            if T11_RESUME.search(candidate):
                break
            prefill = T11_PREFILL.search(candidate)
            if prefill and (int(prefill["cached"]), int(prefill["new"])) == (T11_CACHED_TOKENS, T11_RECOMPUTED_TOKENS):
                observed.append((int(resume["uid"]), int(resume["slot"]), candidate))
                break
    if len(observed) != 1:
        raise ValueError("T11 source log lacks one unique host-restored cached=13376/new=56 target")
    actual_uid, host_slot, prefill_line = observed[0]
    return {
        "trace_index": T11_TARGET_TRACE_INDEX,
        "messages_sha": target_message,
        "cached_tokens": T11_CACHED_TOKENS,
        "recomputed_tokens": T11_RECOMPUTED_TOKENS,
        "historical_uid": T11_HISTORICAL_UID,
        "actual_uid": actual_uid,
        "host_slot": host_slot,
        "serve_log_sha256": sha256(serve_log),
        "source_prefill_line": prefill_line,
    }


def classify_trace_output(log: Path) -> None:
    text = log.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?:API error|HTTP/1\.1\" 5\d\d|Traceback|\bERROR\b)", text, re.I):
        raise ValueError(f"API/error output in {log}")


def classify_state_eq_rc(name: str, returncode: int) -> None:
    """Only legal-reorder comparisons may retain state_eq's diagnostic rc=1."""
    if returncode == 0:
        return
    if returncode == 1 and name in {"eq_R4096_vs_R8192.txt", "eq_R4096_vs_RLM.txt"}:
        return
    raise RuntimeError(f"state_eq {name} failed rc={returncode}")


def t00_base_matches(base: dict[str, Any], full_commit: str) -> bool:
    return base.get("commit") == full_commit and base.get("code_version") == "E2-base@" + EXPECTED_E2_COMMIT


class Runner:
    def __init__(self, options: argparse.Namespace) -> None:
        self.options, self.card = options, CARDS[options.card]
        # E1 cards retain historical trace/flag definitions; new services are E2-only.
        self.worktree, self.commit = ROOT / "wt/e2base", EXPECTED_E2_COMMIT
        self.directory = RUNS / options.rid
        self.proc: subprocess.Popen[str] | None = None
        self.lock: Path | None = None
        self.lock_token: str | None = None
        self.lock_inode: int | None = None

    def status(self, **values: Any) -> None:
        if not self.directory.exists():
            return
        target = self.directory / f"status_batch{self.options.batch}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"card": self.options.card, "rid": self.options.rid, "batch": self.options.batch,
                                         "batch_pid": os.getpid(), "updated_at": time.strftime("%F %T %Z"),
                                         **values}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)

    def environment(self, arm: Path, extra: dict[str, str]) -> dict[str, str]:
        env = os.environ.copy()
        env.update({"PATH": "/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:" + env["PATH"],
                    "LD_LIBRARY_PATH": "/usr/local/cuda-13.0/lib64:" + env.get("LD_LIBRARY_PATH", ""),
                    "VIRTUAL_ENV": "/data2/FreeToken/venv", "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": str(self.worktree / "python")})
        for key, value in extra.items():
            env[key] = str(arm / value) if value == "dump" else value
        if self.options.card == "T10":
            env["FT_REPLAY_MAX_TOKENS"] = "200"
        return env

    def gate(self) -> None:
        if sys.platform != "linux":
            raise RuntimeError("--run only permits the Linux test host")
        if self.directory.exists():
            raise RuntimeError(f"round already exists: {self.directory}")
        if run(["git", "-C", str(self.worktree), "rev-parse", "--short=7", "HEAD"]).strip() != self.commit:
            raise RuntimeError("worktree commit differs from card")
        source = run(["/data2/FreeToken/venv/bin/python", "-c", "import freetoken; print(freetoken.__file__)"],
                     cwd=self.worktree, env=self.environment(self.directory, {})).strip()
        expected_source = str(self.worktree / "python/freetoken/__init__.py")
        if source != expected_source:
            raise RuntimeError(f"import mismatch: {source}")
        run([PY, "-c", "import torch, freetoken.kernel._cpu_moe, freetoken.kernel._pinned_tensor"],
            cwd=self.worktree, env=self.environment(self.directory, {}))
        if run(["git", "-C", str(self.worktree), "status", "--porcelain"]).strip():
            raise RuntimeError("worktree is dirty")
        if (RUNS / "E2-pre-gate-D00/round.json").exists() and (RUNS / "E2-R000/baseline_acceptance.json").exists():
            self.global_evidence()
        else:
            raise RuntimeError("D00 closed evidence and T00 baseline-acceptance files required")
        if not self.card.trace.is_file():
            raise RuntimeError(f"missing trace: {self.card.trace}")
        trace_map(self.card.trace)
        if Path("/data2/_shared/gpu.lock").exists():
            raise RuntimeError("foreign GPU lock exists")
        if any(int(v) >= 1000 for v in run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).split()):
            raise RuntimeError("GPU memory is occupied")
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                raise RuntimeError("port 8095 is occupied")
        except OSError:
            pass
        for line in run(["ps", "-eo", "pid,args"]).splitlines()[1:]:
            pid, _, command_line = line.strip().partition(" ")
            if pid != str(os.getpid()) and re.search(r"ft serve\b|agent_trace\.py (?:replay|generate)\b|state_test_runner\.py.*--run", command_line):
                raise RuntimeError(f"competing GPU/test process: {line}")

    def global_evidence(self) -> None:
        tag = run(["git", "-C", str(ROOT / "wt/e2base"), "describe", "--tags", "--exact-match"]).strip()
        commit = run(["git", "-C", str(ROOT / "wt/e2base"), "rev-parse", "HEAD"]).strip()
        if tag != EXPECTED_E2_TAG + "@" + EXPECTED_E2_COMMIT or commit[:7] != EXPECTED_E2_COMMIT:
            raise RuntimeError(f"E2-base evidence mismatch tag={tag} commit={commit}")
        d00_dir = RUNS / "E2-pre-gate-D00"
        d00 = json.loads((d00_dir / "round.json").read_text(encoding="utf-8"))
        gate = json.loads((d00_dir / "gate_batch26.json").read_text(encoding="utf-8"))
        review = json.loads((d00_dir / "review_batch26.json").read_text(encoding="utf-8"))
        status = json.loads((d00_dir / "status_batch26.json").read_text(encoding="utf-8"))
        if (not d00.get("closed_at") or d00.get("proposed_verdict") != "kept" or d00.get("verdict") not in {"pending_review", "kept"}
                or gate.get("new_commit") != EXPECTED_E2_COMMIT or gate.get("proposed_verdict") != "kept"
                or review.get("rid") != "E2-pre-gate-D00" or review.get("batch") != 26 or review.get("verdict") != "PASS"
                or status.get("state") != "complete"):
            raise RuntimeError("D00 batch26 close/review/status evidence mismatch")
        if d00_dir.stat().st_mode & 0o222:
            raise RuntimeError("D00 closed directory is not read-only")
        manifest = d00_dir / "MANIFEST.sha256"
        if not manifest.is_file() or not manifest.read_text(encoding="utf-8").strip():
            raise RuntimeError("D00 manifest is absent")
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected, relative = line.split(maxsplit=1)
            candidate = d00_dir / relative.lstrip(" *")
            if not candidate.is_file() or sha256(candidate) != expected:
                raise RuntimeError(f"D00 manifest mismatch: {relative}")
        snapshots = sorted((d00_dir / "round_history").glob("round.v*.json"))
        if not snapshots or (d00_dir / "round.json").read_bytes() != snapshots[-1].read_bytes():
            raise RuntimeError("D00 latest round-history snapshot differs from round.json")
        accepted = json.loads((RUNS / "E2-R000/baseline_acceptance.json").read_text(encoding="utf-8"))
        if (accepted.get("verdict") != "kept" or accepted.get("code_version") != "E2-base@23f2e2c"
                or not accepted.get("reviewer")):
            raise RuntimeError("T00 baseline acceptance evidence mismatch")
        t00_dir = RUNS / "E2-R000"
        if t00_dir.stat().st_mode & 0o222:
            raise RuntimeError("accepted T00 baseline directory is not read-only")
        t00_manifest = t00_dir / "MANIFEST.sha256"
        if not t00_manifest.is_file():
            raise RuntimeError("T00 baseline manifest is absent")
        for line in t00_manifest.read_text(encoding="utf-8").splitlines():
            expected, relative = line.split(maxsplit=1)
            candidate = t00_dir / relative.lstrip(" *")
            if not candidate.is_file() or sha256(candidate) != expected:
                raise RuntimeError(f"T00 manifest mismatch: {relative}")
        t00_round = json.loads((t00_dir / "round.json").read_text(encoding="utf-8"))
        base = t00_round.get("base") or {}
        if not t00_base_matches(base, commit):
            raise RuntimeError("T00 round base does not close to E2-base tag/commit")

    def take_lock(self) -> None:
        lock = Path("/data2/_shared/gpu.lock")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("could not acquire exclusive GPU lock") from exc
        self.lock_token = json.dumps({"owner": self.options.rid, "card": self.options.card, "pid": os.getpid(),
                                      "since": time.strftime("%F %T %Z")})
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(self.lock_token)
        self.lock, self.lock_inode = lock, lock.stat().st_ino

    def release_lock(self) -> None:
        if (self.lock and self.lock.exists() and self.lock_token is not None and self.lock_inode is not None
                and self.lock.stat().st_ino == self.lock_inode and self.lock.read_text(encoding="utf-8") == self.lock_token):
            self.lock.unlink()
        self.lock = self.lock_token = None
        self.lock_inode = None

    def start(self, arm: Path, flags: tuple[str, ...], extra: dict[str, str]) -> dict[str, str]:
        env = self.environment(arm, extra)
        argv = ["numactl", "--cpunodebind=0,1", "--interleave=all", FT, "serve", "--model-path",
                str(ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"), "--served-model-name", MODEL,
                "--host", "127.0.0.1", "--port", str(PORT), "--memory-ratio", "0.88", "--moe-cache-auto",
                "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
                "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
                "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--tool-call-parser",
                "qwen3_coder", "--reasoning-parser", "qwen3", *self.card.flags, *flags]
        selected = ["PATH", "LD_LIBRARY_PATH", "VIRTUAL_ENV", "PYTHONUNBUFFERED", "PYTHONPATH", *extra]
        write_new(arm / "SERVE_CMD.txt", "env " + " ".join(f"{k}={shlex.quote(env[k])}" for k in selected)
                  + " " + shlex.join(argv) + "\n")
        source = run([PY, "-c", "import freetoken;print(freetoken.__file__)"], cwd=self.worktree, env=env)
        write_new(arm / "ENV.txt", time.strftime("%F %T CST") + "\n" + source + "\n"
                  + run(["hostname"]) + "\n"
                  + run(["git", "-C", str(self.worktree), "log", "-1", "--format=%H %s"]) + "\n"
                  + run(["nvidia-smi"]) + "\n" + run(["numactl", "-H"]) + "\n"
                  + "\n".join(run(["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"]).splitlines()[:9]) + "\n")
        extensions = run([PY, "-c", "import hashlib,json,freetoken.kernel._cpu_moe as a,freetoken.kernel._pinned_tensor as b;"
                          "print(json.dumps([{\"path\":m.__file__,\"sha256\":hashlib.sha256(open(m.__file__,\"rb\").read()).hexdigest()} for m in (a,b)]))"],
                         cwd=self.worktree, env=env)
        write_new(arm / "compiled_extensions.json", json.loads(extensions))
        with (arm / "serve.log").open("x", encoding="utf-8") as log:
            self.proc = subprocess.Popen(argv, cwd=self.worktree, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
        write_new(arm / "owned_process.json", {"pid": self.proc.pid, "pgid": self.proc.pid,
                  "session": os.getsid(self.proc.pid)})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("owned service died")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8095/health", timeout=5) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    write_new(arm / "health.json", health)
                    break
                if health.get("status") == "error":
                    raise RuntimeError(f"service health error: {health}")
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(5)
        else:
            raise TimeoutError("service readiness timeout")
        parsed = parsed_args(arm / "serve.log")
        try:
            suffix = ast.literal_eval(parsed.get("_unique_suffix", ""))
        except (ValueError, SyntaxError) as exc:
            raise ValueError("parsed PID missing") from exc
        if suffix != ".pid=" + str(self.proc.pid):
            raise ValueError("parsed PID differs from owned service")
        return env

    def stop(self) -> None:
        if self.proc is None:
            return
        proc, self.proc = self.proc, None
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=30)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            free = False
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                    pass
            except OSError:
                free = True
            gpu = run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
            if free and all(int(v) < 1000 for v in gpu.split()):
                return
            time.sleep(2)
        raise RuntimeError("owned service did not release GPU/port")

    def replay(self, arm: Path, name: str, trace: Path, env: dict[str, str], note: str) -> dict[str, Any]:
        out, log = arm / f"{name}.json", arm / f"{name}.log"
        with log.open("x", encoding="utf-8") as sink:
            subprocess.run([PY, str(SCRIPTS / "agent_trace.py"), "replay", "--trace", str(trace), "--out", str(out),
                            "--fresh-note", note], cwd=self.worktree, env=env, stdout=sink,
                           stderr=subprocess.STDOUT, check=True, timeout=1800)
        classify_trace_output(log)
        return validate_replay(trace, out)

    def execute_arm(self, name: str, additions: tuple[str, ...], extra: dict[str, str], replays: tuple[tuple[str, Path], ...],
                    compare_to: Path | None = None, allowed: dict[str, str] | None = None) -> Path:
        arm = self.directory / name
        arm.mkdir()
        if any(value == "dump" for value in extra.values()):
            (arm / "dump").mkdir()
        env = self.start(arm, additions, extra)
        try:
            baseline = parsed_args(arm / "serve.log")
            if self.options.card == "T11":
                require_t11_cache_report(baseline)
            write_new(arm / "serve_args.txt", baseline)
            if compare_to is not None:
                # This is deliberately before the first replay/probe for the arm.
                differences = strict_args(parsed_args(compare_to / "serve.log"), baseline, allowed or {})
                write_new(arm / "args_checked_before_probe.json", differences)
            for label, trace in replays:
                proof = self.replay(arm, label, trace, env, f"{self.options.rid}-{name}-{label}")
                write_new(arm / f"{label}_validation.json", proof)
            if self.options.card == "T04":
                resumes = (arm / "serve.log").read_text(encoding="utf-8", errors="replace").count("GDN bank: resuming")
                if resumes:
                    raise ValueError(f"{name} unexpectedly resumed {resumes} banks with slots=0")
            if self.options.card == "T11":
                index = arm / "dump/index.jsonl"
                if not index.is_file() or not index.read_text(encoding="utf-8").strip():
                    raise ValueError("T11 state dump index is absent or empty")
            return arm
        finally:
            self.stop()

    def execute(self) -> None:
        self.gate()
        if not self.options.run:
            print(f"PREFLIGHT PASS card={self.options.card} rid={self.options.rid} batch={self.options.batch}", flush=True)
            return
        self.take_lock()
        created = False
        try:
            self.directory.mkdir()
            created = True
            write_new(self.directory / "runner_sha256.txt", sha256(Path(__file__)) + "\n")
            with (self.directory / Path(__file__).name).open("xb") as archived_runner:
                archived_runner.write(Path(__file__).read_bytes())
            full_commit = run(["git", "-C", str(self.worktree), "rev-parse", "HEAD"]).strip()
            code_version = run(["git", "-C", str(self.worktree), "describe", "--tags", "--exact-match"]).strip()
            write_new(self.directory / "admission.json", {"card": self.options.card, "rid": self.options.rid,
                      "commit": full_commit, "code_version": code_version,
                      "trace": str(self.card.trace), "trace_sha256": sha256(self.card.trace)})
            write_new(self.directory / "live_checks.json", {"card": self.options.card, "rid": self.options.rid,
                      "commit": full_commit, "code_version": code_version, "worktree": str(self.worktree),
                      "trace": str(self.card.trace), "trace_sha256": sha256(self.card.trace)})
            wrapper = Path(__file__).with_name(f"batch{self.options.batch}_{self.options.rid}_python.sh")
            if not wrapper.is_file():
                raise RuntimeError(f"actual batch wrapper missing: {wrapper}")
            with (self.directory / "batch.sh").open("xb") as archived:
                archived.write(wrapper.read_bytes())
            self.status(state="running")
            arms: list[Path] = []
            if self.options.card == "T11" and not any("FT_D3_TRACE" in path.read_text(encoding="utf-8", errors="ignore")
                                                       for path in (self.worktree / "python/freetoken").rglob("*.py")):
                raise RuntimeError("T11 FT_D3_TRACE hook is absent from admitted worktree")
            if self.options.card == "T10":
                forward = RUNS / "E1-R003-v2/trace.json"
                for name, additions, extra in self.card.arms:
                    arms.append(self.execute_arm(name, additions, extra, (("reversecold", self.card.trace), ("forwardwarm", forward)),
                                                 arms[0] if arms else None))
                joins = {arm.name: {kind: json.loads((arm / f"{kind}_validation.json").read_text())["messages_sha"]
                                    for kind in ("reversecold", "forwardwarm")} for arm in arms}
                for arm, pair in joins.items():
                    if pair["reversecold"] != pair["forwardwarm"]:
                        raise ValueError(f"{arm} reverse/forward messages_sha do not align")
                write_new(self.directory / "messages_sha_joins.json", joins)
                for left, right in (("B1", "B2"), ("B1", "B3"), ("B2", "B3")):
                    output = self.directory / f"cmp_cold_{left}_{right}.json"
                    completed = subprocess.run([PY, str(SCRIPTS / "agent_trace.py"), "compare", "--a", str(self.directory / left / "reversecold.json"),
                                                "--b", str(self.directory / right / "reversecold.json"), "--trace", str(self.card.trace),
                                                "--tokens", "200", "--out", str(output)], cwd=self.worktree, text=True,
                                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    if completed.returncode not in (0, 1):
                        raise RuntimeError(f"T10 compare {left}/{right} failed rc={completed.returncode}")
                    write_new(self.directory / f"cmp_cold_{left}_{right}.log", f"rc={completed.returncode}\n{completed.stdout}")
            else:
                for name, additions, extra in self.card.arms:
                    allowed = ({"max_extend_tokens": "8192"} if self.options.card == "T04" and name == "R8192"
                               else {"prefill_layer_major": "True"} if self.options.card == "T04" and name == "RLM" else {})
                    arms.append(self.execute_arm(name, additions, extra, (("replay", self.card.trace),),
                                                 arms[0] if arms else None, allowed))
                if self.options.card == "T04":
                    # state_eq rc=1 records a diagnostic difference; preserve it rather than treating it as a crash.
                    comparisons = ((RUNS / "E1-R003-stateeq/dump_B", arms[0] / "dump", "eq_B_vs_R4096.txt"),
                                   (arms[0] / "dump", arms[1] / "dump", "eq_R4096_vs_R8192.txt"),
                                   (arms[0] / "dump", arms[2] / "dump", "eq_R4096_vs_RLM.txt"))
                    for left, right, output in comparisons:
                        if not (left / "index.jsonl").is_file() or not (right / "index.jsonl").is_file():
                            if output == "eq_R4096_vs_RLM.txt":
                                write_new(self.directory / "RLM_NODUMP.txt", "RLM dump absent; allowed anomaly by T04 card\n")
                                continue
                            raise RuntimeError(f"required state dump missing for {output}")
                        completed = subprocess.run([PY, str(SCRIPTS / "state_eq.py"), str(left), str(right), "--tol", "0.0"],
                                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        classify_state_eq_rc(output, completed.returncode)
                        write_new(self.directory / output, f"rc={completed.returncode}\n{completed.stdout}")
                if self.options.card == "T11":
                    replay = json.loads((arms[0] / "replay.json").read_text(encoding="utf-8"))
                    historical = RUNS / "E1-R003-stateeq/S_A_coldfirst.json"
                    if not historical.is_file():
                        raise RuntimeError("historical S_A replay is absent")
                    target = t11_target_proof(self.card.trace, arms[0] / "replay.json", arms[0] / "serve.log")
                    target.update({"historical_replay": str(historical), "historical_replay_sha256": sha256(historical),
                                   "actual_worktree": str(self.worktree),
                                   "note": "historical uid=8 and this run's allocated UID are distinct identities"})
                    write_new(self.directory / "t11_target.json", target)
                    completed = subprocess.run([PY, str(SCRIPTS / "state_eq.py"), str(RUNS / "E1-R003-stateeq/dump_A"),
                                               str(arms[0] / "dump"), "--tol", "0.0"], text=True,
                                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    if completed.returncode not in (0, 1):
                        raise RuntimeError(f"T11 historical state_eq failed rc={completed.returncode}")
                    write_new(self.directory / "eq_prevA_vs_new.txt", f"rc={completed.returncode}\n{completed.stdout}")
                    log_lines = (arms[0] / "serve.log").read_text(encoding="utf-8", errors="replace").splitlines()
                    evidence = [line for line in log_lines if "GDN bank: resuming" in line or "donat" in line.lower() or "D3" in line]
                    write_new(self.directory / "t11_target_d3_trace.log", "\n".join(evidence) + "\n")
                    write_new(self.directory / "restore_count.json", {"count": sum("GDN bank: resuming" in line for line in log_lines)})
            self.status(state="complete", arms=[p.name for p in arms],
                        proposed_verdict="pending_review" if self.options.card == "T04" else "measured")
        except BaseException as exc:
            if created:
                write_new(self.directory / "failure.json", {"state": "failed", "error": repr(exc)})
                self.status(state="failed", error=repr(exc))
            raise
        finally:
            try:
                self.stop()
            finally:
                self.release_lock()


def self_test() -> None:
    before = {"model_path": "'/model'", "_unique_suffix": "'.pid=1'", "prefill_layer_major": "False"}
    after = {**before, "_unique_suffix": "'.pid=2'", "prefill_layer_major": "True"}
    strict_args(before, after, {"prefill_layer_major": "True"})
    if "--enable-cache-report" not in CARDS["T11"].flags:
        raise AssertionError("T11 launch flags omit cache reporting")
    require_t11_cache_report({"enable_cache_report": "True"})
    try:
        require_t11_cache_report({"enable_cache_report": "False"})
    except ValueError:
        pass
    else:
        raise AssertionError("T11 cache-report guard accepted disabled configuration")
    try:
        strict_args(before, {**after, "model_path": "'/other'"}, {"prefill_layer_major": "True"})
    except ValueError:
        pass
    else:
        raise AssertionError("argument pollution accepted")
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        trace = root / "trace.json"
        rows = [{"messages": [{"role": "user", "content": str(i)}], "record": {"round": 11 - i, "messages_sha": f"{i:016x}"}} for i in range(12)]
        trace.write_text(json.dumps({"rounds": rows}), encoding="utf-8")
        replay = root / "replay.json"
        replay_rows = [{"round": i, "messages_sha": f"{i:016x}", "trace_messages_sha": f"{i:016x}", "text": "ok", "dry_run": False}
                       for i in reversed(range(12))]
        replay.write_text(json.dumps({"meta": {"params": {"dry_run": False}}, "rounds": replay_rows}), encoding="utf-8")
        assert validate_replay(trace, replay)["rounds"] == 12
        replay_rows[0]["trace_messages_sha"] = "bad"
        replay.write_text(json.dumps({"meta": {"params": {"dry_run": False}}, "rounds": replay_rows}), encoding="utf-8")
        try:
            validate_replay(trace, replay)
        except ValueError:
            pass
        else:
            raise AssertionError("bad messages_sha accepted")
        replay_rows[0]["trace_messages_sha"] = f"{11:016x}"
        replay_rows[0]["dry_run"] = True
        replay.write_text(json.dumps({"meta": {"params": {"dry_run": False}}, "rounds": replay_rows}), encoding="utf-8")
        try:
            validate_replay(trace, replay)
        except ValueError:
            pass
        else:
            raise AssertionError("dry replay row accepted")
        replay_rows[0]["dry_run"] = False
        replay.write_text(json.dumps({"meta": {"params": {"dry_run": True}}, "rounds": replay_rows}), encoding="utf-8")
        try:
            validate_replay(trace, replay)
        except ValueError:
            pass
        else:
            raise AssertionError("dry replay metadata accepted")
        replay_rows[0]["trace_messages_sha"] = replay_rows[0]["messages_sha"]
        replay_rows[0]["round"] = 0
        replay.write_text(json.dumps({"meta": {"params": {"dry_run": False}}, "rounds": replay_rows}), encoding="utf-8")
        try:
            validate_replay(trace, replay)
        except ValueError:
            pass
        else:
            raise AssertionError("wrong replay trace index accepted")
        target_replay = root / "target_replay.json"
        target_rows = [{"round": index, "messages_sha": f"{index:016x}", "trace_messages_sha": f"{index:016x}",
                        "cached_tokens": 13376 if index == 7 else 0,
                        "recomputed_tokens": 56 if index == 7 else 0}
                       for index in range(12)]
        target_replay.write_text(json.dumps({"rounds": target_rows}), encoding="utf-8")
        target_log = root / "target.log"
        target_log.write_text(
            "GDN bank: resuming req 7 from host slot 22\n"
            "Prefill batch, #new-seq: 1, #new-token: 56, #cached-token: 13376, token usage: 0.27\n",
            encoding="utf-8",
        )
        target = t11_target_proof(trace, target_replay, target_log)
        assert (target["messages_sha"], target["actual_uid"], target["historical_uid"], target["host_slot"]) == (
            f"{7:016x}", 7, 8, 22
        )
        target_log.write_text("GDN bank: resuming req 7 from host slot 22\n", encoding="utf-8")
        try:
            t11_target_proof(trace, target_replay, target_log)
        except ValueError:
            pass
        else:
            raise AssertionError("T11 target without source-bound prefill step accepted")
        clean = root / "clean.log"; clean.write_text("replay complete\n", encoding="utf-8")
        classify_trace_output(clean)
        bad = root / "bad.log"; bad.write_text("HTTP/1.1\" 503\n", encoding="utf-8")
        try:
            classify_trace_output(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("API failure accepted")
        runner = object.__new__(Runner)
        runner.options = argparse.Namespace(card="T04", rid="E2-R002", batch=77)
        runner.directory = root / "round"; runner.directory.mkdir()
        runner.status(state="complete")
        status = json.loads((runner.directory / "status_batch77.json").read_text(encoding="utf-8"))
        if status.get("batch") != 77 or status.get("rid") != "E2-R002" or status.get("card") != "T04" or status.get("state") != "complete":
            raise AssertionError("exact batch status binding failed")
        if (runner.directory / "status.json").exists():
            raise AssertionError("unbound status filename created")
    classify_state_eq_rc("eq_R4096_vs_R8192.txt", 1)
    for name, code in (("eq_B_vs_R4096.txt", 1), ("eq_R4096_vs_R8192.txt", 2)):
        try:
            classify_state_eq_rc(name, code)
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid state_eq return code accepted")
    full = "23f2e2c" + "a" * 33
    if not t00_base_matches({"commit": full, "code_version": "E2-base@23f2e2c"}, full):
        raise AssertionError("full T00 commit rejected")
    if t00_base_matches({"commit": "23f2e2c", "code_version": "E2-base@23f2e2c"}, full):
        raise AssertionError("short T00 commit accepted")
    preflight = object.__new__(Runner)
    preflight.options = argparse.Namespace(card="T04", rid="E2-R002", batch=78, run=False)
    preflight.gate = lambda: None
    preflight.take_lock = lambda: (_ for _ in ()).throw(AssertionError("preflight took lock"))
    preflight.directory = root / "must-not-exist"
    preflight.execute()
    if preflight.directory.exists():
        raise AssertionError("preflight created a round directory")
    if ASSIGNED_RIDS["T11"] != "E2-R011":
        raise AssertionError("T11 retry RID is not exact")
    print("SELFTEST PASS: strict args, hash join, T11 cache/target binding, trace/API classification")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--card", choices=sorted(CARDS))
    parser.add_argument("--rid", help="formally assigned round ID from the root executor")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--run", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test(); return
    if not (options.card and options.rid and options.batch is not None):
        parser.error("--card, formally assigned --rid, and --batch are required")
    expected_rid = ASSIGNED_RIDS[options.card]
    if options.rid != expected_rid:
        parser.error(f"RID must be the formally assigned {expected_rid} for {options.card}")
    Runner(options).execute()


if __name__ == "__main__":
    main()
