#!/usr/bin/env python3
"""任务 S 运行器（op-hak）：会话 A 持续输出，B 事件顺序发送，记录停顿、零输出与混入，再按预登记判读。

按 OPHAK_TASK_S_STALL_20261011.md 执行：§3 测量，§4 前置检查，§5 停止规则，§7 判读（纯计算在 stall_core.py）。
httpx 直连（trust_env=False），不绕代理，不重试。任何失败记录后停止。

子命令：
  precheck  只读前置检查（§4）。通过返回 0，否则 3。
  run       先做前置检查，通过后执行 13 个事件，原始记录写入 --run-dir；随后判读。
  judge     读取 --run-dir 的原始记录，按预登记判读，写 result.json。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stall_core as core  # noqa: E402

DEFAULT_ENDPOINT = "http://172.16.108.9:8095"
DEFAULT_ACTIVE_JSON = Path("/data2/FreeToken/run/production.active.json")
DEFAULT_GPU_LOCK = Path("/data2/_shared/gpu.lock")
DEFAULT_STOP_FILE = Path("/data2/FreeToken/plan/OPHAK_TASK_S_STOP.md")
DEFAULT_PREREG = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_S_v2.json")
DEFAULT_TASK_A_DIR = Path("/data2/FreeToken/development/ophak_task_a_20261011")
DEFAULT_L64 = Path("/data2/FreeToken/development/gemini_oom_hybrid_20261011/inputs/L64.json")
JSON_HEADERS = {"content-type": "application/json"}
READ_TIMEOUT_S = 120.0


class StopRun(Exception):
    """停止规则触发或前置条件失败：记录原因后结束运行，不重试。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Ledger:
    """我方在途请求数（A 会话 + B 请求）。"""

    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def inc(self) -> None:
        with self._lock:
            self._n += 1

    def dec(self) -> None:
        with self._lock:
            self._n -= 1

    @property
    def value(self) -> int:
        with self._lock:
            return self._n


class AStream:
    """会话 A：持续输出的流式请求。记录每个非空增量的单调时刻；连接结束或被我方关闭时 ended 置位。"""

    def __init__(self, endpoint: str, body: bytes, clock: Callable[[], float], read_timeout_s: float,
                 ledger: Ledger) -> None:
        self.endpoint = endpoint
        self.body = body
        self.clock = clock
        self.read_timeout_s = read_timeout_s
        self.ledger = ledger
        self.times: list[float] = []
        self.tool_times: list[float] = []
        self.opened_at: float | None = None
        self.ended = False
        self.ended_at: float | None = None
        self.error: str | None = None
        self.closed_by_us = False
        self._lock = threading.Lock()
        self._client: httpx.Client | None = None
        self._counted = False

    def start(self) -> None:
        self.opened_at = self.clock()
        self.ledger.inc()
        self._counted = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            with httpx.Client(trust_env=False, timeout=self.read_timeout_s) as client:
                self._client = client
                with client.stream("POST", f"{self.endpoint}/v1/chat/completions", content=self.body,
                                   headers=JSON_HEADERS) as response:
                    if response.status_code != 200:
                        self.error = f"http {response.status_code}"
                        return
                    for line in response.iter_lines():
                        kind, chunk = core.parse_sse_line(line)
                        if kind == "done":
                            break
                        if kind != "chunk":
                            continue
                        info = core.classify_chunk(chunk)
                        now = self.clock()
                        if info["error"]:
                            self.error = json.dumps(info["error"], ensure_ascii=False)[:300]
                            break
                        with self._lock:
                            if info["nonempty"]:
                                self.times.append(now)
                            if info["tool_calls"]:
                                self.tool_times.append(now)
        except Exception as exc:  # 被我方关闭或连接中断：记录，不重试
            if not self.closed_by_us:
                self.error = repr(exc)[:300]
        finally:
            self.ended = True
            self.ended_at = self.clock()
            if self._counted:
                self._counted = False
                self.ledger.dec()

    def close(self) -> None:
        self.closed_by_us = True
        client = self._client
        if client is not None:
            try:
                client.close()
            except Exception:  # 关闭时读线程可能已结束
                pass

    def snapshot(self, after: float | None = None) -> list[float]:
        with self._lock:
            if after is None:
                return list(self.times)
            return [t for t in self.times if t > after]


