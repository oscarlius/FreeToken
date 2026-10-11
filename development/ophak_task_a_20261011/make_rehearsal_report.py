#!/usr/bin/env python3
"""H4 演练结果核对：把每项演练的实际结果与预期逐条比对，写 REHEARSAL.json（0444）。

只读各演练目录，不改动它们。预期值写在本文件里，不根据结果回填。
注意：桩服务的时序是对预登记的复现（见 stub_server.py 说明），演练结果只证明工装的算术与判读路径，不是证据。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
RUNS = Path("/data2/FreeToken/runs/dev_ophak_task_a_20261011/rehearsal")
OUT = WORK / "REHEARSAL.json"
SOURCES = ("task_a_runner.py", "stub_server.py", "analyze_task_a.py", "test_task_a_runner.py",
           "freeze_inputs.py", "build_restore12.py", "make_rehearsal_report.py", "INPUTS.json",
           "run_rehearsals.sh")
ROLE_EXPECT_SCALE_005 = 18.6 * 0.05  # seed 冷轮的桩服务预填时间（缩放 0.05）
ROLE_EXPECT_SCALE_1 = 18.6           # seed 冷轮（缩放 1.0）


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> tuple[dict, dict, Path]:
    base = RUNS / name
    analysis = json.loads((base / "analysis.json").read_text(encoding="utf-8"))
    window = json.loads((base / "window" / "window_summary.json").read_text(encoding="utf-8"))
    return analysis, window, base


def stub_rows(base: Path, service: str) -> list[dict]:
    path = base / "window" / service / "stub_stats.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check(label: str, expected, actual) -> dict:
    return {"check": label, "expected": expected, "actual": actual, "pass": expected == actual}


def all_services_complete(window: dict, n: int) -> list[dict]:
    return [check(f"{s['service']} 完成 {n} 条", ("complete", n), (s["status"], s.get("done")))
            for s in window["services"]]


def s0_all_ok(analysis: dict) -> dict:
    bad = [(key, svc) for key, row in analysis["rounds"].items() for svc, chk in row["checks"].items()
           if chk is not None and not chk["s0_prompt_tokens"]]
    return check("S0：每轮 prompt_tokens 与预登记一致", [], bad)


def run_R1() -> dict:
    a, w, base = load("R1_positive")
    med = a["G2"]["median_s"]
    seed0 = [a["rounds"]["seed_real/00"]["ttft_s"][s] for s in ("A1_on", "A2_on", "B1_off", "B2_off")]
    checks = [
        check("终态", "complete", a["window_terminal"]),
        *all_services_complete(w, 21),
        s0_all_ok(a),
        check("G1 无切段不符", {}, a["G1"]["model_fails_round_by_service"]),
        check("cached 无不符", {}, a["cached_mismatch_by_service"]),
        check("G2 判读", "成立", a["G2"]["verdict"]),
        check("G2 中位数在 [2.3, 3.0]", True, 2.3 <= med <= 3.0),
        check("G2 每轮 Δ ≥ 1.8", True, a["G2"]["min_s"] >= 1.8),
        check("G2 阴性对照", "阴性对照成立", a["G2_negative_control"]["verdict"]),
        check("G2 无环境漂移", "未见环境漂移", a["G2_drift"]["verdict"]),
        check("G2 上下限无违反", [], a["G2_bounds_violations"]),
        check("冷轮 seed_real/00 Δ 在预测区间 [-0.5, 1.5]", True, a["cold_rounds"]["seed_real/00"]["inside"]),
        check("冷轮 T2/00 Δ 在预测区间 [2.0, 3.0]", True, a["cold_rounds"]["T2/00"]["inside"]),
        check("各轮绝对值全部在预登记带内", True,
              all(v["inside"] for row in a["absolute_bands"].values() for v in row.values())),
        check("G3 同臂两服务逐字相同（全部轮，输出缺失即失败）", True,
              all(p["A1_vs_A2"] is not None and p["B1_vs_B2"] is not None
                  and p["A1_vs_A2"]["equal"] and p["B1_vs_B2"]["equal"]
                  for p in a["G3_reproducibility"].values())),
        check("G5 B 臂冷 87K 未 OOM（桩服务不注入 OOM）", "关闭锚点切段后冷 87K 单段未 OOM", a["G5_oom"]["statement"]),
        check("首分片判定：seed_real/00 首 token ≥ 14 s（role 包未被计时）", True, all(v >= 14.0 for v in seed0)),
    ]
    return {"config": {"scale": 1.0, "port": 18300, "inject": {}}, "checks": checks, "base": base.name}


def run_R2a() -> dict:
    a, w, base = load("R2a_role_packet")
    seed0 = [a["rounds"]["seed_real/00"]["ttft_s"][s] for s in ("A1_on", "A2_on", "B1_off", "B2_off")]
    checks = [
        check("终态", "complete", a["window_terminal"]),
        check("首分片：seed_real/00 首 token ≥ 0.8 × 预填时间（role 包未被计时）", True,
              all(v >= 0.8 * ROLE_EXPECT_SCALE_005 for v in seed0)),
        check("首分片：首 token 不超过预填时间 + 0.5 s", True,
              all(v <= ROLE_EXPECT_SCALE_005 + 0.5 for v in seed0)),
        check("G1 无切段不符", {}, a["G1"]["model_fails_round_by_service"]),
        check("cached 无不符", {}, a["cached_mismatch_by_service"]),
    ]
    return {"config": {"scale": 0.05, "port": 18310, "inject": {}, "control": "a"}, "checks": checks,
            "base": base.name}


def run_R2b() -> dict:
    a, w, base = load("R2b_wrong_cached")
    rows = [json.loads(line) for line in (base / "window" / "A1_on" / "requests.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    rec = next(r for r in rows if r["key"] == "seed_real/02")
    checks = [
        check("终态", "complete", a["window_terminal"]),
        check("复用不符只出现在 A1_on 的 seed_real/02", {"A1_on": ["seed_real/02"]}, a["cached_mismatch_by_service"]),
        check("A1_on seed_real/02：usage 与首条 Prefill 行的 cached 都与预登记不符",
              (True, True), (rec["usage"]["cached_tokens"] != rec["expect"]["cached"],
                             rec["prefill_lines"][0]["cached_token"] != rec["expect"]["cached"])),
        check("G1 切段不受影响", {}, a["G1"]["model_fails_round_by_service"]),
    ]
    return {"config": {"scale": 0.05, "port": 18320, "inject": {"A1_on": {"wrong-cached": "seed_real/02"}},
                       "control": "b"}, "checks": checks, "base": base.name}


def run_R2c() -> dict:
    a, w, base = load("R2c_oom")
    summary = {s["service"]: s for s in w["services"]}
    b1_rows = [json.loads(line) for line in (base / "window" / "B1_off" / "requests.jsonl").read_text(
        encoding="utf-8").splitlines() if line.strip()]
    stats = stub_rows(base, "B1_off")
    after_oom = [r for r in stats if r["key"] not in ("warm/00", "seed_real/00", "seed_real/01", "seed_real/02",
                                                       "seed_real/03")]
    checks = [
        check("终态", "complete", a["window_terminal"]),
        check("B1_off：在 seed_real/03 OOM，已完成 4 条", ("oom", 4), (summary["B1_off"]["status"], summary["B1_off"]["done"])),
        check("B1_off：只记录到 OOM 为止的 5 条（不重试）", 5, len(b1_rows)),
        check("B1_off：seed_real/03 只发送 1 次（stub 计数）", 1,
              sum(1 for r in stats if r["key"] == "seed_real/03")),
        check("B1_off：OOM 之后没有任何新请求", [], after_oom),
        check("B2_off 与 A1_on、A2_on 照常完整跑完", [("complete", 21)] * 3,
              [(summary[s]["status"], summary[s]["done"]) for s in ("B2_off", "A1_on", "A2_on")]),
        check("B1_off 的 OOM 摘录已写出", True, (base / "window" / "B1_off" / "oom_excerpt.log").exists()),
        check("G1 无切段不符", {}, a["G1"]["model_fails_round_by_service"]),
    ]
    return {"config": {"scale": 0.05, "port": 18330, "inject": {"B1_off": {"oom-at": "seed_real/03"}},
                       "control": "c"}, "checks": checks, "base": base.name}


def run_R2d() -> dict:
    a, w, base = load("R2d_segments_mismatch")
    checks = [
        check("终态", "complete", a["window_terminal"]),
        check("G1 只在 B2_off 第 5 轮不符", {"B2_off": ["模型在第 5 轮不成立（seed_real/05）"]},
              a["G1"]["model_fails_round_by_service"]),
        check("cached 无不符", {}, a["cached_mismatch_by_service"]),
        check("工装不因模型不符而停止", [("complete", 21)] * 4,
              [(s["status"], s["done"]) for s in w["services"]]),
    ]
    return {"config": {"scale": 0.05, "port": 18340, "inject": {"B2_off": {"segments-override": "seed_real/05=2000,104"}},
                       "control": "d (extra)"}, "checks": checks, "base": base.name}


def main() -> int:
    runs = {"R1_positive": run_R1(), "R2a_role_packet": run_R2a(), "R2b_wrong_cached": run_R2b(),
            "R2c_oom": run_R2c(), "R2d_segments_mismatch": run_R2d()}
    for name, item in runs.items():
        item["pass"] = all(c["pass"] for c in item["checks"])
    all_pass = all(item["pass"] for item in runs.values())
    doc = {
        "schema": "ophak_task_a_rehearsal/v1",
        "written_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "note": ("桩服务按预登记复现时序，演练只证明工装的算术、切段比对与窗口编排路径，"
                 "不是对生产的测量，也不能当作任务 A 的证据。"),
        "all_pass": all_pass,
        "runs": runs,
        "sources": {name: sha(WORK / name) for name in SOURCES},
    }
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(OUT, 0o444)
    print(json.dumps({"all_pass": all_pass, "runs": {k: v["pass"] for k, v in runs.items()}}, ensure_ascii=False))
    return 0 if all_pass else 3


if __name__ == "__main__":
    raise SystemExit(main())
