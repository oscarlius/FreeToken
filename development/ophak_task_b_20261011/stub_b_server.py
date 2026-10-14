#!/usr/bin/env python3
"""桩服务（op-hak 任务 B 演练专用，只用标准库）。

不加载模型，不占 GPU，不监听 8095。行为按 PREREG_TASK_B_v2 模拟：
- 每条请求先立即发 role 包（与生产相同），再等预填时间，再把 Prefill batch 行写入 serve.log，再逐 token 输出；
- 预填时间：warmup 0.5 秒；seed_real 冷轮两臂相同（18.6 秒）；其它轮按"切段数 × 单遍时长"（单遍 2.7775 秒）。
  这是对预登记的复现，用来演练工装的算术与判读路径，不是对生产的测量，演练结果不能当作证据。
- 启动时写入 Parsed arguments：--parsed-min-tokens 为 absent 时不含该字段（release-e2 的行为），否则含
  prefill_anchor_cut_min_tokens=<值>。
- 注入：--oom-at KEY（该请求输出 OOM 错误并进入重启）；--worker-exit-at KEY（写出 4 个 token，写入退出标记并断开；
  --worker-exit-hold-s S 则先挂起 S 秒不断开）；--output-tweak KEY（该请求第一个 token 改一个字符，用于演练 a）。
KEY 形如 T2/05。
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


def parsed_block(min_tokens: str) -> str:
    """与 args.py 的 logger.info(f"Parsed arguments:\\n{result}") 同形：标题行后紧跟一行 ServerArgs 的单行 repr。"""
    extra = "" if min_tokens == "absent" else f", prefill_anchor_cut_min_tokens={min_tokens}"
    return f"INFO Parsed arguments:\nServerArgs(model_path='{MODEL}', prefill_anchor_cut=True{extra}, port=0)\n"


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
        inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        self.prereg = json.loads(Path(args.prereg).read_text(encoding="utf-8"))
        self.by_sha: dict[str, tuple[str, str, int]] = {inputs["warmup"]["messages_sha256"]: ("warm/00", "warm", 0)}
        for row in inputs["rounds"]:
            key = f'{row["trajectory"]}/{row["round"]:02d}'
            self.by_sha[row["messages_sha256"]] = (key, row["trajectory"], row["round"])
        self.oom_at = args.oom_at
        self.worker_exit_at = args.worker_exit_at
        self.worker_exit_hold_s = args.worker_exit_hold_s
        self.output_tweak = args.output_tweak
        self.recover_s = args.oom_recover_s
        self.dead = False
        self.lock = threading.Lock()
        self.restart_until = 0.0
        self.backend_epoch = 0
        with self.serve_log.open("a", encoding="utf-8") as log:
            log.write(f"stub server arm={self.arm} (no model loaded)\n")
            log.write(parsed_block(args.parsed_min_tokens))
            log.write("--moe-cache-auto resolved moe_cache_size=2700 num_pages=1536 (stub)\n")

    def maintenance(self) -> str:
        with self.lock:
            if self.restart_until and time.monotonic() >= self.restart_until:
                self.restart_until = 0.0
                self.backend_epoch += 1
            return "restarting" if self.restart_until else "serving"

    def enter_restart(self) -> None:
        with self.lock:
            self.restart_until = time.monotonic() + self.recover_s

    def append_prefill(self, segments: list[int], cached: int) -> None:
        lines = [f"INFO Prefill batch, #new-seq: 1, #new-token: {seg}, #cached-token: {cached if i == 0 else 0}, "
                 "token usage: 0.89" for i, seg in enumerate(segments)]
        if lines:
            with self.serve_log.open("a", encoding="utf-8") as log:
                log.write("\n".join(lines) + "\n")

    def plan_for(self, key: str, traj: str, k: int) -> tuple[float, list[int], int, int]:
        """返回 (预填秒数, 切段列表, 回报的 cached, prompt_tokens)。"""
        if key == "warm/00":
            return WARMUP_S, [], 0, 6
        spec = next(s for s in self.prereg["trajectories"][traj] if s["round"] == k)
        segments = spec["on_segments"] if self.arm == "on" else spec["thresh_segments"]
        if spec["class"].startswith("cold") and traj == "seed_real":
            prefill_s = COLD_SEED_S
        else:
            prefill_s = len(segments) * PASS_S
        return prefill_s, list(segments), spec["cached"], spec["prompt_tokens"]

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
            for i in range(4):
                write_event(handler, {"choices": [{"delta": {"reasoning_content": f"t{i} "}, "index": 0,
                                                   "finish_reason": None}]})
            with self.serve_log.open("a", encoding="utf-8") as log:
                log.write("[ERROR] Backend worker is gone (stub mid-request exit)\n")
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
            text = f"t{i} "
            if i == 0 and key == self.output_tweak:
                text = "T0 "  # 演练 a：只改第一个 token 的一个字符
            write_event(handler, {"choices": [{"delta": {"reasoning_content": text}, "index": 0,
                                               "finish_reason": None}]})
        write_event(handler, {"choices": [{"delta": {}, "index": 0, "finish_reason": "length"}]})
        usage: dict = {"prompt_tokens": prompt, "completion_tokens": max_tokens, "total_tokens": prompt + max_tokens}
        if cached:
            usage["prompt_tokens_details"] = {"cached_tokens": cached}
        write_event(handler, {"choices": [], "usage": usage})
        handler.wfile.write(b"data: [DONE]\n\n")
        handler.wfile.flush()


class Handler(BaseHTTPRequestHandler):
    server_version = "op-hak-stub-b"

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名
        stub: Stub = self.server.stub  # type: ignore[attr-defined]
        if self.path == "/health" and stub.dead:
            send_json(self, 503, {"status": "error", "model": MODEL, "maintenance": "stopped"})
        elif self.path == "/health":
            send_json(self, 200, {"status": "ok", "model": MODEL, "maintenance": stub.maintenance(),
                                  "backend_epoch": stub.backend_epoch, "restart_attempts": 0,
                                  "restart_waiters": 0})
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
    parser = argparse.ArgumentParser(description="op-hak 任务 B 桩服务（只用于演练）")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--arm", choices=["on", "thresh"], required=True)
    parser.add_argument("--serve-log", required=True)
    parser.add_argument("--stats-out", required=True)  # 与 runner 的参数表一致；本桩不写统计
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--parsed-min-tokens", required=True, help="absent，或写入 Parsed arguments 的整数值")
    parser.add_argument("--oom-at", default=None)
    parser.add_argument("--worker-exit-at", default=None)
    parser.add_argument("--worker-exit-hold-s", type=float, default=0.0)
    parser.add_argument("--output-tweak", default=None)
    parser.add_argument("--oom-recover-s", type=float, default=10.0)
    parser.add_argument("--exit-before-ready", choices=["oom", "plain"], default=None,
                        help="没到 ready 就退出（演练：启动失败）；oom 时先写出 OOM 文本")
    args = parser.parse_args()
    if args.exit_before_ready:
        with Path(args.serve_log).open("a", encoding="utf-8") as log:
            if args.exit_before_ready == "oom":
                log.write("RuntimeError: CUDA out of memory while loading weights (stub)\n")
        raise SystemExit(3)
    stub = Stub(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.stub = stub  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
