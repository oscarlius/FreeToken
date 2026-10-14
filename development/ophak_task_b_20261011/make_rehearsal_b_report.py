#!/usr/bin/env python3
"""任务 B 演练核对：读取六次演练的 window/window_summary.json 与 analysis.json，逐项核对预期，写 REHEARSAL_B.json（0444）。

预期只描述工装的路径（窗口终态、停在哪个服务、死亡计数、构建门与参数门的记录、判定函数是否走通）。
数字判定来自桩服务按预登记复现，不能当作证据；缩放 0.05 的控制组，其 G2 中位数与漂移只是缩放伪影，不核对数值。
本文件不解释结论。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORK = Path(__file__).resolve().parent
RUNS = Path("/data2/FreeToken/runs/dev_ophak_task_b_20261011/rehearsal")
OUT = WORK / "REHEARSAL_B.json"
ALL_SERVICES = ["R0", "C_A1", "C_B1", "C_B2", "C_A2"]


def load(run: str) -> tuple[dict, dict | None, Path]:
    window_dir = RUNS / run / "window"
    summary = json.loads((window_dir / "window_summary.json").read_text(encoding="utf-8"))
    analysis_path = RUNS / run / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else None
    return summary, analysis, window_dir


def names(summary: dict) -> list[str]:
    return [entry.get("service") for entry in summary["services"]]


def entry(summary: dict, name: str) -> dict[str, Any]:
    return next((e for e in summary["services"] if e.get("service") == name), {})


def exit_line(run: str) -> str | None:
    path = RUNS / f"{run}.stdout"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-1] if lines else None


def gate_record(window_dir: Path, service: str, name: str) -> dict | None:
    path = window_dir / service / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def check_run(run: str) -> dict[str, Any]:
    summary, analysis, window_dir = load(run)
    checks: list[dict[str, Any]] = []

    def add(label: str, ok: bool, detail: Any = None) -> None:
        checks.append({"check": label, "pass": bool(ok), "detail": detail})

    expected_exit = "exit=0" if summary["terminal"] == "complete" else "exit=4"
    add("退出码与终态一致（complete→0，其它→4）", exit_line(run) == expected_exit, exit_line(run))
    if run == "R_positive":
        add("终态 complete", summary["terminal"] == "complete", summary["terminal"])
        add("五个服务依次启动", names(summary) == ALL_SERVICES, names(summary))
        add("五个服务全部 complete", all(entry(summary, n).get("status") == "complete" for n in ALL_SERVICES), None)
        add("无死亡", summary["deaths"] == [], summary["deaths"])
        for n in ALL_SERVICES:
            bg = gate_record(window_dir, n, "build_gate.json")
            pg = gate_record(window_dir, n, "param_gate.json")
            add(f"{n} 构建门与参数门记录 ok", bool(bg and bg["ok"]) and bool(pg and pg["ok"]),
                {"build": bg and bg["imported"], "param": pg and {"expected": pg["expected"], "actual": pg["actual"]}})
        add("T16-lite 成立", analysis["t16_lite"]["verdict"] == "成立", analysis["t16_lite"]["verdict"])
        add("G1 成立", analysis["g1"]["verdict"] == "成立", analysis["g1"]["verdict"])
        add("G2 changed 成立（桩按预登记复现）", analysis["g2_changed"]["verdict"].startswith("成立"),
            analysis["g2_changed"].get("median_s"))
        add("G2 unchanged 成立", analysis["g2_unchanged"]["verdict"] == "成立", analysis["g2_unchanged"].get("median_s"))
        add("G3 成立", analysis["g3"]["verdict"] == "成立", analysis["g3"]["checked"])
        add("G5 成立（演练无 OOM）", analysis["g5"]["verdict"] == "成立", analysis["g5"]["verdict"])
        add("输入哈希与 INPUTS.json 一致", analysis["input_check"]["ok"], analysis["input_check"]["mismatches"])
    elif run == "R_a_output_tweak":
        add("终态 complete（只改输出，不改流程）", summary["terminal"] == "complete", summary["terminal"])
        keys = [m["key"] for m in analysis["t16_lite"]["mismatches"]]
        add("T16-lite 判不等，且只有 T2/03", analysis["t16_lite"]["verdict"] == "不成立" and keys == ["T2/03"], keys)
        pairs = [(d["pair"], d["key"]) for d in analysis["g3"]["differences"]]
        add("G3 指出同臂对 C_A1/C_A2 的 T2/03", pairs == [("C_A1/C_A2", "T2/03")], pairs)
    elif run == "R_b_param_missing":
        add("终态 param_gate_refused", summary["terminal"] == "param_gate_refused", summary["terminal"])
        add("参数门停在 C_B1（前面两个服务正常）", names(summary) == ["R0", "C_A1", "C_B1"], names(summary))
        add("C_B1 状态 param_gate_refused", entry(summary, "C_B1").get("status") == "param_gate_refused", None)
        pg = gate_record(window_dir, "C_B1", "param_gate.json")
        add("C_B1 参数门记录 ok=false，实际 0、期望 32768",
            bool(pg) and pg["ok"] is False and pg["actual"] == 0 and pg["expected"] == 32768, pg)
        add("C_B1 未发出任何请求", not (window_dir / "C_B1" / "requests.jsonl").exists(), None)
        add("C_B2 与 C_A2 未启动", not (window_dir / "C_B2").exists() and not (window_dir / "C_A2").exists(), None)
    elif run == "R_c_wrong_pythonpath":
        add("终态 build_gate_refused", summary["terminal"] == "build_gate_refused", summary["terminal"])
        add("构建门停在 C_B2", names(summary) == ["R0", "C_A1", "C_B1", "C_B2"], names(summary))
        gate = gate_record(window_dir, "C_B2", "build_gate.json")
        add("C_B2 的构建门记录 ok=false", bool(gate) and gate["ok"] is False, gate and gate["imported"])
        add("C_B2 未启动桩服务（无 serve.log）", not (window_dir / "C_B2" / "serve.log").exists(), None)
        add("C_A2 未启动", not (window_dir / "C_A2").exists(), None)
    elif run == "R_d_one_oom":
        add("终态 complete（单服务死亡后继续）", summary["terminal"] == "complete", summary["terminal"])
        add("死亡记录：C_B1 在 T2/05", summary["deaths"] == [{"service": "C_B1", "status": "oom", "key": "T2/05"}],
            summary["deaths"])
        add("五个服务都被尝试", names(summary) == ALL_SERVICES, names(summary))
        add("C_B2 与 C_A2 complete", all(entry(summary, n).get("status") == "complete" for n in ("C_B2", "C_A2")), None)
        pg = gate_record(window_dir, "C_B1", "param_gate.json")
        add("C_B1 参数门通过（死亡发生在参数门之后）", bool(pg) and pg["ok"] is True, pg)
        add("G5 判 阈值策略未避开 E1", analysis["g5"]["verdict"].startswith("不成立"), analysis["g5"]["verdict"])
    elif run == "R_e_two_oom":
        add("终态 second_death_stop", summary["terminal"] == "second_death_stop", summary["terminal"])
        add("两次死亡：C_A1 与 C_B1", [d["service"] for d in summary["deaths"]] == ["C_A1", "C_B1"], summary["deaths"])
        add("第二次死亡后不再启动 C_B2、C_A2", names(summary) == ["R0", "C_A1", "C_B1"]
            and not (window_dir / "C_B2").exists() and not (window_dir / "C_A2").exists(), names(summary))
    elif run == "R_f_startup_oom_one":
        add("终态 complete（启动期死亡后继续）", summary["terminal"] == "complete", summary["terminal"])
        add("死亡记录：C_A1 启动期 serve.log 为 oom",
            summary["deaths"] == [{"service": "C_A1", "status": "oom", "key": None}], summary["deaths"])
        add("五个服务都被尝试", names(summary) == ALL_SERVICES, names(summary))
        add("C_A1 未 ready，没有请求", not (window_dir / "C_A1" / "requests.jsonl").exists(), None)
        add("其余四个服务 complete",
            all(entry(summary, n).get("status") == "complete" for n in ("R0", "C_B1", "C_B2", "C_A2")), None)
    elif run == "R_g_startup_two_plain":
        add("终态 second_death_stop（两次启动失败）", summary["terminal"] == "second_death_stop", summary["terminal"])
        add("两次死亡均为 launch_failed：C_A1、C_B1",
            [(d["service"], d["status"]) for d in summary["deaths"]] == [("C_A1", "launch_failed"),
                                                                       ("C_B1", "launch_failed")], summary["deaths"])
        add("第二次死亡后不再启动 C_B2、C_A2", names(summary) == ["R0", "C_A1", "C_B1"]
            and not (window_dir / "C_B2").exists() and not (window_dir / "C_A2").exists(), names(summary))
    return {"run": run, "terminal": summary["terminal"], "services": names(summary), "deaths": summary["deaths"],
            "checks": checks, "pass": all(c["pass"] for c in checks)}


def main() -> int:
    runs = ["R_positive", "R_a_output_tweak", "R_b_param_missing", "R_c_wrong_pythonpath", "R_d_one_oom",
            "R_e_two_oom", "R_f_startup_oom_one", "R_g_startup_two_plain"]
    results = [check_run(run) for run in runs]
    doc = {"schema": "ophak_task_b_rehearsal/v1",
           "note": "演练：桩服务按预登记复现，只核对工装的路径与判定函数的算术，不是证据。",
           "all_pass": all(item["pass"] for item in results), "runs": results}
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    OUT.chmod(0o444)
    print(json.dumps({"all_pass": doc["all_pass"], "runs": [(r["run"], r["pass"]) for r in results]},
                     ensure_ascii=False))
    return 0 if doc["all_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
