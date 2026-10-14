#!/usr/bin/env python3
"""任务 B 判读（机械计算）：T16-lite、G1、G2（changed 14 轮；unchanged 第 2、3、9、11 轮）、冷轮报告、漂移、G3、G5。

输入：窗口目录（每个服务一个子目录：requests.jsonl、outputs.json、summary.json；另有 window_summary.json）、
预登记 PREREG_TASK_B_v2.json 与 INPUTS.json。服务未启动、中途死亡或参数门拒绝的轮次记为"缺"，不补、不重跑。
判据逐条取自预登记 gates；本文件只输出数字与判定文字，不写解释。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

SERVICES = ("R0", "C_A1", "C_B1", "C_B2", "C_A2")
ON_SERVICES = ("C_A1", "C_A2")        # 开臂（N = 0）：Δ 的 A 臂
THRESH_SERVICES = ("C_B1", "C_B2")    # 阈值臂（N = 32768）：Δ 的 B 臂
PAIRS = (("C_A1", "C_A2"), ("C_B1", "C_B2"))  # 同臂两服务：漂移与 G3
ROUND_KEYS = tuple([f"seed_real/{k:02d}" for k in range(8)] + [f"T2/{k:02d}" for k in range(12)])
G2_UNCHANGED_KEYS = ("T2/02", "T2/03", "T2/09", "T2/11")
COLD_KEYS = ("seed_real/00", "T2/00")
DRIFT_REL = 0.10
DRIFT_MAX_EVENTS = 3
G2_LO, G2_HI, G2_ROUND_MIN, G2_DOWN = 2.3, 3.0, 1.8, 1.0
G2_UNCHANGED_BAND = 0.3


def load_service(window_dir: Path, name: str) -> dict[str, Any]:
    """读取一个服务的目录；目录不存在（未启动）时 present 为 False。"""
    svc_dir = window_dir / name
    svc: dict[str, Any] = {"name": name, "present": svc_dir.is_dir(), "records": {}, "outputs": {}, "summary": None}
    if not svc["present"]:
        return svc
    requests = svc_dir / "requests.jsonl"
    if requests.exists():
        for line in requests.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                svc["records"][rec["key"]] = rec
    outputs = svc_dir / "outputs.json"
    if outputs.exists():
        svc["outputs"] = json.loads(outputs.read_text(encoding="utf-8"))
    summary = svc_dir / "summary.json"
    if summary.exists():
        svc["summary"] = json.loads(summary.read_text(encoding="utf-8"))
    return svc


def spec_of(prereg: dict, key: str) -> dict[str, Any]:
    traj, k = key.split("/")
    matches = [s for s in prereg["trajectories"][traj] if s["round"] == int(k)]
    if len(matches) != 1:
        raise ValueError(f"预登记中找不到唯一的轮次：{key}")
    return matches[0]


def is_ok(svc: dict, key: str) -> bool:
    rec = svc["records"].get(key)
    return bool(rec) and rec.get("status") == "ok"


def observed(svc: dict, key: str) -> tuple[list[int], int | None]:
    """服务端 Prefill 行给出的切段（new_token 依次）与首段 cached。"""
    lines = svc["records"][key].get("prefill_lines") or []
    return [line["new_token"] for line in lines], (lines[0]["cached_token"] if lines else None)


def ttft(svc: dict, key: str) -> float | None:
    return svc["records"][key].get("ttft_s") if is_ok(svc, key) else None


def input_check(services: dict[str, dict], inputs: dict) -> dict[str, Any]:
    """每条记录的 messages 哈希必须与 INPUTS.json 中同一轮次一致（输入没有被替换）。"""
    want = {f'{row["trajectory"]}/{row["round"]:02d}': row["messages_sha256"] for row in inputs["rounds"]}
    bad = [{"service": name, "key": key} for name, svc in services.items()
           for key, rec in svc["records"].items() if key in want and rec.get("messages_sha256") != want[key]]
    return {"ok": not bad, "mismatches": bad}


def t16_lite(r0: dict, c_a1: dict) -> dict[str, Any]:
    """默认参数对 release-e2：20 条 payload 的切段、cached、输出全文逐字相同（warm/00 不计入）。"""
    mismatches, missing = [], []
    for key in ROUND_KEYS:
        if not (is_ok(r0, key) and is_ok(c_a1, key)):
            missing.append(key)
            continue
        items = []
        if observed(r0, key) != observed(c_a1, key):
            items.append("切段或 cached")
        if r0["outputs"].get(key) != c_a1["outputs"].get(key):
            items.append("输出")
        if items:
            mismatches.append({"key": key, "items": items})
    if mismatches:
        verdict = "不成立"
    elif missing:
        verdict = "不可判（缺轮次）"
    else:
        verdict = "成立"
    return {"verdict": verdict, "mismatches": mismatches, "missing": missing}


def g1(services: dict[str, dict], prereg: dict) -> dict[str, Any]:
    """开臂服务的切段与 cached 等于 on_segments；阈值臂服务等于 thresh_segments。"""
    bad, missing, checked = [], [], 0
    for name in ("C_A1", "C_A2", "C_B1", "C_B2"):
        for key in ROUND_KEYS:
            if not is_ok(services[name], key):
                missing.append(f"{name}/{key}")
                continue
            spec = spec_of(prereg, key)
            want = spec["on_segments"] if name in ON_SERVICES else spec["thresh_segments"]
            seg, cached = observed(services[name], key)
            checked += 1
            if seg != want or cached != spec["cached"]:
                bad.append({"service": name, "key": key, "segments": seg, "cached": cached,
                            "want_segments": want, "want_cached": spec["cached"]})
    if bad:
        verdict = f"不成立：模型在第 {bad[0]['key']} 轮不成立（{bad[0]['service']}）"
    elif missing:
        verdict = "成立（缺轮次未计入）"
    else:
        verdict = "成立"
    return {"verdict": verdict, "checked": checked, "mismatches": bad, "missing": missing}


def delta_rows(services: dict[str, dict], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    """每轮 Δ = 开臂两服务首 token 均值 − 阈值臂两服务首 token 均值；缺任一臂则 delta_s 为 None。"""
    rows = []
    for key in keys:
        a = [x for x in (ttft(services[n], key) for n in ON_SERVICES) if x is not None]
        b = [x for x in (ttft(services[n], key) for n in THRESH_SERVICES) if x is not None]
        delta = round(statistics.fmean(a) - statistics.fmean(b), 4) if a and b else None
        rows.append({"key": key, "delta_s": delta, "a_n": len(a), "b_n": len(b)})
    return rows


def _deltas(rows: list[dict]) -> list[float]:
    return [row["delta_s"] for row in rows if row["delta_s"] is not None]


def g2_changed(rows: list[dict], downgraded: bool) -> dict[str, Any]:
    deltas = _deltas(rows)
    if not deltas:
        return {"verdict": "不可判（无可用轮次）", "rounds": rows, "n": 0}
    med, low = statistics.median(deltas), min(deltas)
    if med < G2_DOWN:
        verdict = "不成立"
    elif G2_LO <= med <= G2_HI and low >= G2_ROUND_MIN:
        verdict = "成立"
    else:
        verdict = "部分成立"
    if downgraded:
        verdict += "（漂移超限，G2 降级为仅供参考）"
    return {"verdict": verdict, "rounds": rows, "n": len(deltas), "median_s": round(med, 4),
            "min_s": round(low, 4), "downgraded": downgraded}


def g2_unchanged(rows: list[dict]) -> dict[str, Any]:
    deltas = _deltas(rows)
    if not deltas:
        return {"verdict": "不可判（无可用轮次）", "rounds": rows, "n": 0}
    med = statistics.median(deltas)
    verdict = "成立" if abs(med) <= G2_UNCHANGED_BAND else "不成立"
    return {"verdict": verdict, "rounds": rows, "n": len(deltas), "median_s": round(med, 4)}


def drift(services: dict[str, dict]) -> dict[str, Any]:
    """同臂两服务同轮首 token 相差 |a−b|/max(a,b) > 10% 记为一次漂移事件（按（同臂对，轮次）计数）。"""
    events = []
    for a_name, b_name in PAIRS:
        for key in ROUND_KEYS:
            a, b = ttft(services[a_name], key), ttft(services[b_name], key)
            if a is None or b is None or max(a, b) <= 0:
                continue
            rel = abs(a - b) / max(a, b)
            if rel > DRIFT_REL:
                events.append({"pair": f"{a_name}/{b_name}", "key": key, "a_s": a, "b_s": b, "rel": round(rel, 4)})
    return {"events": events, "count": len(events), "downgrade_g2": len(events) > DRIFT_MAX_EVENTS}


def g3(services: dict[str, dict]) -> dict[str, Any]:
    """同臂两服务同轮输出逐字相同；不同则写首个不同字符的位置。"""
    diffs, checked = [], 0
    for a_name, b_name in PAIRS:
        for key in ROUND_KEYS:
            if not (is_ok(services[a_name], key) and is_ok(services[b_name], key)):
                continue
            checked += 1
            a = services[a_name]["outputs"].get(key, "")
            b = services[b_name]["outputs"].get(key, "")
            if a != b:
                first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                diffs.append({"pair": f"{a_name}/{b_name}", "key": key, "first_diff_char": first})
    return {"verdict": "成立" if not diffs else "不成立", "checked": checked, "differences": diffs}


def memory_trace(svc: dict) -> list[dict[str, Any]]:
    return [{"key": key, "before_mib": rec.get("memory_before_mib"), "after_mib": rec.get("memory_after_mib")}
            for key, rec in svc["records"].items()]


def g5(services: dict[str, dict]) -> dict[str, Any]:
    """阈值臂任一服务 OOM 或 worker 退出：判"阈值策略未避开 E1"，该参数不进生产。"""
    died, unfinished = [], []
    for name in THRESH_SERVICES:
        svc = services[name]
        status = (svc["summary"] or {}).get("status")
        if status in ("oom", "worker_exit"):
            died.append({"service": name, "status": status, "died_at_key": svc["summary"].get("died_at_key"),
                         "memory_trace": memory_trace(svc)})
        elif status != "complete":
            unfinished.append({"service": name, "status": status})
    if died:
        verdict = "不成立：阈值策略未避开 E1，该参数不进生产"
    elif unfinished:
        verdict = "不可判（阈值臂服务未全部完成）"
    else:
        verdict = "成立"
    return {"verdict": verdict, "died": died, "unfinished": unfinished}


def service_rows(services: dict[str, dict], window_services: list[dict]) -> list[dict[str, Any]]:
    entries = {entry.get("service"): entry for entry in window_services}
    rows = []
    for name in SERVICES:
        entry = entries.get(name, {})
        rows.append({"service": name, "present": services[name]["present"], "status": entry.get("status"),
                     "build": entry.get("build"), "done": entry.get("done"), "died_at_key": entry.get("died_at_key"),
                     "rounds_recorded": len(services[name]["records"]),
                     "rounds_ok": sum(1 for key in services[name]["records"] if is_ok(services[name], key))})
    return rows


def ttft_table(services: dict[str, dict]) -> dict[str, dict[str, float | None]]:
    """逐轮逐服务的首 token（秒）：只供核对与 RESULT 表使用，不进判定。"""
    return {key: {name: ttft(services[name], key) for name in SERVICES} for key in ROUND_KEYS}


def analyze_run_b(window_dir: Path, prereg: dict, inputs: dict) -> dict[str, Any]:
    window = json.loads((window_dir / "window_summary.json").read_text(encoding="utf-8"))
    services = {name: load_service(window_dir, name) for name in SERVICES}
    changed = tuple(k for k in ROUND_KEYS if spec_of(prereg, k)["class"] == "changed")
    drift_res = drift(services)
    return {
        "schema": "ophak_task_b_analysis/v1",
        "terminal": window["terminal"],
        "deaths": window.get("deaths", []),
        "services": service_rows(services, window["services"]),
        "input_check": input_check(services, inputs),
        "t16_lite": t16_lite(services["R0"], services["C_A1"]),
        "g1": g1(services, prereg),
        "g2_changed": g2_changed(delta_rows(services, changed), drift_res["downgrade_g2"]),
        "g2_unchanged": g2_unchanged(delta_rows(services, G2_UNCHANGED_KEYS)),
        "cold_report": delta_rows(services, COLD_KEYS),
        "drift": drift_res,
        "g3": g3(services),
        "g5": g5(services),
        "ttft_table": ttft_table(services),
    }
