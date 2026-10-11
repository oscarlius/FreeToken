#!/usr/bin/env python3
"""Stub HTTP server for rehearsal mode (P1-G5).

Uses only Python standard library (http.server.ThreadingHTTPServer).
Simulates FreeToken server behavior with configurable:
1. Determinism / non-determinism (character 100 divergence on repeats).
2. OOM threshold T (triggers CUDA OOM error when prompt chars > T).
3. Prints moe_cache_size=2700 on startup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Print moe_cache_size immediately on startup as required by P1-G5
print("moe_cache_size=2700", flush=True)

RESTART_UNTIL = 0.0
REQUEST_COUNTS: dict[str, int] = {}
NON_DETERMINISTIC = False
OOM_THRESHOLD = -1


def create_dummy_d0_files(d0_prefix: str) -> None:
    """Create dummy D0 files for S6 rehearsal if FT_DEV_D0 is set."""
    p = Path(d0_prefix).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    decode_path = p.parent / f"{p.name}_decode.json"
    steps_path = p.parent / f"{p.name}_decode_steps.jsonl"

    steps_data = []
    # 256 steps. First 16 warmup, rest 240 steps.
    # Total slots per step = 480. Target miss rate ~ 0.29
    # missing_total = round(480 * 0.29) = 139
    for s in range(256):
        m_tot = 480 if s < 16 else 139
        steps_data.append({
            "step": s,
            "t": time.time(),
            "bs": 2,
            "rids": [0, 1],
            "missing_per_layer": [3] * 48,
            "missing_total": m_tot,
            "h2d_bytes": 0,
        })
    with open(steps_path, "w", encoding="utf-8") as f:
        for item in steps_data:
            f.write(json.dumps(item) + "\n")

    decode_data = {
        "ts": time.time(),
        "decode_target": "gpu",
        "layer_calls": 256 * 48,
        "active_per_layer": 10.0,
        "missing_per_layer": 2.9,
        "miss_rate": 0.29,
        "fetched_per_layer": 0.0,
        "cpu_per_layer": 2.9,
        "fetch_rate": 0.0,
        "missing_total": sum(x["missing_total"] for x in steps_data),
    }
    with open(decode_path, "w", encoding="utf-8") as f:
        json.dump(decode_data, f, indent=2)


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Keep serve.log clean, but log errors
        pass

    def do_GET(self) -> None:
        global RESTART_UNTIL
        if self.path == "/health":
            now = time.time()
            if now < RESTART_UNTIL:
                body = json.dumps({"status": "ok", "maintenance": "restarting"}).encode("utf-8")
            else:
                body = json.dumps({"status": "ok", "maintenance": "serving"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/v1/models":
            body = json.dumps({
                "object": "list",
                "data": [
                    {"id": "Qwen3.8-Flash-Next-NVFP4", "object": "model"}
                ]
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        global RESTART_UNTIL, REQUEST_COUNTS, NON_DETERMINISTIC, OOM_THRESHOLD
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body = {}

        messages = body.get("messages", [])
        total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m.get("content"), str))
        max_tokens = int(body.get("max_tokens", 256))

        # Check OOM trigger
        if OOM_THRESHOLD > 0 and total_chars > OOM_THRESHOLD:
            RESTART_UNTIL = time.time() + 8.0
            oom_msg = (
                "worker_restarting_after_oom: OutOfMemoryError: CUDA out of memory. "
                "Tried to allocate 48.00 MiB. GPU 0 has a total capacity of 23.52 GiB of which 21.69 MiB is free. "
                "Including non-PyTorch memory, this process has 23.27 GiB memory in use."
            )
            print(f"OOM: {oom_msg}", flush=True)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            # 1 empty content chunk
            chunk_empty = {
                "id": "chatcmpl-oom",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "Qwen3.8-Flash-Next-NVFP4",
                "choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(chunk_empty)}\n\n".encode("utf-8"))
            self.wfile.flush()

            # Error chunk
            chunk_err = {
                "error": {
                    "message": oom_msg,
                    "type": "invalid_request_error",
                    "code": "insufficient_workspace",
                }
            }
            self.wfile.write(f"data: {json.dumps(chunk_err)}\n\n".encode("utf-8"))
            self.wfile.flush()

            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        # Normal generation
        # Prompt hash key for tracking repeat calls
        p_key = hashlib.sha256(raw_body).hexdigest()[:16]
        call_count = REQUEST_COUNTS.get(p_key, 0)
        REQUEST_COUNTS[p_key] = call_count + 1

        # Text generation
        # Chars 0..99 are 'A'.
        # From char 100 onwards: if NON_DETERMINISTIC, vary by call_count so every repeat differs at char 100.
        prefix = "A" * 100
        if NON_DETERMINISTIC:
            diff_char = chr(ord("B") + (call_count % 25))
        else:
            diff_char = "B"
        full_text = prefix + (diff_char * (max_tokens * 8))

        # Split full_text into max_tokens chunks
        # Each chunk gets full_text[i*4 : (i+1)*4]
        chunk_size_chars = 4
        chunks_text = [
            full_text[i * chunk_size_chars : (i + 1) * chunk_size_chars]
            for i in range(max_tokens)
        ]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        prompt_est = int(total_chars / 3.6)

        for i, piece in enumerate(chunks_text):
            is_last = (i == max_tokens - 1)
            chunk = {
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "Qwen3.8-Flash-Next-NVFP4",
                "choices": [{
                    "delta": {"reasoning_content": piece},
                    "index": 0,
                    "finish_reason": "length" if is_last else None,
                }],
            }
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.005)  # Fast for rehearsal

        # Usage chunk
        usage_chunk = {
            "id": "chatcmpl-stub",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "Qwen3.8-Flash-Next-NVFP4",
            "choices": [],
            "usage": {
                "prompt_tokens": prompt_est,
                "completion_tokens": max_tokens,
                "total_tokens": prompt_est + max_tokens,
            },
        }
        self.wfile.write(f"data: {json.dumps(usage_chunk)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    global NON_DETERMINISTIC, OOM_THRESHOLD
    import hashlib
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--oom-threshold", type=int, default=-1)
    parser.add_argument("--non-deterministic", action="store_true")
    # Accept extra args passed by server argv
    args, unknown = parser.parse_known_args()

    NON_DETERMINISTIC = args.non_deterministic
    OOM_THRESHOLD = args.oom_threshold

    # If FT_DEV_D0_PATH is set in env, create dummy d0 files
    d0_path = os.environ.get("FT_DEV_D0_PATH")
    if os.environ.get("FT_DEV_D0") == "1" and d0_path:
        create_dummy_d0_files(d0_path)

    server = ThreadingHTTPServer((args.host, args.port), StubHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
