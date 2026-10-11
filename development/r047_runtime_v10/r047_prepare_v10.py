#!/usr/bin/env python3
"""Queued E2-R047 T03b trigger probe v10.

This is intentionally inert until ``--run`` is supplied on the Linux GPU
host.  CPU validation only exercises payload, log and cleanup guards: it does
not create a socket, start a server, contact a model endpoint, or use CUDA.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path("/data2/FreeToken")
DEVELOPMENT = Path(__file__).resolve().parents[1]
WORKTREE = ROOT / "wt/e2base1-ordinary-rewind"
VENV = ROOT / "venv"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
MODEL_PATH = ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"
LOCK = Path("/data2/_shared/gpu.lock")
RUNS = ROOT / "runs/dev_T03b"
FORMAL_PARENT = Path('/data2/_shared/runs/ft_rounds')
REVIEW_DIR = ROOT / 'runs/dev_T03b/reviews/E2-R047-v7'
RID = "E2-R047"
# The emitted executor and D07 protocol are frozen together in the same
# source directory; never silently import an older global copy.
CLOSED_ROUND_HELPER = DEVELOPMENT / "d07_g3g4_prepare.py"
ARGS_DIFF_SOURCE = DEVELOPMENT / "d04_original" / "serve_args_diff.py"
ARGS_DIFF_SHA256 = "61ef1c553ef383cfa59c2cec609528ed9cde8998061c354224a17b497948bd21"
PAIR_SOURCE = DEVELOPMENT / "ft_batch_port_pair_v1.py"
SHUTDOWN_SOURCE = DEVELOPMENT / 'r052_d0_shutdown_startup_v1.py'
SNAPSHOT_LINE = re.compile(r"D0 anchor_snapshots_taken=(\d+)")

# T03b is after these queue entries.  A missing or non-kept D04 closure means
# this development probe remains queued; it never allocates a formal round.
FORMAL_PREDECESSORS = (("E2-R041-gate-D17", "kept"), ("E2-R040", "failed_harness"),
                       ("E2-R046g", "measured"), ("E2-R045", "measured"), ("E2-R044", "measured"))



def require_formal_output_root(output_root: Path) -> Path:
    raw = Path(output_root)
    if ".." in raw.parts:
        raise RuntimeError("R047 formal output root cannot contain ..")
    if not raw.is_absolute():
        raise RuntimeError("R047 formal output root must be absolute")
    current = Path(raw.anchor)
    for part in raw.parts[1:]:
        current /= part
        if current.is_symlink():
            raise RuntimeError("R047 formal output root cannot traverse symlink")
    expected = FORMAL_PARENT.resolve(strict=False)
    if raw.resolve(strict=False) != expected:
        raise RuntimeError("R047 output root must equal the formal ft_rounds parent")
    return expected

def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def dynamic_fixture_port() -> int:
    """Get a loopback-only ephemeral port without ever probing 8095."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0))
        port = int(guard.getsockname()[1])
    if not 1024 <= port <= 65535 or port == 8095:
        raise RuntimeError("dynamic socket guard returned an invalid fixture port")
    return port


def port_pair() -> dict:
    spec = importlib.util.spec_from_file_location("r047_port_pair", PAIR_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.port_receipt(module.dynamic_port())


def copy_runtime_sources(target: Path, executor: Path | None = None) -> list[dict]:
    target.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__).resolve(), CLOSED_ROUND_HELPER, ARGS_DIFF_SOURCE, PAIR_SOURCE, SHUTDOWN_SOURCE]
    if executor is not None:
        sources.append(executor)
    rows = []
    for source in sources:
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("R047 runtime source unavailable")
        copied = target / ('d04_original/'+source.name if source == ARGS_DIFF_SOURCE else source.name)
        copied.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source, copied); copied.chmod(0o600)
        with copied.open("ab") as handle:
            handle.flush(); os.fsync(handle.fileno())
        if sha256_file(copied)!=sha256_file(source):raise RuntimeError('R047 runtime source copy differs')
        rows.append({"source": str(source), "copy": str(copied), "sha256": sha256_file(copied),
                     "mode": oct(copied.stat().st_mode & 0o777)})
    return rows


def checked_worktree(worktree: Path) -> dict:
    if worktree.is_symlink():
        raise RuntimeError("R047 candidate worktree cannot be a symlink")
    head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True)
    if head != CANDIDATE or dirty:
        raise RuntimeError("R047 requires the clean E2-base.1 candidate 0aa23431e5b800797543bdecbf35a01045131d7d")
    return {"worktree": str(worktree), "commit": head, "tracked_clean": True}


