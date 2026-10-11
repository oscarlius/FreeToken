#!/usr/bin/env python3
"""桩服务（op-hak 任务 A 演练专用，只用标准库）。

不加载模型，不占 GPU，不监听 8095。行为按预登记模拟：
- 每条请求先立即发 role 包（与生产相同），再等预填时间，再把 Prefill batch 行写入 serve.log，再逐 token 输出；
- 预填时间：warmup 0.5 秒；seed_real 冷轮按计算受限，两臂相同（18.6 秒）；其它轮按"切段数 × 单遍时长"
  （单遍 2.7775 秒，与预登记 constants.single_pass_s 相同）。这是对预登记的复现，用来演练工装的算术与判读路径，
  不是对生产的测量，演练结果不能当作证据。
- 注入：--oom-at KEY（该请求输出 OOM 错误并进入重启）、--wrong-cached KEY（该请求的 cached 返回 0）、
  --segments-override KEY=a,b（该请求的切段改为给定值）。KEY 形如 seed_real/03。
- --worker-exit-at KEY：该请求写出 4 个 token 后写入退出标记并断开；加 --worker-exit-hold-s S 则先挂起 S 秒不断开
  （模拟服务端不关连接，客户端只能靠请求进行中的实时监视识别）。
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
PASS_S = 2.7775
COLD_SEED_S = 18.6
WARMUP_S = 0.5
ITL_S = 0.034
OOM_MESSAGE = "worker_restarting_after_oom: OutOfMemoryError: CUDA out of memory (stub)"


def messages_sha256(messages: list[dict]) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def parse_override(text: str | None) -> dict[str, list[int]]:
    if not text:
        return {}
    key, _, values = text.partition("=")
    return {key: [int(v) for v in values.split(",") if v]}


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
        self.arm = args.arm
        self.scale = args.scale
        self.serve_log = Path(args.serve_log)
        self.stats_out = Path(args.stats_out)
        inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        self.prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
        self.by_sha: dict[str, tuple[str, str, int]] = {inputs["warmup"]["messages_sha256"]: ("warm/00", "warm", 0)}
        for row in inputs["rounds"]:
            key = f'{row["trajectory"]}/{row["round"]:02d}'
            self.by_sha[row["messages_sha256"]] = (key, row["trajectory"], row["round"])
        self.oom_at = args.oom_at
        self.worker_exit_at = args.worker_exit_at
        self.worker_exit_hold_s = args.worker_exit_hold_s
        self.dead = False
        self.wrong_cached = args.wrong_cached
        self.override = parse_override(args.segments_override)
        self.recover_s = args.oom_recover_s
        self.lock = threading.Lock()
        self.active = 0
        self.completed = 0
        self.restart_until = 0.0
        self.backend_epoch = 0
        with self.serve_log.open("a", encoding="utf-8") as log:
            log.write(f"stub server arm={self.arm} (no model loaded)\n")
            log.write("--moe-cache-auto resolved moe_cache_size=2700 num_pages=1536 (stub)\n")

    def maintenance(self) -> str:
        with self.lock:
            if self.restart_until and time.monotonic() >= self.restart_until:
                self.restart_until = 0.0
                self.backend_epoch += 1
            return "restarting" if self.restart_until else "serving"

    def record_stat(self, key: str) -> None:
        with self.lock, self.stats_out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"t": time.time(), "key": key, "arm": self.arm}) + "\n")

    def record_event(self, name: str, key: str) -> None:
        with self.lock, self.stats_out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": name, "t": time.time(), "key": key, "arm": self.arm}) + "\n")

    def append_prefill(self, segments: list[int], cached: int) -> None:
        lines = [f"INFO Prefill batch, #new-seq: 1, #new-token: {seg}, #cached-token: {cached if i == 0 else 0}, "
                 "token usage: 0.89" for i, seg in enumerate(segments)]
        if lines:
            with self.serve_log.open("a", encoding="utf-8") as log:
                log.write("\n".join(lines) + "\n")

    def plan_for(self, key: str, traj: str, k: int) -> tuple[float, list[int], int, int]:
        """返回 (预填秒数, 切段列表, 实际回报的 cached, prompt_tokens)。"""
        if key == "warm/00":
            return WARMUP_S, [], 0, 6
        expect = self.prereg["trajectories"][traj]["rounds"][k]
        segments = self.override.get(key) or (expect["on_segments"] if self.arm == "on" else expect["off_segments"])
        cached = 0 if key == self.wrong_cached else expect["cached"]
        if expect["class"] == "cold" and traj == "seed_real":
            prefill_s = COLD_SEED_S
        else:
            prefill_s = len(segments) * PASS_S
        return prefill_s, list(segments), cached, expect["prompt_tokens"]

    def enter_restart(self) -> None:
        with self.lock:
            self.restart_until = time.monotonic() + self.recover_s

    def chat(self, handler: BaseHTTPRequestHandler, payload: dict) -> None:
        msg_sha = messages_sha256(payload["messages"])
        if msg_sha not in self.by_sha:
            send_json(handler, 400, {"error": {"message": "stub: unknown payload", "type": "invalid_request"}})
            return
        if self.dead:
            send_json(handler, 503, {"error": {"message": "server unavailable: worker is gone"}})
            return
        if self.maintenance() != "serving":
            send_json(handler, 503, {"error": {"message": "server unavailable: engine is restarting"}})
            return
        key, traj, k = self.by_sha[msg_sha]
        with self.lock:
            self.active += 1
        self.record_stat(key)
        handler.send_response(200)
        handler.send_header("content-type", "text/event-stream")
        handler.end_headers()
        write_event(handler, {"choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0,
                                           "finish_reason": None}]})
        prefill_s, segments, cached, prompt = self.plan_for(key, traj, k)
        time.sleep(prefill_s * self.scale)
        self.append_prefill(segments, cached)
        if key == self.worker_exit_at:
            # 中途退出：写出若干 token，写入退出标记，然后关闭连接（不发结束包，不发 [DONE]）。
            # 挂起参数大于 0 时，先挂起这么多秒再关闭（模拟服务端不关连接，只能靠在途实时监视识别）
            for i in range(4):
                write_event(handler, {"choices": [{"delta": {"reasoning_content": f"t{i} "}, "index": 0,
                                                   "finish_reason": None}]})
            with self.serve_log.open("a", encoding="utf-8") as log:
                log.write("[ERROR] Backend worker is gone (stub mid-request exit)\n")
            self.record_event("worker_exit", key)
            self.dead = True
            if self.worker_exit_hold_s > 0:
                time.sleep(self.worker_exit_hold_s)
            return
        if key == self.oom_at:
            write_event(handler, {"error": {"message": OOM_MESSAGE, "type": "server_error"}})
            self.enter_restart()
            return
        max_tokens = int(payload.get("max_tokens") or 32)
        for i in range(max_tokens):
            if i:
                time.sleep(ITL_S * self.scale)
            write_event(handler, {"choices": [{"delta": {"reasoning_content": f"t{i} "}, "index": 0,
                                               "finish_reason": None}]})
        write_event(handler, {"choices": [{"delta": {}, "index": 0, "finish_reason": "length"}]})
        usage: dict = {"prompt_tokens": prompt, "completion_tokens": max_tokens, "total_tokens": prompt + max_tokens}
        if cached:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
        write_event(handler, {"choices": [], "usage": usage})
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()
        with self.lock:
            self.active -= 1
            self.completed += 1


class Handler(BaseHTTPRequestHandler):
    server_version = "op-hak-stub"

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名
        stub: Stub = self.server.stub  # type: ignore[attr-defined]
        if self.path == "/health" and stub.dead:
            send_json(self, 503, {"status": "error", "model": MODEL, "maintenance": "stopped"})
        elif self.path == "/health":
            send_json(self, 200, {"status": "ok", "model": MODEL, "maintenance": stub.maintenance(),
                                  "backend_epoch": stub.backend_epoch, "restart_attempts": 0,
                                  "restart_waiters": 0})
        elif self.path.startswith("/v1/stats"):
            send_json(self, 200, {"requests": {"active": stub.active, "completed": stub.completed},
                                  "recovery": {"maintenance": stub.maintenance(),
                                               "backend_epoch": stub.backend_epoch}})
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
        stub.chat(self, payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - 保持签名
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="op-hak 任务 A 桩服务（只用于演练）")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--arm", choices=["on", "off"], required=True)
    parser.add_argument("--serve-log", required=True)
    parser.add_argument("--stats-out", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--oom-at", default=None)
    parser.add_argument("--worker-exit-at", default=None)
    parser.add_argument("--worker-exit-hold-s", type=float, default=0.0)
    parser.add_argument("--wrong-cached", default=None)
    parser.add_argument("--segments-override", default=None)
    parser.add_argument("--oom-recover-s", type=float, default=10.0)
    args = parser.parse_args()
    stub = Stub(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.stub = stub  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
