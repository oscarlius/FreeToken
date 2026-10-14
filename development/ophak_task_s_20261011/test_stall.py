"""任务 S 工装单测（CPU，pytest）。覆盖判据边界、混入规则、结构两级、总判阈值、A 的 300 秒重启规则、前置检查分支。"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stall_core as core  # noqa: E402
import stall_runner as runner  # noqa: E402

FIXTURE_LINES = [
    "RuntimeError: Triton Error [CUDA]: out of memory",
    "Backend supervisor: backend worker freetoken-TP0-scheduler exited",
    "Backend worker is gone and cannot be restarted; stopping the API server",
]


def timing(scale: float = 1.0) -> core.Timing:
    return core.Timing(scale)


# ---------------------------------------------------------------- 纯计算：G、零输出、结构

def test_max_gap_takes_largest_consecutive_difference_inside_window():
    times = [9.0, 10.0, 12.9, 12.925, 12.95]
    assert core.max_gap(times, 8.0, 14.0) == pytest.approx(2.9)


def test_max_gap_none_when_fewer_than_two_deltas_inside_window():
    assert core.max_gap([10.0], 9.0, 11.0) is None
    assert core.max_gap([1.0, 2.0], 9.0, 11.0) is None


def test_zero_output_window_is_open_on_both_ends():
    t_d, t_f = 100.0, 103.0
    times = [100.4, 100.5, 102.8, 102.7, 101.0]  # 100.4 与 102.8 为边界，不计入
    assert core.zero_output_count(times, t_d, t_f, timing()) == 3  # 100.5、101.0、102.7 在开区间内


def test_zero_output_counts_only_deltas_inside_open_interval():
    assert core.zero_output_count([99.0, 100.2, 103.5], 100.0, 103.0, timing()) == 0
    assert core.zero_output_count([100.5, 102.0], 100.0, 103.0, timing()) == 2


def test_structure_level1_counts_lines_and_level2_checks_lengths_and_cached_on_first_line():
    lines = [{"new_token": 64, "cached_token": 448}, {"new_token": 11931, "cached_token": 0}]
    ok = core.structure(lines, [64, 11931], 448)
    assert ok["level1"] and ok["level2"]
    bad_cached = core.structure([{"new_token": 64, "cached_token": 0}, {"new_token": 11931, "cached_token": 448}],
                                [64, 11931], 448)
    assert bad_cached["level1"] and not bad_cached["level2"]
    one_line = core.structure([{"new_token": 331, "cached_token": 12736}], [64, 257], 12736)
    assert not one_line["level1"] and not one_line["level2"]


def test_in_band_uses_closed_interval():
    assert core.in_band(5.333, (5.333, 6.476))
    assert not core.in_band(5.332, (5.333, 6.476))
    assert not core.in_band(None, (5.333, 6.476))


def test_timing_scales_band_and_time_constants_together():
    t = core.Timing(0.05)
    assert t.band((2.0, 3.0)) == pytest.approx((0.1, 0.15))
    assert t.a_restart_s == pytest.approx(15.0)
    assert t.zero_lead_s == pytest.approx(0.02)
    with pytest.raises(ValueError):
        core.Timing(1.5)


# ---------------------------------------------------------------- 总判阈值（§7：11/13、6/13、n<9）

def test_aggregate_thresholds_for_n_13():
    assert core.aggregate_verdict(13, 11) == "成立"
    assert core.aggregate_verdict(13, 10) == "部分成立"
    assert core.aggregate_verdict(13, 7) == "部分成立"
    assert core.aggregate_verdict(13, 6) == "不成立"
    assert math.ceil(11 * 13 / 13) == 11 and math.floor(6 * 13 / 13) == 6


def test_aggregate_reports_only_when_n_below_nine():
    assert core.aggregate_verdict(8, 8) == "只报告不判"
    assert core.aggregate_verdict(9, 9) == "成立"


# ---------------------------------------------------------------- 混入规则（预登记 gates.contamination）

def test_contamination_when_server_active_exceeds_our_inflight():
    samples = [{"t": 100.5, "active": 2, "completed": 2, "ours": 1},
               {"t": 101.0, "active": 1, "completed": 2, "ours": 1}]
    reasons = core.contamination_reasons(samples, 100.0, 102.0, 2, 3, 1)
    assert any(r.startswith("active 2 > ours 1") for r in reasons)


def test_contamination_when_completed_difference_does_not_match_our_completions():
    samples = [{"t": 100.5, "active": 1, "completed": 2, "ours": 1}]
    assert core.contamination_reasons(samples, 100.0, 102.0, 2, 3, 1) == []
    reasons = core.contamination_reasons(samples, 100.0, 102.0, 2, 4, 1)
    assert any(r.startswith("completed 差 2") for r in reasons)


def test_missing_completed_reading_is_unverified_not_silently_clean():
    reasons = core.contamination_reasons([], 100.0, 102.0, None, 3, 1)
    assert reasons and reasons[0].startswith("unverified")


# ---------------------------------------------------------------- 单事件判读标签

def make_event(**over) -> dict:
    base = {"name": "T2/02", "status": "ok", "invalid_a_ended": False, "t_d": 100.0, "t_f": 102.8,
            "t_end": 103.0, "t_after": 103.6, "prefill_lines": [{"new_token": 331, "cached_token": 12736}],
            "before_completed": 2, "after_completed": 3, "our_completions": 1, "segments": [331],
            "cached": 12736, "band": [2.551, 3.15], "pred": 2.773, "gpu_before_mib": None, "gpu_after_mib": None}
    base.update(over)
    return base


def test_clean_event_enters_judgment_and_is_in_band():
    a_times = [99.5, 100.0, 102.9, 102.925, 102.95]
    judged = core.judge_event(make_event(), a_times, [], timing())
    assert judged["label"] == "进入停顿判读"
    assert judged["entered"] is True
    assert judged["G_s"] == pytest.approx(2.9)
    assert judged["in_band"] is True
    assert judged["zero_output"] == 0


def test_request_error_is_labelled_and_not_entered():
    judged = core.judge_event(make_event(status="request_error"), [], [], timing())
    assert judged["label"] == "请求错误（停窗）" and judged["entered"] is False


def test_invalid_a_ended_is_labelled_and_not_entered():
    judged = core.judge_event(make_event(invalid_a_ended=True), [99.5, 100.0, 102.9], [], timing())
    assert judged["label"] == "invalid_a_ended（不补测）" and judged["entered"] is False


def test_contaminated_event_is_reported_and_excluded_from_n():
    samples = [{"t": 100.5, "active": 2, "completed": 2, "ours": 1}]
    judged = core.judge_event(make_event(), [99.5, 100.0, 102.9], samples, timing())
    assert judged["label"] == "contaminated" and judged["entered"] is False
    assert judged["contamination"]


def test_structure_level1_failure_is_report_only():
    lines = [{"new_token": 331, "cached_token": 12736}, {"new_token": 5, "cached_token": 0}]
    judged = core.judge_event(make_event(prefill_lines=lines), [99.5, 100.0, 102.9], [], timing())
    assert judged["label"] == "一级不符：只报告" and judged["entered"] is False


def test_aggregate_counts_only_entered_events():
    entered_in = core.judge_event(make_event(), [99.5, 100.0, 102.9], [], timing())
    excluded = core.judge_event(make_event(invalid_a_ended=True), [], [], timing())
    result = core.aggregate([entered_in, excluded])
    assert result["n"] == 1 and result["k"] == 1 and result["verdict"] == "只报告不判"


# ---------------------------------------------------------------- 解析、载荷与 SHA

def test_sse_role_packet_is_not_a_nonempty_delta():
    kind, chunk = core.parse_sse_line('data: {"choices":[{"delta":{"role":"assistant","content":""}}]}')
    assert kind == "chunk" and core.classify_chunk(chunk)["nonempty"] is False


def test_sse_reasoning_is_nonempty_and_tool_calls_are_separate():
    _, chunk = core.parse_sse_line('data: {"choices":[{"delta":{"reasoning_content":"1 "}}]}')
    assert core.classify_chunk(chunk)["nonempty"] is True
    _, tools = core.parse_sse_line('data: {"choices":[{"delta":{"tool_calls":[{"id":"x"}]}}]}')
    info = core.classify_chunk(tools)
    assert info["tool_calls"] is True and info["nonempty"] is False


def test_sse_done_and_usage_with_cached_tokens():
    assert core.parse_sse_line("data: [DONE]") == ("done", None)
    _, chunk = core.parse_sse_line(
        'data: {"choices":[],"usage":{"prompt_tokens":12737,"completion_tokens":32,'
        '"prompt_tokens_details":{"cached_tokens":12416}}}')
    assert core.classify_chunk(chunk)["usage"] == {"prompt_tokens": 12737, "completion_tokens": 32,
                                                   "cached_tokens": 12416}


def test_a_body_has_the_fixed_fields_and_no_tools():
    body = json.loads(core.build_a_body().decode("utf-8"))
    assert body["max_tokens"] == 16384 and body["ignore_eos"] is True and body["stream"] is True
    assert body["temperature"] == 0 and body["stream_options"] == {"include_usage": True}
    assert body["messages"][0]["content"] == "从 1 开始，每行写一个整数，一直写下去。"
    assert "tools" not in body


def test_l64_body_changes_only_max_tokens_and_checks_original_sha(monkeypatch):
    raw = json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 2048,
                      "temperature": 0}).encode("utf-8")
    monkeypatch.setattr(core, "L64_SHA256", core.sha256_hex(raw))
    body = json.loads(core.build_l64_body(raw).decode("utf-8"))
    assert body == {"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 32,
                    "temperature": 0}
    with pytest.raises(ValueError):
        core.build_l64_body(raw + b" ")  # SHA 不符


def test_l64_rejects_unexpected_original_max_tokens(monkeypatch):
    raw = json.dumps({"model": "m", "messages": [], "max_tokens": 1024}).encode("utf-8")
    monkeypatch.setattr(core, "L64_SHA256", core.sha256_hex(raw))
    with pytest.raises(ValueError):
        core.build_l64_body(raw)


def test_payload_sha_mismatch_raises():
    with pytest.raises(ValueError):
        core.check_payload_sha(b"abc", "0" * 64, "T2/00")


def test_prefill_lines_parse_in_order():
    text = ("INFO Prefill batch, #new-seq: 1, #new-token: 64, #cached-token: 448, token usage: 0.89\n"
            "INFO Prefill batch, #new-seq: 1, #new-token: 11931, #cached-token: 0, token usage: 0.9\n")
    assert core.parse_prefill_lines(text) == [
        {"new_seq": 1, "new_token": 64, "cached_token": 448},
        {"new_seq": 1, "new_token": 11931, "cached_token": 0}]


# ---------------------------------------------------------------- 日志标记（同任务 A2 的匹配串）

def test_monitor_markers_match_window01_lines_and_ignore_normal_lines(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("", encoding="utf-8")
    monitor = runner.Monitor(lambda: {"status": "ok", "maintenance": "serving"}, log, 1.0, lambda: 0.0,
                             lambda reason: None)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("INFO Prefill batch, #new-seq: 1, #new-token: 64, #cached-token: 0\n")
    assert monitor.scan_log() is None
    with log.open("a", encoding="utf-8") as handle:
        handle.write(FIXTURE_LINES[0] + "\n")
    assert monitor.scan_log().startswith("oom:")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(FIXTURE_LINES[1] + "\n" + FIXTURE_LINES[2] + "\n")
    assert monitor.scan_log().startswith("worker_exit:")


# ---------------------------------------------------------------- 前置检查（§4）

PRECHECK_PASS = {"status": "ok", "maintenance": "serving", "backend_epoch": 0, "restart_attempts": 0}


def stats_ok(**over):
    doc = {"active": 0, "completed": 2, "prompt_tokens_total": 8769}
    doc.update(over)
    return doc


def write_fixture_files(tmp_path: Path, token: str = '{"owner": "x"}', stop: bool = False):
    active = tmp_path / "active.json"
    lock = tmp_path / "gpu.lock"
    serve_log = tmp_path / "serve.log"
    serve_log.write_text("", encoding="utf-8")
    active.write_text(json.dumps({"log": str(serve_log), "gpu_owner": {"lock_token": token}}), encoding="utf-8")
    lock.write_text(token, encoding="utf-8")
    stop_file = tmp_path / "STOP.md"
    if stop:
        stop_file.write_text("stop", encoding="utf-8")
    return active, lock, stop_file


def run_pre(tmp_path, *, health=PRECHECK_PASS, stats=None, token='{"owner": "x"}', stop=False, hits=()):
    active, lock, stop_file = write_fixture_files(tmp_path, token=token, stop=stop)
    return runner.run_precheck(
        timing=core.Timing(0.001), endpoint="http://stub", active_json=active, gpu_lock=lock, stop_file=stop_file,
        read_health_fn=lambda: health, read_stats_fn=lambda: (stats or stats_ok()),
        sleep=lambda s: None, clock=lambda: 0.0, hits_fn=lambda name: list(hits),
        read_text=lambda p: Path(p).read_text(encoding="utf-8"))


def test_precheck_passes_when_all_conditions_hold(tmp_path):
    result = run_pre(tmp_path)
    assert result["pass"] is True
    assert len(result["samples"]) == 13  # 60 秒、每 5 秒一次（0..60 含端点）


def test_precheck_refuses_when_completed_is_not_two(tmp_path):
    result = run_pre(tmp_path, stats=stats_ok(completed=3))
    assert result["pass"] is False and result["checks"]["cache_state"]["pass"] is False


def test_precheck_refuses_when_prompt_total_differs(tmp_path):
    result = run_pre(tmp_path, stats=stats_ok(prompt_tokens_total=8770))
    assert result["checks"]["cache_state"]["pass"] is False


def test_precheck_refuses_when_stop_file_exists(tmp_path):
    result = run_pre(tmp_path, stop=True)
    assert result["checks"]["stop_file_absent"]["pass"] is False


def test_precheck_refuses_when_gpu_lock_differs_from_owner_token(tmp_path):
    active, lock, stop_file = write_fixture_files(tmp_path)
    lock.write_text('{"owner": "other"}', encoding="utf-8")
    result = runner.run_precheck(
        timing=core.Timing(0.001), endpoint="http://stub", active_json=active, gpu_lock=lock, stop_file=stop_file,
        read_health_fn=lambda: PRECHECK_PASS, read_stats_fn=lambda: stats_ok(), sleep=lambda s: None,
        clock=lambda: 0.0, hits_fn=lambda name: [], read_text=lambda p: Path(p).read_text(encoding="utf-8"))
    assert result["checks"]["gpu_lock_matches_owner_token"]["pass"] is False


def test_precheck_refuses_when_health_not_serving_or_epoch_changed(tmp_path):
    assert run_pre(tmp_path, health={**PRECHECK_PASS, "maintenance": "restarting"})["pass"] is False
    assert run_pre(tmp_path, health={**PRECHECK_PASS, "backend_epoch": 1})["pass"] is False


def test_precheck_refuses_when_task_a_runner_is_running(tmp_path):
    result = run_pre(tmp_path, hits=[1234])
    assert result["checks"]["no_task_a_runner"]["pass"] is False


def test_precheck_refuses_when_stats_change_during_idle_window(tmp_path):
    counter = {"n": 0}

    def changing():
        counter["n"] += 1
        return stats_ok(completed=2 + (1 if counter["n"] > 5 else 0))

    active, lock, stop_file = write_fixture_files(tmp_path)
    result = runner.run_precheck(
        timing=core.Timing(0.001), endpoint="http://stub", active_json=active, gpu_lock=lock, stop_file=stop_file,
        read_health_fn=lambda: PRECHECK_PASS, read_stats_fn=changing, sleep=lambda s: None, clock=lambda: 0.0,
        hits_fn=lambda name: [], read_text=lambda p: Path(p).read_text(encoding="utf-8"))
    assert result["checks"]["idle_window"]["pass"] is False


# ---------------------------------------------------------------- A 的 300 秒重启规则与事件循环（假时钟）

class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeA:
    """每秒产生一个非空增量；ended 可由测试置位（模拟 B 在途时 A 结束）。"""
    instances: list = []

    def __init__(self, endpoint, body, clock, read_timeout_s, ledger) -> None:
        self.clock = clock
        self.ledger = ledger
        self.opened_at = None
        self.ended = False
        self.ended_at = None
        self.error = None
        self.closed_by_us = False
        self.end_now = False
        FakeA.instances.append(self)

    def start(self) -> None:
        self.opened_at = self.clock()
        self.ledger.inc()

    @property
    def times(self) -> list[float]:
        if self.opened_at is None:
            return []
        stop = self.ended_at if self.ended else self.clock()
        return [self.opened_at + k for k in range(1, int(stop - self.opened_at) + 1)]

    def snapshot(self, after=None) -> list[float]:
        return self.times if after is None else [t for t in self.times if t > after]

    def close(self) -> None:
        if not self.ended:
            self.closed_by_us = True
            self.ended = True
            self.ended_at = self.clock()
            self.ledger.dec()


def make_events(count: int = 13) -> list[dict]:
    events = []
    for i in range(count):
        events.append({"name": f"E{i:02d}", "kind": "T2", "body": b"{}", "body_sha256": "x", "source_sha256": "y",
                       "segments": [331], "cached": 0, "band": [0.0, 100.0], "pred": 1.0})
    return events


def test_a_restart_rule_and_b_boundaries_with_fake_clock(monkeypatch):
    FakeA.instances.clear()
    clock = FakeClock()
    monkeypatch.setattr(runner, "AStream", FakeA)
    monkeypatch.setattr(runner.StatsSampler, "start", lambda self: None)
    monkeypatch.setattr(runner.StatsSampler, "stop", lambda self: None)
    monkeypatch.setattr(runner.StatsSampler, "completed_before", lambda self, t: 2)
    monkeypatch.setattr(runner.StatsSampler, "first_after", lambda self, t, timeout_s: {"t": t, "completed": 2})
    monkeypatch.setattr(runner.Monitor, "start", lambda self: None)
    monkeypatch.setattr(runner.Monitor, "stop", lambda self: None)
    calls = {"n": 0}

    def fake_run_b(endpoint, body, clk, read_timeout_s, ledger, holder):
        calls["n"] += 1
        t_d = clk()
        clk.sleep(0.2)
        t_f = clk()
        clk.sleep(0.2)
        return {"status": "ok", "error": None, "http_status": 200, "t_d": t_d, "t_f": t_f, "t_end": clk(),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cached_tokens": 0}, "finish_reason": "length"}

    monkeypatch.setattr(runner, "run_b", fake_run_b)
    import tempfile
    out = Path(tempfile.mkdtemp())
    serve_log = out / "serve.log"
    serve_log.write_text("", encoding="utf-8")
    campaign = runner.Campaign(timing=core.Timing(1.0), events=make_events(), endpoint="http://stub",
                               serve_log=serve_log, out_dir=out, a_body=b"{}",
                               read_stats_fn=lambda: stats_ok(), read_health_fn=lambda: PRECHECK_PASS,
                               gpu_fn=lambda: None, clock=clock, sleep=clock.sleep)
    run_doc = campaign.run()
    assert run_doc["status"] == "complete", run_doc
    assert len(campaign.records) == 13
    assert len(FakeA.instances) >= 2, "运行超过 300 秒后必须重启 A"
    assert campaign.restarts and campaign.restarts[0]["reason"] == "A 运行超过重启阈值"
    # 重启前后两个 A 的增量都要写入 a_times.json（判读前面事件时需要重启前的增量）
    merged = json.loads((out / "a_times.json").read_text(encoding="utf-8"))
    # 假时钟里关闭与重开在同一时刻（等待 active 归零用时为 0），故用 <=
    assert min(merged) < campaign.restarts[0]["closed_at"] <= campaign.restarts[0]["reopened_at"] < max(merged)
    old, new = FakeA.instances[0], FakeA.instances[1]
    assert old.closed_by_us and old.ended_at <= new.opened_at, "新 A 必须在旧 A 关闭之后打开"
    # 每个 B 发出前，当前 A 的运行时长不超过 300 秒
    for rec in campaign.records:
        owner = [a for a in FakeA.instances if a.opened_at is not None and a.opened_at <= rec["t_d"]
                 and (not a.ended or a.ended_at >= rec["t_d"])][-1]
        assert rec["t_d"] - owner.opened_at <= 300.0
    # 每个 B 结束后，下一个 B 之前 A 收到 30 个非空增量。假 A 每秒一个增量，30 个覆盖 29 到 30 秒
    for prev, nxt in zip(campaign.records, campaign.records[1:]):
        assert nxt["t_d"] - prev["t_end"] >= 29.0


def test_b_in_flight_a_end_is_recorded_as_invalid_and_a_is_restarted(monkeypatch):
    FakeA.instances.clear()
    clock = FakeClock()
    monkeypatch.setattr(runner, "AStream", FakeA)
    for name in ("start", "stop"):
        monkeypatch.setattr(runner.StatsSampler, name, lambda self: None)
    monkeypatch.setattr(runner.StatsSampler, "completed_before", lambda self, t: 2)
    monkeypatch.setattr(runner.StatsSampler, "first_after", lambda self, t, timeout_s: {"t": t, "completed": 2})
    monkeypatch.setattr(runner.Monitor, "start", lambda self: None)
    monkeypatch.setattr(runner.Monitor, "stop", lambda self: None)
    seen = {"n": 0}

    def fake_run_b(endpoint, body, clk, read_timeout_s, ledger, holder):
        seen["n"] += 1
        t_d = clk()
        if seen["n"] == 3:
            FakeA.instances[-1].ended = True  # 模拟 A 在 B 在途时由服务端结束
            FakeA.instances[-1].ended_at = clk()
        clk.sleep(0.2)
        t_f = clk()
        clk.sleep(0.2)
        return {"status": "ok", "error": None, "http_status": 200, "t_d": t_d, "t_f": t_f, "t_end": clk(),
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cached_tokens": 0}, "finish_reason": "length"}

    monkeypatch.setattr(runner, "run_b", fake_run_b)
    import tempfile
    out = Path(tempfile.mkdtemp())
    serve_log = out / "serve.log"
    serve_log.write_text("", encoding="utf-8")
    campaign = runner.Campaign(timing=core.Timing(1.0), events=make_events(5), endpoint="http://stub",
                               serve_log=serve_log, out_dir=out, a_body=b"{}",
                               read_stats_fn=lambda: stats_ok(), read_health_fn=lambda: PRECHECK_PASS,
                               gpu_fn=lambda: None, clock=clock, sleep=clock.sleep)
    run_doc = campaign.run()
    assert run_doc["status"] == "complete"
    assert campaign.records[2]["invalid_a_ended"] is True
    assert any(r["reason"] == "A 在 B 之外或之中结束" for r in campaign.restarts)


def test_trip_from_monitor_stops_the_run_without_retry(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(runner, "AStream", FakeA)
    monkeypatch.setattr(runner.StatsSampler, "start", lambda self: None)
    monkeypatch.setattr(runner.StatsSampler, "stop", lambda self: None)
    monkeypatch.setattr(runner.Monitor, "start", lambda self: None)
    monkeypatch.setattr(runner.Monitor, "stop", lambda self: None)
    import tempfile
    out = Path(tempfile.mkdtemp())
    serve_log = out / "serve.log"
    serve_log.write_text("", encoding="utf-8")
    campaign = runner.Campaign(timing=core.Timing(1.0), events=make_events(3), endpoint="http://stub",
                               serve_log=serve_log, out_dir=out, a_body=b"{}",
                               read_stats_fn=lambda: stats_ok(), read_health_fn=lambda: PRECHECK_PASS,
                               gpu_fn=lambda: None, clock=clock, sleep=clock.sleep)
    campaign.trip("oom: RuntimeError: Triton Error [CUDA]: out of memory")
    run_doc = campaign.run()
    assert run_doc["status"] == "stopped"
    assert run_doc["reason"].startswith("oom:")
    assert campaign.records == []


def test_judge_run_reads_raw_records_and_writes_result(tmp_path):
    prereg_path = tmp_path / "prereg.json"
    prereg = {"events": [{"event": "E00", "segments_expected": [331], "cached_expected": 0,
                          "stall_band_s": [0.0, 100.0], "prefill_pred_s": 1.0}]}
    prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
    run = {"status": "complete", "scale": 1.0, "prereg": str(prereg_path), "restarts": []}
    (tmp_path / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (tmp_path / "events.jsonl").write_text(json.dumps(make_event(name="E00", t_d=100.0, t_f=101.0, t_end=101.5,
                                                                 t_after=102.0, prefill_lines=[
                                                                     {"new_token": 331, "cached_token": 0}],
                                                                 band=[0.0, 100.0], pred=1.0, segments=[331],
                                                                 cached=0)) + "\n", encoding="utf-8")
    (tmp_path / "a_times.json").write_text(json.dumps([99.0, 100.0, 101.2]), encoding="utf-8")
    (tmp_path / "samples.jsonl").write_text("", encoding="utf-8")
    result = runner.judge_run(tmp_path)
    assert result["aggregate"]["n"] == 1
    assert (tmp_path / "result.json").exists()
