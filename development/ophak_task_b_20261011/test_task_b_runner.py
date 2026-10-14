"""任务 B 工装单测（CPU）：构建门、参数门、死亡计数与停窗、B 臂计划与 argv、clean_env、窗口服务表与协调日志行格式。

运行（服务器上，核心 0、2；不占 GPU，不碰 8095）：
  taskset -c 0,2 env PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/evaluation/toolchain/venv-eval/bin/python -B -m pytest -q -p no:cacheprovider test_task_b_runner.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import task_b_runner as r

BASELINE = ["taskset", "-c", "1,3-47", "/data2/FreeToken/venv/bin/ft", "serve", "--model-path", "/m",
            "--host", "0.0.0.0", "--port", "8095", "--mem-fraction", "0.9"]
PROBE_SH = "#!/bin/sh\necho \"$FAKE_IMPORT_PATH\"\n"


def fake_python(tmp_path: Path) -> str:
    """替代 FT_PYTHON：忽略参数，打印环境变量 FAKE_IMPORT_PATH，用来模拟 freetoken 的导入路径。"""
    script = tmp_path / "fake_python.sh"
    script.write_text(PROBE_SH, encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def probe_env(imported: str) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "FAKE_IMPORT_PATH": imported}


# ---------------------------------------------------------------- 构建门（§3 第 1 条）

def test_build_gate_accepts_candidate_import_under_candidate_root(tmp_path):
    out = tmp_path / "svc"
    out.mkdir()
    imported = r.CANDIDATE_PYTHONPATH + "/freetoken/scheduler/prefill.py"
    record = r.check_build("candidate", probe_env(imported), out, python=fake_python(tmp_path))
    assert record["ok"] is True
    assert json.loads((out / "build_gate.json").read_text(encoding="utf-8"))["imported"] == imported


def test_build_gate_refuses_release_import_for_candidate_service(tmp_path):
    out = tmp_path / "svc"
    out.mkdir()
    imported = r.RELEASE_PYTHONPATH + "/freetoken/scheduler/prefill.py"
    with pytest.raises(r.BuildGateError):
        r.check_build("candidate", probe_env(imported), out, python=fake_python(tmp_path))
    assert json.loads((out / "build_gate.json").read_text(encoding="utf-8"))["ok"] is False


def test_build_gate_refuses_when_the_probe_cannot_run(tmp_path):
    out = tmp_path / "svc"
    out.mkdir()
    with pytest.raises(r.BuildGateError):
        r.check_build("release", probe_env(""), out, python=str(tmp_path / "missing_python"))
    assert json.loads((out / "build_gate.json").read_text(encoding="utf-8"))["ok"] is False


def test_clean_env_pins_the_build_pythonpath_and_drops_dev_switches():
    base = {"FT_DEV_SWITCH": "1", "PATH": "/bin"}
    assert r.clean_env(base, build="candidate")["PYTHONPATH"] == r.CANDIDATE_PYTHONPATH
    assert r.clean_env(base)["PYTHONPATH"] == r.RELEASE_PYTHONPATH
    assert "FT_DEV_SWITCH" not in r.clean_env(base, build="candidate")
    with pytest.raises(r.LaunchError):
        r.clean_env(base, build="other")


# ---------------------------------------------------------------- 参数门（§3 第 2 条）

def serve_log_in(tmp_path: Path, name: str, repr_line: str | None) -> Path:
    """写一个独立的 serve.log：Parsed arguments 标题后紧跟 repr_line；之后的无关行带同名文字，参数门不应被它干扰。"""
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    body = "INFO startup\n"
    if repr_line is not None:
        body += "INFO Parsed arguments:\n" + repr_line + "\n"
    body += "INFO later line mentions prefill_anchor_cut_min_tokens=0\n"
    path = directory / "serve.log"
    path.write_text(body, encoding="utf-8")
    return path


def repr_with(value: str | None) -> str:
    extra = "" if value is None else f", prefill_anchor_cut_min_tokens={value}"
    return f"ServerArgs(model_path='m', prefill_anchor_cut=True{extra}, port=8123)"


def run_param_gate(tmp_path: Path, name: str, repr_line: str | None, build: str, arm: str) -> int | None:
    log = serve_log_in(tmp_path, name, repr_line)
    out = log.parent / "out"
    out.mkdir()
    return r.param_gate(log, build, arm, out)


def test_param_gate_passes_candidate_thresh_and_on_arms(tmp_path):
    assert run_param_gate(tmp_path, "thresh", repr_with("32768"), "candidate", "thresh") == 32768
    assert run_param_gate(tmp_path, "on", repr_with("0"), "candidate", "on") == 0


def test_param_gate_refuses_thresh_arm_that_parsed_zero(tmp_path):
    # 演练 b 的形态：B 臂漏加参数，解析结果为默认 0
    with pytest.raises(r.ParamGateError):
        run_param_gate(tmp_path, "dropped", repr_with("0"), "candidate", "thresh")


def test_param_gate_release_build_expects_the_field_absent(tmp_path):
    assert run_param_gate(tmp_path, "absent", repr_with(None), "release", "on") is None
    with pytest.raises(r.ParamGateError):
        run_param_gate(tmp_path, "present", repr_with("0"), "release", "on")


def test_param_gate_refuses_a_log_without_the_parsed_block(tmp_path):
    with pytest.raises(r.ParamGateError):
        run_param_gate(tmp_path, "nohdr", None, "candidate", "on")


def test_param_gate_writes_its_record_on_pass_and_on_refusal(tmp_path):
    passed = serve_log_in(tmp_path, "pass", repr_with("32768"))
    r.param_gate(passed, "candidate", "thresh", passed.parent)
    assert json.loads((passed.parent / "param_gate.json").read_text(encoding="utf-8"))["ok"] is True
    refused = serve_log_in(tmp_path, "refuse", repr_with("0"))
    with pytest.raises(r.ParamGateError):
        r.param_gate(refused, "candidate", "thresh", refused.parent)
    record = json.loads((refused.parent / "param_gate.json").read_text(encoding="utf-8"))
    assert record["ok"] is False and record["actual"] == 0 and record["expected"] == 32768


def test_release_build_cannot_run_the_thresh_arm():
    with pytest.raises(r.LaunchError):
        r.expected_min_tokens("release", "thresh")


# ---------------------------------------------------------------- 臂、argv、计划（§2、§3）

def test_extra_argv_on_is_empty_and_thresh_carries_the_flag():
    assert r.extra_argv("on") == []
    assert r.extra_argv("thresh") == ["--prefill-anchor-cut-min-tokens", "32768"]
    with pytest.raises(r.LaunchError):
        r.extra_argv("off")


def test_build_argv_thresh_appends_flag_and_verify_rejects_a_dropped_flag():
    expected, diff = r.build_argv(BASELINE, "thresh")
    assert expected[-2:] == ["--prefill-anchor-cut-min-tokens", "32768"]
    assert r.verify_argv(BASELINE, expected, "thresh") == diff
    with pytest.raises(r.LaunchError):
        r.verify_argv(BASELINE, expected[:-2], "thresh")


def test_plan_is_warmup_then_seed_then_t2_and_arm_selects_segments():
    inputs, prereg = r.load_inputs(), r.load_prereg()
    plan = r.build_plan(inputs, prereg, "thresh")
    keys = [item["key"] for item in plan]
    assert keys[0] == "warm/00"
    assert keys[1:9] == [f"seed_real/{k:02d}" for k in range(8)]
    assert keys[9:] == [f"T2/{k:02d}" for k in range(12)]
    assert next(i for i in plan if i["key"] == "T2/00")["expect"]["segments"] == [12443]
    on = r.build_plan(inputs, prereg, "on")
    assert next(i for i in on if i["key"] == "T2/00")["expect"]["segments"] == [512, 11931]
    with pytest.raises(r.RunnerError):
        r.build_plan(inputs, prereg, "off")


def test_services_table_is_fixed_r0_then_cutover_arms_with_builds():
    assert r.SERVICES == (("R0", "on", "release"), ("C_A1", "on", "candidate"), ("C_B1", "thresh", "candidate"),
                          ("C_B2", "thresh", "candidate"), ("C_A2", "on", "candidate"))
    assert r.CAMPAIGNS["b"]["approval"] == "RESTORE481-MORNING-20261011-12"
    assert r.CAMPAIGNS["b"]["limit_s"] == 3600.0 and r.CAMPAIGNS["b"]["reserve_s"] == 480.0


# ---------------------------------------------------------------- 死亡计数、停窗（§3 第 3 条）

class FakeLauncher:
    """替代 RealLauncher / StubLauncher：不起进程，只记录启动顺序。可令某服务构建门失败、启动失败（LaunchError）、
    其它异常启动失败、没到 ready（not_ready: 名称 -> "oom" 或 "plain"），或清场抛异常。"""

    def __init__(self, refuse_build=(), launch_fail=(), raise_generic=(), not_ready=None, stop_raise=()):
        self.started: list[str] = []
        self.refuse_build = set(refuse_build)
        self.launch_fail = set(launch_fail)
        self.raise_generic = set(raise_generic)
        self.not_ready = dict(not_ready or {})
        self.stop_raise = set(stop_raise)

    def start(self, name, arm, out_dir, build="release"):
        self.started.append(name)
        out_dir.mkdir(parents=True, exist_ok=False)
        serve_log = out_dir / "serve.log"
        serve_log.touch()
        if name in self.refuse_build:
            raise r.BuildGateError(f"fake build refusal {name}")
        if name in self.launch_fail:
            raise r.LaunchError(f"fake launch failure {name}")
        if name in self.raise_generic:
            raise RuntimeError(f"fake unexpected failure {name}")
        if name in self.not_ready:
            if self.not_ready[name] == "oom":
                serve_log.write_text("RuntimeError: out of memory while loading (fake)\n", encoding="utf-8")
            return r.Handle(name, arm, "http://fake", serve_log, out_dir, proc=None, ready=False)
        return r.Handle(name, arm, "http://fake", serve_log, out_dir, proc=None, ready=True)

    def stop(self, handle):
        if handle.out_dir.name in self.stop_raise:
            raise RuntimeError("fake cleanup failure")
        return True


def scripted_service(statuses: dict[str, str]):
    def run(endpoint, name, arm, serve_log, out_dir, plan, **kwargs):
        status = statuses.get(name, "complete")
        result = {"service": name, "arm": arm, "status": status, "planned": len(plan), "done": 0,
                  "stop_reason": None if status == "complete" else status}
        if status in ("oom", "worker_exit"):
            result["died_at_key"] = "T2/05"
        return result
    return run


def run_scripted_window(tmp_path: Path, launcher: FakeLauncher, monkeypatch, statuses=None, param_refuse=()):
    monkeypatch.setattr(r, "run_service", scripted_service(statuses or {}))
    monkeypatch.setattr(r, "MEMORY_SAMPLER", lambda: None)

    def gate(serve_log, build, arm, out_dir):
        if any(f"/{name}/" in str(serve_log) for name in param_refuse):
            raise r.ParamGateError("fake param refusal")
        return None

    monkeypatch.setattr(r, "param_gate", gate)
    return r.run_window(launcher, r.SERVICES, tmp_path / "window", lambda arm: [], limit_s=3600.0,
                        reserve_s=480.0)


def test_second_death_stops_the_window_and_later_services_do_not_start(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    summary = run_scripted_window(tmp_path, launcher, monkeypatch, {"C_A1": "oom", "C_B1": "oom"})
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "second_death_stop"
    assert [d["service"] for d in summary["deaths"]] == ["C_A1", "C_B1"]


def test_one_death_closes_that_service_and_the_window_continues(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    summary = run_scripted_window(tmp_path, launcher, monkeypatch, {"C_B1": "oom"})
    assert launcher.started == ["R0", "C_A1", "C_B1", "C_B2", "C_A2"]
    assert summary["terminal"] == "complete"
    assert summary["deaths"] == [{"service": "C_B1", "status": "oom", "key": "T2/05"}]


def test_oom_followed_by_worker_exit_is_a_second_death(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    summary = run_scripted_window(tmp_path, launcher, monkeypatch, {"C_A1": "oom", "C_B1": "worker_exit"})
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "second_death_stop"


def test_build_gate_refusal_stops_the_window_before_the_next_service(tmp_path, monkeypatch):
    launcher = FakeLauncher(refuse_build={"C_B2"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1", "C_B1", "C_B2"]
    assert summary["terminal"] == "build_gate_refused"
    assert summary["services"][-1]["status"] == "build_gate_refused"


def test_param_gate_refusal_stops_the_window_with_its_own_terminal_state(tmp_path, monkeypatch):
    launcher = FakeLauncher()
    summary = run_scripted_window(tmp_path, launcher, monkeypatch, param_refuse=("C_B1",))
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "param_gate_refused"
    assert summary["services"][-1]["status"] == "param_gate_refused"


def test_one_launch_failure_is_a_death_and_the_window_continues(tmp_path, monkeypatch):
    launcher = FakeLauncher(launch_fail={"C_A1"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1", "C_B1", "C_B2", "C_A2"]
    assert summary["terminal"] == "complete"
    assert summary["deaths"] == [{"service": "C_A1", "status": "launch_failed", "key": None}]
    assert summary["services"][1]["status"] == "launch_failed"


def test_two_launch_failures_stop_the_window(tmp_path, monkeypatch):
    launcher = FakeLauncher(launch_fail={"C_A1", "C_B1"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "second_death_stop"


def test_oom_then_launch_failure_is_a_second_death(tmp_path, monkeypatch):
    launcher = FakeLauncher(launch_fail={"C_B1"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch, {"C_A1": "oom"})
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "second_death_stop"
    assert [d["status"] for d in summary["deaths"]] == ["oom", "launch_failed"]


def test_unexpected_start_exception_is_a_death_and_does_not_crash_the_runner(tmp_path, monkeypatch):
    launcher = FakeLauncher(raise_generic={"C_A1"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1", "C_B1", "C_B2", "C_A2"]
    assert summary["terminal"] == "complete"
    assert summary["deaths"] == [{"service": "C_A1", "status": "launch_failed", "key": None}]
    assert (tmp_path / "window" / "window_summary.json").exists()


def test_service_that_never_reaches_ready_is_a_death_classified_by_its_log(tmp_path, monkeypatch):
    launcher = FakeLauncher(not_ready={"C_A1": "oom"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert summary["terminal"] == "complete"
    assert summary["deaths"] == [{"service": "C_A1", "status": "oom", "key": None}]


def test_two_services_that_never_reach_ready_stop_the_window(tmp_path, monkeypatch):
    launcher = FakeLauncher(not_ready={"C_A1": "plain", "C_B1": "plain"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1", "C_B1"]
    assert summary["terminal"] == "second_death_stop"
    assert [d["status"] for d in summary["deaths"]] == ["launch_failed", "launch_failed"]


def test_cleanup_exception_is_recorded_as_cleanup_blocked(tmp_path, monkeypatch):
    launcher = FakeLauncher(stop_raise={"C_A1"})
    summary = run_scripted_window(tmp_path, launcher, monkeypatch)
    assert launcher.started == ["R0", "C_A1"]
    assert summary["terminal"] == "cleanup_blocked"
    assert "fake cleanup failure" in (tmp_path / "window" / "CLEANUP_BLOCKED.md").read_text(encoding="utf-8")


def test_run_service_records_the_round_where_it_died(tmp_path, monkeypatch):
    serve_log = tmp_path / "serve.log"
    serve_log.write_text("RuntimeError: Triton Error [CUDA]: out of memory\n", encoding="utf-8")
    out_dir = tmp_path / "svc"
    out_dir.mkdir()

    def fake_request(endpoint, item, serve_log, **kwargs):
        status = "oom" if item["key"] == "T2/01" else "ok"
        record = {"key": item["key"], "status": status, "error": None,
                  "oom_message": "out of memory" if status == "oom" else None,
                  "prefill_lines": [], "memory_before_mib": None, "memory_after_mib": None}
        return record, f"text-{item['key']}"

    monkeypatch.setattr(r, "run_request", fake_request)
    plan = [{"key": "warm/00"}, {"key": "T2/00"}, {"key": "T2/01"}, {"key": "T2/02"}]
    summary = r.run_service("http://fake", "C_B1", "thresh", serve_log, out_dir, plan,
                            sleep=lambda s: None, between_s=0.0)
    assert summary["status"] == "oom"
    assert summary["died_at_key"] == "T2/01"
    assert summary["done"] == 2
    assert (out_dir / "oom_excerpt.log").exists()
    assert json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))["died_at_key"] == "T2/01"


def test_startup_status_classifies_oom_and_worker_exit_in_serve_log(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("CUDA out of memory while loading\n", encoding="utf-8")
    assert r.startup_status(log) == "oom"
    log.write_text("[ERROR] Backend worker is gone\n", encoding="utf-8")
    assert r.startup_status(log) == "worker_exit"
    log.write_text("starting\n", encoding="utf-8")
    assert r.startup_status(log) == "launch_failed"


# ---------------------------------------------------------------- 协调日志行格式（W0 与既有行）

def test_coordination_line_patterns_match_only_their_own_lines():
    ready = "- 2026-10-12T01:00:00+08:00 op-hak：任务 B P1 就绪（SHA 前 12 位 abc）"
    release = "- 2026-10-12T02:00:00+08:00 主会话（freetoken-06）：任务 B 放行"
    s_review = "- 2026-10-12T00:21:31+08:00 主会话（freetoken-06）：任务 S 复核与裁定（RESULT_S.md）"
    s_end = "- 2026-10-12T00:18:04+08:00 op-hak：任务 S 窗口结束，等主会话复核。"
    assert r.B_READY_LINE_RE.match(ready)
    assert r.B_RELEASE_LINE_RE.match(release)
    assert r.S_REVIEW_LINE_RE.match(s_review)
    assert r.S_END_LINE_RE.match(s_end)
    assert not r.B_RELEASE_LINE_RE.match("- 2026-10-11T22:00:00+08:00 主会话（freetoken-06）：任务 A2 放行")
    assert not r.B_READY_LINE_RE.match("- 2026-10-11T22:00:00+08:00 op-hak：任务 A2 P1 就绪")


# ---------------------------------------------------------------- 与 A2 共用的解析与监视（回归）

def test_absorb_chunk_classifies_an_oom_error_chunk():
    outcome = {"status": "ok", "ttft_s": None, "ttft_source": None, "tool_call_first_s": None, "usage": None,
               "finish_reason": None, "error": None, "oom_message": None, "_parts": []}
    stop = r.absorb_chunk(outcome, {"error": {"message": "RuntimeError: out of memory"}}, 0.1)
    assert stop is True and outcome["status"] == "oom"


def test_worker_watch_trips_on_a_marker_written_after_its_offset(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("old line\n", encoding="utf-8")
    watch = r.WorkerWatch("http://fake", log, log.stat().st_size, health_get=lambda endpoint: {"status": "ok"})
    assert watch.poll() is None
    with log.open("a", encoding="utf-8") as handle:
        handle.write("[ERROR] Backend worker is gone (stub)\n")
    assert watch.poll() == "worker_exit"


# ---------------------------------------------------------------- 没到 ready 就退出（启动失败）与清场

def test_wait_ready_returns_false_as_soon_as_the_process_exits():
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(3)"])
    started = time.monotonic()
    assert r.wait_ready("http://127.0.0.1:9", timeout_s=600.0, proc=proc) is False
    assert time.monotonic() - started < 30
    assert proc.returncode == 3


def test_stub_stop_treats_an_already_exited_process_as_cleaned(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    out = tmp_path / "svc"
    out.mkdir()
    handle = r.Handle("C_A1", "on", "http://127.0.0.1:9", out / "serve.log", out, proc=proc, ready=False)
    assert r.StubLauncher(port=9, scale=1.0, inject={}).stop(handle) is True
