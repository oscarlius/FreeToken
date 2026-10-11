"""Frozen R047 v12 payload/SSE/cache-binding leaf; no launch entry."""
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
ROOT=Path('/data2/FreeToken')
VENV=ROOT/'venv'
MODEL='Qwen3.8-Flash-Next-NVFP4'
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
SNAPSHOT_LINE=re.compile(r'D0 anchor_snapshots_taken=(\d+)')


def serve_argv(port: int) -> list[str]:
    """Use the T03 family flags, with host slots available for actual snapshots."""
    return [str(VENV / "bin/ft"), "serve", "--model-path", str(MODEL_PATH), "--served-model-name", MODEL,
            "--host", "127.0.0.1", "--port", str(port), "--memory-ratio", "0.88", "--moe-cache-auto",
            "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
            "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
            "--kv-reserve-tokens", "98304", "--max-seq-len-override", "98304", "--max-prefill-length", "4096",
            "--enable-cache-report", "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder",
            "--reasoning-parser", "qwen3", "--prefill-layer-major", "--mamba-host-slots", "0"]

def _remaining(deadline, clock):
    value = deadline - clock()
    if value <= 0: raise TimeoutError('transport budget exhausted')
    return value

def _set_read_timeout(response, seconds):
    stream = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
    if stream is not None and hasattr(stream, 'settimeout'): stream.settimeout(seconds)

def request_json(port: int, payload: dict, timeout: float | None = None, *, clock=time.monotonic) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    deadline = None if timeout is None else clock() + timeout
    initial = 1800 if deadline is None else _remaining(deadline, clock)
    with urllib.request.urlopen(request, timeout=initial) as response:
        if deadline is not None: _set_read_timeout(response, _remaining(deadline, clock))
        value = json.load(response)
        if deadline is not None: _remaining(deadline, clock)
        return value

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

def stream_request(port: int, payload: dict, timeout: float | None = None, *, clock=time.monotonic) -> tuple[dict, list[dict], float | None, dict]:
    wire = canonical_wire(payload)
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=wire, headers={"Content-Type": "application/json"}, method="POST")
    started = clock(); deadline = None if timeout is None else started + timeout
    initial = 1800 if deadline is None else _remaining(deadline, clock)
    with urllib.request.urlopen(request, timeout=initial) as response:
        lines = []
        for line in response:
            if deadline is not None: _set_read_timeout(response, _remaining(deadline, clock))
            lines.append(line)
        if deadline is not None: _remaining(deadline, clock)
        events, ttft, final = parse_sse_events(lines, started=started, clock=clock)
    usage = final.get("usage", {}) if isinstance(final, dict) else {}
    details = usage.get("prompt_tokens_details", {}) if isinstance(usage, dict) else {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if cached is not None and (type(cached) is not int or cached < 0): raise ValueError("stream cached_tokens is invalid")
    reasoning = "".join(c["delta"].get("reasoning_content", "") for e in events for c in e.get("choices", []) if isinstance(c.get("delta"), dict))
    content = "".join(c["delta"].get("content", "") for e in events for c in e.get("choices", []) if isinstance(c.get("delta"), dict))
    raw = b"".join(lines)
    return ({"choices": [{"message": {"reasoning_content": reasoning, "content": content}}], "usage": usage}, events, ttft,
            {"input_sha256": hashlib.sha256(wire).hexdigest(), "raw_sse_sha256": hashlib.sha256(raw).hexdigest(), "raw_sse_b64": base64.b64encode(raw).decode("ascii"), "api_cached_tokens": cached, "api_cached_state": "reported" if cached is not None else "unreported"})

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

def sha256_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"R047 expected regular file is unavailable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()
