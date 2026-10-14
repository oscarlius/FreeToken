#!/usr/bin/env python3
"""任务 S 的 CPU 桩服务（只用标准库；不加载模型，不占 GPU，不碰 8095）。

按指令 §3 的形状模拟：会话 A（max_tokens 16384 且 ignore_eos）持续输出非空增量；
事件 B 到达即向 serve.log 写 Prefill 行（每段一行，首行带 cached），预填期间 A 暂停（生产预填优先），
预填时长取预登记的 prefill_pred_s（乘以 --time-scale）；随后输出 32 个增量与 usage。
/health 与 /v1/stats 的形状与生产一致。

演练注入（只用于演练工装的路径，不是证据）：
  --contaminate KEY        该事件期间 requests.active 多报 1（应被判 contaminated）
  --a-no-pause KEY         该事件 B 预填期间 A 不停（应被零输出检查标出）
  --completed-init N       初始 completed（默认 2）
  --prompt-tokens-init N   初始 prompt_tokens_total（默认 8769）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = "Qwen3.8-Flash-Next-NVFP4"
A_MAX_TOKENS = 16384
B_TOKENS = 32
A_ITL_S = 0.025
B_ITL_S = 0.034


def messages_sha256(messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def send_json(handler: BaseHTTPRequestHandler, status: int, doc: dict) -> None:
    body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def write_event(handler: BaseHTTPRequestHandler, doc: dict) -> None:
    handler.wfile.write(f"data: {json.dumps(doc, ensure_ascii=False)}\n\n".encode("utf-8"))
    handler.wfile.flush()


class Stub:
    def __init__(self, args: argparse.Namespace) -> None:
        self.scale = args.time_scale
        self.serve_log = Path(args.serve_log)
        self.lock = threading.Lock()
        self.active = 0
        self.extra_active = 0
        self.completed = args.completed_init
        self.prompt_total = args.prompt_tokens_init
        self.completion_total = 256
        self.busy_until = 0.0
        self.contaminate = args.contaminate
        self.a_no_pause = set(args.a_no_pause or [])
        self.started = time.monotonic()
        prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
        self.spec = {e["event"]: e for e in prereg["events"]}
        inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        self.by_sha: dict[str, str] = {}
        for row in inputs["rounds"]:
            if row["trajectory"] == "T2":
                self.by_sha[row["messages_sha256"]] = f'T2/{row["round"]:02d}'
        l64 = json.loads(Path(args.l64).read_text(encoding="utf-8"))
        self.by_sha[messages_sha256(l64["messages"])] = "L64"
        with self.serve_log.open("a", encoding="utf-8") as log:
            log.write(f"stub server (time_scale={self.scale}, no model loaded)\n")

    def stats(self) -> dict:
        with self.lock:
            return {"active": self.active + self.extra_active, "completed": self.completed, "p95_ms": 0,
                    "ttft_mean_ms": 0, "prompt_tokens_total": self.prompt_total,
                    "completion_tokens_total": self.completion_total}

    def wait_busy(self) -> None:
        while True:
            with self.lock:
                until = self.busy_until
            now = time.monotonic()
            if now >= until:
                return
            time.sleep(min(until - now, 0.01))

    def serve_a(self, handler: BaseHTTPRequestHandler) -> None:
        with self.lock:
            self.active += 1
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.end_headers()
        try:
            write_event(handler, {"choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0,
                                               "finish_reason": None}]})
            for i in range(A_MAX_TOKENS):
                self.wait_busy()
                write_event(handler, {"choices": [{"delta": {"reasoning_content": f"{i} "}, "index": 0,
                                                   "finish_reason": None}]})
                time.sleep(A_ITL_S * self.scale)
            write_event(handler, {"choices": [{"delta": {}, "index": 0, "finish_reason": "length"}]})
            handler.wfile.write(b"data: [DONE]\n\n")
            handler.wfile.flush()
        except OSError:
            pass  # 客户端断开：按完成计（演练假设）
        finally:
            with self.lock:
                self.active -= 1
                self.completed += 1

    def serve_b(self, handler: BaseHTTPRequestHandler, payload: dict) -> None:
        key = self.by_sha.get(messages_sha256(payload.get("messages") or []))
        if key is None or key not in self.spec:
            send_json(handler, 400, {"error": {"message": "stub: unknown payload", "type": "invalid_request"}})
            return
        spec = self.spec[key]
        segments = list(spec["segments_expected"])
        cached = int(spec["cached_expected"])
        pred = float(spec["prefill_pred_s"]) * self.scale
        prompt = sum(segments) + cached
        with self.lock:
            self.active += 1
            contaminated = key == self.contaminate
            if contaminated:
                self.extra_active += 1
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.end_headers()
        try:
            write_event(handler, {"choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0,
                                               "finish_reason": None}]})
            lines = [f"Prefill batch, #new-seq: 1, #new-token: {seg}, #cached-token: {cached if i == 0 else 0}, "
                     "token usage: 0.89" for i, seg in enumerate(segments)]
            with self.serve_log.open("a", encoding="utf-8") as log:
                log.write("\n".join(lines) + "\n")
            if key not in self.a_no_pause:
                with self.lock:
                    self.busy_until = time.monotonic() + pred
            time.sleep(pred)
            for i in range(B_TOKENS):
                if i:
                    time.sleep(B_ITL_S * self.scale)
                write_event(handler, {"choices": [{"delta": {"reasoning_content": f"b{i} "}, "index": 0,
                                                   "finish_reason": None}]})
            write_event(handler, {"choices": [{"delta": {}, "index": 0, "finish_reason": "length"}]})
            usage: dict = {"prompt_tokens": prompt, "completion_tokens": B_TOKENS,
                           "total_tokens": prompt + B_TOKENS}
            if cached:
                usage["prompt_tokens_details"] = {"cached_tokens": cached}
            write_event(handler, {"choices": [], "usage": usage})
            handler.wfile.write(b"data: [DONE]\n\n")
            handler.wfile.flush()
        finally:
            with self.lock:
                self.active -= 1
                if contaminated:
                    self.extra_active -= 1
                self.completed += 1
                self.prompt_total += prompt
                self.completion_total += B_TOKENS


class Handler(BaseHTTPRequestHandler):
    server_version = "op-hak-stall-stub"

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名
        stub: Stub = self.server.stub  # type: ignore[attr-defined]
        if self.path == "/health":
            send_json(self, 200, {"status": "ok", "model": MODEL, "instance_id": "stub",
                                  "uptime_s": round(time.monotonic() - stub.started, 1), "version": "stub",
                                  "maintenance": "serving", "backend_epoch": 0, "restart_attempts": 0,
                                  "restart_waiters": 0})
        elif self.path.startswith("/v1/stats"):
            send_json(self, 200, {"requests": stub.stats()})
        else:
            send_json(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        stub: Stub = self.server.stub  # type: ignore[attr-defined]
        if not self.path.startswith("/v1/chat/completions"):
            send_json(self, 404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length") or 0)
        try:
            payload = json.loads(self.rfile.read(length))
        except ValueError:
            send_json(self, 400, {"error": {"message": "stub: bad json"}})
            return
        if payload.get("max_tokens") == A_MAX_TOKENS and payload.get("ignore_eos"):
            stub.serve_a(self)
        else:
            stub.serve_b(self, payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 保持签名
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="任务 S 的 CPU 桩服务（只用于演练）")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--serve-log", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--l64", required=True)
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--contaminate", default=None)
    parser.add_argument("--a-no-pause", action="append", default=[])
    parser.add_argument("--completed-init", type=int, default=2)
    parser.add_argument("--prompt-tokens-init", type=int, default=8769)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.stub = Stub(args)  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
