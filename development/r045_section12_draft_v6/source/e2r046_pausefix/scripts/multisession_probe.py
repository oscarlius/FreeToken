#!/usr/bin/env python3
"""Two-session streaming measurements backed by engine token acknowledgements.

The development stream contract is intentionally narrow.  When the server has
``FT_DEV_PAUSE_ENDPOINT=1``, a data-bearing OpenAI SSE chunk that represents a
completed engine output acknowledgement carries::

    {"ft_dev": {"schema": "ft_dev_stream/v1", "uid": 7,
                "request_seq": 23, "completion_tokens_delta": 1,
                "completion_tokens_cumulative": 12}}

The client measures the selected Qwen checkpoint's standard chat-template path.
Tokenizers selecting the separate DSV4 encoder are rejected before any request.
The client treats this as measurement evidence, not as a public API feature.
The OpenAI formatter emits one separate development event per sampled tokenizer
ACK. ``request_seq`` starts at one and each completion counter advances by one.
A repeated, skipped, zero, or changed acknowledgement is rejected rather than
estimating tokens from text fragments or SSE frame counts.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
from contextlib import contextmanager
import json
import math
import os
import socket
from pathlib import Path
import threading
import time
from typing import Any, Iterable
from urllib.parse import urlsplit


DEFAULT_BASE_URL = "http://127.0.0.1:8095/v1"
DEFAULT_MODEL = "Qwen3.8-Flash-Next-NVFP4"
DEFAULT_TOKENIZER = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
DEV_SCHEMA = "ft_dev_stream/v1"
DEFAULT_D0_BASE = "/tmp/ft_dev_d0"


class ProbeError(RuntimeError):
    """A measured request was not backed by the required evidence."""


def _finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ProbeError(f"{label} must be finite")
    return float(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ProbeError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProbeError(f"{label} must be a positive integer")
    return value


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def prompt_sha256(ids: list[int]) -> str:
    if not ids or any(type(token) is not int or token < 0 for token in ids):
        raise ProbeError("tokenizer must provide nonempty nonnegative integer IDs")
    payload = b"".join(int(token).to_bytes(4, "little", signed=True) for token in ids)
    return hashlib.sha256(payload).hexdigest()


def common_prefix_tokens(left: list[int], right: list[int]) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def load_tokenizer(path: str):
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:  # pragma: no cover - exercised on Linux measurement host
        raise ProbeError("transformers tokenizer is required to prove prompt token counts") from exc
    try:
        tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    except Exception as exc:  # pragma: no cover - depends on local model assets
        raise ProbeError(f"cannot load tokenizer evidence from {path}: {exc}") from exc
    return tokenizer


def frontend_ids(tokenizer: Any, messages: list[dict[str, str]]) -> list[int]:
    if not getattr(tokenizer, "chat_template", None):
        raise ProbeError("this probe requires the standard chat-template frontend; DSV4 rendering is outside this measurement")
    if not hasattr(tokenizer, "apply_chat_template"):
        raise ProbeError("tokenizer cannot prove frontend chat-template IDs")
    try:
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        if not isinstance(rendered, str):
            raise ProbeError("chat template did not return rendered text")
        ids = tokenizer.encode(rendered, add_special_tokens=False)
    except Exception as exc:
        raise ProbeError(f"cannot produce frontend token evidence: {exc}") from exc
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 for i in ids):
        raise ProbeError("tokenizer returned invalid frontend IDs")
    return ids


def make_messages(tokenizer: Any, context_tokens: int, seed: str) -> tuple[list[dict[str, str]], list[int]]:
    _positive_int(context_tokens, "context token target")
    # Distinct text starts directly after the chat template, before shared prose.
    prefix = f"{seed}\nUse this technical record to give a factual answer.\n"
    unit = "The scheduler records timings, counters, and identifiers. "
    def render(length: int) -> tuple[list[dict[str, str]], list[int]]:
        messages = [{"role": "user", "content": prefix + filler[:length]}]
        return messages, frontend_ids(tokenizer, messages)
    filler = ""
    base_messages, base_ids = render(0)
    if len(base_ids) > context_tokens:
        raise ProbeError("context target is smaller than the seeded frontend template")
    if len(base_ids) == context_tokens:
        return base_messages, base_ids
    repeats = 1
    while True:
        filler = unit * repeats
        messages, ids = render(len(filler))
        if len(ids) >= context_tokens:
            break
        repeats *= 2
        if repeats > context_tokens * 4:
            raise ProbeError("cannot construct the requested frontend context")
    low, high = 0, len(filler)
    while low <= high:
        middle = (low + high) // 2
        messages, ids = render(middle)
        if len(ids) == context_tokens:
            return messages, ids
        if len(ids) < context_tokens:
            low = middle + 1
        else:
            high = middle - 1
    # BPE merges can make the count locally non-monotonic.
    for length in range(max(0, low - 16), min(len(filler), low + 16) + 1):
        messages, ids = render(length)
        if len(ids) == context_tokens:
            return messages, ids
    raise ProbeError("tokenizer cannot construct the exact requested frontend token count")


class RequestControl:
    """Own a request socket so deadline/failure cancellation interrupts reads."""
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self._lock = threading.Lock()
        self._socket: socket.socket | None = None
        self.reason = "request cancelled"

    def bind(self, connection_socket: socket.socket) -> None:
        with self._lock:
            self._socket = connection_socket
            cancelled = self.cancelled.is_set()
        if cancelled:
            self.cancel(self.reason)
            self.check()

    def cancel(self, reason: str = "request cancelled") -> None:
        with self._lock:
            if not self.cancelled.is_set():
                self.reason = reason
            self.cancelled.set()
            connection_socket = self._socket
        if connection_socket is not None:
            try:
                connection_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection_socket.close()
            except OSError:
                pass

    def check(self) -> None:
        if self.cancelled.is_set():
            raise ProbeError(self.reason)


@contextmanager
def _open_response(url: str, body: bytes, timeout: float, control: RequestControl):
    timeout = _finite(timeout, "timeout")
    if timeout <= 0:
        raise ProbeError("timeout must be positive")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None:
        raise ProbeError("base URL must be an HTTP(S) URL without credentials")
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
    response = None
    timer = threading.Timer(timeout, control.cancel, args=("total request timeout",))
    timer.name = "probe-request-deadline"
    control.check()
    timer.start()
    try:
        connection.connect()
        if connection.sock is None:
            raise ProbeError("HTTP connection has no socket")
        control.bind(connection.sock)
        control.check()
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        connection.request("POST", target, body=body,
                           headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
        response = connection.getresponse()
        control.check()
        if response.status != 200:
            raise ProbeError(f"HTTP endpoint returned {response.status}")
        yield response
        control.check()
    except ProbeError as exc:
        if control.cancelled.is_set():
            raise ProbeError(control.reason) from exc
        raise
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        if control.cancelled.is_set():
            raise ProbeError(control.reason) from exc
        raise ProbeError(f"stream request failed: {exc}") from exc
    finally:
        timer.cancel()
        timer.join(timeout=0.5)
        if response is not None:
            response.close()
        connection.close()


def _cancel_join(controls: list[RequestControl], threads: list[threading.Thread]) -> None:
    for control in controls:
        control.cancel()
    deadline = time.perf_counter() + 2.0
    for thread in threads:
        thread.join(timeout=max(0.0, deadline - time.perf_counter()))
    if any(thread.is_alive() for thread in threads):
        raise ProbeError("request worker did not stop after socket cancellation")


def _sse_events(response: Any) -> Iterable[dict[str, Any] | str]:
    for raw in response:
        line = raw.decode("utf-8", errors="strict").strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            yield "[DONE]"
            return
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProbeError("invalid SSE JSON") from exc
        if not isinstance(event, dict):
            raise ProbeError("SSE payload must be an object")
        yield event
    raise ProbeError("stream ended without [DONE]")


def _ack(
    event: dict[str, Any],
    previous: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int, bool]:
    dev = event.get("ft_dev")
    if not isinstance(dev, dict) or dev.get("schema") != DEV_SCHEMA:
        raise ProbeError("missing ft_dev completion acknowledgement")
    uid = dev.get("uid")
    if type(uid) is not int or uid < 0:
        raise ProbeError("invalid or changing ft_dev uid")
    sequence = dev.get("request_seq")
    _positive_int(sequence, "request_seq")
    delta = dev.get("completion_tokens_delta")
    cumulative = dev.get("completion_tokens_cumulative")
    if type(delta) is not int or delta != 1:
        raise ProbeError("completion_tokens_delta must equal one sampled token")
    if type(cumulative) is not int or cumulative <= 0:
        raise ProbeError("completion_tokens_cumulative must be positive")
    if previous is not None and (uid != previous[0] or sequence != previous[1] + 1):
        raise ProbeError("invalid or changing ft_dev uid/request_seq")
    if previous is not None and cumulative != previous[2] + 1:
        raise ProbeError("non-contiguous completion token acknowledgement")
    if previous is None and (sequence != 1 or cumulative != 1):
        raise ProbeError("first completion acknowledgement must be sequence one")
    return uid, sequence, delta, cumulative, False


def _has_content(event: dict[str, Any]) -> bool:
    for choice in event.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        if isinstance(delta, dict) and isinstance(delta.get("content"), str) and delta["content"]:
            return True
    return False


def stream_request(
    *,
    base_url: str,
    model: str,
    timeout: float,
    messages: list[dict[str, str]],
    max_tokens: int,
    start: threading.Event | None = None,
    clock_origin: float | None = None,
    wall_anchor: float | None = None,
    on_first_real: Any | None = None,
    control: RequestControl | None = None,
) -> dict[str, Any]:
    _positive_int(max_tokens, "max_tokens")
    control = control or RequestControl()
    if start is not None:
        start.wait()
    if wall_anchor is None:
        wall_anchor = time.time()
    t0 = time.perf_counter()
    if clock_origin is None:
        clock_origin = t0
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    t0 = time.perf_counter()

    acknowledgement: tuple[int, int, int, int] | None = None
    first_real: float | None = None
    last_token: float | None = None
    events: list[dict[str, Any]] = []
    usage: dict[str, Any] | None = None
    done = False
    with _open_response(url, body, timeout, control) as response:
        for event in _sse_events(response):
            control.check()
            now = time.perf_counter()
            if event == "[DONE]":
                done = True
                break
            assert isinstance(event, dict)
            if "error" in event:
                raise ProbeError(f"server stream error: {event['error']}")
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            if "ft_dev" in event:
                uid, sequence, delta, cumulative, duplicate = _ack(event, acknowledgement)
                acknowledgement = (uid, sequence, cumulative, delta)
                if not duplicate:
                    last_token = now
                    events.append({
                        "t_s": now - clock_origin,
                        "completion_tokens_delta": delta,
                        "completion_tokens_cumulative": cumulative,
                        "uid": uid,
                        "request_seq": sequence,
                    })
            if _has_content(event):
                if acknowledgement is None:
                    raise ProbeError("content arrived before a validated completion acknowledgement")
                if first_real is None:
                    first_real = now
                    if on_first_real is not None:
                        on_first_real(acknowledgement[0])
    if not done:
        raise ProbeError("stream missing [DONE]")
    if acknowledgement is None or first_real is None or last_token is None:
        raise ProbeError("stream lacked content-bearing acknowledged completion tokens")
    uid, _sequence, cumulative, _delta = acknowledgement
    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
        if usage["completion_tokens"] != cumulative:
            raise ProbeError("usage completion_tokens disagrees with ft_dev acknowledgements")
    return {
        "uid": uid,
        "t_anchor_unix_s": wall_anchor,
        "t_start_s": t0 - clock_origin,
        "ttft_s": first_real - t0,
        "t_first_s": first_real - clock_origin,
        "t_last_s": last_token - clock_origin,
        "completion_tokens": cumulative,
        "token_events": events,
        "usage": usage,
    }


def decode_tps(record: dict[str, Any]) -> float | None:
    first = _finite(record["t_first_s"], "t_first_s")
    last = _finite(record["t_last_s"], "t_last_s")
    tokens = _positive_int(record["completion_tokens"], "completion_tokens")
    if tokens < 2 or last <= first:
        return None
    return (tokens - 1) / (last - first)


def prompt_new_tokens(record: dict[str, Any]) -> int | None:
    usage = record.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if type(prompt) is not int or prompt < 0 or type(cached) is not int or cached < 0 or cached > prompt:
        return None
    return prompt - cached


def common_window(records: list[dict[str, Any]]) -> tuple[float, int, float | None]:
    if len(records) != 2:
        raise ProbeError("common window requires exactly two ways")
    start = max(_finite(row["t_first_s"], "t_first_s") for row in records)
    end = min(_finite(row["t_last_s"], "t_last_s") for row in records)
    if end <= start:
        return 0.0, 0, None
    total = 0
    for row in records:
        for event in row["token_events"]:
            timestamp = _finite(event["t_s"], "token timestamp")
            if start < timestamp <= end:
                total += _positive_int(event["completion_tokens_delta"], "token delta")
    duration = end - start
    return duration, total, total / duration


def _per_way(record: dict[str, Any], token_path: Path) -> dict[str, Any]:
    return {
        "uid": record["uid"],
        "ttft_s": record["ttft_s"],
        "decode_tps": decode_tps(record),
        "completion_tokens": record["completion_tokens"],
        "t_first": record["t_first_s"],
        "t_last": record["t_last_s"],
        "token_timestamps": str(token_path),
        "wall_anchor_unix_s": record["t_anchor_unix_s"],
    }


def _run_parallel(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(calls) != 2:
        raise ProbeError("parallel measurement requires two requests")
    ready = threading.Event()
    clock_origin = time.perf_counter()
    wall_anchor = time.time()
    outcomes: list[dict[str, Any] | BaseException | None] = [None, None]
    controls = [RequestControl(), RequestControl()]

    def worker(index: int) -> None:
        try:
            outcomes[index] = stream_request(
                start=ready, clock_origin=clock_origin, wall_anchor=wall_anchor,
                control=controls[index], **calls[index],
            )
        except BaseException as exc:
            outcomes[index] = exc
            controls[1 - index].cancel("sibling stream failed")

    threads = [threading.Thread(target=worker, args=(index,), name=f"probe-way-{index}") for index in range(2)]
    try:
        for thread in threads:
            thread.start()
        ready.set()
        deadline = time.perf_counter() + max(_finite(call["timeout"], "timeout") for call in calls) + 1.0
        for thread in threads:
            thread.join(timeout=max(0.0, deadline - time.perf_counter()))
    finally:
        _cancel_join(controls, [thread for thread in threads if thread.ident is not None])
    errors = [value for value in outcomes if isinstance(value, BaseException)]
    if errors:
        raise ProbeError("parallel stream failed: " + "; ".join(map(str, errors)))
    if any(not isinstance(value, dict) for value in outcomes):
        raise ProbeError("parallel stream returned no record")
    return list(outcomes)


def run_two_decode(args: argparse.Namespace) -> dict[str, Any]:
    tokenizer = load_tokenizer(args.tokenizer_path)
    per_rep = []
    for rep in range(args.reps):
        left, left_ids = make_messages(tokenizer, args.ctx, f"left-{rep}")
        if args.same_prompt:
            right, right_ids = left, left_ids
        else:
            right, right_ids = make_messages(tokenizer, args.ctx, f"right-{rep}")
        rows = _run_parallel([
            {"base_url": args.base_url, "model": args.model, "timeout": args.timeout, "messages": left, "max_tokens": args.max_tokens},
            {"base_url": args.base_url, "model": args.model, "timeout": args.timeout, "messages": right, "max_tokens": args.max_tokens},
        ])
        window_s, window_tokens, window_tps = common_window(rows)
        per_rep.append({
            "rep": rep,
            "_records": rows,
            "common_window_s": window_s,
            "common_window_tokens": window_tokens,
            "common_window_tps": window_tps,
            "prompt_sha256": [prompt_sha256(left_ids), prompt_sha256(right_ids)],
            "frontend_overlap_tokens": common_prefix_tokens(left_ids, right_ids),
            "frontend_token_counts": [len(left_ids), len(right_ids)],
        })
    return {"schema": "multisession_probe/v1", "command": "two-decode", "same_prompt": bool(args.same_prompt), "reps": per_rep}


def _trace_messages(path: Path, round_index: int) -> list[dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError(f"invalid trace: {exc}") from exc
    rows = value.get("rounds") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not (0 <= round_index < len(rows)):
        raise ProbeError("trace round is unavailable")
    row = rows[round_index]
    messages = row.get("messages") if isinstance(row, dict) else None
    if not isinstance(messages, list) or not messages:
        raise ProbeError("trace round lacks messages")
    if any(not isinstance(message, dict) or not isinstance(message.get("role"), str) or not isinstance(message.get("content"), str) for message in messages):
        raise ProbeError("trace messages are malformed")
    return messages


def _dev_pause(base_url: str, seconds: float, timeout: float,
               control: RequestControl | None = None) -> dict[str, Any]:
    seconds = _finite(seconds, "pause seconds")
    timeout = _finite(timeout, "timeout")
    if timeout <= 0:
        raise ProbeError("timeout must be positive")
    if seconds <= 0:
        raise ProbeError("pause seconds must be positive")
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    sent = time.time()
    with _open_response(root + "/dev/pause",
                        json.dumps({"seconds": seconds, "timeout": min(timeout, 10.0)}).encode("utf-8"),
                        timeout, control or RequestControl()) as response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ProbeError("pause response exceeds 64 KiB")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ProbeError("invalid pause acknowledgement") from exc
        if not isinstance(value, dict) or value.get("status") != "accepted":
            raise ProbeError("pause endpoint did not acknowledge scheduler acceptance")
        for key in ("accepted_wallclock_s", "pause_started_wallclock_s", "deadline_wallclock_s"):
            _finite(value.get(key), key)
        if value["deadline_wallclock_s"] <= value["pause_started_wallclock_s"]:
            raise ProbeError("pause endpoint reported an invalid idle interval")
        duration = value["deadline_wallclock_s"] - value["pause_started_wallclock_s"]
        if not math.isclose(duration, seconds, rel_tol=1e-6, abs_tol=1e-4):
            raise ProbeError("pause endpoint did not acknowledge the requested full idle duration")
        return {"client_sent_wallclock_s": sent, "client_ack_wallclock_s": time.time(), "response": value}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ProbeError(f"D0 evidence file is missing: {path}")
    if path.stat().st_size > 512 * 1024 * 1024:
        raise ProbeError(f"D0 evidence exceeds the 512 MiB reader bound: {path}")
    rows = []
    with path.open("rb") as stream:
        for _ in range(200001):
            line = stream.readline(2 * 1024 * 1024 + 1)
            if not line:
                return rows
            if len(line) > 2 * 1024 * 1024 or len(rows) == 200000:
                raise ProbeError(f"D0 evidence exceeds the row/line reader bound: {path}")
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise ProbeError(f"invalid or unfinished D0 JSONL: {path}") from exc
            if not isinstance(value, dict):
                raise ProbeError(f"invalid D0 row: {path}")
            rows.append(value)
    raise ProbeError(f"D0 evidence exceeds the reader bound: {path}")


def d0_evidence() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    base = os.environ.get("FT_DEV_D0_PATH", DEFAULT_D0_BASE)
    return (
        _jsonl(Path(base + "_prefill.jsonl")),
        _jsonl(Path(base + "_decode_steps.jsonl")),
        _jsonl(Path(base + "_decode_timeline.jsonl")),
        base,
    )


def _prefill_rows(rows: list[dict[str, Any]], uid: int) -> list[dict[str, Any]]:
    return [row for row in rows if isinstance(row.get("reqs"), list)
            and any(isinstance(req, dict) and req.get("rid") == uid for req in row["reqs"])]


def _prefill_for_uid(rows: list[dict[str, Any]], uid: int) -> dict[str, Any] | None:
    matches = _prefill_rows(rows, uid)
    if not matches:
        return None
    starts = [_finite(row.get("t_start"), "prefill t_start") for row in matches]
    ends = [_finite(row.get("t_end"), "prefill t_end") for row in matches]
    if any(end <= start for start, end in zip(starts, ends)):
        raise ProbeError("D0 prefill chunk has an invalid interval")
    return {"uid": uid, "t_start": min(starts), "t_end": max(ends),
            "chunks": len(matches), "rows": matches}


def pair_batch_evidence(left_uid: int, right_uid: int) -> tuple[bool | None, str | None]:
    try:
        base = os.environ.get("FT_DEV_D0_PATH", DEFAULT_D0_BASE)
        prefill = _jsonl(Path(base + "_prefill.jsonl"))
    except ProbeError as exc:
        return None, str(exc)
    left = _prefill_rows(prefill, left_uid)
    right = _prefill_rows(prefill, right_uid)
    if not left or not right:
        return None, "D0 prefill reqs do not bind both stream UIDs"
    return any(a is b for a in left for b in right), None


def _counter(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if type(value) is not int or value < 0:
        raise ProbeError(f"D0 step lacks a nonnegative integer {key}")
    return value


def h_steps(uid: int, event_end_wallclock_s: float, horizons: list[int],
            event_start_wallclock_s: float | None = None) -> dict[str, Any]:
    try:
        _prefill, steps, timeline, base = d0_evidence()
        end = _finite(event_end_wallclock_s, "event end")
        timeline_by_step = {}
        for row in timeline:
            step = _nonnegative_int(row.get("step"), "timeline step")
            if step in timeline_by_step:
                raise ProbeError("duplicate D0 timeline step")
            timeline_by_step[step] = row
        bound = [row for row in steps if uid in (row.get("rids") or [])]
        bound.sort(key=lambda row: _nonnegative_int(row.get("step"), "decode step"))
        if len({row["step"] for row in bound}) != len(bound):
            raise ProbeError("duplicate UID-bound D0 decode step")
        for row in bound:
            _finite(row.get("t"), "decode step timestamp")
        rows = [row for row in bound if row["t"] >= end]
        result: dict[str, Any] = {"d0_base": base, "uid": uid,
                                 "event_end_wallclock_s": end, "H": {}}
        for horizon in horizons:
            selected = rows[:horizon]
            if len(selected) != horizon:
                result["H"][str(horizon)] = {"value": None, "nullreason": "insufficient UID-bound D0 decode steps"}
                continue
            timing_rows = [timeline_by_step.get(row["step"]) for row in selected]
            if any(row is None or uid not in (row.get("rids") or [])
                   or type(row.get("step_ms")) not in (int, float)
                   or not math.isfinite(row["step_ms"]) or row["step_ms"] < 0
                   for row in timing_rows):
                result["H"][str(horizon)] = {"value": None, "nullreason": "D0 timeline lacks step_ms for UID-bound steps"}
                continue
            if any(not math.isclose(_finite(timing["t"], "timeline t"), row["t"], abs_tol=1e-6)
                   for row, timing in zip(selected, timing_rows)):
                raise ProbeError("D0 timing and counter step timestamps disagree")
            result["H"][str(horizon)] = {
                "value": sum(row["step_ms"] for row in timing_rows),
                "steps": [row["step"] for row in selected],
                "post_event_h2d_bytes": sum(_counter(row, "h2d_bytes") for row in selected),
                "post_event_miss_total": sum(_counter(row, "missing_total") for row in selected),
            }
        if event_start_wallclock_s is None:
            result["event_counters"] = {"value": None, "nullreason": "event start is unavailable"}
        else:
            start = _finite(event_start_wallclock_s, "event start")
            if start > end:
                raise ProbeError("event starts after it ends")
            result["event_start_wallclock_s"] = start
            # A zero requires observed steps on both sides, not an absent log.
            if not any(row["t"] < start for row in bound) or not rows:
                result["event_counters"] = {"value": None, "nullreason": "D0 does not bracket the event window"}
            else:
                event_rows = [row for row in bound if start <= row["t"] < end]
                result["event_counters"] = {
                    "window_rule": "decode step begins in [event_start,event_end)",
                    "steps": [row["step"] for row in event_rows],
                    "h2d_bytes": sum(_counter(row, "h2d_bytes") for row in event_rows),
                    "miss_total": sum(_counter(row, "missing_total") for row in event_rows),
                }
        return result
    except ProbeError as exc:
        return {"nullreason": str(exc)}


def run_pair_short(args: argparse.Namespace) -> dict[str, Any]:
    rounds = [int(item) for item in args.rounds.split(",")]
    if len(rounds) != 2 or rounds[0] == rounds[1]:
        raise ProbeError("--rounds must name two distinct indices")
    messages = [_trace_messages(args.trace, item) for item in rounds]
    values = []
    for _ in range(args.reps):
        rows = _run_parallel([
            {"base_url": args.base_url, "model": args.model, "timeout": args.timeout, "messages": messages[0], "max_tokens": 200},
            {"base_url": args.base_url, "model": args.model, "timeout": args.timeout, "messages": messages[1], "max_tokens": 200},
        ])
        same_batch, nullreason = pair_batch_evidence(rows[0]["uid"], rows[1]["uid"])
        values.append({
            "ttft_s": [row["ttft_s"] for row in rows],
            "submit_skew_s": abs(rows[0]["t_start_s"] - rows[1]["t_start_s"]),
            "same_prefill_batch": same_batch,
            "same_prefill_batch_nullreason": nullreason,
            "requests": rows,
        })
    return {
        "schema": "multisession_probe/v1", "command": "pair-short", "rounds": rounds,
        "reps": values,
    }


def run_stall(args: argparse.Namespace) -> dict[str, Any]:
    tokenizer = load_tokenizer(args.tokenizer_path)
    delay = _finite(args.delay, "stall delay")
    if delay < 0:
        raise ProbeError("stall delay cannot be negative")
    if args.prefill_kind == "agent_turn" and (args.trace is None or args.round is None):
        raise ProbeError("agent_turn requires --trace and --round")
    if args.prefill_kind == "cold32k" and args.prefill_target is None:
        raise ProbeError("cold32k requires --prefill-target")
    values = []
    for rep in range(args.reps):
        seed = f"stall-{time.time_ns()}-{rep}"
        decode_messages, decode_ids = make_messages(tokenizer, args.decode_ctx, seed + "-decode")
        if args.prefill_kind == "agent_turn":
            prefill_messages = _trace_messages(args.trace, args.round)
            prefill_ids = frontend_ids(tokenizer, prefill_messages)
        else:
            prefill_messages, prefill_ids = make_messages(tokenizer, args.prefill_target, seed + "-prefill")
        outcome: list[dict[str, Any] | BaseException | None] = [None]
        decode_real, decode_done = threading.Event(), threading.Event()
        controls = [RequestControl(), RequestControl()]
        clock_origin, wall_anchor = time.perf_counter(), time.time()

        def decode_worker() -> None:
            try:
                outcome[0] = stream_request(
                    base_url=args.base_url, model=args.model, timeout=args.timeout,
                    messages=decode_messages, max_tokens=args.decode_max_tokens,
                    on_first_real=lambda _uid: decode_real.set(), clock_origin=clock_origin,
                    wall_anchor=wall_anchor, control=controls[0],
                )
            except BaseException as exc:
                outcome[0] = exc
                controls[1].cancel("decode stream failed")
            finally:
                decode_done.set()

        thread = threading.Thread(target=decode_worker, name="probe-stall-decode")
        try:
            thread.start()
            deadline = time.perf_counter() + args.timeout
            while not decode_real.wait(0.01):
                if decode_done.is_set() or time.perf_counter() >= deadline:
                    raise ProbeError(f"decode did not reach first content: {outcome[0]}")
            if decode_done.wait(delay):
                raise ProbeError("decode ended before the interference request")
            prefill = stream_request(
                base_url=args.base_url, model=args.model, timeout=args.timeout,
                messages=prefill_messages, max_tokens=1, clock_origin=clock_origin,
                wall_anchor=wall_anchor, control=controls[1],
            )
            thread.join(timeout=max(0.0, deadline - time.perf_counter()) + 1.0)
        finally:
            _cancel_join(controls, [thread] if thread.ident is not None else [])
        if isinstance(outcome[0], BaseException):
            raise ProbeError(f"decode stream failed: {outcome[0]}")
        if not isinstance(outcome[0], dict):
            raise ProbeError("decode stream returned no record")
        decode = outcome[0]
        timestamps = [event["t_s"] for event in decode["token_events"]]
        interval_start, interval_end = prefill["t_start_s"], prefill["t_first_s"]
        if decode["t_first_s"] > interval_start or decode["t_last_s"] < interval_end:
            raise ProbeError("decode stream did not cover the full interference interval")
        gaps = [right - left for left, right in zip(timestamps, timestamps[1:])
                if left < interval_end and right > interval_start]
        decoded = sum(event["completion_tokens_delta"] for event in decode["token_events"]
                      if interval_start < event["t_s"] <= interval_end)
        duration = interval_end - interval_start
        values.append({
            "max_gap_s": max((right - left for left, right in zip(timestamps, timestamps[1:])), default=None),
            "max_gap_during_interference_s": max(gaps) if gaps else None,
            "interference_tps": decoded / duration if duration > 0 else None,
            "prefill_ttft_s": prefill["ttft_s"],
            "prefill_new_tokens": prompt_new_tokens(prefill),
            "prefill_new_tokens_nullreason": None if prompt_new_tokens(prefill) is not None else "stream usage lacks prompt/cache token evidence",
            "decode": decode, "prefill": prefill,
            "prompt_sha256": [prompt_sha256(decode_ids), prompt_sha256(prefill_ids)],
            "frontend_token_counts": [len(decode_ids), len(prefill_ids)],
        })
    return {"schema": "multisession_probe/v1", "command": "stall", "reps": values}


def _wait_decode_steps(uid: int, count: int, timeout: float, control: RequestControl) -> None:
    """Apply the same observed decode-step warmup before each H1 event."""
    base = os.environ.get("FT_DEV_D0_PATH", DEFAULT_D0_BASE)
    deadline = time.perf_counter() + timeout
    last_error: ProbeError | None = None
    while time.perf_counter() < deadline:
        control.check()
        try:
            rows = _jsonl(Path(base + "_decode_steps.jsonl"))
            observed = [row for row in rows if uid in (row.get("rids") or [])]
            if len(observed) >= count:
                return
        except ProbeError as exc:
            last_error = exc
        control.cancelled.wait(0.01)
    raise ProbeError(f"H1 decode warmup lacks {count} UID-bound D0 steps: {last_error}")


def run_h1(args: argparse.Namespace) -> dict[str, Any]:
    tokenizer = load_tokenizer(args.tokenizer_path)
    horizons = [int(item) for item in args.H.split(",")]
    if not horizons or len(set(horizons)) != len(horizons) or any(item not in (1, 8, 32) for item in horizons):
        raise ProbeError("--H must be a comma-separated subset of 1,8,32")
    decode_messages, decode_ids = make_messages(tokenizer, min(4000, args.prefill_target), "h1-decode")

    def condition(kind: str, prefill_messages: list[dict[str, str]],
                  idle_seconds: float | None = None) -> dict[str, Any]:
        action_done = threading.Event()
        marker: dict[str, Any] = {}
        action_errors: list[BaseException] = []
        controls = [RequestControl(), RequestControl()]
        action_thread: list[threading.Thread] = []
        clock_origin, wall_anchor = time.perf_counter(), time.time()

        def action(decode_uid: int) -> None:
            try:
                _wait_decode_steps(decode_uid, 8, args.timeout, controls[1])
                if kind == "idle":
                    marker["pause"] = _dev_pause(args.base_url, idle_seconds, args.timeout, control=controls[1])
                    reply = marker["pause"]["response"]
                    marker["event_start_wallclock_s"] = reply["pause_started_wallclock_s"]
                    marker["event_end_wallclock_s"] = reply["deadline_wallclock_s"]
                elif kind == "prefill":
                    record = stream_request(base_url=args.base_url, model=args.model, timeout=args.timeout,
                                            messages=prefill_messages, max_tokens=1, control=controls[1],
                                            clock_origin=clock_origin, wall_anchor=wall_anchor)
                    marker["prefill"] = record
                    prefill, _steps, _timeline, _base = d0_evidence()
                    bound = _prefill_for_uid(prefill, record["uid"])
                    if bound is None:
                        raise ProbeError("prefill stream lacks D0 chunk/UID binding")
                    marker["prefill_d0"] = bound
                    marker["event_start_wallclock_s"] = bound["t_start"]
                    marker["event_end_wallclock_s"] = bound["t_end"]
                else:
                    marker["event_start_wallclock_s"] = time.time()
                    marker["event_end_wallclock_s"] = marker["event_start_wallclock_s"]
            except BaseException as exc:
                action_errors.append(exc)
                controls[0].cancel("H1 event action failed")
            finally:
                action_done.set()

        def first_real(uid: int) -> None:
            thread = threading.Thread(target=action, args=(uid,), name="probe-h1-event")
            action_thread.append(thread)
            thread.start()

        try:
            decode = stream_request(
                base_url=args.base_url, model=args.model, timeout=args.timeout,
                messages=decode_messages, max_tokens=512, on_first_real=first_real,
                control=controls[0], clock_origin=clock_origin, wall_anchor=wall_anchor,
            )
            if not action_done.is_set():
                raise ProbeError("decode ended before the H1 event completed")
            for thread in action_thread:
                thread.join(timeout=1.0)
        except ProbeError as exc:
            if action_errors:
                raise ProbeError(f"H1 event action failed: {action_errors[0]}") from exc
            raise
        finally:
            _cancel_join(controls, action_thread)
        if action_errors:
            raise ProbeError(f"H1 event action failed: {action_errors[0]}")
        duration = marker["event_end_wallclock_s"] - marker["event_start_wallclock_s"]
        if kind != "none" and duration <= 0:
            raise ProbeError("H1 event interval is empty")
        evidence = h_steps(decode["uid"], marker["event_end_wallclock_s"], horizons,
                           event_start_wallclock_s=marker["event_start_wallclock_s"])
        if "nullreason" in evidence or any(evidence.get("H", {}).get(str(h), {}).get("value") is None for h in horizons):
            raise ProbeError(f"H1 lacks required post-event timing evidence: {evidence}")
        if "nullreason" in evidence["event_counters"]:
            raise ProbeError(f"H1 lacks event-period counter evidence: {evidence['event_counters']}")
        return {"decode_uid": decode["uid"], "decode": decode, "event": marker,
                "event_duration_s": duration, "evidence": evidence}

    rows = []
    for rep in range(args.reps):
        prefill_messages, prefill_ids = make_messages(tokenizer, args.prefill_target,
                                                      f"h1-prefill-{time.time_ns()}-{rep}")
        # Measure the real event first; each idle control uses that repetition's duration.
        prefill = condition("prefill", prefill_messages)
        idle = condition("idle", prefill_messages, prefill["event_duration_s"])
        none = condition("none", prefill_messages)
        if not math.isclose(idle["event_duration_s"], prefill["event_duration_s"], rel_tol=1e-6, abs_tol=1e-4):
            raise ProbeError("H1 idle and real prefill durations differ")
        prefill_counters, idle_counters = prefill["evidence"]["event_counters"], idle["evidence"]["event_counters"]
        rows.append({
            "execution_order": ["prefill", "idle", "none"],
            "none": none, "idle": idle, "prefill": prefill,
            "delta_H": {str(h): prefill["evidence"]["H"][str(h)]["value"] - idle["evidence"]["H"][str(h)]["value"] for h in horizons},
            "event_extra_h2d_bytes": prefill_counters["h2d_bytes"] - idle_counters["h2d_bytes"],
            "event_extra_miss_total": prefill_counters["miss_total"] - idle_counters["miss_total"],
            "prompt_sha256": [prompt_sha256(decode_ids), prompt_sha256(prefill_ids)],
            "frontend_token_counts": [len(decode_ids), len(prefill_ids)],
        })
    return {"schema": "multisession_probe/v1", "command": "h1", "H": horizons, "reps": rows}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", default=DEFAULT_BASE_URL)
    common.add_argument("--model", default=DEFAULT_MODEL)
    common.add_argument("--timeout", type=float, default=1800.0)
    common.add_argument("--tokenizer-path", default=DEFAULT_TOKENIZER)
    sub = parser.add_subparsers(dest="command", required=True)

    two = sub.add_parser("two-decode", parents=[common])
    two.add_argument("--ctx", type=int, required=True)
    two.add_argument("--max-tokens", type=int, required=True)
    two.add_argument("--same-prompt", type=int, choices=(0, 1), required=True)
    two.add_argument("--reps", type=int, required=True)
    two.add_argument("--out", type=Path, required=True)
    two.set_defaults(handler=run_two_decode)

    stall = sub.add_parser("stall", parents=[common])
    stall.add_argument("--decode-ctx", type=int, required=True)
    stall.add_argument("--decode-max-tokens", type=int, required=True)
    stall.add_argument("--prefill-kind", choices=("cold32k", "agent_turn"), required=True)
    stall.add_argument("--prefill-target", type=int)
    stall.add_argument("--trace", type=Path)
    stall.add_argument("--round", type=int)
    stall.add_argument("--delay", type=float, required=True)
    stall.add_argument("--reps", type=int, required=True)
    stall.add_argument("--out", type=Path, required=True)
    stall.set_defaults(handler=run_stall)

    pair = sub.add_parser("pair-short", parents=[common])
    pair.add_argument("--trace", type=Path, required=True)
    pair.add_argument("--rounds", required=True)
    pair.add_argument("--reps", type=int, required=True)
    pair.add_argument("--out", type=Path, required=True)
    pair.set_defaults(handler=run_pair_short)

    h1 = sub.add_parser("h1", parents=[common])
    h1.add_argument("--H", required=True)
    h1.add_argument("--reps", type=int, required=True)
    h1.add_argument("--prefill-target", type=int, required=True)
    h1.add_argument("--out", type=Path, required=True)
    h1.set_defaults(handler=run_h1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.out.exists():
        return 2
    try:
        _positive_int(args.reps, "reps")
        if _finite(args.timeout, "timeout") <= 0:
            raise ProbeError("timeout must be positive")
        result = args.handler(args)
        if args.command == "two-decode":
            for rep in result["reps"]:
                records = rep.pop("_records")
                per_way = []
                for index, row in enumerate(records):
                    sidecar = args.out.with_name(f"{args.out.stem}.rep{rep['rep']}.way{index}.tokens.json")
                    write_exclusive(sidecar, {"uid": row["uid"], "token_events": row["token_events"]})
                    per_way.append(_per_way(row, sidecar))
                rep["per_way"] = per_way
        write_exclusive(args.out, result)
        return 0
    except (ProbeError, ValueError, OSError) as exc:
        failure = {"schema": "multisession_probe/v1", "state": "error", "error": str(exc)}
        try:
            write_exclusive(args.out, failure)
        except OSError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
