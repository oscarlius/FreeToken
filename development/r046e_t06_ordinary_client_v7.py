#!/usr/bin/env python3
"""T06 v7 binding with the sealed ordinary-route reader and terminal normalization."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2_PATH = HERE / "r046c_t06_ordinary_client_v2.py"
API_SCHEMA = "ft_t06_ordinary_sse/v3"
INPUT_SCHEMA = "ft_t06_ordinary_input/v3"
TOKEN_SCHEMA = "ft_t06_ordinary_token/v3"
BINDING_SCHEMA = "ft_t06_ordinary_binding/v7"
ROUTE_ANALYZER = HERE / "r046c_route_analyze_ordinary_v2.py"
# This is the model-root provenance recorded by the b96 packet, rather than
# an overlay convenience path whose target can vary between worktrees.
DEFAULT_GENERATION_CONFIG = Path("/data2/model/Qwen3.8-Flash-Next-NVFP4/generation_config.json")


def _v2():
    spec = importlib.util.spec_from_file_location("t06_ordinary_v2_for_v3", V2_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    if ROUTE_ANALYZER.is_symlink() or not ROUTE_ANALYZER.is_file():
        raise RuntimeError("sealed ordinary route analyzer unavailable")
    # v2's legacy e2base1 reader path is not part of the R046e closure.
    # Bind its unchanged routes_for_uid implementation to the reviewed reader.
    module.ROUTE_ANALYZER = ROUTE_ANALYZER
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _eos_provenance(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("generation config unavailable")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("generation config is invalid") from error
    eos = document.get("eos_token_id")
    if (not isinstance(eos, list) or not eos or any(type(token) is not int or token < 0 for token in eos)
            or len(set(eos)) != len(eos)):
        raise ValueError("generation config EOS contract differs")
    return {"path": str(path), "sha256": sha256(path), "eos_token_ids": eos}


def _serve_overlap_provenance(path: Path, *, require_explicit_env: bool = False) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("actual serve argv unavailable")
    try:
        argv = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("actual serve argv is invalid") from error
    if not isinstance(argv, dict) or argv.get("schema") != "ft_r046c_serve_args_actual/v1":
        raise ValueError("actual serve argv differs")
    parsed = argv.get("parsed")
    if not isinstance(parsed, dict) or parsed.get("moe_prefill_overlap") != "True":
        raise ValueError("actual serve argv disables overlap")
    environment = argv.get("environment")
    if require_explicit_env:
        if not isinstance(environment, dict) or environment.get("FREETOKEN_DISABLE_OVERLAP_SCHEDULING") != "0":
            raise ValueError("actual serve environment does not explicitly enable overlap")
        basis = "explicit_runtime_env_and_observed_parsed_branch"
    else:
        # b96 predates the explicit environment receipt.  Its parsed args are
        # an observation of the enabled branch, with source default as context.
        basis = "observed_parsed_branch_with_source_default"
    return {"path": str(path), "sha256": sha256(path),
            "overlap": "enabled", "basis": basis,
            "parsed_moe_prefill_overlap": parsed["moe_prefill_overlap"]}


def _route_accounting(*, prefill: int, decode: int, completion: int, max_tokens: int,
                      tokens: list[dict], api_finish: str, worker_finish: str,
                      eos: dict, serve: dict) -> dict:
    if (type(prefill) is not int or prefill <= 0 or type(decode) is not int or decode < 0
            or type(completion) is not int or completion <= 0 or type(max_tokens) is not int or max_tokens <= 0
            or len(tokens) != completion or tokens[-1].get("completion_tokens_cumulative") != completion):
        raise ValueError("route/token accounting inputs differ")
    terminal_token = tokens[-1].get("next_token")
    terminal_is_eos = terminal_token in eos["eos_token_ids"]
    if api_finish == "length":
        if worker_finish != "length" or completion != max_tokens or terminal_is_eos:
            raise ValueError("length terminal provenance differs")
        extra = 0
    elif terminal_is_eos:
        if worker_finish != "stop" or api_finish not in {"stop", "tool_calls"}:
            raise ValueError("EOS terminal provenance differs")
        # Prefill supplies token one; overlap has already launched exactly one
        # terminal-after-forward decode which scheduler drains without shipping.
        extra = 1
    else:
        raise ValueError("non-length terminal lacks EOS provenance")
    expected_decode = completion - 1 + extra
    if decode != expected_decode:
        raise ValueError("route decode/token accounting differs")
    return {"prefill_tokens": prefill, "route_decode_tokens": decode,
            "streamed_completion_tokens": completion, "payload_max_tokens": max_tokens,
            "terminal_token": terminal_token, "terminal_is_eos": terminal_is_eos,
            "unstreamed_overlap_forward_tokens": extra,
            "formula": "decode=completion-1+unstreamed_overlap_forward_tokens",
            "generation_config": eos, "serve_overlap": serve}


def _valid_birth(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"pid", "start_ticks", "execution_id", "pgid", "session"}:
        return False
    if any(type(value[key]) is not int for key in ("pid", "start_ticks", "pgid", "session")):
        return False
    return value["pid"] > 0 and value["start_ticks"] >= 0 and value["execution_id"] == f"{value['pid']}:{value['start_ticks']}"


def _canonical_ids(raw: bytes) -> tuple[list[int], str]:
    try:
        ids = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("worker input ids are not canonical ASCII JSON") from error
    if not isinstance(ids, list) or any(type(token) is not int or token < 0 for token in ids):
        raise ValueError("worker input ids contain negative or non-integer token")
    canonical = json.dumps(ids, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if raw != canonical:
        raise ValueError("worker input ids canonical bytes differ")
    return ids, hashlib.sha256(raw).hexdigest()


def ordinary_request(base_url: str, input_path: Path, output: Path, timeout: float = 1800) -> dict:
    """Capture normal SSE; the payload file is a claim, not the worker-input proof."""
    if os.environ.get("FT_DEV_PAUSE_ENDPOINT") == "1":
        raise RuntimeError("ordinary client refuses pause environment")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.port == 8095:
        raise RuntimeError("ordinary client must not contact 8095")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("stream") is not True or (payload.get("stream_options") or {}).get("include_usage") is not True:
        raise ValueError("ordinary request requires stream usage")
    raw_path = output.with_suffix(".sse")
    request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    partial = bytearray()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                partial.extend(chunk)
    except urllib.error.HTTPError as exc:
        partial.extend(exc.read()); raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(bytes(partial))
        raise RuntimeError("ordinary SSE HTTP error; raw response preserved") from exc
    except Exception as exc:
        raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(bytes(partial))
        raise RuntimeError("ordinary SSE read error; partial raw response preserved") from exc
    raw = bytes(partial)
    raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_bytes(raw)
    v2 = _v2(); uid, usage, finish = v2.parse_sse(raw)
    value = {"schema": API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
        "payload_source": {"path": str(input_path), "sha256": sha256(input_path)},
        "sse": str(raw_path), "sse_sha256": sha256(raw_path), "id": f"chatcmpl-{uid}", "uid": uid,
        "usage": usage, "finish_reason": finish}
    write_new(output, value)
    return value


def _input_for_uid(path: Path, uid: int, service: dict, worker: dict) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("worker input sidecar unavailable")
    selected = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("uid") == uid]
    if len(selected) != 1:
        raise ValueError("worker input sidecar lacks exactly one API UID")
    row = selected[0]
    if (not _valid_birth(service) or not _valid_birth(worker) or row.get("schema") != INPUT_SCHEMA or row.get("service_birth") != service or row.get("worker_birth") != worker
            or row.get("canonical_encoding") != "utf8-json-int-array-separators=,:" or type(row.get("input_tokens")) is not int
            or row["input_tokens"] < 0 or not isinstance(row.get("input_ids_sha256"), str) or len(row["input_ids_sha256"]) != 64
            or row.get("source") != "Scheduler._process_one_msg(UserMsg)" or type(row.get("time_ns")) is not int or row["time_ns"] <= 0
            or not isinstance(row.get("input_ids_path"), str) or row.get("input_ids_file_sha256") != row.get("input_ids_sha256")):
        raise ValueError("worker input receipt differs")
    ids_path = Path(row["input_ids_path"])
    if ids_path.is_symlink() or not ids_path.is_file():
        raise ValueError("worker input ids file unavailable")
    ids, digest = _canonical_ids(ids_path.read_bytes())
    if len(ids) != row["input_tokens"] or digest != row["input_ids_sha256"]:
        raise ValueError("worker input ids length or digest differs")
    return row


def _terminal_binding(api_finish: str, worker_finish: object) -> dict:
    """Explain the only permitted cross-layer finish spelling difference.

    OpenAI SSE uses ``tool_calls`` when the assistant response ends in a tool
    call.  The scheduler sidecar records that token emission stopped, so its
    terminal event is ``stop``.  It does not claim that the API response was a
    normal assistant stop.
    """
    if api_finish == "tool_calls" and worker_finish == "stop":
        return {"api_finish_reason": api_finish, "worker_finish_reason": worker_finish,
                "normalized": "tool_calls_api_terminal_to_worker_decode_stop"}
    if worker_finish != api_finish:
        raise ValueError("worker terminal finish is incompatible with API finish")
    return {"api_finish_reason": api_finish, "worker_finish_reason": worker_finish,
            "normalized": "identical"}


def _tokens_for_uid(path: Path, uid: int, expected: int, finish: str) -> tuple[list[dict], dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("worker token sidecar unavailable")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in rows if row.get("uid") == uid]
    if not selected:
        raise ValueError("worker token sidecar lacks API UID")
    service, worker, terminal = selected[0].get("service_birth"), selected[0].get("worker_birth"), False
    if not _valid_birth(service) or not _valid_birth(worker):
        raise ValueError("worker token birth differs")
    for index, row in enumerate(selected, 1):
        if (row.get("schema") != TOKEN_SCHEMA or row.get("service_birth") != service or row.get("worker_birth") != worker
                or row.get("request_seq") != index or row.get("completion_tokens_delta") != 1
                or row.get("completion_tokens_cumulative") != index or type(row.get("next_token")) is not int
                or type(row.get("finished")) is not bool or type(row.get("time_ns")) is not int or row["time_ns"] <= 0
                or (row.get("finish_reason") is not None and not isinstance(row.get("finish_reason"), str))):
            raise ValueError("worker token sidecar sequence differs")
        if terminal:
            raise ValueError("worker token sidecar has event after terminal")
        terminal = row.get("finished") is True
        if row["finished"] != (index == len(selected)):
            raise ValueError("worker token terminal position differs")
        if index != len(selected) and row.get("finish_reason") is not None:
            raise ValueError("worker token finish appears before terminal")
    if not terminal or len(selected) != expected:
        raise ValueError("worker token sidecar terminal/API completion differs")
    return selected, _terminal_binding(finish, selected[-1].get("finish_reason"))


def _require_input_before_tokens(input_receipt: dict, tokens: list[dict]) -> None:
    if not tokens or input_receipt["time_ns"] >= tokens[0]["time_ns"]:
        raise ValueError("worker input receipt is not earlier than first token")


def bind(input_path: Path, api_path: Path, d0_path: Path, route_dir: Path, input_sidecar: Path, token_sidecar: Path, output: Path,
         *, generation_config: Path = DEFAULT_GENERATION_CONFIG, serve_args: Path | None = None,
         require_explicit_overlap_env: bool = False) -> dict:
    api = json.loads(api_path.read_text(encoding="utf-8")); v2 = _v2()
    source = api.get("payload_source")
    if api.get("schema") != API_SCHEMA or api.get("pause_enabled") is not False or not isinstance(source, dict) or source.get("path") != str(input_path) or source.get("sha256") != sha256(input_path):
        raise ValueError("payload source binding differs")
    raw_path = Path(api.get("sse", ""))
    if raw_path.is_symlink() or not raw_path.is_file() or api.get("sse_sha256") != sha256(raw_path):
        raise ValueError("API raw SSE SHA differs")
    uid, usage, finish = v2.parse_sse(raw_path.read_bytes())
    if api.get("uid") != uid or api.get("usage") != usage or api.get("finish_reason") != finish:
        raise ValueError("API record differs from raw SSE")
    try:
        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("payload max_tokens provenance unavailable") from error
    max_tokens = payload.get("max_tokens")
    if type(max_tokens) is not int or max_tokens <= 0 or usage["completion_tokens"] > max_tokens:
        raise ValueError("payload max_tokens provenance differs")
    tokens, terminal_binding = _tokens_for_uid(token_sidecar, uid, usage["completion_tokens"], finish)
    actual = _input_for_uid(input_sidecar, uid, tokens[0]["service_birth"], tokens[0]["worker_birth"])
    _require_input_before_tokens(actual, tokens)
    if actual["input_tokens"] != usage["prompt_tokens"]:
        raise ValueError("worker input length disagrees with API prompt_tokens")
    details = usage.get("prompt_tokens_details")
    cached = None if not isinstance(details, dict) or "cached_tokens" not in details else details["cached_tokens"]
    if cached is not None and (type(cached) is not int or cached < 0):
        raise ValueError("API cached_tokens invalid")
    new, scheduled_cached, schedule = v2.d0_for_uid(d0_path, uid)
    prefill, decode, routes = v2.routes_for_uid(route_dir, uid, v2.ROUTE_ANALYZER)
    if prefill != new or new + scheduled_cached != usage["prompt_tokens"] or (cached is not None and cached != scheduled_cached):
        raise ValueError("D0, route, and API prompt totals disagree")
    eos = _eos_provenance(generation_config)
    serve = _serve_overlap_provenance(api_path.parent / "serve_args_actual.json" if serve_args is None else serve_args,
                                      require_explicit_env=require_explicit_overlap_env)
    accounting = _route_accounting(prefill=prefill, decode=decode, completion=usage["completion_tokens"],
                                   max_tokens=max_tokens, tokens=tokens, api_finish=finish,
                                   worker_finish=terminal_binding["worker_finish_reason"], eos=eos, serve=serve)
    value = {"schema": BINDING_SCHEMA, "verdict": "worker_input_uid_token_bound",
        "payload_source": source, "worker_input": {"path": str(input_sidecar), "sha256": sha256(input_sidecar), **actual},
        "api": {"path": str(api_path), "sha256": sha256(api_path), "uid": uid, "usage": usage, "finish_reason": finish,
                "cached_tokens": {"state": "missing" if cached is None else "reported", "value": cached,
                                  "independently_verified": cached is not None}},
        "d0": {"path": str(d0_path), "sha256": sha256(d0_path), "schedule": schedule, "new_tokens": new, "cached_tokens": scheduled_cached},
        "route": {"directory": str(route_dir), "records": routes, "prefill_tokens": prefill, "decode_tokens": decode,
                  "accounting": accounting},
        "token_sidecar": {"path": str(token_sidecar), "sha256": sha256(token_sidecar), "events": tokens,
                          "terminal_binding": terminal_binding}}
    write_new(output, value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True); group.add_argument("--ordinary-request", action="store_true"); group.add_argument("--bind", action="store_true")
    parser.add_argument("--base-url"); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--api", type=Path); parser.add_argument("--d0", type=Path); parser.add_argument("--route-dir", type=Path); parser.add_argument("--input-sidecar", type=Path); parser.add_argument("--token-sidecar", type=Path); parser.add_argument("--generation-config", type=Path, default=DEFAULT_GENERATION_CONFIG); parser.add_argument("--serve-args", type=Path); parser.add_argument("--require-explicit-overlap-env", action="store_true"); parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args(argv)
    if options.ordinary_request:
        if not options.base_url: parser.error("ordinary request needs --base-url")
        value = ordinary_request(options.base_url, options.input, options.out)
    else:
        if not all((options.api, options.d0, options.route_dir, options.input_sidecar, options.token_sidecar)): parser.error("bind arguments differ")
        value = bind(options.input, options.api, options.d0, options.route_dir, options.input_sidecar, options.token_sidecar, options.out,
                     generation_config=options.generation_config, serve_args=options.serve_args,
                     require_explicit_overlap_env=options.require_explicit_overlap_env)
    print(json.dumps(value, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())



