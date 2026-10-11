#!/usr/bin/env python3
"""T06 ordinary-SSE evidence client and UID binding checker.

This tool deliberately has no pause endpoint or ``ft_dev`` ACK parser.  It
captures the normal OpenAI chat SSE id/usage, then binds that UID to the D0
prefill schedule and route records.  It does not claim a token-index proof:
ordinary SSE exposes usage totals but no backend request sequence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTE_ANALYZER = HERE / "e2base1" / "scripts" / "route_analyze.py"
SCHEMA = "ft_t06_ordinary_client/v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def dynamic_private_port() -> int:
    """A short-lived socket guard for fixtures; it never starts a listener."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0))
        port = int(guard.getsockname()[1])
    if port == 8095:
        raise RuntimeError("T06 fixture must never select 8095")
    return port


def _uid(value: object) -> int:
    if not isinstance(value, str) or not value.startswith("chatcmpl-"):
        raise ValueError("ordinary SSE lacks chatcmpl-{uid} id")
    suffix = value.removeprefix("chatcmpl-")
    if not suffix.isdecimal():
        raise ValueError("ordinary SSE id UID is invalid")
    return int(suffix)


def parse_sse(raw: bytes) -> tuple[int, dict, str]:
    """Read normal OpenAI chunks only; any dev ACK is a hard failure."""
    uid: int | None = None
    usage: dict | None = None
    finish: str | None = None
    saw_done = False
    for line in raw.decode("utf-8", errors="strict").splitlines():
        if not line.startswith("data:"):
            continue
        value = line[5:].strip()
        if value == "[DONE]":
            saw_done = True
            continue
        event = json.loads(value)
        if "ft_dev" in event:
            raise ValueError("ordinary T06 client rejects development ACK events")
        event_uid = _uid(event.get("id"))
        if uid is None:
            uid = event_uid
        elif event_uid != uid:
            raise ValueError("ordinary SSE id changes within one request")
        if event.get("usage") is not None:
            if usage is not None:
                raise ValueError("ordinary SSE has multiple usage records")
            usage = event["usage"]
        for choice in event.get("choices") or []:
            candidate = choice.get("finish_reason")
            if candidate is not None:
                if candidate not in {"stop", "length", "tool_calls"}:
                    raise ValueError("ordinary SSE finish reason is invalid")
                finish = candidate
    if uid is None or usage is None or finish is None or not saw_done:
        raise ValueError("ordinary SSE lacks id, usage, finish, or DONE")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("prompt_tokens", "completion_tokens")):
        raise ValueError("ordinary SSE usage totals are invalid")
    if usage["completion_tokens"] <= 0:
        raise ValueError("ordinary SSE completion is empty")
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    if type(cached) is not int or cached < 0:
        raise ValueError("ordinary SSE cached usage is invalid")
    return uid, usage, finish


def ordinary_request(base_url: str, payload_path: Path, output: Path, timeout: float = 1800) -> dict:
    """Send one ordinary chat SSE request and preserve its byte-level evidence."""
    if os.environ.get("FT_DEV_PAUSE_ENDPOINT") == "1":
        raise RuntimeError("T06 ordinary client refuses a pause-enabled environment")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if payload.get("stream") is not True or (payload.get("stream_options") or {}).get("include_usage") is not True:
        raise ValueError("ordinary T06 request requires stream and include_usage")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                     headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    uid, usage, finish = parse_sse(raw)
    raw_path = output.with_suffix(".sse")
    raw_path.write_bytes(raw)
    record = {"schema": SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
              "input": str(payload_path), "input_sha256": sha256(payload_path),
              "sse": str(raw_path), "sse_sha256": sha256(raw_path), "id": f"chatcmpl-{uid}",
              "uid": uid, "usage": usage, "finish_reason": finish}
    write_new(output, record)
    return record