def load_closed_round_helper(source: Path = CLOSED_ROUND_HELPER):
    """Use the shared bounded D04 admission helper; never rehash payload trees."""
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("R047 closed-round helper is unavailable")
    spec = importlib.util.spec_from_file_location("r047_closed_round_helper", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    helper = getattr(module, "require_closed_round", None)
    if not callable(helper):
        raise RuntimeError("R047 requires d07 require_closed_round(rid, verdict) helper")
    return helper


def require_predecessors(require_round=None) -> dict[str, object]:
    supplied = require_round is not None
    require_round = load_closed_round_helper() if require_round is None else require_round
    result: dict[str, object] = {}
    for rid, verdict in FORMAL_PREDECESSORS:
        closure = require_round(rid, verdict)
        if not isinstance(closure, Path):
            raise RuntimeError(f"R047 closed-round helper returned no Path for {rid}")
        result[rid] = str(closure)
    return result


def serialized_predecessors(predecessors: dict[str, object]) -> dict[str, object]:
    """Make small receipt paths explicit before writing a launch/preflight JSON."""
    value = dict(predecessors)
    dev = value.get("development_receipts")
    if isinstance(dev, dict):
        value["development_receipts"] = {
            rid: {"result": str(paths[0]), "result_sha256": sha256_file(paths[0]),
                  "cleanup": str(paths[1]), "cleanup_sha256": sha256_file(paths[1])}
            for rid, paths in dev.items()
        }
    return value


def load_d07_protocol(source: Path = CLOSED_ROUND_HELPER):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("R047 D07 launch protocol is unavailable")
    spec = importlib.util.spec_from_file_location("r047_d07_protocol", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    required = ("load_owned_lifecycle", "require_child_receipt", "publish_child_binding", "argv_sha256",
                "process_birth", "take_d07_gpu_lock", "release_d07_gpu_lock", "require_gpu_idle")
    if any(not callable(getattr(module, name, None)) for name in required):
        raise RuntimeError("R047 D07 owned launch protocol is incomplete")
    return module


def environment(worktree: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("FT_") or key in {"PYTHONPATH", "CUDA_VISIBLE_DEVICES"}:
            env.pop(key)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", PYTHONPATH=str(worktree / "python"),
               VIRTUAL_ENV=str(VENV), PATH=str(VENV / "bin") + ":" + env.get("PATH", ""), CUDA_VISIBLE_DEVICES="0")
    return env


def serve_argv(port: int) -> list[str]:
    """Use the T03 family flags, with host slots available for actual snapshots."""
    return [str(VENV / "bin/ft"), "serve", "--model-path", str(MODEL_PATH), "--served-model-name", MODEL,
            "--host", "127.0.0.1", "--port", str(port), "--memory-ratio", "0.88", "--moe-cache-auto",
            "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
            "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
            "--kv-reserve-tokens", "98304", "--max-seq-len-override", "98304", "--max-prefill-length", "4096",
            "--enable-cache-report", "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder",
            "--reasoning-parser", "qwen3", "--prefill-layer-major", "--mamba-host-slots", "0"]


def start_server(run_dir: Path, worktree: Path, port: int, *, cut_on: bool = True, file_dry: bool = False):
    argv, env = serve_argv(port), environment(worktree)
    if not cut_on:
        argv.append("--no-prefill-anchor-cut")
    # This is the T03 business D0 source.  Its final log line is the only
    # accepted snapshot count; cache donations are not substitute evidence.
    wrapper=run_dir.parent/'source'/SHUTDOWN_SOURCE.name
    if wrapper.is_symlink() or not wrapper.is_file() or sha256_file(wrapper)!=sha256_file(SHUTDOWN_SOURCE):
        raise RuntimeError('R047 actual shutdown wrapper is not copied and bound')
    argv=[str(VENV/'bin/python'),'-u',str(wrapper),*argv[1:]]
    env.update(FT_DEV_D0="1", FT_DEV_D0_PATH=str(run_dir / "d0"), FT_DEV_D0_TIMELINE="1", FT_DEV_D0_TIMELINE_STEPS="20000",FT_R052_WORKER_SHUTDOWN=str(run_dir/'worker_shutdown.json'))
    env['PYTHONPATH']=str(wrapper.parent)+':'+str(worktree/'python')
    write_new(run_dir / "serve_argv.json", {"argv": argv, "port": port, "environment": {k: v for k,v in env.items() if k.startswith('FT_') or k in ("CUDA_VISIBLE_DEVICES", "PYTHONPATH", "VIRTUAL_ENV")}})
    log = (run_dir / "serve.log").open("x", encoding="utf-8")
    if file_dry:
        log.close()
        for name in ('worker_shutdown.json','owned_process.json','snapshot_count.json','positive_turn0.json','negative.json','arm_result.json','d0_prefill.jsonl','d0_decode.json','d0_decode.json.tmp','d0_decode_timeline.jsonl'):
            with (run_dir/(name+'.write_probe')).open('x') as stream:stream.write('{}\n');stream.flush();os.fsync(stream.fileno())
        return {'argv':argv,'service_started':False,'serve_argv_sha256':sha256_file(run_dir/'serve_argv.json')}
    try:process = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    finally:log.close()
    try:
        if os.getpgid(process.pid) != process.pid or os.getsid(process.pid) != process.pid:
            raise RuntimeError("R047 owned service did not receive a private process group/session")
        write_new(run_dir / "owned_process.json", {"pid": process.pid, "pgid": process.pid, "port": port})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"R047 owned service exited during startup: {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    if json.load(response).get("status") == "ok":
                        return process
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(2)
        raise TimeoutError("R047 owned service did not become healthy")
    except BaseException as startup_error:
        try:
            stop_owned_process(process)
        except BaseException as cleanup_error:
            cleanup_error.owned_process = process
            cleanup_error.owned_cleanup_failed = True
            raise cleanup_error from startup_error
        raise


def stop_owned_process(process: subprocess.Popen) -> None:
    # The leader can exit while descendants remain in its private group.
    # Reuse the owned lifecycle instead of treating a leader poll as cleanup.
    load_d07_protocol().load_owned_lifecycle().stop_owned_process(process)


def request_json(port: int, payload: dict) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                    headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=1800) as response:
        return json.load(response)


def parse_sse_events(lines, *, started: float, clock=time.monotonic) -> tuple[list[dict], float | None, dict]:
    """Parse SSE and timestamp only the first meaningful generated delta."""
    events, first, final = [], None, None
    for raw in lines:
        line = raw.decode("utf-8").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        event = json.loads(line[6:]); events.append(event); final = event
        choices = event.get("choices")
        if first is None and isinstance(choices, list) and choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict) and any(isinstance(delta.get(key), str) and delta[key] for key in ("reasoning_content", "content")):
                first = clock() - started
    if final is None:
        raise ValueError("stream produced no JSON event")
    return events, first, final


