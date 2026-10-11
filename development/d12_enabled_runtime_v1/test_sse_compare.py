"""Native metadata validation and semantic comparison over SDK-assembled SSE."""
import copy
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("openai")
from sse_compare import compare_native_sse
from test_ordinary_sse import client, sha


API = Path(os.environ.get("FT_D12_NATIVE_API_SOURCE", "/data2/FreeToken/wt/e2d12-short-suffix/python/freetoken/server/openai_api.py"))


def stream_fixture(tmp_path):
    payload = {"model": "test-only", "messages": [{"role": "user", "content": "test"}],
        "tools": [{"type": "function", "function": {"name": "list_dir", "parameters": {"type": "object"}}}],
        "stream": True, "stream_options": {"include_usage": True}, "max_tokens": 2048, "temperature": 0}
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload))
    common = {"id": "chatcmpl-0", "object": "chat.completion.chunk", "created": 1, "model": "test-only"}
    deltas = [{"role": "assistant", "content": ""}, {"reasoning_content": "thinking 中文"},
        {"content": "hello "}, {"tool_calls": [{"index": 0, "id": "call_list-dir_0_abcd0123",
            "type": "function", "function": {"name": "list_dir", "arguments": ""}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '"."}'}}]}]
    chunks = [{**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas]
    chunks += [{**common, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
        {**common, "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": 1}}}]
    return path, chunks


