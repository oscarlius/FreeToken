"""Fixed-count HTTP/SSE benchmark client for layer-major prefill arms."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CONNECT_TIMEOUT_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 300
MAX_DEADLINE_REQUEST_SECONDS = 60
MAX_TOKENS = 128
_SAFE_LABEL = re.compile(r"[^A-Za-z0-9_.-]+")


class BenchmarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class SSEOutcome:
    text: str
    finish_reason: str | None
    usage: dict
    ttft_seconds: float | None


def _json_line(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n")


def _sse_path(output_path: str | Path, label: str) -> tuple[Path, Path]:
    root = Path(output_path)
    root.mkdir(parents=True, exist_ok=True)
    safe_label = _SAFE_LABEL.sub("_", label)
    return root / "receipts.jsonl", root / f"{safe_label}.sse"


def _request_timeout(deadline_unix: float | None, label: str) -> float:
    if deadline_unix is None:
        return REQUEST_TIMEOUT_SECONDS
    remaining = deadline_unix - time.time()
    if remaining <= 0:
        raise BenchmarkError(f"{label}: measurement deadline has expired")
    return min(MAX_DEADLINE_REQUEST_SECONDS, remaining)


def _parse_sse(lines: Iterable[bytes], raw_handle, started: float) -> SSEOutcome:
    text_parts: list[str] = []
    finish_reason: str | None = None
    usage: dict | None = None
    ttft_seconds: float | None = None
    data_lines: list[str] = []

    def consume() -> None:
        nonlocal finish_reason, usage, ttft_seconds
        if not data_lines:
            return
        payload = "\n".join(data_lines)
        data_lines.clear()
        if payload == "[DONE]":
            return
        try:
            event = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"invalid SSE JSON: {exc}") from exc
        event_usage = event.get("usage")
        if event_usage is not None:
            if not isinstance(event_usage, dict):
                raise BenchmarkError("SSE usage is not an object")
            usage = event_usage
        choices = event.get("choices", [])
        if not isinstance(choices, list):
            raise BenchmarkError("SSE choices is not a list")
        for choice in choices:
            if not isinstance(choice, dict) or "text" not in choice:
                raise BenchmarkError("SSE choice is not a completion event")
            content = choice["text"]
            if not isinstance(content, str):
                raise BenchmarkError("SSE completion text is not text")
            if content:
                if ttft_seconds is None:
                    ttft_seconds = time.monotonic() - started
                text_parts.append(content)
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]

    for raw_line in lines:
        raw_handle.write(raw_line)
        try:
            line = raw_line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError as exc:
            raise BenchmarkError(f"non-UTF8 SSE line: {exc}") from exc
        if not line:
            consume()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    consume()
    if usage is None:
        raise BenchmarkError("stream ended without usage")
    if finish_reason is None:
        raise BenchmarkError("stream ended without finish_reason")
    return SSEOutcome("".join(text_parts), finish_reason, usage, ttft_seconds)


def _api_cached_tokens(usage: dict, label: str) -> int | None:
    details = usage.get("prompt_tokens_details")
    if details is None:
        return None
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if not isinstance(cached, int):
        raise BenchmarkError(f"{label}: malformed usage.prompt_tokens_details.cached_tokens")
    return cached


def _native_terminal(native_dir: str | Path, started_unix_ns: int, label: str) -> dict:
    root = Path(native_dir)
    paths = sorted(root.glob("native_ids_*.jsonl"))
    if not paths:
        raise BenchmarkError(f"{label}: no native_ids_*.jsonl in {root}")
    matches = []
    try:
        for path in paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if isinstance(record, dict) and record.get("finished_unix_ns", -1) >= started_unix_ns:
                    matches.append(record)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise BenchmarkError(f"{label}: unreadable native observer record: {exc}") from exc
    if len(matches) != 1:
        raise BenchmarkError(f"{label}: expected one native terminal record, found {len(matches)}")
    record = matches[0]
    required = (
        "uid", "finished_unix_ns", "native_token_ids", "prompt_tokens",
        "cached_tokens", "pid", "finish_reason",
    )
    if any(key not in record for key in required):
        raise BenchmarkError(f"{label}: native terminal record lacks required fields")
    if not all(isinstance(record[key], int) for key in ("uid", "finished_unix_ns", "pid")):
        raise BenchmarkError(f"{label}: native terminal uid/timestamp/pid is invalid")
    if not isinstance(record["native_token_ids"], list) or len(record["native_token_ids"]) != MAX_TOKENS:
        raise BenchmarkError(f"{label}: native terminal token ID length is not {MAX_TOKENS}")
    if not all(isinstance(token, int) for token in record["native_token_ids"]):
        raise BenchmarkError(f"{label}: native terminal token IDs are invalid")
    if not isinstance(record["prompt_tokens"], int) or not isinstance(record["cached_tokens"], int):
        raise BenchmarkError(f"{label}: native terminal prompt/cache count is invalid")
    if record["cached_tokens"] < 0 or not isinstance(record["finish_reason"], str):
        raise BenchmarkError(f"{label}: native cached_tokens is negative")
    return record


def _bind_native_receipt(receipt: dict, native_dir: str | Path, label: str) -> None:
    usage = receipt.get("usage")
    if not isinstance(usage, dict) or not isinstance(usage.get("prompt_tokens"), int):
        raise BenchmarkError(f"{label}: missing API prompt_tokens for native binding")
    record = _native_terminal(native_dir, receipt["started_unix_ns"], label)
    if record["prompt_tokens"] != usage["prompt_tokens"]:
        raise BenchmarkError(f"{label}: API/native prompt_tokens differ")
    api_cached = _api_cached_tokens(usage, label)
    native_cached = record["cached_tokens"]
    if api_cached is not None and api_cached != native_cached:
        raise BenchmarkError(f"{label}: API/native cached_tokens differ")
    if api_cached is None and native_cached != 0:
        raise BenchmarkError(f"{label}: API cache details omitted for nonzero native cache")
    if record["finish_reason"] != receipt.get("finish_reason"):
        raise BenchmarkError(f"{label}: API/native finish_reason differs")
    receipt.update(
        native_uid=record["uid"],
        native_token_ids=record["native_token_ids"],
        native_cached_tokens=native_cached,
        native_finished_unix_ns=record["finished_unix_ns"],
    )


def invoke(
    baseurl: str, model: str, input: str, label: str, outputpath: str | Path,
    native_dir: str | Path | None = None, deadline_unix: float | None = None,
) -> dict:
    """Perform exactly one streamed completion and append raw SSE plus a receipt."""
    if not isinstance(input, str) or not input:
        raise BenchmarkError(f"{label}: input must be a non-empty string")
    request_timeout = _request_timeout(deadline_unix, label)
    receipts_path, raw_path = _sse_path(outputpath, label)
    payload = {
        "model": model,
        "prompt": input,
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_id = str(uuid.uuid4())
    request = urllib.request.Request(
        baseurl.rstrip("/") + "/v1/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Request-Id": request_id,
        },
    )
    started = time.monotonic()
    started_unix_ns = time.time_ns()
    receipt = {
        "label": label,
        "model": model,
        "input_sha256": hashlib.sha256(input.encode("utf-8")).hexdigest(),
        "input_chars": len(input),
        "raw_sse": raw_path.name,
        "request_id": request_id,
        "started_monotonic": started,
        "started_unix_ns": started_unix_ns,
        "deadline_unix": deadline_unix,
    }
    response = None
    raw_path.touch()
    try:
        response = urllib.request.urlopen(request, timeout=request_timeout)
        with raw_path.open("wb") as raw_handle:
            outcome = _parse_sse(response, raw_handle, started)
        receipt.update(
            text=outcome.text,
            finish_reason=outcome.finish_reason,
            usage=outcome.usage,
            ttft_seconds=outcome.ttft_seconds,
            wall_seconds=time.monotonic() - started,
            ok=True,
        )
        if native_dir is not None:
            _bind_native_receipt(receipt, native_dir, label)
    except (urllib.error.URLError, TimeoutError, OSError, BenchmarkError) as exc:
        receipt.update(error=str(exc), wall_seconds=time.monotonic() - started, ok=False)
        _json_line(receipts_path, receipt)
        raise BenchmarkError(f"{label}: {exc}") from exc
    finally:
        if response is not None:
            response.close()
    _json_line(receipts_path, receipt)
    return receipt


def _validate_terminal(receipt: dict, label: str, expected_prompt_tokens: int) -> None:
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        raise BenchmarkError(f"{label}: missing usage")
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens != expected_prompt_tokens:
        raise BenchmarkError(
            f"{label}: prompt_tokens={prompt_tokens!r}, expected {expected_prompt_tokens}"
        )
    if completion_tokens != MAX_TOKENS:
        raise BenchmarkError(
            f"{label}: completion_tokens={completion_tokens!r}, expected {MAX_TOKENS}"
        )
    if receipt.get("finish_reason") != "length":
        raise BenchmarkError(f"{label}: finish_reason={receipt.get('finish_reason')!r}, expected 'length'")


def _get_json(baseurl: str, endpoint: str) -> dict:
    request = urllib.request.Request(baseurl.rstrip("/") + endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=CONNECT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"{endpoint}: {exc}") from exc


def check_service(baseurl: str, model: str) -> None:
    health = _get_json(baseurl, "/health")
    if health.get("status") != "ok" or health.get("maintenance") != "serving":
        raise BenchmarkError(f"health status is not serving: {health!r}")
    models = _get_json(baseurl, "/v1/models")
    ids = {entry.get("id") for entry in models.get("data", []) if isinstance(entry, dict)}
    if model not in ids:
        raise BenchmarkError(f"requested model {model!r} absent from /v1/models: {sorted(ids)!r}")


def _load_inputs(path: str | Path) -> tuple[str, list[tuple[str, str, str]]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"invalid inputs file: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"version", "short512", "long", "sampling"}:
        raise BenchmarkError("inputs must use the frozen v1 schema")
    if value["version"] != 1:
        raise BenchmarkError("inputs.version must be 1")
    short = value["short512"]
    pairs = value["long"]
    if value["sampling"] != {
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "ignore_eos": True,
    }:
        raise BenchmarkError("inputs.sampling does not match the fixed benchmark settings")
    if not isinstance(short, str) or not short:
        raise BenchmarkError("inputs.short512 must be a non-empty string")
    if not isinstance(pairs, list) or len(pairs) != 3:
        raise BenchmarkError("inputs.long must contain exactly three pairs")
    parsed: list[tuple[str, str, str]] = []
    for index, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict) or set(pair) != {"label", "cold", "continuation"}:
            raise BenchmarkError(f"pair {index} is not an object")
        label, cold, continuation = pair["label"], pair["cold"], pair["continuation"]
        if not isinstance(label, str) or not label or not isinstance(cold, str) or not isinstance(continuation, str):
            raise BenchmarkError(f"pair {index} lacks string label/cold/continuation")
        if not continuation.startswith(cold):
            raise BenchmarkError(f"pair {index} continuation does not retain the cold prefix")
        parsed.append((label, cold, continuation))
    if len({label for label, _, _ in parsed}) != 3:
        raise BenchmarkError("long inputs must have three distinct labels")
    if len({hashlib.sha256(cold.encode("utf-8")).digest() for _, cold, _ in parsed}) != 3:
        raise BenchmarkError("long inputs must have three distinct cold prefixes")
    return short, parsed


def run_arm(
    baseurl: str, model: str, inputs_path: str | Path, outputpath: str | Path,
    arm: str, native_dir: str | Path, deadline_unix: float,
) -> list[dict]:
    short, pairs = _load_inputs(inputs_path)
    check_service(baseurl, model)
    arm_path = Path(outputpath) / arm
    results = []
    for label in ("warmup-short512-1", "warmup-short512-2", "short512"):
        receipt = invoke(
            baseurl, model, short, label, arm_path, native_dir=native_dir,
            deadline_unix=deadline_unix,
        )
        _validate_terminal(receipt, label, 512)
        results.append(receipt)
    for index, (pair_label, long, continuation) in enumerate(pairs, start=1):
        cold = invoke(
            baseurl, model, long, f"{pair_label}-cold32012", arm_path,
            native_dir=native_dir, deadline_unix=deadline_unix,
        )
        _validate_terminal(cold, cold["label"], 32012)
        cached_cold = cold["native_cached_tokens"]
        if cached_cold != 0:
            raise BenchmarkError(f"pair {index} cold cached_tokens={cached_cold!r}, expected 0")
        continuation_receipt = invoke(
            baseurl, model, continuation, f"{pair_label}-continuation32077", arm_path,
            native_dir=native_dir, deadline_unix=deadline_unix,
        )
        _validate_terminal(continuation_receipt, continuation_receipt["label"], 32077)
        cached_continuation = continuation_receipt["native_cached_tokens"]
        if not isinstance(cached_continuation, int) or cached_continuation <= 0:
            raise BenchmarkError(f"pair {index} continuation missing positive cached_tokens")
        tail = continuation_receipt["usage"]["prompt_tokens"] - cached_continuation
        if tail < 65:
            raise BenchmarkError(f"pair {index} continuation uncached tail={tail}, expected at least 65")
        results.extend((cold, continuation_receipt))
    if len(results) != 9:
        raise AssertionError(f"fixed benchmark plan produced {len(results)} calls")
    _json_line(arm_path / "arm.jsonl", {"arm": arm, "calls": len(results), "ok": True})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run-arm")
    run.add_argument("--base-url", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--inputs", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--arm", required=True, choices=("main", "candidate_off", "candidate_on"))
    run.add_argument("--native-dir", required=True)
    run.add_argument(
        "--deadline-unix", required=True, type=float,
        help="Absolute measurement cutoff in Unix seconds; the orchestrator reserves restoration time.",
    )
    args = parser.parse_args(argv)
    try:
        run_arm(
            args.base_url, args.model, args.inputs, args.output, args.arm,
            args.native_dir, args.deadline_unix,
        )
    except BenchmarkError as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