def run_b(endpoint: str, body: bytes, clock: Callable[[], float], client: httpx.Client, ledger: Ledger,
          holder: dict) -> dict:
    """事件 B：一次流式请求，复用运行开始时建立的客户端（建立客户端的开销不计入 A 与 B 之间的间隔）。
    t_d 为发出时刻，t_f 为首个非空增量时刻，usage 取自末尾的 usage 包。"""
    rec: dict[str, Any] = {"status": None, "error": None, "http_status": None, "t_d": None, "t_f": None,
                           "t_end": None, "usage": None, "finish_reason": None}
    ledger.inc()
    try:
        holder["client"] = client
        rec["t_d"] = clock()
        with client.stream("POST", f"{endpoint}/v1/chat/completions", content=body,
                           headers=JSON_HEADERS) as response:
            rec["http_status"] = response.status_code
            if response.status_code != 200:
                rec["error"] = f"http {response.status_code}"
            else:
                done = False
                for line in response.iter_lines():
                    kind, chunk = core.parse_sse_line(line)
                    if kind == "done":
                        done = True
                        break
                    if kind != "chunk":
                        continue
                    info = core.classify_chunk(chunk)
                    now = clock()
                    if info["error"]:
                        rec["error"] = json.dumps(info["error"], ensure_ascii=False)[:300]
                        break
                    if info["nonempty"] and rec["t_f"] is None:
                        rec["t_f"] = now
                    if info["usage"]:
                        rec["usage"] = info["usage"]
                    if info["finish_reason"]:
                        rec["finish_reason"] = info["finish_reason"]
                if done and rec["usage"] and rec["error"] is None:
                    rec["status"] = "ok"
                elif rec["error"] is None:
                    rec["error"] = "no usage or no [DONE]"
    except Exception as exc:  # 连接中断、超时或被监视线程关闭：记录，不重试
        rec["error"] = repr(exc)[:300]
    finally:
        rec["t_end"] = clock()
        ledger.dec()
    if rec["status"] is None:
        rec["status"] = "request_error"
    return rec


class StatsSampler(threading.Thread):
    """每 interval 秒读一次 /v1/stats。ours 取读数前后我方在途数的较大者，避免把刚开始的请求误判为混入。"""

    def __init__(self, read_fn: Callable[[], dict], interval_s: float, clock: Callable[[], float],
                 ledger: Ledger) -> None:
        super().__init__(daemon=True)
        self.read_fn = read_fn
        self.interval_s = interval_s
        self.clock = clock
        self.ledger = ledger
        self._lock = threading.Lock()
        self._samples: list[dict] = []
        self._stop_flag = threading.Event()

    def run(self) -> None:
        while not self._stop_flag.is_set():
            before = self.ledger.value
            t = self.clock()
            try:
                req = self.read_fn()
                sample = {"t": t, "active": int(req["active"]), "completed": int(req["completed"]),
                          "prompt_tokens_total": req.get("prompt_tokens_total")}
            except Exception as exc:  # 失败只记录，不重试
                sample = {"t": t, "error": repr(exc)[:200]}
            sample["ours"] = max(before, self.ledger.value)
            with self._lock:
                self._samples.append(sample)
            self._stop_flag.wait(self.interval_s)

    def stop(self) -> None:
        self._stop_flag.set()

    def snapshot(self) -> list[dict]:
        with self._lock:
            return list(self._samples)

    def completed_before(self, t: float) -> int | None:
        for sample in reversed(self.snapshot()):
            if sample["t"] <= t and "completed" in sample:
                return sample["completed"]
        return None

    def first_after(self, t: float, timeout_s: float) -> dict | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for sample in self.snapshot():
                if sample["t"] >= t and "completed" in sample:
                    return sample
            time.sleep(0.02)
        return None


