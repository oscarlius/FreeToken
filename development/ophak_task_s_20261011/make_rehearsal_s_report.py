#!/usr/bin/env python3
"""任务 S P1 的 CPU 演练结果核对：逐条比对预期与实际，写 REHEARSAL_S.json（0444）。

只读各演练目录，不改运行数据。预期值写在本文件里，不根据结果回填。
桩服务按预登记 v2 复现时序：演练证明工装的算术、结构两级、混入与零输出判读路径、A 的 300 秒重启规则与前置检查，
不是对生产的测量，不能当作任务 S 的证据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
RUNS = Path("/data2/FreeToken/runs/dev_ophak_task_s_20261011/rehearsal")
PREREG = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_S_v2.json")
OUT = WORK / "REHEARSAL_S.json"
SOURCES = ("stall_core.py", "stall_runner.py", "stub_stall_server.py", "test_stall.py",
           "make_rehearsal_s_report.py", "run_rehearsals_s.sh")
N_EVENTS = 13
A_RESTART_PREREG_S = 300.0
A_START_DELTAS = 50
A_AFTER_B_DELTAS = 30
ENTERED = "进入停顿判读"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def opt_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def check(label: str, expected, actual, ok: bool) -> dict:
    return {"check": label, "expected": expected, "actual": actual, "pass": bool(ok)}


def load(name: str) -> dict:
    base = RUNS / name
    run_dir = base / "run"
    exit_code = None
    tool = base / "tool.stdout"
    if tool.exists():
        marks = [line for line in tool.read_text(encoding="utf-8").splitlines() if line.startswith("exit=")]
        exit_code = int(marks[-1].split("=", 1)[1]) if marks else None
    return {"exit": exit_code, "run": opt_json(run_dir / "run.json"), "result": opt_json(run_dir / "result.json"),
            "precheck": opt_json(run_dir / "precheck.json"), "a_times": opt_json(run_dir / "a_times.json") or [],
            "events": jsonl(run_dir / "events.jsonl")}


def restart_checks(data: dict) -> list[dict]:
    """每次重启：旧 A 先关闭、新 A 之后打开；重开后收够 50 个增量才发下一个 B。"""
    out = []
    events = data["events"]
    times = data["a_times"]
    for i, r in enumerate(data["run"].get("restarts", [])):
        out.append(check(f"重启{i}：旧 A 关闭不晚于新 A 打开", True,
                         r["closed_at"] <= r["reopened_at"], r["closed_at"] <= r["reopened_at"]))
        nxt = next((e for e in events if e["t_d"] is not None and e["t_d"] > r["reopened_at"]), None)
        if nxt is None:
            out.append(check(f"重启{i}：重启后有下一个事件", True, False, False))
            continue
        after_open = [t for t in times if r["reopened_at"] < t < nxt["t_d"]]
        out.append(check(f"重启{i}：下一个 B 之前新 A 至少 {A_START_DELTAS} 个非空增量",
                         f">= {A_START_DELTAS}", len(after_open), len(after_open) >= A_START_DELTAS))
    return out


def age_checks(data: dict, limit_s: float) -> list[dict]:
    """每个 B 发出时，当前 A 的运行时长不超过重启阈值。"""
    opened = sorted(data["run"].get("a_opened_at", []))
    worst = 0.0
    for e in data["events"]:
        if e["t_d"] is None:
            continue
        owner = max((o for o in opened if o <= e["t_d"]), default=None)
        if owner is not None:
            worst = max(worst, e["t_d"] - owner)
    return [check(f"每个 B 发出时 A 的运行时长 ≤ {limit_s} s", f"<= {limit_s}", round(worst, 3), worst <= limit_s)]


def after_b_checks(data: dict) -> list[dict]:
    """相邻两个 B 之间，A 在上一个 B 结束后收到至少 30 个非空增量。"""
    times = data["a_times"]
    bad = []
    events = [e for e in data["events"] if e.get("t_end") is not None and e.get("status") == "ok"]
    for prev, nxt in zip(events, events[1:]):
        if nxt["t_d"] is None:
            continue
        window = [t for t in times if prev["t_end"] < t <= nxt["t_d"]]
        if len(window) < A_AFTER_B_DELTAS:
            bad.append((prev["name"], nxt["name"], len(window)))
    return [check(f"相邻 B 之间 A 收到 ≥ {A_AFTER_B_DELTAS} 个增量", "无不足", bad, not bad)]


def labels(data: dict) -> dict:
    return {e["name"]: e for e in data["result"]["events"]}


def positive_checks(data: dict) -> list[dict]:
    run, res = data["run"], data["result"]
    lab = labels(data)
    checks = [
        check("正向：运行状态 complete", "complete", run.get("status"), run.get("status") == "complete"),
        check("正向：13 个事件全部执行", N_EVENTS, len(data["events"]), len(data["events"]) == N_EVENTS),
        check("正向：13 个事件状态全部 ok", "ok", sorted({e["status"] for e in data["events"]}),
              all(e["status"] == "ok" for e in data["events"])),
        check("正向：每个事件进入停顿判读", ENTERED, sorted({e["label"] for e in res["events"]}),
              all(e["label"] == ENTERED for e in res["events"])),
        check("正向：结构两级全中（13/13）", 13, sum(1 for e in res["events"] if e["structure"]["level2"]),
              all(e["structure"]["level2"] for e in res["events"])),
        check("正向：13 个事件全部在区间内（n=13, k=13）", "成立", res["aggregate"]["verdict"],
              res["aggregate"]["n"] == 13 and res["aggregate"]["k"] == 13 and res["aggregate"]["verdict"] == "成立"),
        check("正向：零输出总数为 0", 0, res["zero_output_total"], res["zero_output_total"] == 0),
        check("正向：前置检查通过", True, data["precheck"]["pass"], data["precheck"]["pass"]),
        check("正向：空闲窗口内 active 全为 0", True,
              all(s["active"] == 0 for s in data["precheck"]["samples"]), all(s["active"] == 0 for s in data["precheck"]["samples"])),
        check("正向：运行未超过 300 秒，A 未重启（规则未触发）", "无重启",
              [r["reason"] for r in run.get("restarts", [])], not run.get("restarts", [])),
        check("正向：重启阈值为预登记的 300 秒（未覆盖）", 300.0, run.get("a_restart_s"),
              run.get("a_restart_s") == A_RESTART_PREREG_S and run.get("a_restart_override") is None),
        check("正向：开始前 A 收够 50 个增量", f">= {A_START_DELTAS}",
              sum(1 for t in data["a_times"] if t < data["events"][0]["t_d"]),
              sum(1 for t in data["a_times"] if t < data["events"][0]["t_d"]) >= A_START_DELTAS),
        check("正向：演练未使用 GPU 读数（--no-gpu）", "全部为 None",
              sorted({e.get("gpu_before_mib") for e in data["events"]}, key=str),
              all(e.get("gpu_before_mib") is None for e in data["events"])),
    ]
    checks += age_checks(data, A_RESTART_PREREG_S)
    checks += restart_checks(data)
    checks += after_b_checks(data)
    checks.append(check("正向：标签与判读表一致", len(lab), len(res["events"]), len(lab) == len(res["events"])))
    return checks


def restart_control_checks(data: dict) -> list[dict]:
    run, res = data["run"], data["result"]
    limit = float(run.get("a_restart_s"))
    checks = [
        check("A 重启：运行状态 complete", "complete", run.get("status"), run.get("status") == "complete"),
        check("A 重启：覆盖阈值已记录（演练专用）", 1.5, run.get("a_restart_override"),
              run.get("a_restart_override") == 1.5),
        check("A 重启：至少发生一次重启，原因为运行时长", "≥ 1", len(run.get("restarts", [])),
              any(r["reason"] == "A 运行超过重启阈值" for r in run.get("restarts", []))),
        check("A 重启：13 个事件全部进入判读", N_EVENTS, res["aggregate"]["n"], res["aggregate"]["n"] == N_EVENTS),
        check("A 重启：零输出总数为 0", 0, res["zero_output_total"], res["zero_output_total"] == 0),
    ]
    checks += age_checks(data, limit)
    checks += restart_checks(data)
    checks += after_b_checks(data)
    return checks


def zero_control_checks(data: dict) -> list[dict]:
    res = data["result"]
    events = {e["name"]: e for e in res["events"]}
    others_zero = all((e["zero_output"] or 0) == 0 for n, e in events.items() if n != "T2/03")
    return [
        check("零输出：运行状态 complete", "complete", data["run"].get("status"), data["run"].get("status") == "complete"),
        check("零输出：T2/03 的零输出计数大于 0（A 在 B 预填时未停）", "> 0", events["T2/03"]["zero_output"],
              (events["T2/03"]["zero_output"] or 0) > 0),
        check("零输出：只有 T2/03 被标出", ["T2/03"], res["zero_output_events"], res["zero_output_events"] == ["T2/03"]),
        check("零输出：其余事件计数为 0", True, others_zero, others_zero),
        check("零输出：判读为有零输出事件", "有零输出事件", res["verdict_zero_output"],
              res["verdict_zero_output"] == "有零输出事件"),
    ]


def contamination_control_checks(data: dict) -> list[dict]:
    res = data["result"]
    events = {e["name"]: e for e in res["events"]}
    t05 = events["T2/05"]
    others_entered = all(e["label"] == ENTERED for n, e in events.items() if n != "T2/05")
    return [
        check("混入：运行状态 complete（混入不停止运行）", "complete", data["run"].get("status"),
              data["run"].get("status") == "complete"),
        check("混入：T2/05 标为 contaminated", "contaminated", t05["label"], t05["label"] == "contaminated"),
        check("混入：T2/05 的原因含 active 多报", True,
              any(r.startswith("active") for r in t05["contamination"]), any(r.startswith("active") for r in t05["contamination"])),
        check("混入：T2/05 不进入判读", False, t05["entered"], t05["entered"] is False),
        check("混入：其余 12 个事件进入判读", True, others_entered, others_entered),
        check("混入：n = 12", 12, res["aggregate"]["n"], res["aggregate"]["n"] == 12),
    ]


def precheck_control_checks(data: dict) -> list[dict]:
    pre = data["precheck"] or {}
    cache = (pre.get("checks") or {}).get("cache_state", {})
    return [
        check("前置检查：tool 退出码 3", 3, data["exit"], data["exit"] == 3),
        check("前置检查：precheck.json 判定为不通过", False, pre.get("pass"), pre.get("pass") is False),
        check("前置检查：cache_state 因 completed=3 不通过", (False, 3), (cache.get("pass"), cache.get("completed")),
              cache.get("pass") is False and cache.get("completed") == 3),
        check("前置检查：run.json 状态为 precheck_failed", "precheck_failed", (data["run"] or {}).get("status"),
              (data["run"] or {}).get("status") == "precheck_failed"),
        check("前置检查：没有发送任何事件", 0, len(data["events"]), len(data["events"]) == 0),
        check("前置检查：没有打开 A", None, (data["run"] or {}).get("a_opened_at"),
              "a_opened_at" not in (data["run"] or {})),
    ]


def build() -> dict:
    loaded = {name: load(name) for name in ("R_positive", "R_a_restart", "R_b_zero", "R_c_contaminate", "R_d_precheck")}
    runs = {
        "R_positive": {"config": {"scale": 1.0, "stub": {}}, "checks": positive_checks(loaded["R_positive"])},
        "R_a_restart": {"config": {"scale": 1.0, "a_restart_override_s": 1.5, "stub": {}},
                        "checks": restart_control_checks(loaded["R_a_restart"])},
        "R_b_zero": {"config": {"scale": 1.0, "stub": {"a_no_pause": "T2/03"}},
                     "checks": zero_control_checks(loaded["R_b_zero"])},
        "R_c_contaminate": {"config": {"scale": 1.0, "stub": {"contaminate": "T2/05"}},
                            "checks": contamination_control_checks(loaded["R_c_contaminate"])},
        "R_d_precheck": {"config": {"scale": 1.0, "stub": {"completed_init": 3}},
                         "checks": precheck_control_checks(loaded["R_d_precheck"])},
    }
    for item in runs.values():
        item["pass"] = all(c["pass"] for c in item["checks"])
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description="任务 S 演练结果核对")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写 REHEARSAL_S.json")
    args = parser.parse_args()
    runs = build()
    all_pass = all(item["pass"] for item in runs.values())
    summary = {name: item["pass"] for name, item in runs.items()}
    if args.dry_run:
        print(json.dumps({"all_pass": all_pass, "runs": summary}, ensure_ascii=False))
        for name, item in runs.items():
            for c in item["checks"]:
                if not c["pass"]:
                    print("FAIL", name, c["check"], "| 预期", c["expected"], "| 实际", c["actual"])
        return 0 if all_pass else 3
    doc = {
        "schema": "ophak_task_s_rehearsal/v1",
        "written_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "note": ("桩服务按预登记 v2 复现时序。演练证明工装的算术、结构两级、混入与零输出判读路径、"
                 "A 的 300 秒重启规则与前置检查；不是对生产的测量，不能当作任务 S 的证据。"
                 "A 重启的覆盖阈值（1.5 秒）只用于缩放演练，正向演练使用预登记的 300 秒。"),
        "all_pass": all_pass,
        "runs": runs,
        "sources": {name: sha(WORK / name) for name in SOURCES},
        "prereg_sha256": sha(PREREG),
    }
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(OUT, 0o444)
    print(json.dumps({"all_pass": all_pass, "runs": summary}, ensure_ascii=False))
    return 0 if all_pass else 3


if __name__ == "__main__":
    raise SystemExit(main())
