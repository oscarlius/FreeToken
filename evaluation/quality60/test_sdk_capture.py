"""Protocol regressions for metadata previously lost by the custom SSE reader."""
import copy
import json

import httpx
import pytest
from openai import OpenAI
from openai.types.chat import ChatCompletionChunk

from sdk_capture import capture_chat_stream, project_chat_chunks


def chunk(delta=None, finish=None, usage=None):
    data = {"id": "q60-fixture", "object": "chat.completion.chunk", "created": 0,
            "model": "fixture", "choices": [] if delta is None else [
                {"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage is not None:
        data["usage"] = usage
    return data


def complete_chunks():
    return [chunk({"role": "assistant"}), chunk({"reasoning_content": "thinking"}),
            chunk({"content": "  answer\n"}), chunk({}, "length"),
            chunk(usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})]


def test_sdk_chunk_projection_preserves_text_and_terminal_metadata():
    chunks = [ChatCompletionChunk.model_validate(data).model_dump(mode="json")
              for data in complete_chunks()]
    result = project_chat_chunks(chunks)
    assert result["response"] == "  answer\n"
    assert result["thinking"] == "thinking"
    assert result["finish_reason"] == "length"
    assert result["usage"]["total_tokens"] == 7


@pytest.mark.parametrize("mutation, expected", [
    (lambda rows: rows.pop(3), "without terminal"),
    (lambda rows: rows.pop(), "without usage"),
    (lambda rows: rows.append(chunk({"content": "late"})), "follows terminal"),
    (lambda rows: rows[1].update(id="other"), "id changed"),
    (lambda rows: rows[-1]["usage"].update(total_tokens=99), "inconsistent usage"),
    (lambda rows: rows[-1]["usage"].update(prompt_tokens=True), "invalid usage"),
    (lambda rows: rows[2]["choices"][0]["delta"].update(tool_calls=[{"id": "x"}]), "native tool"),
    (lambda rows: rows[2]["choices"][0]["delta"].update(content=17), "non-text"),
])
def test_invalid_or_incomplete_capture_is_rejected(mutation, expected):
    rows = complete_chunks()
    mutation(rows)
    with pytest.raises(ValueError, match=expected):
        project_chat_chunks(rows)


class FixtureStream:
    def __init__(self, chunks, failure=None):
        self.chunks, self.failure = chunks, failure
        self.closed = False
        self.response = type("Response", (), {"headers": {"x-request-id": "fixture-request"}})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __iter__(self):
        for data in self.chunks:
            yield ChatCompletionChunk.model_validate(data)
        if self.failure:
            raise self.failure


class FixtureClient:
    max_retries = 0

    def __init__(self, stream):
        self.stream = stream
        self.requests = []
        self.chat = self.completions = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        return self.stream


REQUEST = {"model": "fixture", "messages": [{"role": "user", "content": "ping"}],
           "max_tokens": 768, "temperature": 0, "stream": True,
           "stream_options": {"include_usage": True}}


def test_capture_preserves_payload_and_exclusive_artifact(tmp_path):
    stream = FixtureStream(complete_chunks())
    client = FixtureClient(stream)
    path = tmp_path / "chunks.jsonl"
    result = capture_chat_stream(client, REQUEST, path)
    assert client.requests == [REQUEST]
    assert result["request_id"] == "fixture-request" and stream.closed
    raw = path.read_bytes()
    with pytest.raises(FileExistsError):
        capture_chat_stream(client, REQUEST, path)
    assert path.read_bytes() == raw and len(client.requests) == 1
    events = [json.loads(line) for line in raw.splitlines()]
    assert events[0] == {"kind": "response", "request_id": "fixture-request"}
    assert events[-1] == {"kind": "complete"}


@pytest.mark.parametrize("failure", [None, TimeoutError("interrupted")])
def test_partial_capture_survives_missing_terminal_or_transport_failure(tmp_path, failure):
    stream = FixtureStream(complete_chunks()[:3], failure)
    client = FixtureClient(stream)
    path = tmp_path / "partial.jsonl"
    with pytest.raises((ValueError, TimeoutError)):
        capture_chat_stream(client, REQUEST, path)
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len([event for event in events if event["kind"] == "chunk"]) == 3
    assert events[-1]["kind"] == "error" and stream.closed
    assert len(client.requests) == 1


def test_retry_policy_is_checked_before_any_request_or_file(tmp_path):
    client = FixtureClient(FixtureStream(complete_chunks()))
    client.max_retries = 2
    path = tmp_path / "not-created.jsonl"
    with pytest.raises(ValueError, match="max_retries=0"):
        capture_chat_stream(client, REQUEST, path)
    assert not path.exists() and not client.requests


@pytest.mark.parametrize("malformed", [False, True])
def test_actual_sdk_sse_parser_preserves_metadata_or_rejects_bad_json(tmp_path, malformed):
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        frames = ["data: " + json.dumps(row) + "\n\n" for row in complete_chunks()]
        if malformed:
            frames.insert(2, "data: {broken-json\n\n")
        return httpx.Response(200, headers={"content-type": "text/event-stream", "x-request-id": "sdk-fixture"},
                              content="".join(frames) + "data: [DONE]\n\n")

    path = tmp_path / "sdk.jsonl"
    with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as transport:
        with OpenAI(base_url="http://fixture.invalid/v1", api_key="fixture", max_retries=0,
                    timeout=5.0, http_client=transport) as client:
            if malformed:
                with pytest.raises(json.JSONDecodeError):
                    capture_chat_stream(client, REQUEST, path)
            else:
                result = capture_chat_stream(client, REQUEST, path)
                assert result["finish_reason"] == "length"
                assert result["thinking"] == "thinking"
                assert result["request_id"] == "sdk-fixture"
    assert calls == [REQUEST]
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["kind"] == ("error" if malformed else "complete")