def write_stream(path, chunks):
    raw = b"".join(b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n" for chunk in chunks)
    raw += b"data: [DONE]\n\n"
    path.write_bytes(raw)
    return path, sha(raw)


def compare(tmp_path, payload, left, right, **overrides):
    args = {"payload_path": payload, "payload_sha": sha(payload.read_bytes()), "expected_uid": 0,
            "api_source": API, "ordinary_client": client, **overrides}
    result = compare_native_sse(write_stream(tmp_path / "left.sse", left), write_stream(tmp_path / "right.sse", right), **args)
    (tmp_path / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def test_only_source_generated_runtime_fields_and_chunk_boundaries_may_differ(tmp_path):
    payload, left = stream_fixture(tmp_path)
    right = copy.deepcopy(left)
    for i, chunk in enumerate(right): chunk["created"] = 100 + i
    right[3]["choices"][0]["delta"]["tool_calls"][0]["id"] = "call_list-dir_0_87654321"
    right[4]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = '{"path":"."}'
    right.pop(5)
    result = compare(tmp_path, payload, left, right)
    assert result["sse_semantics_equal"] and not result["output_equivalence_verified"]
    assert result["left"]["sse_sha256"] != result["right"]["sse_sha256"]
    assert result["left"]["runtime_identity"]["tool_ids"] != result["right"]["runtime_identity"]["tool_ids"]
    assert result["left"]["completion"]["choices"][0]["message"]["tool_calls"][0]["id"].endswith("abcd0123")


@pytest.mark.parametrize("mode", ["text_only", "two_tools"])
def test_empty_and_multiple_native_tool_lists(tmp_path, mode):
    payload, left = stream_fixture(tmp_path)
    if mode == "text_only":
        left[3:6] = []
        left[-2]["choices"][0]["finish_reason"] = "stop"
    else:
        second = copy.deepcopy(left[3:6])
        for chunk in second: chunk["choices"][0]["delta"]["tool_calls"][0]["index"] = 1
        second[0]["choices"][0]["delta"]["tool_calls"][0]["id"] = "call_list-dir_1_01234567"
        left[-2:-2] = second
    result = compare(tmp_path, payload, left, copy.deepcopy(left))
    assert result["sse_semantics_equal"]
    assert len(result["left"]["runtime_identity"]["tool_ids"]) == (0 if mode == "text_only" else 2)


@pytest.mark.parametrize("change", ["content", "reasoning", "arguments", "argument_whitespace", "name", "finish", "usage", "cache"])
def test_model_and_semantic_fields_are_exact(tmp_path, change):
    payload, left = stream_fixture(tmp_path)
    right = copy.deepcopy(left)
    if change == "content": right[2]["choices"][0]["delta"]["content"] += "!"
    elif change == "reasoning": right[1]["choices"][0]["delta"]["reasoning_content"] += "!"
    elif change == "arguments": right[5]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = '"python"}'
    elif change == "argument_whitespace": right[4]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = '{"path": '
    elif change == "name":
        call = right[3]["choices"][0]["delta"]["tool_calls"][0]
        call["function"]["name"] = "read_file"
        call["id"] = "call_read-file_0_abcd0123"
    elif change == "finish": right[-2]["choices"][0]["finish_reason"] = "length"
    elif change == "usage":
        right[-1]["usage"]["completion_tokens"] += 1
        right[-1]["usage"]["total_tokens"] += 1
    elif change == "cache": right[-1]["usage"]["prompt_tokens_details"]["cached_tokens"] += 1
    result = compare(tmp_path, payload, left, right)
    assert not result["sse_semantics_equal"] and not result["output_equivalence_verified"]


@pytest.mark.parametrize("fault", ["uid", "model", "object", "clock_bool", "clock_str", "clock_negative",
    "tool_id", "tool_name_id", "tool_index", "repeated_tool_start", "continuation_index", "unknown_chunk",
    "unknown_delta", "unknown_usage", "early_usage", "opening", "source", "expected_uid", "payload_sha"])
def test_invalid_native_metadata_or_external_binding_is_rejected(tmp_path, fault):
    payload, chunks = stream_fixture(tmp_path)
    overrides = {}
    if fault == "uid": chunks[1]["id"] = "chatcmpl-1"
    elif fault == "model": chunks[1]["model"] = "different"
    elif fault == "object": chunks[1]["object"] = "chat.completion"
    elif fault == "clock_bool": chunks[1]["created"] = True
    elif fault == "clock_str": chunks[1]["created"] = "1"
    elif fault == "clock_negative": chunks[1]["created"] = -1
    elif fault == "tool_id": chunks[3]["choices"][0]["delta"]["tool_calls"][0]["id"] = "call_arbitrary"
    elif fault == "tool_name_id": chunks[3]["choices"][0]["delta"]["tool_calls"][0]["id"] = "call_other_0_abcd0123"
    elif fault == "tool_index": chunks[3]["choices"][0]["delta"]["tool_calls"][0]["index"] = 1
    elif fault == "repeated_tool_start": chunks.insert(4, copy.deepcopy(chunks[3]))
    elif fault == "continuation_index": chunks[4]["choices"][0]["delta"]["tool_calls"][0]["index"] = 1
    elif fault == "unknown_chunk": chunks[2]["unexpected"] = "value"
    elif fault == "unknown_delta": chunks[2]["choices"][0]["delta"]["unexpected"] = "value"
    elif fault == "unknown_usage": chunks[-1]["usage"]["unexpected"] = 1
    elif fault == "early_usage": chunks.insert(0, chunks.pop())
    elif fault == "opening": chunks[0]["choices"][0]["delta"]["role"] = "user"
    elif fault == "source":
        source = tmp_path / "api.py"
        source.write_bytes(API.read_bytes() + b"\n")
        overrides["api_source"] = source
    elif fault == "expected_uid": overrides["expected_uid"] = 1
    elif fault == "payload_sha": overrides["payload_sha"] = "0" * 64
    with pytest.raises(ValueError):
        compare(tmp_path, payload, chunks, chunks, **overrides)


def test_three_retained_business_responses_keep_semantics_with_fresh_runtime_metadata(tmp_path):
    root = os.environ.get("FT_D12_HISTORICAL_GROUP")
    if not root:
        pytest.skip("requires sealed R046g G_seed12k evidence")
    for uid in range(3):
        binding = json.loads((Path(root) / f"round-{uid:02d}.binding.json").read_bytes())
        api = json.loads(Path(binding["api"]["path"]).read_bytes())
        original = Path(api["sse"])
        before = original.read_bytes()
        assert sha(before) == api["sse_sha256"]
        chunks = [json.loads(line[6:]) for line in before.splitlines() if line.startswith(b"data: {")]
        for i, chunk in enumerate(chunks):
            chunk["created"] = i + 1
            for choice in chunk["choices"]:
                for call in choice["delta"].get("tool_calls", []):
                    if "id" in call: call["id"] = call["id"].rsplit("_", 1)[0] + "_12345678"
        changed = write_stream(tmp_path / f"runtime-changed-{uid}.sse", chunks)
        result = compare_native_sse((original, api["sse_sha256"]), changed,
            payload_path=binding["payload_source"]["path"], payload_sha=binding["payload_source"]["sha256"],
            expected_uid=uid, api_source=API, ordinary_client=client)
        assert result["sse_semantics_equal"] and not result["output_equivalence_verified"]
        assert result["left"]["wire_usage"]["completion_tokens"] == [140, 58, 113][uid]
        assert original.read_bytes() == before
        (tmp_path / f"business-comparison-{uid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
