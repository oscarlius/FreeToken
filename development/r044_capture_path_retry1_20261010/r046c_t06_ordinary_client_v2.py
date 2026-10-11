#!/usr/bin/env python3
"""T06 ordinary SSE v2: bind real scheduler token sidecar without pause."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTE_ANALYZER = HERE / "e2base1" / "scripts" / "route_analyze.py"
API_SCHEMA = "ft_t06_ordinary_sse/v2"
TOKEN_SCHEMA = "ft_t06_ordinary_token/v2"


def sha256(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2); handle.write("\n")


def dynamic_private_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as guard:
        guard.bind(("127.0.0.1", 0)); port = int(guard.getsockname()[1])
    if port == 8095: raise RuntimeError("T06 guard must not select 8095")
    return port


def uid_from_id(value: object) -> int:
    if not isinstance(value, str) or not value.startswith("chatcmpl-") or not value[9:].isdecimal():
        raise ValueError("ordinary SSE lacks valid chatcmpl-{uid} id")
    return int(value[9:])


def parse_sse(raw: bytes) -> tuple[int, dict, str]:
    uid = usage = finish = None; done = False
    for line in raw.decode("utf-8", errors="strict").splitlines():
        if not line.startswith("data:"): continue
        payload = line[5:].strip()
        if payload == "[DONE]": done = True; continue
        event = json.loads(payload)
        if "ft_dev" in event: raise ValueError("ordinary client rejects ft_dev ACK")
        current = uid_from_id(event.get("id"))
        if uid is None: uid = current
        elif uid != current: raise ValueError("ordinary SSE UID changed")
        if event.get("usage") is not None:
            if usage is not None: raise ValueError("ordinary SSE has multiple usage records")
            usage = event["usage"]
        for choice in event.get("choices") or []:
            if choice.get("finish_reason") is not None: finish = choice["finish_reason"]
    if uid is None or not isinstance(usage, dict) or finish not in {"stop", "length", "tool_calls"} or not done:
        raise ValueError("ordinary SSE lacks id, usage, finish, or DONE")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("prompt_tokens", "completion_tokens")) or usage["completion_tokens"] <= 0:
        raise ValueError("ordinary SSE usage is invalid")
    return uid, usage, finish


def ordinary_request(base_url: str, input_path: Path, output: Path, timeout: float = 1800) -> dict:
    if os.environ.get("FT_DEV_PAUSE_ENDPOINT") == "1": raise RuntimeError("ordinary client refuses pause environment")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.port == 8095: raise RuntimeError("ordinary client must not contact 8095")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("stream") is not True or (payload.get("stream_options") or {}).get("include_usage") is not True:
        raise ValueError("ordinary request requires stream usage")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    raw_path = output.with_suffix(".sse")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response: raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(raw)
        raise RuntimeError("ordinary SSE HTTP error; raw response preserved") from exc
    raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(raw)
    uid, usage, finish = parse_sse(raw)
    value = {"schema": API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
             "input": str(input_path), "input_sha256": sha256(input_path), "sse": str(raw_path), "sse_sha256": sha256(raw_path),
             "id": f"chatcmpl-{uid}", "uid": uid, "usage": usage, "finish_reason": finish}
    write_new(output, value); return value


def load_analyzer(path: Path):
    if path.is_symlink() or not path.is_file(): raise ValueError("route analyzer unavailable")
    spec = importlib.util.spec_from_file_location("t06_route_analyzer_v2", path); module = importlib.util.module_from_spec(spec)
    assert spec.loader; spec.loader.exec_module(module); return module


def d0_for_uid(path: Path, uid: int) -> tuple[int, int, list[dict]]:
    if path.is_symlink() or not path.is_file(): raise ValueError("D0 evidence unavailable")
    new = cached = 0; rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        reqs = json.loads(line).get("reqs")
        if not isinstance(reqs, list): raise ValueError("D0 lacks reqs")
        for req in reqs:
            if not isinstance(req, dict) or set(req) != {"rid", "new_tokens", "cached_tokens"} or any(type(req[key]) is not int or req[key] < 0 for key in req):
                raise ValueError("D0 req schema differs")
            if req["rid"] == uid:
                if req["new_tokens"] <= 0: raise ValueError("D0 segment lacks scheduled tokens")
                new += req["new_tokens"]; cached += req["cached_tokens"]; rows.append({"line": line_number, **req})
    if not rows: raise ValueError("D0 has no matching UID")
    return new, cached, rows


def routes_for_uid(directory: Path, uid: int, analyzer_path: Path) -> tuple[int, int, list[dict]]:
    analyzer = load_analyzer(analyzer_path); prefill = decode = 0; rows = []
    paths = sorted(directory.glob("route-*.json"))
    if not paths: raise ValueError("route evidence empty")
    for path in paths:
        record, _ = analyzer.load_route(path); npz = path.parent / record["file"]
        for req in record["reqs"]:
            if req["rid"] == uid:
                count = req["n_tokens"]
                if record["phase"] == "prefill": prefill += count
                else: decode += count
                rows.append({"path": str(path), "json_sha256": sha256(path), "npz": str(npz), "npz_sha256": sha256(npz),
                             "seq": record["seq"], "phase": record["phase"], "n_tokens": count})
    if prefill <= 0: raise ValueError("route lacks matching prefill UID")
    return prefill, decode, rows


def token_sidecar(path: Path, uid: int, expected_completion: int, finish_reason: str) -> list[dict]:
    if path.is_symlink() or not path.is_file(): raise ValueError("observer token sidecar unavailable")
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in events if row.get("uid") == uid]
    if not selected: raise ValueError("token sidecar lacks API UID")
    service = selected[0].get("service_birth"); worker = selected[0].get("worker_birth")
    terminal = False
    for index, row in enumerate(selected, 1):
        if (row.get("schema") != TOKEN_SCHEMA or row.get("service_birth") != service or row.get("worker_birth") != worker
                or row.get("request_seq") != index or row.get("completion_tokens_delta") != 1
                or row.get("completion_tokens_cumulative") != index or type(row.get("next_token")) is not int):
            raise ValueError("token sidecar sequence or birth binding differs")
        if terminal: raise ValueError("token sidecar has event after terminal")
        terminal = row.get("finished") is True
    if not terminal or len(selected) != expected_completion or selected[-1].get("finish_reason") != finish_reason:
        raise ValueError("token sidecar terminal/API completion differs")
    return selected


def bind(input_path: Path, api_path: Path, d0_path: Path, route_dir: Path, token_path: Path, output: Path,
         analyzer_path: Path = ROUTE_ANALYZER) -> dict:
    api = json.loads(api_path.read_text(encoding="utf-8"))
    if api.get("schema") != API_SCHEMA or api.get("pause_enabled") is not False or api.get("input_sha256") != sha256(input_path):
        raise ValueError("API evidence binding differs")
    raw_path = Path(api.get("sse", ""))
    if not raw_path.is_file() or raw_path.is_symlink() or api.get("sse_sha256") != sha256(raw_path):
        raise ValueError("API raw SSE SHA differs")
    uid, replayed_usage, replayed_finish = parse_sse(raw_path.read_bytes())
    if api.get("uid") != uid or api.get("usage") != replayed_usage or api.get("finish_reason") != replayed_finish:
        raise ValueError("API record differs from raw SSE")
    details = replayed_usage.get("prompt_tokens_details")
    api_cached_missing = not isinstance(details, dict) or "cached_tokens" not in details
    cached = None if api_cached_missing else details["cached_tokens"]
    if cached is not None and (type(cached) is not int or cached < 0): raise ValueError("API cached_tokens invalid")
    new, scheduled_cached, schedule = d0_for_uid(d0_path, uid)
    prefill, decode, routes = routes_for_uid(route_dir, uid, analyzer_path)
    if prefill != new or new + scheduled_cached != replayed_usage["prompt_tokens"]:
        raise ValueError("D0, route, and API prompt totals disagree")
    if cached is not None and cached != scheduled_cached:
        raise ValueError("API cached_tokens disagrees with D0")
    tokens = token_sidecar(token_path, uid, replayed_usage["completion_tokens"], replayed_finish)
    if decode != max(0, replayed_usage["completion_tokens"] - 1):
        raise ValueError("route decode total disagrees with real completion sequence")
    value = {"schema": "ft_t06_ordinary_binding/v2", "verdict": "uid_and_token_index_bound",
             "input": {"path": str(input_path), "sha256": sha256(input_path)},
             "api": {"path": str(api_path), "sha256": sha256(api_path), "raw_sse": str(raw_path), "raw_sse_sha256": sha256(raw_path),
                     "id": api["id"], "uid": uid, "usage": replayed_usage, "finish_reason": replayed_finish,
                     "cached_tokens": {"state": "missing" if api_cached_missing else "reported", "value": cached,
                                       "independently_verified": not api_cached_missing}},
             "d0": {"path": str(d0_path), "sha256": sha256(d0_path), "schedule": schedule, "new_tokens": new, "cached_tokens": scheduled_cached},
             "route": {"directory": str(route_dir), "records": routes, "prefill_tokens": prefill, "decode_tokens": decode,
                       "analyzer": str(analyzer_path), "analyzer_sha256": sha256(analyzer_path)},
             "token_sidecar": {"path": str(token_path), "sha256": sha256(token_path), "events": tokens}}
    write_new(output, value); return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ordinary-request", action="store_true"); group.add_argument("--bind", action="store_true")
    parser.add_argument("--base-url"); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--api", type=Path)
    parser.add_argument("--d0", type=Path); parser.add_argument("--route-dir", type=Path); parser.add_argument("--token-sidecar", type=Path)
    parser.add_argument("--route-analyzer", type=Path, default=ROUTE_ANALYZER); parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.ordinary_request:
        if not options.base_url or any(x is not None for x in (options.api, options.d0, options.route_dir, options.token_sidecar)): parser.error("ordinary request arguments differ")
        value = ordinary_request(options.base_url, options.input, options.out)
    else:
        if options.base_url or not all((options.api, options.d0, options.route_dir, options.token_sidecar)): parser.error("bind arguments differ")
        value = bind(options.input, options.api, options.d0, options.route_dir, options.token_sidecar, options.out, options.route_analyzer)
    print(json.dumps(value, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