def canonical_wire(payload: dict) -> bytes:
    """The exact ordinary request input, serialized once before it is sent."""
    wire = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    return json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stream_request(port: int, payload: dict) -> tuple[dict, list[dict], float | None, dict]:
    wire = canonical_wire(payload)
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=wire,
                                    headers={"Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=1800) as response:
        lines = list(response)
        events, ttft, final = parse_sse_events(lines, started=started)
    usage = final.get("usage", {}) if isinstance(final, dict) else {}
    details = usage.get("prompt_tokens_details", {}) if isinstance(usage, dict) else {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if cached is not None and (type(cached) is not int or cached < 0):
        raise ValueError("stream cached_tokens is invalid")
    # Rebuild the normal completion shape from deltas for transcript reuse.
    reasoning = "".join(c["delta"].get("reasoning_content", "") for e in events for c in e.get("choices", []) if isinstance(c.get("delta"), dict))
    content = "".join(c["delta"].get("content", "") for e in events for c in e.get("choices", []) if isinstance(c.get("delta"), dict))
    raw = b"".join(lines)
    return ({"choices": [{"message": {"reasoning_content": reasoning, "content": content}}], "usage": usage}, events, ttft,
            {"input_sha256": hashlib.sha256(wire).hexdigest(), "raw_sse_sha256": hashlib.sha256(raw).hexdigest(),
             "raw_sse_b64": base64.b64encode(raw).decode("ascii"), "api_cached_tokens": cached,
             "api_cached_state": "reported" if cached is not None else "unreported"})


def _d0_rows(path: Path, uid: int) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("R047 D0 prefill evidence is missing")
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        reqs = value.get("reqs") if isinstance(value, dict) else None
        if not isinstance(reqs, list):
            raise ValueError("R047 D0 prefill row lacks reqs")
        for req in reqs:
            if not isinstance(req, dict) or set(req) != {"rid", "new_tokens", "cached_tokens"}:
                raise ValueError("R047 D0 request schema differs")
            if any(type(req[key]) is not int or req[key] < 0 for key in req):
                raise ValueError("R047 D0 request values are invalid")
            if req["rid"] == uid:
                rows.append({"line": line_no, **req})
    if not rows:
        raise ValueError("R047 D0 lacks the ordinary SSE UID")
    return rows


def bind_post_trigger_cache(turn: dict, d0_path: Path) -> dict:
    """Bind final ordinary wire/SSE evidence to D0's real first admission."""
    wire = turn.get("wire")
    response = turn.get("response")
    payload = turn.get("payload")
    if not isinstance(wire, dict) or not isinstance(response, dict) or not isinstance(payload, dict):
        raise ValueError("R047 post-trigger turn is incomplete")
    if not isinstance(wire.get("input_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", wire["input_sha256"]):
        raise ValueError("R047 canonical request input SHA is invalid")
    if hashlib.sha256(canonical_wire(payload)).hexdigest() != wire["input_sha256"]:
        raise ValueError("R047 actual request input SHA differs")
    raw = base64.b64decode(wire.get("raw_sse_b64", ""), validate=True)
    if hashlib.sha256(raw).hexdigest() != wire.get("raw_sse_sha256"):
        raise ValueError("R047 raw SSE SHA differs")
    events, _, final = parse_sse_events(raw.splitlines(keepends=True), started=0.0, clock=lambda: 0.0)
    ids = {event.get("id") for event in events if isinstance(event, dict)}
    if len(ids) != 1 or not isinstance(next(iter(ids)), str) or not re.fullmatch(r"chatcmpl-(\d+)", next(iter(ids))):
        raise ValueError("R047 ordinary SSE UID is absent or inconsistent")
    uid = int(next(iter(ids)).removeprefix("chatcmpl-"))
    usage = final.get("usage") if isinstance(final, dict) else None
    prompt = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    if type(prompt) is not int or prompt <= 0 or response.get("usage") != usage:
        raise ValueError("R047 final SSE/API prompt evidence differs")
    rows = _d0_rows(d0_path, uid)
    first, *continuations = rows
    if type(first.get("cached_tokens")) is not int:
        raise ValueError("R047 D0 first admission cache value is invalid")
    if any(row["cached_tokens"] != 0 for row in continuations):
        raise ValueError("R047 D0 continuation cache value must be zero")
    scheduled = first["cached_tokens"]
    if scheduled + sum(row["new_tokens"] for row in rows) != prompt:
        raise ValueError("R047 D0/API prompt accounting differs")
    api_cached = wire.get("api_cached_tokens")
    if wire.get("api_cached_state") not in {"reported", "unreported"}:
        raise ValueError("R047 API cache state is invalid")
    if wire["api_cached_state"] == "reported" and (type(api_cached) is not int or api_cached != scheduled):
        raise ValueError("R047 reported API cache value differs from D0")
    if wire["api_cached_state"] == "unreported" and api_cached is not None:
        raise ValueError("R047 unreported API cache value must be null")
    return {"uid": uid, "input_sha256": wire.get("input_sha256"), "raw_sse_sha256": wire.get("raw_sse_sha256"),
            "api_cache": {"state": wire["api_cached_state"], "value": api_cached},
            "scheduled_cached_tokens": scheduled, "d0_prefill_sha256": sha256_file(d0_path), "d0_rows": rows}


def retained_followup(messages: list[dict], response: dict) -> list[dict]:
    """Use the actual prior reasoning/content as the next-turn context."""
    return [*messages, {"role": "assistant", "content": decoded_text(response)},
            {"role": "user", "content": "Continue from the reasoning above and calculate 41 - 16."}]


def positive_payload() -> dict:
    return {"model": MODEL, "stream": False, "max_tokens": 2048,
            "messages": [{"role": "user", "content": "Solve 17 × 19 − 23. Think through the arithmetic, then state the final integer after your reasoning."}],
            "chat_template_kwargs": {"enable_thinking": True}}


def negative_payload() -> dict:
    return {"model": MODEL, "stream": False, "max_tokens": 64,
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "chat_template_kwargs": {"enable_thinking": False}}


def decoded_text(response: dict) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("response has no first choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("response choice has no message")
    parts = [message.get(key) for key in ("reasoning_content", "content")]
    if not all(value is None or isinstance(value, str) for value in parts):
        raise ValueError("response thinking/content fields are not strings")
    return "".join(value or "" for value in parts)


def classify_positive(response: dict) -> dict:
    text = decoded_text(response)
    marker = text.find("</think>")
    # A reasoning parser can expose reasoning and content as separate fields.
    message = response["choices"][0]["message"]
    split_hit = isinstance(message.get("reasoning_content"), str) and isinstance(message.get("content"), str) and bool(message["content"])
    hit = marker >= 0 and bool(text[marker + len("</think>"):].strip()) or split_hit
    return {"classification": "hit" if hit else "missed", "has_think_close": marker >= 0,
            "has_post_think_decode": bool(text[marker + len("</think>"):].strip()) if marker >= 0 else split_hit,
            "response_chars": len(text)}


def snapshot_count(serve_log: Path) -> int:
    values = [int(value) for value in SNAPSHOT_LINE.findall(serve_log.read_text(encoding="utf-8", errors="replace"))]
    if len(values) != 1:
        raise ValueError("expected exactly one final D0 anchor_snapshots_taken log line")
    return values[0]


def write_snapshot_count(run_dir: Path) -> int:
    value = snapshot_count(run_dir / "serve.log")
    write_new(run_dir / "snapshot_count.json", {"actual_successful_snapshots": value})
    return value


def packet(worktree: Path) -> dict:
    return {"schema": "ft_t03b_r047_prepare/v1", "rid": RID, "candidate_commit": CANDIDATE,
            "worktree": str(worktree), "model": MODEL, "output_root": str(FORMAL_PARENT),
            "fixture_port": "allocated only by --run after the admission gates",
            "run_requires": ["explicit --run", "Linux host", "clean candidate", "formal D04 closures at their actual kept/measured verdicts", "GPU idle", "owned O_EXCL lock"],
            "template": {"local": "plan/01_测试与调研/batches/batch29_E2-R008_python.sh", "sha256": "19ad60685d8fcb9942535dc3268e72ea205ceed4e2152ba8a569328faf2daad0"},
            "formal_design": {"arms": ["A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3"], "only_ab_difference": "--no-prefill-anchor-cut", "measure": ["per-arm final snapshot_count", "post-trigger cache-hit length", "first-token cold/hot"]},
            "positive": "thinking enabled with 2048-token budget; hit only after </think> plus decode, otherwise missed",
            "negative": "thinking disabled short request", "snapshot_evidence": "each arm has one final serve.log D0 anchor_snapshots_taken line; snapshot_count.json must equal it",
            "verdict": "ready_for_review"}


def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"R047 expected regular file is unavailable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_bindings():
    paths=[Path(__file__).resolve(),CLOSED_ROUND_HELPER,ARGS_DIFF_SOURCE,PAIR_SOURCE,SHUTDOWN_SOURCE]
    paths.extend(WORKTREE/name for name in ('python/freetoken/server/launch.py','python/freetoken/server/args.py','python/freetoken/moe/offload_cache.py','python/freetoken/moe/d0_decode.py','python/freetoken/scheduler/cache.py','python/freetoken/server/openai_api.py'))
    return {str(p):sha256_file(p) for p in paths}


def require_file_dry_receipt(path: Path) -> dict:
    path=Path(path)
    if (any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_mode&0o222
        or path.name!='dry_run_receipt.json' or path.parent.parent.resolve()!=FORMAL_PARENT.resolve()
        or not path.parent.name.startswith('.dryrun_R047_')):raise RuntimeError('R047 actual file-dry receipt missing or writable')
    value=json.loads(path.read_text())
    expected={'schema':'ft_r047_file_dry_run/v2','rid':RID,'candidate_commit':CANDIDATE,'passed':True,
              'source_bindings':source_bindings(),'cwd':os.getcwd(),'uid':os.getuid()}
    if any(value.get(k)!=v for k,v in expected.items()) or len(value.get('arms',[]))!=6:raise RuntimeError('R047 file-dry identity/source/coverage differs')
    if any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')):raise RuntimeError('R047 file-dry prohibited effects')
    return {'path':str(path),'sha256':sha256_file(path)}


def review_input_sha256() -> str:
    value = {"arms": ["A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3"],
             "only_ab_difference": "--no-prefill-anchor-cut", "positive": positive_payload(),
             "negative": negative_payload(), "window": 98304, "host_slots": 0, "stream_measure": "actual_ttft"}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sealed_review_path(path: Path) -> None:
    expected = REVIEW_DIR / 'review.json'
    if Path(path) != expected or '..' in Path(path).parts:
        raise RuntimeError('R047 review receipt path is not the fixed sealed review.json')
    current = Path(expected.anchor)
    for part in expected.parts[1:]:
        current /= part
        if current.is_symlink(): raise RuntimeError('R047 sealed review path traverses symlink')
    for item in (REVIEW_DIR, expected, REVIEW_DIR / 'pin.json'):
        if item.is_symlink() or not item.is_file() and item != REVIEW_DIR or item.stat().st_mode & 0o222:
            raise RuntimeError('R047 sealed review/pin is missing or writable')
def validate_review_receipt(path: Path, executor: Path, prepare_source: Path | None = None) -> dict:
    _sealed_review_path(path)
    review, pin = REVIEW_DIR / 'review.json', REVIEW_DIR / 'pin.json'
    try: doc=json.loads(review.read_text(encoding='utf-8')); pin_doc=json.loads(pin.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc: raise RuntimeError('R047 sealed review/pin is invalid JSON') from exc
    prepare_source = Path(__file__).resolve() if prepare_source is None else prepare_source
    template = Path(os.environ.get('T03B_TEMPLATE_PATH', DEVELOPMENT.parent / 'plan/01_测试与调研/batches/batch29_E2-R008_python.sh'))
    expected={'schema':'ft_t03b_r047_review/v2','rid':RID,'candidate_commit':CANDIDATE,'executor_sha256':sha256_file(executor),'prepare_sha256':sha256_file(prepare_source),'template_sha256':sha256_file(template),'input_sha256':review_input_sha256(),'canonical_output_root':str(FORMAL_PARENT),'source_bindings':source_bindings()}
    pin_expected={'schema':'ft_t03b_r047_review_pin/v1','rid':RID,'review_path':str(review),'review_sha256':sha256_file(review),'prepare_sha256':sha256_file(prepare_source)}
    if doc.get('approved') is not True or any(doc.get(k)!=v for k,v in expected.items()) or any(pin_doc.get(k)!=v for k,v in pin_expected.items()):
        raise RuntimeError('R047 sealed review/pin does not bind this executor/source/template/input/output')
    dry=require_file_dry_receipt(doc.get('file_dry_receipt',''))
    if doc.get('file_dry_receipt_sha256')!=dry['sha256']:raise RuntimeError('R047 review file-dry SHA differs')
    return doc

def load_args_parser():
    if sha256_file(ARGS_DIFF_SOURCE) != ARGS_DIFF_SHA256:
        raise RuntimeError("R047 pinned serve_args_diff source differs")
    parser = runpy.run_path(str(ARGS_DIFF_SOURCE)).get("parse")
    if not callable(parser):
        raise RuntimeError("R047 pinned serve_args_diff parser is unavailable")
    return parser


def _parsed_args_diff(left: dict, right: dict) -> set[str]:
    return {key for key in set(left) | set(right) if left.get(key) != right.get(key)}


def verify_args_pairs(root: Path, parse) -> list[dict]:
    pairs = [(f"A_cut_on_p{index}", f"B_cut_off_p{index}", {"_unique_suffix", "prefill_anchor_cut"})
             for index in range(1, 4)]
    pairs += [("A_cut_on_p1", "A_cut_on_p2", {"_unique_suffix"}),
              ("A_cut_on_p1", "A_cut_on_p3", {"_unique_suffix"}),
              ("B_cut_off_p1", "B_cut_off_p2", {"_unique_suffix"}),
              ("B_cut_off_p1", "B_cut_off_p3", {"_unique_suffix"})]
    rows = []
    for left, right, allowed in pairs:
        left_args, right_args = parse(root / left / "serve.log"), parse(root / right / "serve.log")
        required = {"model_path", "server_port", "special_token_ckpt", "_unique_suffix", "prefill_anchor_cut"}
        if any(key not in left_args or key not in right_args for key in required):
            raise RuntimeError(f"R047 parsed arguments lack required fields for {left}/{right}")
        if not all(re.fullmatch(r"['\"]\.pid=\d+['\"]", value) for value in
                   (left_args["_unique_suffix"], right_args["_unique_suffix"])):
            raise RuntimeError(f"R047 parsed _unique_suffix is not a pid identity for {left}/{right}")
        if left.startswith("A_") != (left_args["prefill_anchor_cut"] == "True"):
            raise RuntimeError(f"R047 parsed cut setting differs from arm name: {left}")
        if right.startswith("A_") != (right_args["prefill_anchor_cut"] == "True"):
            raise RuntimeError(f"R047 parsed cut setting differs from arm name: {right}")
        diff = _parsed_args_diff(left_args, right_args)
        row = {"a": left, "b": right, "diff_keys": sorted(diff), "allowed": sorted(allowed)}
        if diff != allowed:
            raise RuntimeError(f"R047 dirty control {left}/{right}: {row}")
        rows.append(row)
    return rows


def child_argv(batch: int, receipt: Path, executor: Path, review_receipt: Path,
               worktree: Path, output_root: Path) -> list[str]:
    return [str(VENV / "bin/python"), str(executor), "--run", "--owned-child", "--batch", str(batch),
            "--launch-receipt", str(receipt), "--review-receipt", str(review_receipt),
            "--worktree", str(worktree), "--out", str(output_root)]


def file_dry_run(directory: Path, executor: Path, review_receipt: Path, worktree: Path, output_root: Path) -> dict:
    """Formal writer rehearsal; it deliberately cannot reserve, lock, spawn or request."""
    directory = Path(directory)
    if (directory.exists() or any(p.is_symlink() for p in (directory,*directory.parents))
        or directory.parent.resolve()!=FORMAL_PARENT.resolve() or not directory.name.startswith('.dryrun_R047_')):
        raise RuntimeError("R047 file-dry output must be a fresh canonical hidden sibling")
    output_root = require_formal_output_root(output_root)
    checked_worktree(worktree); predecessors = require_predecessors()
    directory.mkdir(parents=True, mode=0o700)
    copies = copy_runtime_sources(directory / "source", executor)
    arms = []
    pair=port_pair();write_new(directory/'port_pair.json',pair)
    for name, cut in (("A_cut_on_p1", True), ("B_cut_off_p1", False), ("A_cut_on_p2", True),
                      ("B_cut_off_p2", False), ("A_cut_on_p3", True), ("B_cut_off_p3", False)):
        arm = directory / name; arm.mkdir()
        files=start_server(arm,worktree,pair['api'],cut_on=cut,file_dry=True)
        arms.append({"arm": name, "port_pair": pair,'service':files})
    receipt = {"schema": "ft_r047_file_dry_run/v2", "rid": RID, "candidate_commit": CANDIDATE,
               'source_bindings':source_bindings(),'cwd':os.getcwd(),'uid':os.getuid(),
               "passed": True, "source_copies": copies, "arms": arms, "predecessors": serialized_predecessors(predecessors),
               "formal_rid_directory_created": False, "service_started": False, "requests_sent": False,
               "gpu_lock_taken": False, "batch_allocated": False}
    write_new(directory / "dry_run_receipt.json", receipt); (directory / "dry_run_receipt.json").chmod(0o444)
    return receipt


def controller_launch(executor: Path, review_receipt: Path, worktree: Path, output_root: Path) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R047 --run requires the Linux GPU host")
    checked_worktree(worktree)
    predecessors = require_predecessors()
    validate_review_receipt(review_receipt, executor)
    output_root = require_formal_output_root(output_root)
    protocol = load_d07_protocol()
    if LOCK.exists() or LOCK.is_symlink():
        raise RuntimeError("foreign GPU lock exists; R047 remains queued")
    owned = protocol.load_owned_lifecycle()
    helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", protocol.ATOMIC_HELPER_SHA,
                                   "r047_atomic_launcher")
    batch = helper.next_batch(protocol.ROUNDS)
    receipt_path = RUNS / f"launch_{RID}_batch{batch}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    argv = child_argv(batch, receipt_path, executor, review_receipt, worktree, output_root)
    reserved = {"schema": "ft_t03b_owned_launch/v1", "state": "reserved", "rid": RID, "batch": batch,
                "candidate_commit": CANDIDATE, "argv_sha256": protocol.argv_sha256(argv),
                "controller": protocol.process_birth(), "executor_sha256": sha256_file(executor),
                "review_receipt_sha256": sha256_file(review_receipt),
                "predecessors": serialized_predecessors(predecessors)}
    receipt = owned.reserve_process(helper, batch, RID, argv, receipt_path, reserved)
    identity = owned.process_identity(receipt["batch_pid"])
    if identity is None or identity.get("pid") != receipt["batch_pid"] or type(identity.get("start_ticks")) is not int:
        raise RuntimeError("R047 reserved child birth is unavailable")
    child = {"pid": identity["pid"], "start_ticks": identity["start_ticks"],
             "execution_id": f"{identity['pid']}:{identity['start_ticks']}"}
    return protocol.publish_child_binding(receipt_path, receipt, child, lifecycle=owned)


def _run_arms(root: Path, worktree: Path, port: int) -> None:
    arms = (("A_cut_on_p1", True), ("B_cut_off_p1", False), ("A_cut_on_p2", True),
            ("B_cut_off_p2", False), ("A_cut_on_p3", True), ("B_cut_off_p3", False))
    for name, cut in arms:
        arm = root / name
        arm.mkdir()
        process = None
        try:
            process = start_server(arm, worktree, port, cut_on=cut)
            messages, responses, observations = positive_payload()["messages"], [], []
            for turn in range(3):
                payload = {**positive_payload(), "messages": messages}
                response, raw, ttft, wire = stream_request(port, payload)
                responses.append(response)
                write_new(arm / f"positive_turn{turn}.json",
                          {"payload": payload, "response": response, "sse_events": raw, "wire": wire})
                observations.append({"turn": turn, "first_token_s": ttft, "input_sha256": wire["input_sha256"],
                                     "raw_sse_sha256": wire["raw_sse_sha256"], "api_cache":
                                     {"state": wire["api_cached_state"], "value": wire["api_cached_tokens"]}})
                messages = retained_followup(messages, response)
            negative = request_json(port, negative_payload())
            write_new(arm / "negative.json", negative)
            trigger = classify_positive(responses[0])
            write_new(arm / "trigger_probe.json", trigger)
            try:
                load_d07_protocol().load_owned_lifecycle().stop_owned_process(process)
            except BaseException as cleanup_error:
                cleanup_error.owned_process = process
                raise
            process = None
            shutdown=json.loads((arm/'worker_shutdown.json').read_text())
            if shutdown.get('schema')!='ft_r052_worker_shutdown/v1' or shutdown.get('status')!='complete' or shutdown.get('scheduler_run_started') is not True:
                raise RuntimeError('R047 actual worker D0 shutdown did not finish')
            count = write_snapshot_count(arm)
            decode=json.loads((arm/'d0_decode.json').read_text())
            if decode.get('anchor_snapshots_taken')!=count:raise RuntimeError('R047 final D0 decode snapshot count differs from serve.log')
            final_turn = json.loads((arm / "positive_turn2.json").read_text(encoding="utf-8"))
            hit = bind_post_trigger_cache(final_turn, arm / "d0_prefill.jsonl")
            write_new(arm / "arm_result.json", {"arm": name, "cut_on": cut, "trigger": trigger,
                      "actual_successful_snapshots": count, "turns": observations,
                      "post_trigger_cache_hit": hit,
                      "first_token_s": observations[-1]["first_token_s"]})
        finally:
            if process is not None:
                try:
                    load_d07_protocol().load_owned_lifecycle().stop_owned_process(process)
                except BaseException as cleanup_error:
                    cleanup_error.owned_process = process
                    raise


def summarize_arms(root: Path) -> tuple[list[dict], bool]:
    arms = []
    for name in ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3"):
        path = root / name / "arm_result.json"
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            count = row["actual_successful_snapshots"]
            turns = row["turns"]
            cached = row["post_trigger_cache_hit"]
            ttft = row["first_token_s"]
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"R047 arm summary is incomplete: {name}") from exc
        if type(count) is not int or count < 0 or not isinstance(turns, list) or not isinstance(cached, dict):
            raise RuntimeError(f"R047 arm summary has invalid D0 evidence: {name}")
        arms.append({"arm": name, "actual_successful_snapshots": count,
                     "post_trigger_cache_hit": cached, "first_token_s": ttft,
                     "turns": turns})
    return arms, any(row["actual_successful_snapshots"] > 0 for row in arms)


def child_execute(executor: Path, review_receipt: Path, worktree: Path, output_root: Path,
                  batch: int | None, launch_receipt: Path | None) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R047 --run requires the Linux GPU host")
    if batch is None or launch_receipt is None:
        raise RuntimeError("R047 owned child requires controller receipt and reserved batch")
    protocol = load_d07_protocol()
    expected = child_argv(batch, launch_receipt, executor, review_receipt, worktree, output_root)
    protocol.require_child_receipt(launch_receipt, batch, worktree, output_root, rid=RID,
                                   expected_argv=expected, schema="ft_t03b_owned_launch/v1")
    output_root = require_formal_output_root(output_root)
    checked_worktree(worktree)
    predecessors = require_predecessors()
    validate_review_receipt(review_receipt, executor)
    owner = protocol.take_d07_gpu_lock(RID, batch)
    root = None
    active = None
    release = True
    try:
        idle = protocol.require_gpu_idle()
        root = output_root / RID
        root.mkdir(parents=False, exist_ok=False)
        copies = copy_runtime_sources(root / "source", executor)
        write_new(root / "preflight.json", {**packet(worktree), "batch": batch, "gpu_owner": owner,
                  "gpu_memory_mib": idle, "predecessors": serialized_predecessors(predecessors),
                  "review_receipt_sha256": sha256_file(review_receipt), "executor_sha256": sha256_file(executor), "source_copies": copies})
        pair = port_pair(); port = pair["api"]; write_new(root / "port_pair.json", pair)
        _run_arms(root, worktree, port)
        rows = verify_args_pairs(root, load_args_parser())
        write_new(root / "args_diff.json", {"rows": rows})
        arms, nonzero_coverage = summarize_arms(root)
        result = {"schema": "ft_t03b_r047_result/v1", "rid": RID, "batch": batch,
                  "candidate_commit": CANDIDATE, "verdict": "pending_review",
                  "proposed_verdict": "measured", "args_diff": rows, "arms": arms,
                  "nonzero_coverage_claimed": nonzero_coverage,
                  "coverage_status": "nonzero_observed" if nonzero_coverage else "coverage_not_achieved",
                  "run_dir": str(root)}
        write_new(root / "result.json", result)
        return result
    except BaseException as exc:
        active = getattr(exc, "owned_process", active)
        if getattr(exc, "owned_cleanup_failed", False):
            # A failed first stop is indeterminate even if a later group probe says false.
            release = False
        if root is not None:
            write_new(root / "failed_harness.json", {"rid": RID, "batch": batch, "error": repr(exc),
                                                     "verdict": "pending_review"})
        raise
    finally:
        if active is not None and protocol.load_owned_lifecycle().owned_group_alive(active.pid):
            release = False
        if release:
            protocol.release_d07_gpu_lock(owner)
        if root is not None:
            write_new(root / "owned_cleanup.json", {"schema": "ft_t03b_owned_cleanup/v1", "rid": RID,
                      "batch": batch, "candidate_commit": CANDIDATE, "gpu_owner": owner,
                      "lock_released": release})


def emit_review_executor(destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("refuse to overwrite an existing reviewed executor")
    template = Path(os.environ.get("T03B_TEMPLATE_PATH",
                    DEVELOPMENT.parent / "plan/01_测试与调研/batches/batch29_E2-R008_python.sh"))
    if sha256_file(template) != "19ad60685d8fcb9942535dc3268e72ea205ceed4e2152ba8a569328faf2daad0":
        raise RuntimeError("local batch29 template binding differs")
    source_dir = str(Path(__file__).resolve().parent)
    body = f'''
#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, {source_dir!r})
import r047_prepare_v10 as source
ARMS = ("A_cut_on_p1", "B_cut_off_p1", "A_cut_on_p2", "B_cut_off_p2", "A_cut_on_p3", "B_cut_off_p3")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--file-dry-run", type=Path)
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--launch-receipt", type=Path)
    parser.add_argument("--review-receipt", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    executor = Path(__file__).resolve()
    if args.file_dry_run:
        if args.run or args.owned_child or args.batch is not None or args.launch_receipt is not None:
            raise RuntimeError("--file-dry-run cannot mix launch arguments")
        source.file_dry_run(args.file_dry_run, executor, args.review_receipt, args.worktree, args.out)
        return
    if not args.run:
        raise RuntimeError("explicit --run is required")
    if args.owned_child:
        source.child_execute(executor, args.review_receipt, args.worktree, args.out, args.batch, args.launch_receipt)
    else:
        source.controller_launch(executor, args.review_receipt, args.worktree, args.out)
if __name__ == "__main__":
    main()
'''.lstrip()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(body, encoding="utf-8", newline="\n")
    return destination


def execute(worktree: Path, output_root: Path) -> dict:
    raise RuntimeError("R047 must run only through the reviewed emitted controller/child executor")


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); log = root / "serve.log"
        log.write_text("x\nD0 anchor_snapshots_taken=3\n", encoding="utf-8")
        assert write_snapshot_count(root) == 3
        assert json.loads((root / "snapshot_count.json").read_text())["actual_successful_snapshots"] == 3
        log.write_text("D0 anchor_snapshots_taken=1\nD0 anchor_snapshots_taken=2\n", encoding="utf-8")
        try: snapshot_count(log)
        except ValueError: pass
        else: raise AssertionError("multiple snapshot counts accepted")
    assert classify_positive({"choices": [{"message": {"content": "<think>x</think>answer"}}]})["classification"] == "hit"
    assert classify_positive({"choices": [{"message": {"content": "answer"}}]})["classification"] == "missed"
    argv = serve_argv(12345)
    assert argv[argv.index("--mamba-host-slots") + 1] == "0" and "8095" not in argv
    print("SELFTEST PASS: payload classification, final-log count, T03 flags, and no service binding")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly run the queued Linux GPU probe")
    parser.add_argument("--emit", type=Path, help="emit a review-bound six-arm executor; CPU only")
    parser.add_argument("--self-test", action="store_true", help="CPU-only parser test; no socket, service, CUDA, or model connection")
    parser.add_argument("--worktree", type=Path, default=WORKTREE)
    parser.add_argument("--output-root", type=Path, default=FORMAL_PARENT)
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.run, args.self_test, args.emit)) > 1: parser.error("select one action")
    if args.self_test: self_test(); return 0
    if args.emit: print(emit_review_executor(args.emit)); return 0
    if args.run: print(json.dumps(execute(args.worktree, args.output_root), ensure_ascii=False, sort_keys=True)); return 0
    print(json.dumps(packet(args.worktree), ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
