"""SDK tools reconstruction and sealed historical replay; no live endpoint."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("openai")
from ordinary_sse import decode_ordinary_sse


CLIENT_PATH = Path(os.environ.get("FT_D12_ORDINARY_CLIENT", Path(__file__).parent.parent / "r046e_t06_ordinary_client_v8.py"))
spec = importlib.util.spec_from_file_location("d12_ordinary_client", CLIENT_PATH)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def fixtures(tmp_path, finish="tool_calls"):
    payload = {"model": "test-only", "messages": [{"role": "user", "content": "test"}],
               "tools": [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
               "stream": True, "stream_options": {"include_usage": True}, "max_tokens": 2048, "temperature": 0}
    common = {"id": "chatcmpl-0", "object": "chat.completion.chunk", "created": 1, "model": "test-only"}
    deltas = [
        {"role": "assistant", "content": "hello ", "reasoning_content": "think "},
        {"reasoning_content": "again", "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
            "function": {"name": "lookup", "arguments": '{"q":'}}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": '"x"}'}}]},
    ]
    events = [{**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas]
    events += [{**common, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
               {**common, "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                                                    "prompt_tokens_details": {"cached_tokens": 1}}}]
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload_path, events


def decode(tmp_path, payload_path, events, trailer=b"data: [DONE]\n\n"):
    raw = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events) + trailer
    raw_path = tmp_path / "response.sse"
    raw_path.write_bytes(raw)
    result = decode_ordinary_sse(raw_path, payload_path, raw_sha=sha(raw),
                                 payload_sha=sha(payload_path.read_bytes()), ordinary_client=client)
    (tmp_path / "decoded.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert raw_path.read_bytes() == raw
    return result


@pytest.mark.parametrize("finish", ["tool_calls", "length", "stop"])
def test_preserves_split_tools_reasoning_and_terminal(tmp_path, finish):
    payload, events = fixtures(tmp_path, finish)
    result = decode(tmp_path, payload, events)
    message = result["completion"]["choices"][0]["message"]
    assert message["content"] == "hello " and message["reasoning_content"] == "think again"
    assert message["tool_calls"][0]["id"] == "call_1"
    assert message["tool_calls"][0]["function"]["name"] == "lookup"
    assert message["tool_calls"][0]["function"]["arguments"] == '{"q":"x"}'
    assert result["completion"]["choices"][0]["finish_reason"] == finish
    assert result["wire_usage"]["prompt_tokens_details"] == {"cached_tokens": 1}
    assert result["output_equivalence_verified"] is False


@pytest.mark.parametrize("fault", ["done", "duplicate_done", "after_done", "terminal", "after_terminal",
                                   "uid", "choice", "usage", "duplicate_usage", "json", "hash"])
def test_incomplete_or_inconsistent_stream_is_rejected(tmp_path, fault):
    payload, events = fixtures(tmp_path)
    trailer = b"data: [DONE]\n\n"
    if fault == "done": trailer = b""
    elif fault == "duplicate_done": trailer *= 2
    elif fault == "after_done": trailer += b"data: " + json.dumps(events[0]).encode() + b"\n\n"
    elif fault == "terminal": events[-2]["choices"][0]["finish_reason"] = None
    elif fault == "after_terminal": events.insert(-1, events[0])
    elif fault == "uid": events[1]["id"] = "chatcmpl-1"
    elif fault == "choice": events[1]["choices"][0]["index"] = 1
    elif fault == "usage": events[-1]["usage"]["total_tokens"] = 4
    elif fault == "duplicate_usage": events.append(events[-1])
    elif fault == "json": trailer = b"data: {broken\n\n" + trailer
    elif fault == "hash":
        raw = tmp_path / "response.sse"
        raw.write_bytes(trailer)
        with pytest.raises(ValueError, match="SHA"):
            decode_ordinary_sse(raw, payload, raw_sha="0" * 64,
                                payload_sha=sha(payload.read_bytes()), ordinary_client=client)
        return
    with pytest.raises((ValueError, IndexError)):
        decode(tmp_path, payload, events, trailer)


def test_three_sealed_tools_responses_are_decoded_without_network(tmp_path):
    root = os.environ.get("FT_D12_HISTORICAL_GROUP")
    if not root:
        pytest.skip("requires the sealed R046g G_seed12k evidence")
    root = Path(root)
    for uid, count in enumerate([140, 58, 113]):
        binding = json.loads((root / f"round-{uid:02d}.binding.json").read_bytes())
        api_path = Path(binding["api"]["path"])
        assert sha(api_path.read_bytes()) == binding["api"]["sha256"]
        api = json.loads(api_path.read_bytes())
        result = decode_ordinary_sse(api["sse"], binding["payload_source"]["path"],
                                    raw_sha=api["sse_sha256"], payload_sha=binding["payload_source"]["sha256"],
                                    ordinary_client=client)
        assert result["uid"] == uid
        final = result["completion"]
        assert final["usage"]["completion_tokens"] == count
        assert final["choices"][0]["finish_reason"] == "tool_calls"
        assert final["choices"][0]["message"]["tool_calls"]
        (tmp_path / f"historical-{uid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
