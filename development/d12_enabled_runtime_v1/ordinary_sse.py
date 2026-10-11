"""Offline D12 tools-SSE reconstruction using the existing reader and SDK.

The caller collects wire bytes with ordinary_client_v8. This helper sends no
network request, executes no tools, and supplies no round/output verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _read(path, expected_sha):
    path = Path(path).absolute()
    if path.resolve() != path or not path.is_file():
        raise ValueError("D12 SSE input must be a physical regular file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("D12 SSE input SHA differs")
    return raw


def decode_ordinary_sse(raw_path, payload_path, *, raw_sha, payload_sha, ordinary_client):
    """Reconstruct one hash-bound ordinary result without changing its payload.

    ordinary_client is the caller's pinned, existing v8 module. Its v2 parser
    remains responsible for ordinary UID/usage/finish/DONE metadata. The SDK
    assembles all message fields, including split native tool calls.
    """
    import httpx
    import openai

    raw = _read(raw_path, raw_sha)
    payload = json.loads(_read(payload_path, payload_sha))
    if (payload.get("stream") is not True or payload.get("n", 1) != 1
            or payload.get("stream_options") != {"include_usage": True}):
        raise ValueError("D12 expects one ordinary streamed completion with usage")
    uid, usage, finish = ordinary_client._v2().parse_sse(raw)
    # The old metadata parser accepts records after DONE. Require one final DONE
    # before handing the stream to the SDK, which stops reading at that marker.
    records = [line.strip() for line in raw.splitlines() if line.strip()]
    done = [i for i, line in enumerate(records)
            if line.startswith(b"data:") and line[5:].strip() == b"[DONE]"]
    if done != [len(records) - 1]:
        raise ValueError("D12 requires one final DONE marker")
    if (type(usage.get("total_tokens")) is not int
            or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
        raise ValueError("D12 usage total differs")

    calls = []

    def replay(request):
        # MockTransport is the only transport. Even an accidental second SDK
        # call fails locally, and all original tools/messages remain unchanged.
        if calls or json.loads(request.content) != payload:
            raise ValueError("D12 offline SDK request differs from original payload")
        calls.append(True)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=raw)

    terminal = False
    chunk_count = 0
    request = {key: value for key, value in payload.items() if key != "stream"}
    with httpx.Client(transport=httpx.MockTransport(replay), trust_env=False) as transport:
        with openai.OpenAI(api_key="offline-placeholder", base_url="http://offline.invalid/v1",
                           max_retries=0, timeout=5, http_client=transport) as client:
            with client.chat.completions.stream(**request) as stream:
                for event in stream:
                    if event.type != "chunk":
                        continue
                    chunk_count += 1
                    chunk = event.chunk.model_dump(mode="json")
                    if chunk["id"] != f"chatcmpl-{uid}" or len(chunk["choices"]) > 1:
                        raise ValueError("D12 SDK completion identity or choice count differs")
                    for choice in chunk["choices"]:
                        if choice["index"] != 0 or terminal:
                            raise ValueError("D12 choice follows terminal or has a different index")
                        if choice["finish_reason"] is not None:
                            terminal = True
                # Public snapshot preserves a length-terminated raw response.
                # get_final_completion() invokes structured parsing and raises
                # LengthFinishReasonError even when no JSON schema was requested.
                final = stream.current_completion_snapshot.model_dump(mode="json")
                sdk_usage = stream.current_completion_snapshot.usage
    # Exclude SDK defaults at every nesting level (e.g. audio_tokens=None inside
    # prompt_tokens_details); retain all fields actually present on the wire.
    if (not terminal or len(calls) != 1 or len(final["choices"]) != 1
            or final["choices"][0]["finish_reason"] != finish
            or sdk_usage is None or sdk_usage.model_dump(mode="json", exclude_unset=True) != usage):
        raise ValueError("D12 reconstructed terminal metadata differs")
    return {"uid": uid, "payload_sha256": payload_sha, "sse_sha256": raw_sha,
            "openai_version": openai.__version__, "sdk_chunks": chunk_count,
            "wire_usage": usage, "completion": final, "output_equivalence_verified": False,
            "scope": "offline SDK reconstruction of retained ordinary SSE; no model or round verdict"}
