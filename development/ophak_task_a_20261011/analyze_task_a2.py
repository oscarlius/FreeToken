#!/usr/bin/env python3
"""任务 A2（只跑 T2）机械判读（plan/OPHAK_TASK_A2_T2_ONLY_20261011.md §7）。

只按预登记的 T2 行与 §7 规则计算，不加解释。输入是 window02 目录（每个服务一个子目录），
以及预登记与 INPUTS.json。基础函数复用 analyze_task_a.py（只 import，不改）。

Δ（每轮）= mean(A1_on, A2_on) − mean(B1_off, B2_off)。缺任一服务则该轮 Δ 为 None。
同臂漂移的相对差 = |a − b| / max(a, b)。显存只报告，不设判据。
"""
from __future__ import annotations

import importlib.util
import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("analyze_task_a", HERE / "analyze_task_a.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
load_service = _base.load_service
record_checks = _base.record_checks
first_diff = _base.first_diff

A_SERVICES = ("A1_on", "A2_on")
B_SERVICES = ("B1_off", "B2_off")
ALL_SERVICES = A_SERVICES + B_SERVICES
CHANGED_BAND = (2.3, 3.0)
CHANGED_FLOOR = 1.8
COLD_PREDICTED = (2.0, 3.0)
DRIFT_LIMIT = 0.10
DRIFT_ROUNDS_MAX = 3
NEG_ABS_LIMIT = 0.3
BOUND_HIGH = 3.2


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _ready_memory(window_dir: Path, name: str) -> int | None:
    path = window_dir / name / "memory_ready.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("memory_used_mib")


def analyze_run_t2(window_dir: Path, prereg: dict, inputs: dict) -> dict[str, Any]:
    services = {name: load_service(window_dir, name) for name in ALL_SERVICES}
    window = json.loads((window_dir / "window_summary.json").read_text(encoding="utf-8"))
    run_status = {s["service"]: s for s in window["services"]}

    rounds_exp = prereg["trajectories"]["T2"]["rounds"]
    keys = [(f"T2/{k:02d}", k, exp["class"]) for k, exp in enumerate(rounds_exp)]

    service_info: dict[str, dict] = {}
    for name in ALL_SERVICES:
        svc = services[name]
        s0_bad = []
        for key, rec in svc["records"].items():
            chk = record_checks(rec)
            if chk is not None and rec.get("status") == "ok" and not chk["s0_prompt_tokens"]:
                s0_bad.append(key)
        status = run_status.get(name, {})
        service_info[name] = {
            "status": status.get("status", "not_run"),
            "stop_reason": status.get("stop_reason"),
            "done": status.get("done"),
            "requests_recorded": len(svc["records"]),
            "s0_failed_keys": s0_bad,
            "void_failed_harness": bool(s0_bad),
            "ready_memory_mib": _ready_memory(window_dir, name),
        }

    def usable(name: str, key: str) -> float | None:
        rec = services[name]["records"].get(key)
        if rec is None or service_info[name]["void_failed_harness"]:
            return None
        if rec.get("status") != "ok" or rec.get("ttft_s") is None:
            return None
        return float(rec["ttft_s"])

    rounds: dict[str, dict] = {}
    for key, k, cls in keys:
        ttft = {name: usable(name, key) for name in ALL_SERVICES}
        on_vals = [ttft[n] for n in A_SERVICES if ttft[n] is not None]
        off_vals = [ttft[n] for n in B_SERVICES if ttft[n] is not None]
        delta = (statistics.mean(on_vals) - statistics.mean(off_vals)
                 if len(on_vals) == 2 and len(off_vals) == 2 else None)
        checks = {name: record_checks(services[name]["records"][key]) if key in services[name]["records"] else None
                  for name in ALL_SERVICES}
        rounds[key] = {"class": cls, "ttft_s": ttft, "delta_s": delta, "checks": checks,
                       "expect": {"prompt_tokens": rounds_exp[k]["prompt_tokens"], "cached": rounds_exp[k]["cached"],
                                  "on_segments": rounds_exp[k]["on_segments"],
                                  "off_segments": rounds_exp[k]["off_segments"]}}

    def keys_of(cls: str) -> list[str]:
        return [key for key, _, c in keys if c == cls]

    changed, unchanged, cold = keys_of("changed"), keys_of("unchanged"), keys_of("cold")
    changed_deltas = {key: rounds[key]["delta_s"] for key in changed}
    present = [d for d in changed_deltas.values() if d is not None]
    med = _median(present)
    if med is None:
        g2 = "无数据"
    elif med < 1.0:
        g2 = "不成立"
    elif CHANGED_BAND[0] <= med <= CHANGED_BAND[1] and min(present) >= CHANGED_FLOOR and len(present) == len(changed):
        g2 = "成立"
    else:
        g2 = "部分成立"

    unchanged_deltas = [rounds[key]["delta_s"] for key in unchanged if rounds[key]["delta_s"] is not None]
    neg_med = _median(unchanged_deltas)
    if neg_med is None:
        neg_verdict = "无数据"
    else:
        neg_verdict = "成立" if abs(neg_med) <= NEG_ABS_LIMIT else "不成立（写明）"

    drift_rows = []
    for key in changed + unchanged:
        for pair in (("A1_on", "A2_on"), ("B1_off", "B2_off")):
            a, b = rounds[key]["ttft_s"][pair[0]], rounds[key]["ttft_s"][pair[1]]
            if a is None or b is None or max(a, b) <= 0:
                continue
            rel = abs(a - b) / max(a, b)
            drift_rows.append({"key": key, "pair": "/".join(pair), "rel_diff": round(rel, 4),
                               "over_limit": rel > DRIFT_LIMIT})
    drift_over = sum(1 for row in drift_rows if row["over_limit"])
    if not drift_rows:
        drift_verdict = "无数据（同臂两服务均未完成）"
    elif drift_over > DRIFT_ROUNDS_MAX:
        drift_verdict = "环境漂移，G2 降级为仅供参考"
    else:
        drift_verdict = "未见环境漂移"

    bounds = [{"key": key, "delta_s": rounds[key]["delta_s"]} for key in changed
              if rounds[key]["delta_s"] is not None and (rounds[key]["delta_s"] > BOUND_HIGH
                                                          or rounds[key]["delta_s"] < 0)]

    cold_report = {}
    for key in cold:
        d = rounds[key]["delta_s"]
        cold_report[key] = {"delta_s": d, "predicted_range_s": list(COLD_PREDICTED),
                            "inside": None if d is None else COLD_PREDICTED[0] <= d <= COLD_PREDICTED[1]}

    g1_fail: dict[str, list[str]] = {}
    cache_fail: dict[str, list[str]] = {}
    for name in ALL_SERVICES:
        for key, rec in services[name]["records"].items():
            chk = record_checks(rec)
            if chk is None:
                continue
            if chk["status_ok"] and not chk["g1_segments"]:
                g1_fail.setdefault(name, []).append(key)
            if chk["status_ok"] and not (chk["cached_usage"] and chk["cached_first_line"]):
                cache_fail.setdefault(name, []).append(key)

    def pair_equal(a_name: str, b_name: str, key: str) -> dict | None:
        ta = services[a_name]["outputs"].get(key)
        tb = services[b_name]["outputs"].get(key)
        if ta is None or tb is None:
            return None
        return {"equal": ta == tb, "first_diff_char": None if ta == tb else first_diff(ta, tb)}

    g3 = {key: {"A1_vs_A2": pair_equal("A1_on", "A2_on", key), "B1_vs_B2": pair_equal("B1_off", "B2_off", key)}
          for key, _, _ in keys}
    g4 = {key: {"A1_vs_B1": pair_equal("A1_on", "B1_off", key), "A2_vs_B2": pair_equal("A2_on", "B2_off", key)}
          for key, _, _ in keys}

    memory: dict[str, dict] = {}
    for name in ALL_SERVICES:
        rows = []
        for key in ["warm/00"] + [k for k, _, _ in keys]:
            rec = services[name]["records"].get(key)
            if rec is None:
                continue
            before, after = rec.get("memory_before_mib"), rec.get("memory_after_mib")
            rows.append({"key": key, "before_mib": before, "after_mib": after,
                         "increment_mib": (after - before) if before is not None and after is not None else None})
        values = [v for r in rows for v in (r["before_mib"], r["after_mib"]) if v is not None]
        increments = [r["increment_mib"] for r in rows if r["increment_mib"] is not None]
        memory[name] = {"ready_mib": service_info[name]["ready_memory_mib"], "rows": rows,
                        "max_mib": max(values) if values else None,
                        "max_increment_mib": max(increments) if increments else None}

    return {
        "schema": "ophak_task_a2_analysis/v1",
        "window_terminal": window.get("terminal"),
        "services": service_info,
        "rounds": rounds,
        "G1": {"segments_mismatch_by_service": g1_fail},
        "cached_mismatch_by_service": cache_fail,
        "G2": {"changed_deltas_s": changed_deltas, "median_s": med,
               "min_s": min(present) if present else None,
               "rounds_missing": [k for k, d in changed_deltas.items() if d is None], "verdict": g2},
        "G2_negative_control": {"unchanged_deltas_s": {k: rounds[k]["delta_s"] for k in unchanged},
                                "median_abs_s": None if neg_med is None else abs(neg_med),
                                "verdict": neg_verdict},
        "G2_drift": {"rows": drift_rows, "rounds_over_limit": drift_over, "verdict": drift_verdict},
        "G2_bounds_violations": bounds,
        "cold_rounds": cold_report,
        "G3_reproducibility": g3,
        "G4_on_vs_off": g4,
        "memory_mib": memory,
        "rule_notes": [
            "Δ = mean(A1_on, A2_on) − mean(B1_off, B2_off)",
            "同臂漂移相对差 = |a − b| / max(a, b)，阈值 10%，超过 3 轮为环境漂移",
            "G2 成立：中位数在 [2.3, 3.0] 且每轮 Δ ≥ 1.8；中位数 < 1.0 为不成立；其余为部分成立",
            "显存只报告：每条请求前后的 memory.used，服务就绪时一次",
        ],
    }
