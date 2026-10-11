"""Source-bound comparison of native ordinary SSE, using the existing SDK reader."""
from __future__ import annotations

import copy
import json
import re

from ordinary_sse import _read, decode_ordinary_sse


NATIVE_API_SHA256 = "37b2a0034288dddda25d06213e9f5d470c2f2a56c84b77aa32995f0763546801"


def _require(condition, message):
    if not condition:
        raise ValueError("D12 native SSE: " + message)


def _runtime_identity(raw, *, uid, model):
    """Validate pinned _chat_chunk/_tool_call_id output, without assembling text.

    The SDK remains the text/reasoning/tool-argument assembler. This narrow wire
    check establishes which fields may vary between independent executions.
    """
    created, tool_ids, names = [], [], []
    terminal = False
    for line in raw.splitlines():
        if not line.strip():
            continue
        _require(line.startswith(b"data: "), "unsupported native SSE line")
        if line == b"data: [DONE]":
            continue  # The existing reader requires exactly one final DONE.
        chunk = json.loads(line[6:])
        required = {"id", "object", "created", "model", "choices"}
        _require(isinstance(chunk, dict) and set(chunk) in (required, required | {"usage"}),
                 "unknown/missing native chunk fields")
        _require(chunk["id"] == f"chatcmpl-{uid}" and chunk["object"] == "chat.completion.chunk"
                 and chunk["model"] == model and type(chunk["created"]) is int and chunk["created"] >= 0,
                 "UID/model/object/clock differs from the native contract")
        created.append(chunk["created"])
        choices = chunk["choices"]
        _require(isinstance(choices, list) and len(choices) <= 1, "native choice count differs")
        if "usage" in chunk:
            usage = chunk["usage"]
            keys = {"prompt_tokens", "completion_tokens", "total_tokens"}
            _require(terminal and choices == [] and isinstance(usage, dict)
                     and set(usage) in (keys, keys | {"prompt_tokens_details"})
                     and all(type(usage[key]) is int and usage[key] >= 0 for key in keys),
                     "native usage fields differ")
            if "prompt_tokens_details" in usage:
                details = usage["prompt_tokens_details"]
                _require(isinstance(details, dict) and set(details) == {"cached_tokens"}
                         and type(details["cached_tokens"]) is int
                         and 0 < details["cached_tokens"] <= usage["prompt_tokens"], "invalid cached-token usage")
            continue
        _require(not terminal and len(choices) == 1, "native text chunk has no choice or follows terminal")
        choice = choices[0]
        _require(set(choice) == {"index", "delta", "finish_reason"} and type(choice["index"]) is int
                 and choice["index"] == 0, "unknown/missing native choice fields")
        delta, finish = choice["delta"], choice["finish_reason"]
        _require(isinstance(delta, dict) and finish in (None, "stop", "length", "tool_calls"),
                 "native delta/finish differs")
        if len(created) == 1:
            _require(delta == {"role": "assistant", "content": ""} and finish is None,
                     "native assistant opening differs")
        elif finish is not None:
            _require(delta == {}, "native terminal delta differs")
            terminal = True
        elif set(delta) in ({"content"}, {"reasoning_content"}):
            _require(isinstance(next(iter(delta.values())), str), "native text is not a string")
        else:
            _require(set(delta) == {"tool_calls"} and isinstance(delta["tool_calls"], list)
                     and len(delta["tool_calls"]) == 1, "unknown native delta fields")
            call = delta["tool_calls"][0]
            index = call["index"]
            function = call["function"]
            _require(type(index) is int and index >= 0 and isinstance(function, dict), "invalid tool index/function")
            if "id" in call:
                _require(set(call) == {"index", "id", "type", "function"} and call["type"] == "function"
                         and index == len(tool_ids) and set(function) == {"name", "arguments"}
                         and isinstance(function["name"], str) and function["arguments"] == "",
                         "tool start/order differs")
                prefix = "call_" + (function["name"] or "tool").replace("_", "-")[:24] + f"_{index}_"
                _require(isinstance(call["id"], str) and re.fullmatch(re.escape(prefix) + r"[0-9a-f]{8}", call["id"]),
                         "tool ID does not match source-generated name/index/UUID")
                tool_ids.append(call["id"])
                names.append(function["name"])
            else:
                _require(set(call) == {"index", "function"} and index == len(tool_ids) - 1
                         and set(function) == {"arguments"} and isinstance(function["arguments"], str),
                         "tool continuation identity differs")
    return {"created_per_chunk": created, "tool_ids": tool_ids, "tool_names": names}


def read_native_sse(raw_path, payload_path, *, raw_sha, payload_sha, expected_uid, api_source, ordinary_client):
    """Read one stream, retaining full wire/SDK results and a semantic comparison view."""
    _require(type(expected_uid) is int and expected_uid in (0, 1, 2), "frozen UID 0/1/2 required")
    _read(api_source, NATIVE_API_SHA256)
    raw = _read(raw_path, raw_sha)
    payload = json.loads(_read(payload_path, payload_sha))
    identity = _runtime_identity(raw, uid=expected_uid, model=payload["model"])
    decoded = decode_ordinary_sse(raw_path, payload_path, raw_sha=raw_sha, payload_sha=payload_sha,
                                  ordinary_client=ordinary_client)
    _require(decoded["uid"] == expected_uid, "decoded UID differs from external expectation")
    semantic = copy.deepcopy(decoded["completion"])
    semantic.pop("created")
    calls = semantic["choices"][0]["message"]["tool_calls"] or []
    _require([call["id"] for call in calls] == identity["tool_ids"]
             and [call["function"]["name"] for call in calls] == identity["tool_names"],
             "SDK tool assembly differs from native wire identity")
    for index, call in enumerate(calls):
        _require(call.get("index") == index, "SDK tool ordinal differs")
        # Keep name/index-derived identity; exclude only the source-generated
        # random suffix. Original IDs remain in decoded completion and wire.
        call["id"] = call["id"].rsplit("_", 1)[0]
    _read(raw_path, raw_sha)
    _read(payload_path, payload_sha)
    _read(api_source, NATIVE_API_SHA256)
    return {**decoded, "native_api_sha256": NATIVE_API_SHA256, "runtime_identity": identity,
            "semantic_completion": semantic,
            "excluded_runtime_fields": ["completion.created", "tool_call.id UUID suffix"]}


def compare_native_sse(left, right, *, payload_path, payload_sha, expected_uid, api_source, ordinary_client):
    """Compare two file/SHA pairs for one frozen payload and UID; no token/gate verdict."""
    common = {"payload_path": payload_path, "payload_sha": payload_sha, "expected_uid": expected_uid,
              "api_source": api_source, "ordinary_client": ordinary_client}
    results = [read_native_sse(path, raw_sha=digest, **common) for path, digest in (left, right)]
    _require(results[0]["openai_version"] == results[1]["openai_version"], "SDK versions differ")
    return {"schema": "ft_d12_native_sse_compare/v1", "uid": expected_uid,
            "sse_semantics_equal": results[0]["semantic_completion"] == results[1]["semantic_completion"],
            "left": results[0], "right": results[1], "output_equivalence_verified": False,
            "scope": "native API result comparison only; generated token IDs and numerical gates are separate"}
