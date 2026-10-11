"""CPU fixtures for the standard OpenAI completions collector."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from sdk_completions import collect_completion, compare_completion


REQUEST = {"model": "fixture-model", "prompt": "approved mapped text", "max_tokens": 128,
           "temperature": 0, "top_p": 1, "stream": True,
           "stream_options": {"include_usage": True}, "extra_body": {"ignore_eos": True}}


def frame(choices, usage=None):
    value = {"id": "cmpl-fixture", "object": "text_completion.chunk", "created": 0,
             "model": "fixture-model", "choices": choices}
    if usage is not None:
        value["usage"] = usage
    return "data: " + json.dumps(value) + "\n\n"


def body(*, terminal=True, usage=True, finish="length", completion_tokens=128):
    result = frame([{"text": "fixture answer", "index": 0, "finish_reason": None, "logprobs": None}])
    if terminal:
        result += frame([{"text": "", "index": 0, "finish_reason": finish, "logprobs": None}])
    if usage:
        result += frame([], {"prompt_tokens": 2, "completion_tokens": completion_tokens,
                             "total_tokens": 2 + completion_tokens})
    return result + "data: [DONE]\n\n"


def client_with(payload, sent):
    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)
    transport = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    return transport, OpenAI(base_url="http://fixture.invalid/v1", api_key="fixture", max_retries=0,
                             timeout=5.0, http_client=transport)


def test_actual_sdk_collector_uses_completion_text_terminal_and_usage():
    sent = []
    transport, client = client_with(body(), sent)
    try:
        artifact = collect_completion(client, REQUEST)
    finally:
        client.close(); transport.close()
    assert sent == [{"model": "fixture-model", "prompt": "approved mapped text", "max_tokens": 128,
                     "temperature": 0, "top_p": 1, "stream": True,
                     "stream_options": {"include_usage": True}, "ignore_eos": True}]
    assert artifact["request"] == sent[0]
    assert artifact["response"]["status_code"] == 200
    assert artifact["response"]["headers"]["content-type"] == "text/event-stream"
    assert artifact["response"]["received_seconds"] >= 0
    assert len(artifact["chunks"]) == 3
    assert all(row["arrival_seconds"] >= 0 and isinstance(row["data"], dict) for row in artifact["chunks"])
    assert artifact["projection"] == {"text": "fixture answer", "finish_reason": "length",
                                       "usage": {"prompt_tokens": 2, "completion_tokens": 128,
                                                 "total_tokens": 130}, "completion_id": "cmpl-fixture"}


@pytest.mark.parametrize(("payload", "error"), [
    (body(terminal=True, usage=False), "without usage"),
    (body(terminal=False, usage=True), "without finish_reason"),
    (body(terminal=False, usage=False), "without finish_reason"),
    (body(finish="stop"), "must end at length"),
    (body(completion_tokens=127), "must end at length"),
])
def test_collector_rejects_missing_terminal_metadata_or_truncated_stream(payload, error):
    transport, client = client_with(payload, [])
    try:
        with pytest.raises(ValueError, match=error):
            collect_completion(client, REQUEST)
    finally:
        client.close(); transport.close()


def test_comparison_rejects_any_comparable_field_difference():
    left = {"text": "a", "finish_reason": "length", "usage": {"prompt_tokens": 1,
            "completion_tokens": 128, "total_tokens": 129}}
    right = {"text": "a", "finish_reason": "length", "usage": {"prompt_tokens": 1,
             "completion_tokens": 128, "total_tokens": 129}}
    compare_completion(left, right)
    for field, value in (("text", "b"), ("finish_reason", "stop"),
                         ("usage", {"prompt_tokens": 1, "completion_tokens": 127, "total_tokens": 128})):
        right = dict(left); right[field] = value
        with pytest.raises(ValueError, match=field):
            compare_completion(left, right)


def test_prepared_scope_binds_six_services_eight_calls_and_cpu_mapping():
    root = Path(__file__).parent
    scope = json.loads((root / "scope_payloads.json").read_text(encoding="utf-8"))
    binding = json.loads((root / "interleave_input_binding.json").read_text(encoding="utf-8"))
    assert scope["services"] == 6 and len(scope["calls"]) == 8
    assert all(row["service"].startswith("interleave_") and row["label"] != "primer"
               for row in scope["calls"])
    for label in ("pair_0", "pair_1", "pair_2", "pair_3"):
        members = [row for row in scope["calls"] if row["compare"] == label]
        assert len(members) == 2 and members[0]["input"] == members[1]["input"]
    assert len(binding["inputs"]) == 2
    assert [len(row["original_input_ids"]) for row in binding["inputs"]] == [512, 8257]
    assert all(row["retokenized_matches_original"] is True for row in binding["inputs"])
