#!/usr/bin/env python3
"""任务 A 机械判读（指令 §6）。只按预登记与 §6 的规则计算，不加解释。

输入：window 目录（每个服务一个子目录：requests.jsonl、outputs.json、summary.json），预登记，INPUTS.json。
输出：analysis 字典（由 task_a_runner 写成 analysis.json）。

记号：
  Δ（每轮）= mean(A1_on, A2_on) − mean(B1_off, B2_off)，单位秒。缺任一服务则该轮 Δ 为 None。
  同臂漂移的相对差 = |a − b| / max(a, b)。
  轮次分类完全取自预登记（class：cold / changed / unchanged）。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

A_SERVICES = ("A1_on", "A2_on")
B_SERVICES = ("B1_off", "B2_off")
ALL_SERVICES = A_SERVICES + B_SERVICES
CHANGED_BAND = (2.3, 3.0)
CHANGED_FLOOR = 1.8
COLD_PREDICTED = {"seed_real": (-0.5, 1.5), "T2": (2.0, 3.0)}
DRIFT_LIMIT = 0.10
DRIFT_ROUNDS_MAX = 3
NEG_ABS_LIMIT = 0.3
BOUND_HIGH = 3.2


def load_service(window_dir: Path, name: str) -> dict[str, Any]:
    base = window_dir / name
    records: dict[str, dict] = {}
    req = base / "requests.jsonl"
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                records[rec["key"]] = rec
    outputs_path = base / "outputs.json"
    summary_path = base / "summary.json"
    return {
        "records": records,
        "outputs": json.loads(outputs_path.read_text(encoding="utf-8")) if outputs_path.exists() else {},
        "summary": json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None,
    }


def record_checks(rec: dict[str, Any]) -> dict[str, bool] | None:
    """逐轮的机械核对：S0 输入、G1 切段、cached（usage 与首条 Prefill 行）。warmup 没有预期值，返回 None。"""
    exp = rec.get("expect")
    if exp is None:
        return None
    usage = rec.get("usage") or {}
    lines = rec.get("prefill_lines") or []
    return {
        "status_ok": rec.get("status") == "ok",
        "s0_prompt_tokens": usage.get("prompt_tokens") == exp["prompt_tokens"],
        "g1_segments": [line["new_token"] for line in lines] == exp["segments"],
        "cached_usage": usage.get("cached_tokens") == exp["cached"],
        "cached_first_line": bool(lines) and lines[0]["cached_token"] == exp["cached"],
    }


def first_diff(a: str, b: str) -> int | None:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def analyze_run(window_dir: Path, prereg: dict, inputs: dict) -> dict[str, Any]:
    services = {name: load_service(window_dir, name) for name in ALL_SERVICES}
    window = json.loads((window_dir / "window_summary.json").read_text(encoding="utf-8"))
    run_status = {s["service"]: s for s in window["services"]}

    # 轮次键与预登记分类（seed 8 轮 + T2 12 轮，不含 warmup）
    keys: list[tuple[str, str, int, str]] = []
    for traj in ("seed_real", "T2"):
        for k, exp in enumerate(prereg["trajectories"][traj]["rounds"]):
            keys.append((f"{traj}/{k:02d}", traj, k, exp["class"]))

    # 逐服务：S0 失败的服务整体作废（§6 S0）
    service_info: dict[str, dict] = {}
    for name in ALL_SERVICES:
        svc = services[name]
        s0_bad = [key for key, rec in svc["records"].items()
                  if (chk := record_checks(rec)) is not None and rec.get("status") == "ok" and not chk["s0_prompt_tokens"]]
        service_info[name] = {
            "status": (run_status.get(name) or {}).get("status", "not_run"),
            "stop_reason": (run_status.get(name) or {}).get("stop_reason"),
            "requests_recorded": len(svc["records"]),
            "s0_failed_keys": s0_bad,
            "void_failed_harness": bool(s0_bad),
        }

    def usable(name: str, key: str) -> float | None:
        rec = services[name]["records"].get(key)
        if rec is None or service_info[name]["void_failed_harness"]:
            return None
        if rec.get("status") != "ok" or rec.get("ttft_s") is None:
            return None
        return float(rec["ttft_s"])

    rounds: dict[str, dict] = {}
    for key, traj, k, cls in keys:
        ttft = {name: usable(name, key) for name in ALL_SERVICES}
        on_vals = [ttft[n] for n in A_SERVICES if ttft[n] is not None]
        off_vals = [ttft[n] for n in B_SERVICES if ttft[n] is not None]
        delta = (statistics.mean(on_vals) - statistics.mean(off_vals)
                 if len(on_vals) == 2 and len(off_vals) == 2 else None)
        checks = {name: record_checks(services[name]["records"][key]) if key in services[name]["records"] else None
                  for name in ALL_SERVICES}
        rounds[key] = {"class": cls, "ttft_s": ttft, "delta_s": delta, "checks": checks,
                       "expect": {"prompt_tokens": prereg["trajectories"][traj]["rounds"][k]["prompt_tokens"],
                                  "cached": prereg["trajectories"][traj]["rounds"][k]["cached"],
                                  "on_segments": prereg["trajectories"][traj]["rounds"][k]["on_segments"],
                                  "off_segments": prereg["trajectories"][traj]["rounds"][k]["off_segments"]}}

    def keys_of(cls: str) -> list[str]:
        return [key for key, _, _, c in keys if c == cls]

    changed, unchanged, cold = keys_of("changed"), keys_of("unchanged"), keys_of("cold")
    changed_deltas = {key: rounds[key]["delta_s"] for key in changed}
    present = [d for d in changed_deltas.values() if d is not None]
    med = median_or_none(present)
    if med is None:
        g2 = "无数据"
    elif med < 1.0:
        g2 = "不成立"
    elif CHANGED_BAND[0] <= med <= CHANGED_BAND[1] and min(present) >= CHANGED_FLOOR and len(present) == len(changed):
        g2 = "成立"
    else:
        g2 = "部分成立"

    unchanged_deltas = [rounds[key]["delta_s"] for key in unchanged if rounds[key]["delta_s"] is not None]
    neg_med = median_or_none(unchanged_deltas)
    neg_verdict = "无数据" if neg_med is None else (
        "阴性对照成立" if abs(neg_med) <= NEG_ABS_LIMIT else "阴性对照不成立（写明）")

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
    drift = {"rows": drift_rows, "rounds_over_limit": drift_over,
             "verdict": "环境漂移，G2 仅供参考" if drift_over > DRIFT_ROUNDS_MAX else "未见环境漂移"}

    bounds = [{"key": key, "delta_s": rounds[key]["delta_s"]} for key in changed
              if rounds[key]["delta_s"] is not None
              and (rounds[key]["delta_s"] > BOUND_HIGH or rounds[key]["delta_s"] < 0)]

    cold_report = {}
    for key in cold:
        traj = key.split("/")[0]
        lo, hi = COLD_PREDICTED[traj]
        d = rounds[key]["delta_s"]
        cold_report[key] = {"delta_s": d, "predicted_range_s": [lo, hi],
                            "inside": None if d is None else lo <= d <= hi}

    bands: dict[str, dict] = {}
    for key, traj, k, cls in keys:
        if cls == "cold":
            continue
        exp = prereg["trajectories"][traj]["rounds"][k]
        for name in ALL_SERVICES:
            value = rounds[key]["ttft_s"][name]
            if value is None:
                continue
            band = exp["on_ttft_band_s"] if name.endswith("_on") else exp["off_ttft_band_s"]
            bands.setdefault(key, {})[name] = {"ttft_s": value, "band_s": band,
                                                "inside": band[0] <= value <= band[1]}

    g1_fail: dict[str, list[str]] = {}
    cached_fail: dict[str, list[str]] = {}
    for name in ALL_SERVICES:
        for key in services[name]["records"]:
            chk = record_checks(services[name]["records"][key])
            if chk is None:
                continue
            if chk["status_ok"] and not chk["g1_segments"]:
                g1_fail.setdefault(name, []).append(key)
            if chk["status_ok"] and not (chk["cached_usage"] and chk["cached_first_line"]):
                cached_fail.setdefault(name, []).append(key)

    def pair_equal(a_name: str, b_name: str, key: str) -> dict | None:
        ta = services[a_name]["outputs"].get(key)
        tb = services[b_name]["outputs"].get(key)
        if ta is None or tb is None:
            return None
        return {"equal": ta == tb, "first_diff_char": None if ta == tb else first_diff(ta, tb)}

    g3 = {key: {"A1_vs_A2": pair_equal("A1_on", "A2_on", key), "B1_vs_B2": pair_equal("B1_off", "B2_off", key)}
          for key, _, _, _ in keys}
    g4 = {key: {"A1_vs_B1": pair_equal("A1_on", "B1_off", key), "A2_vs_B2": pair_equal("A2_on", "B2_off", key)}
          for key, _, _, _ in keys}

    def seed0_status(name: str) -> str | None:
        rec = services[name]["records"].get("seed_real/00")
        if rec is None:
            return None
        return rec.get("status")

    return {
        "schema": "ophak_task_a_analysis/v1",
        "window_terminal": window.get("terminal"),
        "services": service_info,
        "rounds": rounds,
        "G1": {"segments_mismatch_by_service": g1_fail,
               "model_fails_round_by_service": {name: [f"模型在第 {int(k.split('/')[1])} 轮不成立（{k}）" for k in keys_]
                                                 for name, keys_ in g1_fail.items()}},
        "cached_mismatch_by_service": cached_fail,
        "G2": {"changed_deltas_s": changed_deltas, "median_s": med, "min_s": min(present) if present else None,
               "rounds_missing": [k for k, d in changed_deltas.items() if d is None],
               "verdict": g2},
        "G2_negative_control": {"unchanged_deltas_s": {k: rounds[k]["delta_s"] for k in unchanged},
                                "median_abs_s": None if neg_med is None else abs(neg_med),
                                "verdict": neg_verdict},
        "G2_drift": drift,
        "G2_bounds_violations": bounds,
        "cold_rounds": cold_report,
        "absolute_bands": bands,
        "G3_reproducibility": g3,
        "G4_on_vs_off": g4,
        "G5_oom": {"B1_off_seed_r0": seed0_status("B1_off"), "B2_off_seed_r0": seed0_status("B2_off"),
                   "statement": ("关闭锚点切段后冷 87K 单段 OOM" if "oom" in (seed0_status("B1_off"),
                                                                       seed0_status("B2_off"))
                                 else "关闭锚点切段后冷 87K 单段未 OOM")},
        "rule_notes": [
            "Δ = mean(A1_on, A2_on) − mean(B1_off, B2_off)",
            "同臂漂移相对差 = |a − b| / max(a, b)，阈值 10%（指令'相差不超过 10%'的取法由主会话确认）",
            "G2 成立：中位数在 [2.3, 3.0] 且每轮 Δ ≥ 1.8；中位数 < 1.0 为不成立；其余为部分成立",
        ],
    }
