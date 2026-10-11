"""Owned, loopback-only contract check for the OpenAI Python client.

This fixture validates parser compatibility only.  It never contacts a
FreeToken/model endpoint and is not target-model or performance evidence.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from openai import OpenAI


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    request_count = 0
    request_lock = threading.Lock()

    def log_message(self, _format: str, *_args: object) -> None:
        pass

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        with self.request_lock:
            type(self).request_count += 1
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request.get("stream", False):
            events = (
                {"id": "fixture", "object": "chat.completion.chunk", "created": 0,
                 "model": "fixture", "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
                {"id": "fixture", "object": "chat.completion.chunk", "created": 0,
                 "model": "fixture", "choices": [{"index": 0, "delta": {"reasoning_content": "fixture-reasoning"}, "finish_reason": None}]},
                {"id": "fixture", "object": "chat.completion.chunk", "created": 0,
                 "model": "fixture", "choices": [{"index": 0, "delta": {"content": "fixture-sse"}, "finish_reason": None}]},
                {"id": "fixture", "object": "chat.completion.chunk", "created": 0,
                 "model": "fixture", "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
                 "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}},
            )
            payload = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload.encode())))
            self.end_headers()
            self.wfile.write(payload.encode())
            return
        payload = {"id": "fixture", "object": "chat.completion", "created": 0,
                   "model": "fixture", "choices": [{"index": 0, "message": {"role": "assistant", "content": "fixture-json", "reasoning_content": "fixture-reasoning"}, "finish_reason": "length"}],
                   "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_openai_json_and_sse_contract() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as transport, OpenAI(base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="fixture", max_retries=0, timeout=5.0, http_client=transport) as client:
            response = client.chat.completions.create(model="fixture", messages=[{"role": "user", "content": "ping"}])
            response_dump = response.model_dump()
            assert response_dump["choices"][0]["message"]["content"] == "fixture-json"
            assert response_dump["choices"][0]["message"]["reasoning_content"] == "fixture-reasoning"
            assert response_dump["choices"][0]["finish_reason"] == "length"
            assert response_dump["usage"]["prompt_tokens"] == 2
            assert response_dump["usage"]["completion_tokens"] == 3
            assert response_dump["usage"]["total_tokens"] == 5
            chunks = client.chat.completions.create(model="fixture", messages=[{"role": "user", "content": "ping"}], stream=True)
            chunk_dumps = [chunk.model_dump() for chunk in chunks]
            assert "".join(item["choices"][0]["delta"].get("content") or "" for item in chunk_dumps) == "fixture-sse"
            assert any(item["choices"][0]["delta"].get("reasoning_content") == "fixture-reasoning" for item in chunk_dumps)
            assert chunk_dumps[-1]["choices"][0]["finish_reason"] == "length"
            assert chunk_dumps[-1]["usage"]["prompt_tokens"] == 2
            assert chunk_dumps[-1]["usage"]["completion_tokens"] == 3
            assert chunk_dumps[-1]["usage"]["total_tokens"] == 5
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