def load_route_analyzer(source: Path):
    if source.is_symlink() or not source.is_file():
        raise ValueError("route analyzer source is unavailable")
    spec = importlib.util.spec_from_file_location("t06_route_analyzer", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def d0_totals(path: Path, uid: int) -> tuple[int, int, list[dict]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("D0 prefill evidence is unavailable")
    new = cached = 0
    matched: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        reqs = row.get("reqs")
        if not isinstance(reqs, list):
            raise ValueError(f"D0 line {number} lacks reqs")
        for req in reqs:
            if not isinstance(req, dict) or set(req) != {"rid", "new_tokens", "cached_tokens"}:
                raise ValueError(f"D0 line {number} req schema differs")
            if any(type(req[key]) is not int or req[key] < 0 for key in req):
                raise ValueError(f"D0 line {number} req values differ")
            if req["rid"] == uid:
                if req["new_tokens"] <= 0:
                    raise ValueError("D0 UID segment has no scheduled tokens")
                new += req["new_tokens"]
                cached += req["cached_tokens"]
                matched.append({"line": number, **req})
    if not matched:
        raise ValueError("D0 has no request UID matching ordinary SSE id")
    return new, cached, matched


def route_totals(route_dir: Path, uid: int, analyzer_source: Path) -> tuple[int, list[dict]]:
    analyzer = load_route_analyzer(analyzer_source)
    records: list[dict] = []
    total = 0
    paths = sorted(route_dir.glob("route-*.json"))
    if not paths:
        raise ValueError("route evidence is empty")
    for path in paths:
        record, _ids = analyzer.load_route(path)
        if record["phase"] != "prefill":
            continue
        for req in record["reqs"]:
            if req["rid"] == uid:
                total += req["n_tokens"]
                records.append({"path": str(path), "sha256": sha256(path), "seq": record["seq"], "n_tokens": req["n_tokens"]})
    if total <= 0:
        raise ValueError("route records have no prefill UID matching ordinary SSE id")
    return total, records


def bind_evidence(input_path: Path, api_path: Path, d0_path: Path, route_dir: Path, output: Path,
                  analyzer_source: Path = ROUTE_ANALYZER) -> dict:
    """Fail closed unless input, normal API, D0 schedule, and route agree."""
    api = json.loads(api_path.read_text(encoding="utf-8"))
    if api.get("schema") != SCHEMA or api.get("mode") != "ordinary_sse" or api.get("pause_enabled") is not False:
        raise ValueError("ordinary API evidence schema differs")
    if api.get("input_sha256") != sha256(input_path):
        raise ValueError("ordinary API evidence is not bound to input bytes")
    uid = _uid(api.get("id"))
    if api.get("uid") != uid:
        raise ValueError("ordinary API UID fields disagree")
    usage = api.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("ordinary API usage absent")
    scheduled_new, scheduled_cached, d0_rows = d0_totals(d0_path, uid)
    routed, route_rows = route_totals(route_dir, uid, analyzer_source)
    reported_cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    if routed != scheduled_new:
        raise ValueError("route UID token total disagrees with D0 schedule")
    if scheduled_new + scheduled_cached != usage.get("prompt_tokens"):
        raise ValueError("D0 schedule totals disagree with ordinary API prompt usage")
    if scheduled_cached != reported_cached:
        raise ValueError("D0 cached tokens disagree with ordinary API usage")
    schedule_sha = hashlib.sha256(json.dumps(d0_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    record = {"schema": "ft_t06_ordinary_binding/v1", "verdict": "uid_bound_not_token_index_bound",
              "input": {"path": str(input_path), "sha256": sha256(input_path)},
              "ordinary_api": {"path": str(api_path), "sha256": sha256(api_path), "id": api["id"], "uid": uid,
                               "usage": usage, "finish_reason": api.get("finish_reason")},
              "d0": {"path": str(d0_path), "sha256": sha256(d0_path), "rows": d0_rows,
                     "new_tokens": scheduled_new, "cached_tokens": scheduled_cached},
              "schedule": {"source": "D0 reqs UID schedule", "sha256": schedule_sha},
              "route": {"directory": str(route_dir), "records": route_rows, "new_tokens": routed,
                        "analyzer": str(analyzer_source), "analyzer_sha256": sha256(analyzer_source)},
              "token_index_binding": {"proven": False,
                  "reason": "ordinary SSE usage has totals only; D0 reqs and route records have UID/token totals but no per-output-token request_seq"},
              "backend_minimum_field_requirement": {"required": ["uid", "request_seq", "completion_tokens_delta", "completion_tokens_cumulative"],
                  "purpose": "prove contiguous per-token output binding without pause"}}
    write_new(output, record)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ordinary-request", action="store_true")
    group.add_argument("--bind", action="store_true")
    parser.add_argument("--base-url")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--api", type=Path)
    parser.add_argument("--d0", type=Path)
    parser.add_argument("--route-dir", type=Path)
    parser.add_argument("--route-analyzer", type=Path, default=ROUTE_ANALYZER)
    parser.add_argument("--out", required=True, type=Path)
    options = parser.parse_args(argv)
    if options.ordinary_request:
        if not options.base_url or any(value is not None for value in (options.api, options.d0, options.route_dir)):
            parser.error("--ordinary-request requires only --base-url, --input, and --out")
        result = ordinary_request(options.base_url, options.input, options.out)
    else:
        if not all((options.api, options.d0, options.route_dir)) or options.base_url:
            parser.error("--bind requires --input --api --d0 --route-dir --out")
        result = bind_evidence(options.input, options.api, options.d0, options.route_dir, options.out, options.route_analyzer)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