class LogFile:
    """serve.log 的按偏移读取（生产日志与演练日志共用）。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def read_between(self, start: int, end: int) -> str:
        if end <= start or not self.path.exists():
            return ""
        with self.path.open("rb") as handle:
            handle.seek(start)
            return handle.read(end - start).decode("utf-8", "replace")


class Monitor(threading.Thread):
    """每 interval 秒查 /health 与 serve.log 新增内容。不是 serving，或出现 OOM / worker 标记，即调用 trip。"""

    def __init__(self, health_fn: Callable[[], dict], serve_log: Path, interval_s: float,
                 clock: Callable[[], float], trip: Callable[[str], None]) -> None:
        super().__init__(daemon=True)
        self.health_fn = health_fn
        self.log = LogFile(serve_log)
        self.interval_s = interval_s
        self.clock = clock
        self.trip = trip
        self.readings: list[dict] = []
        self.offset = self.log.size()
        self._stop_flag = threading.Event()

    def scan_log(self) -> str | None:
        end = self.log.size()
        text = self.log.read_between(self.offset, end)
        self.offset = end
        for line in text.splitlines():
            if core.OOM_TEXT_RE.search(line):
                return f"oom: {line[:200]}"
            if core.WORKER_MARKER_RE.search(line):
                return f"worker_exit: {line[:200]}"
        return None

    def run(self) -> None:
        while not self._stop_flag.is_set():
            t = self.clock()
            try:
                doc = self.health_fn()
                healthy = doc.get("status") == "ok" and doc.get("maintenance") == "serving"
                entry: dict[str, Any] = {"t": t, "status": doc.get("status"), "maintenance": doc.get("maintenance"),
                                         "healthy": healthy}
            except Exception as exc:
                healthy = False
                entry = {"t": t, "error": repr(exc)[:200], "healthy": False}
            hit = self.scan_log()
            entry["log_marker"] = hit
            self.readings.append(entry)
            if not healthy:
                self.trip(f"/health 不为 serving：{entry}")
            elif hit:
                self.trip(f"serve.log 标记：{hit}")
            self._stop_flag.wait(self.interval_s)

    def stop(self) -> None:
        self._stop_flag.set()


def read_stats(endpoint: str) -> dict:
    with httpx.Client(trust_env=False, timeout=10.0) as client:
        response = client.get(f"{endpoint}/v1/stats")
        response.raise_for_status()
        return response.json()["requests"]


def read_health(endpoint: str) -> dict:
    with httpx.Client(trust_env=False, timeout=10.0) as client:
        response = client.get(f"{endpoint}/health")
        response.raise_for_status()
        return response.json()


def proc_hits(needle: str) -> list[int]:
    """/proc 中 argv 含名为 needle 的脚本的进程（排除本进程与父进程）。"""
    me, parent = os.getpid(), os.getppid()
    hits = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in (me, parent):
            continue
        try:
            argv = [a.decode("utf-8", "replace") for a in (entry / "cmdline").read_bytes().split(b"\0") if a]
        except OSError:
            continue
        if any(Path(a).name == needle for a in argv):
            hits.append(int(entry.name))
    return hits


def read_gpu_mib() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, check=False).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def run_precheck(*, timing: core.Timing, endpoint: str, active_json: Path, gpu_lock: Path, stop_file: Path,
                 read_health_fn: Callable[[], dict], read_stats_fn: Callable[[], dict],
                 sleep: Callable[[float], None], clock: Callable[[], float],
                 hits_fn: Callable[[str], list[int]], read_text: Callable[[Path], str]) -> dict:
    """§4 前置检查。全部条件满足才算通过；任一不满足即 pass = False，由调用方停下。"""
    checks: dict[str, dict] = {}
    health = read_health_fn()
    checks["health_serving"] = {
        "pass": (health.get("status") == "ok" and health.get("maintenance") == "serving"
                 and health.get("backend_epoch") == 0 and health.get("restart_attempts") == 0),
        "value": {k: health.get(k) for k in ("status", "maintenance", "backend_epoch", "restart_attempts")}}
    samples: list[dict] = []
    t0 = clock()
    steps = int(round(timing.precheck_s / timing.precheck_step_s))
    for i in range(steps + 1):
        if i:
            sleep(timing.precheck_step_s)
        req = read_stats_fn()
        samples.append({"t": round(clock() - t0, 3), "active": req.get("active"),
                        "completed": req.get("completed"), "prompt_tokens_total": req.get("prompt_tokens_total")})
    checks["idle_window"] = {
        "pass": all(s["active"] == 0 for s in samples) and len({s["completed"] for s in samples}) == 1,
        "samples": len(samples)}
    last = samples[-1]
    checks["cache_state"] = {
        "pass": last["completed"] == 2 and last["prompt_tokens_total"] == 8769,
        "completed": last["completed"], "prompt_tokens_total": last["prompt_tokens_total"]}
    checks["stop_file_absent"] = {"pass": not stop_file.exists()}
    hits = hits_fn("task_a_runner.py")
    checks["no_task_a_runner"] = {"pass": not hits, "pids": hits}
    active = json.loads(read_text(active_json))
    token = (active.get("gpu_owner") or {}).get("lock_token")
    lock_text = read_text(gpu_lock)
    checks["gpu_lock_matches_owner_token"] = {"pass": token is not None and lock_text == token}
    log_path = active.get("log")
    checks["serve_log_present"] = {"pass": bool(log_path) and Path(log_path).exists(), "path": log_path}
    return {"pass": all(c["pass"] for c in checks.values()), "endpoint": endpoint, "checks": checks,
            "samples": samples}


def build_events(prereg_path: Path, inputs_path: Path, task_a_dir: Path, l64_path: Path) -> list[dict]:
    """13 个事件（§3.2 顺序）：T2 第 0–11 轮（原样字节）与 L64（只改 max_tokens）。每个事件先校验 SHA。"""
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    spec = {e["event"]: e for e in prereg["events"]}
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    rows = {f'{r["trajectory"]}/{r["round"]:02d}': r for r in inputs["rounds"] if r["trajectory"] == "T2"}
    events = []
    for name in [f"T2/{k:02d}" for k in range(12)] + ["L64"]:
        s = spec[name]
        if name == "L64":
            raw = l64_path.read_bytes()
            body = core.build_l64_body(raw)
            source_sha = core.sha256_hex(raw)
            kind = "L64"
        else:
            row = rows[name]
            raw = (task_a_dir / row["file"]).read_bytes()
            core.check_payload_sha(raw, row["sha256"], name)
            doc = json.loads(raw.decode("utf-8"))
            if core.messages_sha256(doc["messages"]) != row["messages_sha256"]:
                raise ValueError(f"{name} 的 messages 与 INPUTS.json 不符")
            body = raw
            source_sha = row["sha256"]
            kind = "T2"
        events.append({"name": name, "kind": kind, "body": body, "body_sha256": core.sha256_hex(body),
                       "source_sha256": source_sha, "segments": s["segments_expected"],
                       "cached": s["cached_expected"], "band": s["stall_band_s"], "pred": s["prefill_pred_s"]})
    return events


class Campaign:
    """§3 的事件循环：A 先发并收够 50 个增量；每个 B 发出前检查 A 的运行时长（> 300 s 则重启 A）；
    B 结束后等 A 再收够 30 个增量。任何 OOM、worker 标记或 /health 非 serving 立即停止。"""

    def __init__(self, *, timing: core.Timing, events: list[dict], endpoint: str, serve_log: Path,
                 out_dir: Path, a_body: bytes, read_stats_fn: Callable[[], dict],
                 read_health_fn: Callable[[], dict], gpu_fn: Callable[[], int | None],
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.timing = timing
        self.events = events
        self.endpoint = endpoint
        self.out_dir = out_dir
        self.a_body = a_body
        self.read_stats = read_stats_fn
        self.gpu = gpu_fn
        self.clock = clock
        self.sleep = sleep
        self.ledger = Ledger()
        self.abort = threading.Event()
        self.abort_reason: str | None = None
        self.a: AStream | None = None
        self.a_instances: list[AStream] = []
        self.a_opened_at: list[float] = []
        self.restarts: list[dict] = []
        self.records: list[dict] = []
        self.log = LogFile(serve_log)
        self.sampler = StatsSampler(read_stats_fn, timing.stats_s, clock, self.ledger)
        self.monitor = Monitor(read_health_fn, serve_log, timing.health_s, clock, self.trip)
        self.t0 = 0.0
        self.read_timeout_s = READ_TIMEOUT_S
        self.b_client: httpx.Client | None = None

    def trip(self, reason: str) -> None:
        if self.abort_reason is None:
            self.abort_reason = reason
        self.abort.set()

    def note(self, text: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {text}"
        print(line, flush=True)
        with (self.out_dir / "run.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def check(self) -> None:
        if self.abort.is_set():
            raise StopRun(self.abort_reason or "abort")
        if self.clock() - self.t0 > self.timing.total_limit_s:
            raise StopRun("总时限 15 分钟已到")

    def open_a(self, reason: str) -> None:
        self.a = AStream(self.endpoint, self.a_body, self.clock, self.read_timeout_s, self.ledger)
        self.a.start()
        self.a_instances.append(self.a)
        self.a_opened_at.append(self.a.opened_at)
        self.note(f"A 开始（{reason}）")

    def wait_a_deltas(self, n: int, after: float | None = None) -> None:
        deadline = self.clock() + self.timing.a_delta_wait_s
        while True:
            self.check()
            if len(self.a.snapshot(after)) >= n:
                return
            if self.a.ended:
                raise StopRun(f"A 在收够 {n} 个非空增量前结束：{self.a.error}")
            if self.clock() > deadline:
                raise StopRun(f"等待 A 的 {n} 个非空增量超时")
            self.sleep(min(0.05, self.timing.stats_s / 10))

    def wait_active_zero(self) -> float:
        start = self.clock()
        deadline = start + self.timing.active_wait_s
        while True:
            self.check()
            if int(self.read_stats()["active"]) == 0:
                return self.clock() - start
            if self.clock() > deadline:
                raise StopRun("等待 active 归零超时")
            self.sleep(self.timing.stats_s)

    def restart_a(self, reason: str) -> None:
        closed_at = self.clock()
        if self.a is not None and not self.a.ended:
            self.a.close()
        waited = self.wait_active_zero()
        self.open_a(f"重启：{reason}")
        self.wait_a_deltas(core.A_START_DELTAS)
        self.restarts.append({"reason": reason, "closed_at": closed_at, "active_zero_wait_s": round(waited, 3),
                              "reopened_at": self.a.opened_at, "start_deltas_at": self.clock()})

    def run_event(self, ev: dict) -> dict:
        # §3.1：发出 B 之前检查 A 的运行时长。检查紧贴发出（之间只有线程启动与一次网络写入）
        if self.clock() - self.a.opened_at > self.timing.a_restart_s:
            self.restart_a("A 运行超过重启阈值")
        t_pre = self.clock()
        off0 = self.log.size()
        gpu_before = self.gpu()
        holder: dict[str, Any] = {}
        box: dict[str, Any] = {}
        worker = threading.Thread(target=lambda: box.update(run_b(self.endpoint, ev["body"], self.clock,
                                                                  self.b_client, self.ledger, holder)),
                                  daemon=True)
        worker.start()
        while worker.is_alive():
            if self.abort.is_set() and self.b_client is not None:
                self.b_client.close()
                break
            worker.join(0.05)
        worker.join(timeout=5.0 * self.timing.scale + 1.0)
        rec: dict[str, Any] = {"name": ev["name"], "kind": ev["kind"], "body_sha256": ev["body_sha256"],
                               "source_sha256": ev["source_sha256"], "t_pre": t_pre}
        for key in ("status", "error", "http_status", "t_d", "t_f", "t_end", "usage", "finish_reason"):
            rec[key] = box.get(key)
        if self.abort.is_set() and rec["status"] != "ok":
            rec["status"] = "aborted"
        self.sleep(self.timing.settle_s)
        rec["prefill_lines"] = core.parse_prefill_lines(self.log.read_between(off0, self.log.size()))
        rec["gpu_before_mib"] = gpu_before
        rec["gpu_after_mib"] = self.gpu()
        t_after = self.clock()
        rec["t_after"] = t_after
        rec["before_completed"] = self.sampler.completed_before(t_pre)
        sample_after = self.sampler.first_after(t_after, 3.0 * self.timing.stats_s + 0.5)
        rec["after_completed"] = sample_after["completed"] if sample_after else None
        a_ended_in = self.a.ended_at is not None and t_pre < self.a.ended_at <= t_after
        b_done_in = rec["t_end"] is not None and rec["status"] == "ok" and rec["t_end"] <= t_after
        rec["our_completions"] = int(b_done_in) + int(a_ended_in)
        rec["invalid_a_ended"] = (self.a.ended_at is not None and rec["t_end"] is not None
                                  and self.a.ended_at < rec["t_end"])
        rec["t_end_wall"] = rec["t_end"]
        return rec

    def persist_event(self, rec: dict) -> None:
        with (self.out_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def run(self) -> dict:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.t0 = self.clock()
        status, reason = "complete", None
        self.b_client = httpx.Client(trust_env=False, timeout=self.read_timeout_s)
        try:
            self.sampler.start()
            self.monitor.start()
            self.open_a("起始")
            self.wait_a_deltas(core.A_START_DELTAS)
            for ev in self.events:
                self.check()
                self.note(f"事件 {ev['name']}：发送 B")
                rec = self.run_event(ev)
                self.records.append(rec)
                self.persist_event(rec)
                self.note(f"事件 {ev['name']}：{rec['status']}  t_f−t_d="
                          f"{None if rec['t_f'] is None or rec['t_d'] is None else round(rec['t_f'] - rec['t_d'], 3)}")
                if rec["status"] != "ok":
                    raise StopRun(f"{ev['name']}：{rec['status']}：{rec.get('error')}")
                if self.a.ended or rec["invalid_a_ended"]:
                    self.restart_a("A 在 B 之外或之中结束")
                else:
                    self.wait_a_deltas(core.A_AFTER_B_DELTAS, after=rec["t_end"])
        except StopRun as exc:
            status, reason = "stopped", exc.reason
        except Exception as exc:  # 运行器异常：记录后停止
            status, reason = "runner_exception", repr(exc)[:300]
        finally:
            if self.a is not None:
                self.a.close()
            self.b_client.close()
            self.sampler.stop()
            self.monitor.stop()
        summary = self.write_outputs(status, reason)
        self.note(f"结束：{status} {reason or ''}")
        return summary

    def write_outputs(self, status: str, reason: str | None) -> dict:
        # 所有 A 会话的非空增量合并：重启前的增量也参与前面事件的停顿与零输出计算
        a_times = sorted(t for instance in self.a_instances for t in instance.snapshot())
        (self.out_dir / "a_times.json").write_text(json.dumps(a_times), encoding="utf-8")
        with (self.out_dir / "samples.jsonl").open("w", encoding="utf-8") as handle:
            for sample in self.sampler.snapshot():
                handle.write(json.dumps(sample) + "\n")
        with (self.out_dir / "monitor.jsonl").open("w", encoding="utf-8") as handle:
            for entry in self.monitor.readings:
                handle.write(json.dumps(entry) + "\n")
        run_doc = {"status": status, "reason": reason, "scale": self.timing.scale, "endpoint": self.endpoint,
                   "started_at": self.t0, "ended_at": self.clock(), "events_planned": len(self.events),
                   "events_run": len(self.records), "restarts": self.restarts,
                   "a_opened_at": self.a_opened_at, "a_restart_s": self.timing.a_restart_s,
                   "a_start_deltas_seen": len(a_times),
                   "a_error": self.a.error if self.a is not None else None}
        (self.out_dir / "run.json").write_text(json.dumps(run_doc, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        return run_doc


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def judge_run(run_dir: Path) -> dict:
    """§7 判读：只读原始记录，按预登记 v2 计算。"""
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").exists() \
        else {"scale": 1.0, "status": "no_run"}
    timing = core.Timing(float(run.get("scale", 1.0)))
    prereg_path = Path(run.get("prereg", DEFAULT_PREREG))
    spec = {e["event"]: e for e in json.loads(prereg_path.read_text(encoding="utf-8"))["events"]}
    events = read_jsonl(run_dir / "events.jsonl")
    a_times = json.loads((run_dir / "a_times.json").read_text(encoding="utf-8")) \
        if (run_dir / "a_times.json").exists() else []
    samples = read_jsonl(run_dir / "samples.jsonl")
    judged = []
    for rec in events:
        s = spec[rec["name"]]
        ev = dict(rec, segments=s["segments_expected"], cached=s["cached_expected"], band=s["stall_band_s"],
                  pred=s["prefill_pred_s"])
        judged.append(core.judge_event(ev, a_times, samples, timing))
    zero_events = [e["name"] for e in judged if (e["zero_output"] or 0) > 0]
    result = {
        "schema": "ophak_task_s_judgement/v1",
        "run_dir": str(run_dir),
        "scale": timing.scale,
        "run_status": run.get("status"),
        "run_reason": run.get("reason"),
        "restarts": run.get("restarts", []),
        "events": judged,
        "aggregate": core.aggregate(judged),
        "zero_output_total": sum(e["zero_output"] or 0 for e in judged),
        "zero_output_events": zero_events,
        "verdict_zero_output": "成立" if not zero_events else "有零输出事件",
        "memory_mib": [{"name": e["name"], "before": e["gpu_before_mib"], "after": e["gpu_after_mib"]}
                       for e in judged],
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return result


def cmd_precheck(args: argparse.Namespace) -> int:
    timing = core.Timing(args.time_scale)
    result = run_precheck(timing=timing, endpoint=args.endpoint, active_json=args.active_json,
                          gpu_lock=args.gpu_lock, stop_file=args.stop_file,
                          read_health_fn=lambda: read_health(args.endpoint),
                          read_stats_fn=lambda: read_stats(args.endpoint), sleep=time.sleep,
                          clock=time.monotonic, hits_fn=proc_hits,
                          read_text=lambda p: Path(p).read_text(encoding="utf-8"))
    print(json.dumps({"pass": result["pass"], "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 3


def cmd_run(args: argparse.Namespace) -> int:
    timing = core.Timing(args.time_scale, args.a_restart_s)
    out = args.run_dir
    out.mkdir(parents=True, exist_ok=True)
    pre = run_precheck(timing=timing, endpoint=args.endpoint, active_json=args.active_json,
                       gpu_lock=args.gpu_lock, stop_file=args.stop_file,
                       read_health_fn=lambda: read_health(args.endpoint),
                       read_stats_fn=lambda: read_stats(args.endpoint), sleep=time.sleep,
                       clock=time.monotonic, hits_fn=proc_hits,
                       read_text=lambda p: Path(p).read_text(encoding="utf-8"))
    (out / "precheck.json").write_text(json.dumps(pre, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not pre["pass"]:
        (out / "run.json").write_text(json.dumps({"status": "precheck_failed", "scale": args.time_scale,
                                                  "prereg": str(args.prereg)}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "precheck_failed"}, ensure_ascii=False))
        return 3
    active = json.loads(args.active_json.read_text(encoding="utf-8"))
    events = build_events(args.prereg, args.inputs, args.task_a_dir, args.l64)
    a_body = core.build_a_body()
    campaign = Campaign(timing=timing, events=events, endpoint=args.endpoint, serve_log=Path(active["log"]),
                        out_dir=out, a_body=a_body,
                        read_stats_fn=lambda: read_stats(args.endpoint),
                        read_health_fn=lambda: read_health(args.endpoint),
                        gpu_fn=(lambda: None) if args.no_gpu else read_gpu_mib)
    run_doc = campaign.run()
    run_doc["prereg"] = str(args.prereg)
    run_doc["a_restart_override"] = args.a_restart_s
    (out / "run.json").write_text(json.dumps(run_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = judge_run(out)
    print(json.dumps({"status": run_doc["status"], "reason": run_doc["reason"],
                      "aggregate": result["aggregate"], "zero_output_total": result["zero_output_total"]},
                     ensure_ascii=False))
    return 0 if run_doc["status"] == "complete" else 4


def cmd_judge(args: argparse.Namespace) -> int:
    result = judge_run(args.run_dir)
    print(json.dumps({"run_status": result["run_status"], "aggregate": result["aggregate"],
                      "zero_output_total": result["zero_output_total"]}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="任务 S 停顿测量运行器（op-hak）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("precheck", "run", "judge"):
        p = sub.add_parser(name)
        p.add_argument("--time-scale", type=float, default=1.0)
        if name in ("precheck", "run"):
            p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
            p.add_argument("--active-json", type=Path, default=DEFAULT_ACTIVE_JSON)
            p.add_argument("--gpu-lock", type=Path, default=DEFAULT_GPU_LOCK)
            p.add_argument("--stop-file", type=Path, default=DEFAULT_STOP_FILE)
        if name == "run":
            p.add_argument("--run-dir", type=Path, required=True)
            p.add_argument("--prereg", type=Path, default=DEFAULT_PREREG)
            p.add_argument("--inputs", type=Path, default=DEFAULT_TASK_A_DIR / "INPUTS.json")
            p.add_argument("--task-a-dir", type=Path, default=DEFAULT_TASK_A_DIR)
            p.add_argument("--l64", type=Path, default=DEFAULT_L64)
            p.add_argument("--no-gpu", action="store_true", help="演练用：不读 nvidia-smi")
            p.add_argument("--a-restart-s", type=float, default=None,
                           help="仅演练用：覆盖 A 的重启阈值（秒）。正式运行不传，阈值为预登记的 300 秒")
        if name == "judge":
            p.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "precheck":
        return cmd_precheck(args)
    if args.cmd == "run":
        return cmd_run(args)
    return cmd_judge(args)


if __name__ == "__main__":
    raise SystemExit(main())
