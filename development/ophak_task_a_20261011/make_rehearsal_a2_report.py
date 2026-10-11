#!/usr/bin/env python3
"""A2 CPU 演练结果核对：逐条比对预期与实际，写 REHEARSAL_A2.json（0444）。

只读演练目录，不改运行数据。预期值写在本文件里，不根据结果回填。
桩服务按预登记 T2 行复现时序：演练证明工装的算术、识别路径（请求结束后复扫、请求进行中的实时监视）与窗口编排在桩服务上成立，
不是对生产的测量，不能当作任务 A2 的证据。缩放演练（scale < 1）的预填与解码时间同比缩短，G2 的绝对判读不适用，按缩放后的区间核对。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
RUNS = Path("/data2/FreeToken/runs/dev_ophak_task_a2_20261011/rehearsal")
PREREG = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json")
OUT = WORK / "REHEARSAL_A2.json"
SOURCES = ("task_a_runner.py", "stub_server.py", "analyze_task_a.py", "analyze_task_a2.py",
           "test_task_a_runner.py", "make_rehearsal_a2_report.py", "run_rehearsals_a2.sh", "INPUTS.json")
SERVICES = ("A1_on", "A2_on", "B1_off", "B2_off")
FULL_KEYS = ["warm/00"] + [f"T2/{k:02d}" for k in range(12)]
ABORT_KEY = "T2/05"
ABORT_INDEX = 5
DETECT_LIMIT_S = 10.0
G2_BAND = (2.3, 3.0)    # 预登记 §7：变化轮 Δ 中位数区间（秒，缩放 1.0）
G2_FLOOR = 1.8          # 变化轮 Δ 下限（秒，缩放 1.0）
COLD_BAND = (2.0, 3.0)  # 冷轮 T2/00 的 Δ 预测区间（秒，缩放 1.0）


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jrows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def eq(label: str, expected, actual) -> dict:
    return {"check": label, "expected": expected, "actual": actual, "pass": expected == actual}


def flag(label: str, expected: str, ok: bool, actual) -> dict:
    return {"check": label, "expected": expected, "actual": actual, "pass": bool(ok)}


def in_band(value, band: tuple[float, float], scale: float) -> bool:
    return value is not None and band[0] * scale <= value <= band[1] * scale


def band_text(band: tuple[float, float], scale: float) -> str:
    return f"[{band[0] * scale:.4f}, {band[1] * scale:.4f}]"


def prereg_t2() -> tuple[list[str], list[str]]:
    rounds = json.loads(PREREG.read_text(encoding="utf-8"))["trajectories"]["T2"]["rounds"]
    keys = [f"T2/{k:02d}" for k in range(len(rounds))]
    changed = [key for key, row in zip(keys, rounds) if row["class"] == "changed"]
    cold = [key for key, row in zip(keys, rounds) if row["class"] == "cold"]
    return changed, cold


def load(name: str) -> tuple[dict, dict, Path]:
    base = RUNS / name
    analysis = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    window = json.loads((base / "window" / "window_summary.json").read_text(encoding="utf-8"))
    return analysis, window, base


def window_checks(window: dict, base: Path, expected: dict[str, tuple[str, int]]) -> list[dict]:
    rows = {row["service"]: row for row in window["services"]}
    checks = [eq("窗口终态", "complete", window.get("terminal"))]
    for svc in SERVICES:
        row = rows.get(svc, {})
        checks.append(eq(f"{svc}：状态与完成条数", list(expected[svc]), [row.get("status"), row.get("done")]))
        checks.append(eq(f"{svc}：清场成功", True, row.get("cleanup_ok")))
        checks.append(eq(f"{svc}：就绪显存读数已写入", True, (base / "window" / svc / "memory_ready.json").exists()))
    return checks


def request_checks(base: Path, svc: str, keys: list[str], statuses: list[str]) -> tuple[list[dict], list[dict]]:
    rows = jrows(base / "window" / svc / "requests.jsonl")
    no_memory = [r["key"] for r in rows if r.get("memory_before_mib") is None or r.get("memory_after_mib") is None]
    checks = [
        eq(f"{svc}：请求序列", keys, [r["key"] for r in rows]),
        eq(f"{svc}：每条记录状态", statuses, [r.get("status") for r in rows]),
        eq(f"{svc}：每条请求前后都有显存读数", [], no_memory),
    ]
    return checks, rows


def s0_failures(base: Path, analysis: dict) -> list[str]:
    """只核对 ok 行。中止行没有 usage（流在结束包之前断开），S0 无从核对，与 analyze_task_a2 的 s0_failed_keys 一致。"""
    status = {(r["key"], svc): r.get("status") for svc in SERVICES
              for r in jrows(base / "window" / svc / "requests.jsonl")}
    return [f"{key}/{svc}" for key, row in analysis["rounds"].items()
            for svc, chk in row["checks"].items()
            if chk is not None and status.get((key, svc)) == "ok" and not chk["s0_prompt_tokens"]]


def arithmetic_checks(base: Path, analysis: dict, scale: float) -> list[dict]:
    g2 = analysis["G2"]
    cold = analysis["cold_rounds"]["T2/00"]["delta_s"]
    floor = G2_FLOOR * scale
    return [
        flag("G2 Δ 中位数在缩放后的区间内", band_text(G2_BAND, scale),
             in_band(g2["median_s"], G2_BAND, scale), g2["median_s"]),
        flag("G2 每个已完成变化轮 Δ 不低于缩放后的下限", f">= {floor:.4f}",
             g2["min_s"] is not None and g2["min_s"] >= floor, g2["min_s"]),
        flag("冷轮 T2/00 Δ 在缩放后的预测区间内", band_text(COLD_BAND, scale),
             in_band(cold, COLD_BAND, scale), cold),
        eq("S0：每轮 prompt_tokens 与预登记一致", [], s0_failures(base, analysis)),
        eq("G1 切段无不符", {}, analysis["G1"]["segments_mismatch_by_service"]),
    ]


def control_checks(analysis: dict) -> list[dict]:
    return [
        eq("G2 阴性对照（未变化轮）成立", "成立", analysis["G2_negative_control"]["verdict"]),
        eq("G2 同臂漂移未超限", "未见环境漂移", analysis["G2_drift"]["verdict"]),
        eq("G2 上下限无违反", [], analysis["G2_bounds_violations"]),
    ]


def positive_checks(base: Path, analysis: dict, window: dict) -> list[dict]:
    checks = window_checks(window, base, {svc: ("complete", 13) for svc in SERVICES})
    for svc in SERVICES:
        checks += request_checks(base, svc, FULL_KEYS, ["ok"] * 13)[0]
    checks += arithmetic_checks(base, analysis, 1.0)
    checks += control_checks(analysis)
    checks += [
        eq("G2 判读", "成立", analysis["G2"]["verdict"]),
        eq("cached 无不符", {}, analysis["cached_mismatch_by_service"]),
    ]
    g3_bad = [key for key, pair in analysis["G3_reproducibility"].items()
              if not (pair["A1_vs_A2"] and pair["B1_vs_B2"]
                      and pair["A1_vs_A2"]["equal"] and pair["B1_vs_B2"]["equal"])]
    checks.append(eq("G3 同臂两服务输出逐字相同（全部轮）", [], g3_bad))
    return checks


def worker_exit_checks(base: Path, analysis: dict, window: dict, scale: float,
                       hang_s: float | None) -> tuple[list[dict], str]:
    changed, _ = prereg_t2()
    checks = window_checks(window, base, {"A1_on": ("complete", 13), "B1_off": ("worker_exit", 6),
                                          "B2_off": ("complete", 13), "A2_on": ("complete", 13)})
    for svc in ("A1_on", "B2_off", "A2_on"):
        checks += request_checks(base, svc, FULL_KEYS, ["ok"] * 13)[0]
    b1_checks, b1_rows = request_checks(base, "B1_off", FULL_KEYS[:7], ["ok"] * 6 + ["worker_exit"])
    checks += b1_checks
    last = b1_rows[-1] if b1_rows else {}
    events = [e for e in jrows(base / "window" / "B1_off" / "stub_stats.jsonl") if e.get("event") == "worker_exit"]
    latency = None
    if events and last.get("trip_wall_time") is not None:
        latency = last["trip_wall_time"] - events[0]["t"]
    polls = last.get("watch_polls") or 0
    checks += [
        eq("B1_off：退出事件只一次，位于 T2/05", [ABORT_KEY], [e["key"] for e in events]),
        eq("B1_off：末条记录的识别来源", "worker_exit", last.get("watch_trip")),
        flag("B1_off：中止行无 usage（流在结束包之前断开）", "无", not last.get("usage"), last.get("usage")),
        flag("识别时延在 [0, 10) 秒内", "[0, 10)", latency is not None and 0 <= latency < DETECT_LIMIT_S, latency),
        eq("G2 Δ 缺失的轮次 = 中止后仍在计划内的变化轮",
           [key for key in changed if int(key[3:]) >= ABORT_INDEX], analysis["G2"]["rounds_missing"]),
        eq("cached 无不符", {}, analysis["cached_mismatch_by_service"]),
    ]
    checks += arithmetic_checks(base, analysis, scale)
    checks += control_checks(analysis)
    if hang_s is not None:
        total = last.get("total_s")
        checks += [
            flag("在途识别：请求结束前由实时监视识别（watch_polls ≥ 1）", "≥ 1", polls >= 1, polls),
            flag("客户端主动断开：总耗时明显短于挂起时长", f"< {hang_s - 5:.0f}",
                 total is not None and total < hang_s - 5, total),
        ]
    return checks, ("in_flight" if polls >= 1 else "post_request_scan")


def wrong_cached_checks(base: Path, analysis: dict, window: dict, scale: float) -> list[dict]:
    checks = window_checks(window, base, {svc: ("complete", 13) for svc in SERVICES})
    for svc in SERVICES:
        checks += request_checks(base, svc, FULL_KEYS, ["ok"] * 13)[0]
    rows = jrows(base / "window" / "A1_on" / "requests.jsonl")
    rec = next((r for r in rows if r["key"] == "T2/02"), {})
    want = (rec.get("expect") or {}).get("cached")
    via_usage = (rec.get("usage") or {}).get("cached_tokens")
    via_line = ((rec.get("prefill_lines") or [{}])[0]).get("cached_token")
    checks += [
        eq("复用不符只在 A1_on 的 T2/02", {"A1_on": ["T2/02"]}, analysis["cached_mismatch_by_service"]),
        flag("T2/02：usage 与首条 Prefill 行的 cached 都与预登记不符", f"!= {want}",
             want is not None and via_usage != want and via_line != want,
             {"usage": via_usage, "prefill": via_line}),
    ]
    checks += arithmetic_checks(base, analysis, scale)
    checks += control_checks(analysis)
    return checks


def finish(checks: list[dict], scale: float, inject: dict, detection_path: str | None) -> dict:
    return {"config": {"scale": scale, "inject": inject}, "detection_path": detection_path,
            "pass": all(c["pass"] for c in checks), "checks": checks}


def build_runs() -> dict[str, dict]:
    runs: dict[str, dict] = {}
    analysis, window, base = load("R_positive")
    runs["R_positive"] = finish(positive_checks(base, analysis, window), 1.0, {}, None)
    analysis, window, base = load("R_a_worker_exit")
    checks, path = worker_exit_checks(base, analysis, window, 0.05, None)
    runs["R_a_worker_exit"] = finish(checks, 0.05, {"B1_off": {"worker-exit-at": "T2/05"}}, path)
    analysis, window, base = load("R_a_hang")
    checks, path = worker_exit_checks(base, analysis, window, 0.05, 30.0)
    runs["R_a_hang"] = finish(checks, 0.05,
                              {"B1_off": {"worker-exit-at": "T2/05", "worker-exit-hold-s": "30"}}, path)
    analysis, window, base = load("R_b_wrong_cached")
    checks = wrong_cached_checks(base, analysis, window, 0.05)
    runs["R_b_wrong_cached"] = finish(checks, 0.05, {"A1_on": {"wrong-cached": "T2/02"}}, None)
    return runs


NOTE = ("桩服务按预登记 T2 行复现时序。演练证明工装的算术、识别（请求结束后复扫与请求进行中的实时监视两条路径）"
        "与窗口编排在桩服务上成立；不是对生产的测量，不能当作任务 A2 的证据。缩放演练的 G2 绝对判读不适用，按缩放后的区间核对。"
        "生产上 /health 的响应时延、显存读数与 OOM 文本匹配尚未在真实服务上验证。")


def build_doc() -> dict:
    runs = build_runs()
    return {
        "schema": "ophak_task_a2_rehearsal/v2",
        "written_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "note": NOTE,
        "all_pass": all(run["pass"] for run in runs.values()),
        "runs": runs,
        "sources": {name: sha(WORK / name) for name in SOURCES},
        "prereg_sha256": sha(PREREG),
    }


def failing(doc: dict) -> list[str]:
    return [f"{name}: {c['check']} | 预期 {c['expected']!r} | 实际 {c['actual']!r}"
            for name, run in doc["runs"].items() for c in run["checks"] if not c["pass"]]


def main() -> int:
    parser = argparse.ArgumentParser(description="A2 CPU 演练结果核对")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写 REHEARSAL_A2.json")
    args = parser.parse_args()
    doc = build_doc()
    summary = {name: run["pass"] for name, run in doc["runs"].items()}
    if args.dry_run:
        print(json.dumps({"all_pass": doc["all_pass"], "runs": summary}, ensure_ascii=False))
        for line in failing(doc):
            print("FAIL", line)
        return 0 if doc["all_pass"] else 3
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(OUT, 0o444)
    print(json.dumps({"all_pass": doc["all_pass"], "runs": summary}, ensure_ascii=False))
    return 0 if doc["all_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
