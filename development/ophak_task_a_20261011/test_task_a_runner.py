"""op-hak 任务 A 工装单元测试。

不碰网络（httpx.MockTransport）、不碰 GPU、不碰 8095。窗口编排用假的启动器与假的 run_service。
覆盖指令 §3 H2 要求：非空首分片判定、Prefill 行解析、启动参数差异门（正反各一）、cached 提取、
OOM 分支、超时、清理失败分支、ABBA 顺序固定；另加请求计划、窗口时限、启动失败、请求错误、环境变量清理。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import threading
import time
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("task_a_runner", HERE / "task_a_runner.py")
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)

BASELINE = ["taskset", "-c", "1,3-47", "/data2/FreeToken/venv/bin/ft", "serve",
            "--model-path", "/m", "--host", "172.16.108.9", "--port", "8095",
            "--memory-ratio", "0.88", "--prefill-layer-major"]

@pytest.fixture(autouse=True)
def no_gpu_sampling(monkeypatch):
    """单测不调用 nvidia-smi；显存字段由专门的测试单独设置。"""
    monkeypatch.setattr(runner, "MEMORY_SAMPLER", lambda: None)


ROLE_PACKET = b'data: {"choices":[{"delta":{"role":"assistant","content":""},"index":0,"finish_reason":null}]}\n\n'
REASON_PACKET = b'data: {"choices":[{"delta":{"reasoning_content":"The"},"index":0,"finish_reason":null}]}\n\n'
USAGE_PACKET = (b'data: {"choices":[],"usage":{"prompt_tokens":87100,"completion_tokens":1,'
                b'"total_tokens":87101}}\n\n')
DONE = b"data: [DONE]\n\n"
OK_SSE = ROLE_PACKET + REASON_PACKET + USAGE_PACKET + DONE
OOM_SSE = ROLE_PACKET + (b'data: {"error": {"message": "worker_restarting_after_oom: OutOfMemoryError: '
                         b'CUDA out of memory", "type": "server_error"}}\n\n')


def fresh_outcome() -> dict:
    return {"status": "ok", "http_status": 200, "ttft_s": None, "ttft_source": None,
            "tool_call_first_s": None, "usage": None, "finish_reason": None, "error": None,
            "oom_message": None, "_parts": []}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- 首分片与 SSE

def test_role_packet_is_not_counted_as_first_token():
    out = fresh_outcome()
    role = {"choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0, "finish_reason": None}]}
    assert runner.absorb_chunk(out, role, 0.01) is False
    assert out["ttft_s"] is None
    first = {"choices": [{"delta": {"reasoning_content": "The"}, "index": 0, "finish_reason": None}]}
    runner.absorb_chunk(out, first, 2.5)
    assert out["ttft_s"] == 2.5
    assert out["ttft_source"] == "reasoning_content"


def test_tool_call_is_recorded_but_not_used_as_first_token():
    out = fresh_outcome()
    tool = {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "read_file"}}]},
                         "index": 0, "finish_reason": None}]}
    runner.absorb_chunk(out, tool, 1.0)
    assert out["ttft_s"] is None
    assert out["tool_call_first_s"] == 1.0
    assert out["_parts"] and "read_file" in out["_parts"][0]


# ---------------------------------------------------------------- Prefill 行与 cached

def test_prefill_lines_are_parsed_in_order_and_only_new_bytes_are_read(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text(
        "[1m[2026-10-11|18:24:53|core|rank=0][0m [32mINFO    [0m Prefill batch, #new-seq: 1, "
        "#new-token: 22272, #cached-token: 0, token usage: 0.89\n"
        "[INFO] Decode batch, #running-req: 1, gen throughput (token/s): 46.8\n"
        "[INFO] Prefill batch, #new-seq: 1, #new-token: 64, #cached-token: 87040, #route-reqs: 1:64\n"
        "[INFO] Prefill batch, #new-seq: 1, #new-token: 224, #cached-token: 0, #route-reqs: 1:224\n",
        encoding="utf-8")
    lines = runner.read_prefill_lines(log, 0)
    assert [(line["new_token"], line["cached_token"]) for line in lines] == [(22272, 0), (64, 87040), (224, 0)]
    assert runner.read_prefill_lines(log, log.stat().st_size) == []


def test_cached_tokens_come_from_usage_details_or_zero():
    with_details = fresh_outcome()
    runner.absorb_chunk(with_details, {"choices": [], "usage": {
        "prompt_tokens": 87328, "completion_tokens": 87,
        "prompt_tokens_details": {"cached_tokens": 87040}}}, 1.0)
    assert with_details["usage"] == {"prompt_tokens": 87328, "completion_tokens": 87, "cached_tokens": 87040}
    without = fresh_outcome()
    runner.absorb_chunk(without, {"choices": [], "usage": {"prompt_tokens": 87100, "completion_tokens": 124}}, 1.0)
    assert without["usage"]["cached_tokens"] == 0


# ---------------------------------------------------------------- argv 差异门（正反各一）

def test_argv_gate_accepts_only_host_port_and_the_appended_flag():
    on, diff_on = runner.build_argv(BASELINE, "on")
    assert on[on.index("--host") + 1] == "127.0.0.1"
    assert on[on.index("--port") + 1] == "8123"
    assert "--no-prefill-anchor-cut" not in on
    assert {d["index"] for d in diff_on} == {BASELINE.index("--host") + 1, BASELINE.index("--port") + 1}

    off, diff_off = runner.build_argv(BASELINE, "off")
    assert off[:-1] == on
    assert off[-1] == "--no-prefill-anchor-cut"
    assert diff_off[-1] == {"index": len(BASELINE), "baseline": None, "actual": "--no-prefill-anchor-cut"}
    runner.verify_argv(BASELINE, on, "on")
    runner.verify_argv(BASELINE, off, "off")


def test_argv_gate_rejects_unapproved_differences():
    on, _ = runner.build_argv(BASELINE, "on")
    off, _ = runner.build_argv(BASELINE, "off")
    bad_port = list(on)
    bad_port[bad_port.index("--port") + 1] = "8124"
    cases = [
        ("hybrid flag appended to A arm", on + ["--moe-hybrid-max-fetch", "0"], "on"),
        ("B flag appended to A arm", on + ["--no-prefill-anchor-cut"], "on"),
        ("port changed", bad_port, "on"),
        ("last token dropped", on[:-1], "on"),
        ("B argv submitted as A", off, "on"),
    ]
    for label, argv, arm in cases:
        with pytest.raises(runner.LaunchError):
            runner.verify_argv(BASELINE, argv, arm)


def test_clean_env_drops_dev_switches_and_pins_required_variables():
    env = runner.clean_env({"FT_D3_ANCHOR_MODE": "first", "FREETOKEN_X": "1", "PATH": "/bin"})
    assert "FT_D3_ANCHOR_MODE" not in env
    assert "FREETOKEN_X" not in env
    assert env["PATH"] == "/bin"
    assert env["CUDA_VISIBLE_DEVICES"] == "0"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


# ---------------------------------------------------------------- OOM 与超时（单次请求、不重试）

def test_oom_chunk_is_classified_and_sent_exactly_once():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, content=OOM_SSE, headers={"content-type": "text/event-stream"})

    out = runner.post_chat("http://stub", b"{}", transport=httpx.MockTransport(handler))
    assert out["status"] == "oom"
    assert out["oom_message"].startswith("worker_restarting_after_oom")
    assert calls == ["/v1/chat/completions"]


def test_non_oom_error_chunk_is_plain_error():
    out = runner.post_chat("http://stub", b"{}", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b'data: {"error": {"message": "bad request"}}\n\n')))
    assert out["status"] == "error"
    assert out["oom_message"] is None


def test_timeout_is_recorded_and_not_retried():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    out = runner.post_chat("http://stub", b"{}", transport=httpx.MockTransport(handler))
    assert out["status"] == "timeout"
    assert len(calls) == 1


# ---------------------------------------------------------------- 请求计划（顺序固定）

def make_fixture(root: Path) -> tuple[dict, dict]:
    """两个 seed 轮（第 0 轮冷、第 1 轮变）和一个 T2 轮（第 0 轮冷），写到 root/inputs 并返回 (inputs, prereg)。"""
    inputs_dir = root / "inputs"
    inputs_dir.mkdir()

    def write_payload(name: str, messages: list[dict]) -> dict:
        body = json.dumps({"model": "m", "messages": messages, "max_tokens": 32, "stream": True},
                          ensure_ascii=False).encode("utf-8")
        (inputs_dir / name).write_bytes(body)
        return {"file": f"inputs/{name}", "sha256": sha(body),
                "messages_sha256": runner.messages_sha256(messages)}

    warm = write_payload("warmup.json", [{"role": "user", "content": "warmup"}])
    seed0 = write_payload("seed_round_00.json", [{"role": "user", "content": "seed0"}])
    seed1 = write_payload("seed_round_01.json", [{"role": "user", "content": "seed1"}])
    t20 = write_payload("t2_round_00.json", [{"role": "user", "content": "t2-0"}])
    inputs = {"warmup": warm,
              "rounds": [{"trajectory": "seed_real", "round": 0, **seed0},
                         {"trajectory": "seed_real", "round": 1, **seed1},
                         {"trajectory": "T2", "round": 0, **t20}]}
    prereg = {"trajectories": {
        "seed_real": {"rounds": [
            {"class": "cold", "prompt_tokens": 87100, "cached": 0,
             "on_segments": [22272, 64828], "off_segments": [87100]},
            {"class": "changed", "prompt_tokens": 87328, "cached": 87040,
             "on_segments": [64, 224], "off_segments": [288],
             "on_ttft_band_s": [5.2, 6.3], "off_ttft_band_s": [2.6, 3.6]}]},
        "T2": {"rounds": [
            {"class": "cold", "prompt_tokens": 12443, "cached": 0,
             "on_segments": [512, 11931], "off_segments": [12443]}]}}}
    return inputs, prereg


def test_plan_order_is_fixed_and_arm_selects_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "WORK", tmp_path)
    inputs, prereg = make_fixture(tmp_path)
    on = runner.build_plan(inputs, prereg, "on")
    off = runner.build_plan(inputs, prereg, "off")
    assert [item["key"] for item in on] == ["warm/00", "seed_real/00", "seed_real/01", "T2/00"]
    assert on[0]["expect"] is None
    assert on[1]["expect"]["segments"] == [22272, 64828]
    assert off[1]["expect"]["segments"] == [87100]
    assert on[2]["expect"]["segments"] == [64, 224]
    assert off[2]["expect"]["segments"] == [288]
    assert on[2]["expect"]["cached"] == off[2]["expect"]["cached"] == 87040


def test_plan_refuses_a_changed_input_file(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "WORK", tmp_path)
    inputs, prereg = make_fixture(tmp_path)
    (tmp_path / "inputs" / "seed_round_01.json").write_bytes(b"{}")
    with pytest.raises(runner.RunnerError):
        runner.build_plan(inputs, prereg, "on")


# ---------------------------------------------------------------- 服务级：OOM 后不再发送

def fake_item(key: str, text: str) -> dict:
    body = json.dumps({"model": "m", "messages": [{"role": "user", "content": text}], "max_tokens": 32,
                       "stream": True}).encode("utf-8")
    return {"key": key, "trajectory": key.split("/")[0], "round": int(key.split("/")[1]),
            "file": "x", "body": body, "payload_sha256": sha(body),
            "messages_sha256": runner.messages_sha256([{"role": "user", "content": text}]), "expect": None}


def test_run_service_stops_at_oom_and_sends_nothing_after(tmp_path):
    serve_log = tmp_path / "serve.log"
    serve_log.write_text("", encoding="utf-8")
    out_dir = tmp_path / "svc"
    out_dir.mkdir()
    plan = [fake_item("seed_real/00", "a"), fake_item("seed_real/01", "b"), fake_item("T2/00", "c")]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(200, content=OOM_SSE if len(seen) == 2 else OK_SSE)

    summary = runner.run_service("http://stub", "B1_off", "off", serve_log, out_dir, plan,
                                 transport=httpx.MockTransport(handler), sleep=lambda s: None, between_s=0)
    assert summary["status"] == "oom"
    assert summary["done"] == 1
    assert seen == ["a", "b"]
    assert (out_dir / "oom_excerpt.log").exists()  # OOM 时一定写出摘录文件（此处 serve.log 为空，摘录为空）


# ---------------------------------------------------------------- 窗口编排（假启动器）

class FakeLauncher:
    def __init__(self, fail_start=(), stop_fail=()) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.fail_start = set(fail_start)
        self.stop_fail = set(stop_fail)

    def start(self, name, arm, out_dir):
        self.started.append(name)
        if name in self.fail_start:
            raise runner.LaunchError("argv gate (fake)")
        out_dir.mkdir(parents=True, exist_ok=False)
        (out_dir / "serve.log").touch()
        return runner.Handle(name, arm, "http://fake", out_dir / "serve.log", out_dir,
                             proc=None, ready=True)

    def stop(self, handle):
        self.stopped.append(handle.name)
        return handle.name not in self.stop_fail


def fake_run_service(statuses: dict, calls: list):
    def run(endpoint, name, arm, serve_log, out_dir, plan, **kwargs):
        calls.append(name)
        status = statuses.get(name, "complete")
        if status == "raise":
            raise RuntimeError("runner bug (fake)")
        return {"service": name, "arm": arm, "status": status, "done": 0,
                "planned": len(plan), "stop_reason": None}
    return run


def no_plan(arm):
    return []


def test_window_runs_abba_in_fixed_order_and_oom_stops_only_that_service(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_service", fake_run_service({"B1_off": "oom"}, calls))
    summary = runner.run_window(FakeLauncher(), runner.SERVICES, tmp_path / "w", no_plan, clock=lambda: 0.0)
    assert [name for name, _ in runner.SERVICES] == ["A1_on", "B1_off", "B2_off", "A2_on"]
    assert calls == ["A1_on", "B1_off", "B2_off", "A2_on"]
    assert [s["status"] for s in summary["services"]] == ["complete", "oom", "complete", "complete"]
    assert summary["terminal"] == "complete"


def test_cleanup_failure_stops_window_and_writes_blocked_marker(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_service", fake_run_service({}, calls))
    summary = runner.run_window(FakeLauncher(stop_fail={"B1_off"}), runner.SERVICES, tmp_path / "w", no_plan,
                                clock=lambda: 0.0)
    assert summary["terminal"] == "cleanup_blocked"
    assert calls == ["A1_on", "B1_off"]
    assert (tmp_path / "w" / "CLEANUP_BLOCKED.md").exists()


def test_time_limit_prevents_starting_the_next_service(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_service", fake_run_service({}, calls))
    readings = iter([0.0, 0.0, 3300.0] + [3300.0] * 10)  # 第二个服务开始时只剩 300 秒，低于 480 秒保留
    summary = runner.run_window(FakeLauncher(), runner.SERVICES, tmp_path / "w", no_plan,
                                clock=lambda: next(readings))
    assert calls == ["A1_on"]
    assert summary["terminal"] == "time_limit"


def test_launch_failure_is_recorded_and_next_service_runs(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_service", fake_run_service({}, calls))
    summary = runner.run_window(FakeLauncher(fail_start={"B1_off"}), runner.SERVICES, tmp_path / "w", no_plan,
                                clock=lambda: 0.0)
    assert calls == ["A1_on", "B2_off", "A2_on"]
    assert summary["services"][1]["status"] == "launch_failed"
    assert summary["terminal"] == "complete"


def test_d11p0_check_counts_only_recently_updated_d11_p0_directories(tmp_path):
    """补充 1 第 3 节：名称含 d11_p0 的顶层目录，最近 10 分钟内有更新才算 D11-P0 仍在运行。"""
    runs = tmp_path / "runs"
    (runs / "dev_gemini_d11_p0_20261011").mkdir(parents=True)
    (runs / "dev_gemini_d11_p0_20261011" / "a.jsonl").write_text("x", encoding="utf-8")
    (runs / "dev_other_20261011").mkdir()
    (runs / "dev_other_20261011" / "fresh.jsonl").write_text("x", encoding="utf-8")
    stale = runs / "dev_d11_p0_20261011"
    stale.mkdir()
    stale_file = stale / "b.jsonl"
    stale_file.write_text("y", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale_file, (old, old))
    os.utime(stale, (old, old))
    active = runner.active_d11p0_dirs(runs, now=time.time(), quiet_s=600)
    assert [Path(item["dir"]).name for item in active] == ["dev_gemini_d11_p0_20261011"]


def test_d11p0_check_passes_when_no_such_directory(tmp_path):
    assert runner.active_d11p0_dirs(tmp_path / "absent") == []


def test_request_error_and_runner_exception_stop_the_window(tmp_path, monkeypatch):
    for status, label in (("request_error", "request_error"), ("raise", "runner_exception")):
        calls: list[str] = []
        monkeypatch.setattr(runner, "run_service", fake_run_service({"B1_off": status}, calls))
        launcher = FakeLauncher()
        summary = runner.run_window(launcher, runner.SERVICES, tmp_path / label, no_plan, clock=lambda: 0.0)
        assert calls == ["A1_on", "B1_off"], label
        assert summary["terminal"] == label
        assert launcher.stopped == ["A1_on", "B1_off"], "清场必须在停止之前执行"


# ---------------------------------------------------------------- 任务 A2（续篇）

A2_FIXTURE = HERE / "fixtures" / "window01_b1_off_markers.log"


def make_t2_fixture(root: Path) -> tuple[dict, dict]:
    """T2 第 0–11 轮（每轮一个小 payload）与预登记行，写到 root/inputs 并返回 (inputs, prereg)。"""
    inputs_dir = root / "inputs"
    inputs_dir.mkdir(exist_ok=True)
    rows, t2_rounds = [], []
    for k in range(12):
        messages = [{"role": "user", "content": f"t2-round-{k}"}]
        body = json.dumps({"model": "m", "messages": messages, "max_tokens": 32, "stream": True},
                          ensure_ascii=False).encode("utf-8")
        name = f"t2_round_{k:02d}.json"
        (inputs_dir / name).write_bytes(body)
        rows.append({"trajectory": "T2", "round": k, "file": f"inputs/{name}", "sha256": sha(body),
                     "messages_sha256": runner.messages_sha256(messages)})
        t2_rounds.append({"class": "changed" if k in (1, 4, 5, 6, 7, 8, 10) else "unchanged",
                          "prompt_tokens": 12000 + k, "cached": 0,
                          "on_segments": [64, 257] if k == 1 else [331],
                          "off_segments": [321] if k == 1 else [331]})
    warm_messages = [{"role": "user", "content": "warmup"}]
    warm_body = json.dumps({"model": "m", "messages": warm_messages, "max_tokens": 8, "stream": True}).encode("utf-8")
    (inputs_dir / "warmup.json").write_bytes(warm_body)
    warm = {"file": "inputs/warmup.json", "sha256": sha(warm_body),
            "messages_sha256": runner.messages_sha256(warm_messages)}
    inputs = {"warmup": warm, "rounds": rows}
    prereg = {"trajectories": {"T2": {"rounds": t2_rounds}}}
    return inputs, prereg


def test_t2_only_plan_has_warmup_and_twelve_t2_rounds_and_no_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "WORK", tmp_path)
    inputs, prereg = make_t2_fixture(tmp_path)
    plan = runner.build_plan(inputs, prereg, "on", trajectories=("T2",))
    assert [item["key"] for item in plan] == ["warm/00"] + [f"T2/{k:02d}" for k in range(12)]
    assert not any(item["trajectory"] == "seed_real" for item in plan)
    off = runner.build_plan(inputs, prereg, "off", trajectories=("T2",))
    assert off[2]["expect"]["segments"] == [321]  # T2/01 的 B 臂
    assert plan[2]["expect"]["segments"] == [64, 257]  # T2/01 的 A 臂


def test_campaign_a2_parameters_and_release_line_patterns():
    cfg = runner.CAMPAIGNS["a2"]
    assert cfg["trajectories"] == ("T2",)
    assert cfg["limit_s"] == 2700.0 and cfg["reserve_s"] == 360.0
    assert cfg["approval"] == "RESTORE481-MORNING-20261011-11"
    a2_line = "- 2026-10-11T22:01:00+08:00 主会话（freetoken-06）：任务 A2 放行（用户确认）。"
    a1_line = "- 2026-10-11T20:53:17+08:00 主会话（freetoken-06）：任务 A 放行（用户确认）。"
    assert runner.A2_RELEASE_LINE_RE.match(a2_line)
    assert not runner.A2_RELEASE_LINE_RE.match(a1_line)
    ready = "- 2026-10-11T21:59:00+08:00 op-hak：任务 A2 P1 就绪。CPU_READINESS_A2.md。"
    assert runner.A2_READY_LINE_RE.match(ready)
    assert not runner.A2_READY_LINE_RE.match(a2_line)


def test_window01_marker_lines_are_matched_exactly(tmp_path):
    """正例：window01 B1_off serve.log 第 87–89 行的原文（夹具逐字节取自服务器）。"""
    lines = A2_FIXTURE.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "out of memory" in lines[0]
    assert "backend worker freetoken-TP0-scheduler exited" in lines[1]
    assert "Backend worker is gone" in lines[2]
    expected = ["oom", "worker_exit", "worker_exit"]
    for idx, want in enumerate(expected):
        log = tmp_path / f"serve_{idx}.log"
        log.write_text(lines[idx] + "\n", encoding="utf-8")
        assert runner.WorkerWatch("http://stub", log, 0).scan_new_log() == want


def test_normal_serve_lines_do_not_trip_the_watch(tmp_path):
    normal = [
        "[INFO] Prefill batch, #new-seq: 1, #new-token: 64, #cached-token: 87040, token usage: 0.89",
        "[INFO] Decode batch, #running-req: 1, #token: 87424, gen throughput (token/s): 11.06",
        "[INFO] Free memory after initialization: 2.55 GiB",
        "INFO:     Finished server process [3077786]",
        "[INFO] API server is ready to serve on 127.0.0.1:8123",
        "[INFO] --moe-cache-auto resolved moe_cache_size=2700 num_pages=1536",
    ]
    log = tmp_path / "serve.log"
    log.write_text("\n".join(normal) + "\n", encoding="utf-8")
    assert runner.WorkerWatch("http://stub", log, 0).scan_new_log() is None


def test_health_failures_are_recorded_and_never_trip(tmp_path):
    """/health 只记录（2026-10-11 改动）：连续失败不判定；计数与最后状态写入 watch；成功则清零连续计数。"""
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")

    def refused(endpoint):
        raise httpx.ConnectError("refused")

    watch = runner.WorkerWatch("http://stub", log, 0, health_get=refused)
    assert watch.poll() is None
    assert watch.poll() is None  # 连续两次失败也不判定
    assert (watch.health_failures, watch.health_failures_max, watch.health_last) == (2, 2, "error:ConnectError")

    replies = iter([{"status": "loading"}, {"status": "ok"}])
    watch = runner.WorkerWatch("http://stub", log, 0, health_get=lambda endpoint: next(replies))
    assert watch.poll() is None
    assert (watch.health_failures, watch.health_last) == (1, "status:loading")
    assert watch.poll() is None
    assert (watch.health_failures, watch.health_failures_max, watch.health_last) == (0, 1, "ok")


def test_marker_still_trips_while_health_keeps_failing(tmp_path):
    """健康检查持续失败时，服务日志里的 worker 标记仍然判定退出（判定只看标记）。"""
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")

    def refused(endpoint):
        raise httpx.ConnectError("refused")

    watch = runner.WorkerWatch("http://stub", log, 0, health_get=refused)
    assert watch.poll() is None
    with log.open("a", encoding="utf-8") as handle:
        handle.write("[ERROR] Backend worker is gone and cannot be restarted; stopping the API server\n")
    assert watch.poll() == "worker_exit"


def test_watch_outcome_carries_health_counters(tmp_path):
    """请求记录里带上 /health 的计数与最后状态（只记录，不影响判定）。"""
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")

    def refused(endpoint):
        raise httpx.ConnectError("refused")

    def slow(request):
        time.sleep(0.3)
        return httpx.Response(200, content=OK_SSE)

    outcome = runner.post_chat_watched("http://stub", b"{}", log, transport=httpx.MockTransport(slow),
                                       poll_s=0.05, health_get=refused)
    assert outcome["watch_trip"] is None
    assert outcome["health_failures_max"] >= 1
    assert outcome["health_last"] == "error:ConnectError"


def test_worker_exit_mid_request_is_detected_within_10s(tmp_path):
    """请求进行中 worker 退出（标记在第 1 秒写入，服务端不再返回）：监视线程在 10 秒内识别，并主动断开。"""
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")
    release = threading.Event()
    marker = {}

    def handler(request):
        release.wait(timeout=30)  # 服务端已退出，不再返回数据
        return httpx.Response(200, content=OK_SSE)

    def writer():
        time.sleep(1.0)
        marker["t"] = time.time()
        with log.open("a", encoding="utf-8") as handle:
            handle.write("[ERROR] Backend worker is gone and cannot be restarted; stopping the API server\n")

    def refused_health(endpoint):
        raise httpx.ConnectError("refused")

    threading.Thread(target=writer, daemon=True).start()
    try:
        record, _text = runner.run_request("http://stub", fake_item("T2/05", "x"), log,
                                           transport=httpx.MockTransport(handler), sleep=lambda s: None,
                                           health_get=refused_health)
    finally:
        release.set()
    assert record["status"] == "worker_exit"
    assert record["watch_trip"] == "worker_exit"
    assert record["trip_wall_time"] - marker["t"] < 10.0


def test_marker_before_connection_drop_is_worker_exit_not_request_error(tmp_path):
    """竞态：标记写入后服务端直接断开连接，客户端先看到连接错误。请求结束后的复扫把它记为 worker_exit。"""
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")

    def handler(request):
        with log.open("a", encoding="utf-8") as handle:
            handle.write("[ERROR] Backend worker is gone and cannot be restarted; stopping the API server\n")
        raise httpx.RemoteProtocolError("server disconnected without sending a response.", request=request)

    record, _ = runner.run_request("http://stub", fake_item("T2/05", "x"), log,
                                   transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert record["status"] == "worker_exit"


def test_plain_disconnect_without_marker_stays_a_request_error(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")

    def handler(request):
        raise httpx.RemoteProtocolError("server disconnected without sending a response.", request=request)

    record, _ = runner.run_request("http://stub", fake_item("T2/05", "x"), log,
                                   transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert record["status"] == "transport_error"


def test_memory_is_sampled_before_and_after_each_request(tmp_path, monkeypatch):
    samples = iter([21000, 23000])
    monkeypatch.setattr(runner, "MEMORY_SAMPLER", lambda: next(samples))
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")
    record, _ = runner.run_request("http://stub", fake_item("T2/00", "a"), log,
                                   transport=httpx.MockTransport(lambda r: httpx.Response(200, content=OK_SSE)),
                                   sleep=lambda s: None)
    assert record["memory_before_mib"] == 21000
    assert record["memory_after_mib"] == 23000


def test_ready_memory_is_written_into_the_service_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "run_service", fake_run_service({}, []))
    monkeypatch.setattr(runner, "MEMORY_SAMPLER", lambda: 22222)
    runner.run_window(FakeLauncher(), (("T2_only_probe", "on"),), tmp_path / "w", no_plan, clock=lambda: 0.0)
    doc = json.loads((tmp_path / "w" / "T2_only_probe" / "memory_ready.json").read_text(encoding="utf-8"))
    assert doc["memory_used_mib"] == 22222


def test_worker_exit_aborts_that_service_and_the_window_continues(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "run_service", fake_run_service({"B1_off": "worker_exit"}, calls))
    summary = runner.run_window(FakeLauncher(), runner.SERVICES, tmp_path / "w", no_plan, clock=lambda: 0.0)
    assert calls == ["A1_on", "B1_off", "B2_off", "A2_on"]
    assert [s["status"] for s in summary["services"]] == ["complete", "worker_exit", "complete", "complete"]
    assert summary["terminal"] == "complete"


def test_cached_mismatch_is_flagged_by_the_checker():
    """反向对照 (b)：cached 错误时，逐轮核对能标出。"""
    spec = importlib.util.spec_from_file_location("analyze_task_a", HERE / "analyze_task_a.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    rec = {"status": "ok",
           "expect": {"prompt_tokens": 12737, "cached": 12416, "class": "changed", "segments": [64, 257]},
           "usage": {"prompt_tokens": 12737, "cached_tokens": 0},
           "prefill_lines": [{"new_token": 64, "cached_token": 0}, {"new_token": 257, "cached_token": 0}]}
    checks = analyzer.record_checks(rec)
    assert checks["g1_segments"] is True
    assert checks["cached_usage"] is False
    assert checks["cached_first_line"] is False
