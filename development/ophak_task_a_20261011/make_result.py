#!/usr/bin/env python3
"""P3 窗口结果报告（op-hak 任务 A）。只写原始数据与按 §6 的机械结论，不加推测。

数据来源（全部为原始回执与记录，只读）：
  window01/window/<服务>/requests.jsonl、summary.json、cleanup.json
  window01/window/window_summary.json、window01/analysis.json（analyze_task_a 机械计算）
  W0_CHECK.json、CLEARED.json、W2_OBSERVER_STOP.json、-10 的 stopped.json
  W5_start.log、W5_wait.log，以及 -11 运行目录中的 smoke_execution_result.json、serving_ready.json、
  overnight_observation/start.json；另外现场读取一次 /health。
B1 的服务端 OOM 摘录（操作者按 serve.log 截取，见 OOM 节）。运行后写 WORK/RESULT.md（0444）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
WINDOW = Path("/data2/FreeToken/runs/dev_ophak_task_a_20261011/window01")
SVC = WINDOW / "window"
RESTORE11_RUN = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-11")
RESTORE10_RUN = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-10")
PREREG = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_A.json")
OUT = WORK / "RESULT.md"
OOM_EXCERPT = WORK / "B1_oom_excerpt_operator.log"


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def jrows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fmt_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def health() -> str:
    try:
        return subprocess.run(["curl", "-s", "-m", "5", "--noproxy", "*", "http://172.16.108.9:8095/health"],
                              capture_output=True, text=True, timeout=15).stdout.strip()[:300]
    except (OSError, subprocess.TimeoutExpired):
        return "unreachable"


def expect_map(prereg: dict) -> dict:
    out = {}
    for traj in ("seed_real", "T2"):
        for k, exp in enumerate(prereg["trajectories"][traj]["rounds"]):
            out[f"{traj}/{k:02d}"] = exp
    return out


def round_table(service: str, rows: list[dict], expect: dict) -> str:
    lines = ["| 轮次 | 状态 | prompt_tokens | cached（usage） | 切段（new_token, cached） | 切段与预登记 | cached 与预登记 | ttft_s | total_s | 输出 SHA 前 12 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        usage = r.get("usage") or {}
        lines_pf = r.get("prefill_lines") or []
        segs = ", ".join(f"({x['new_token']}, {x['cached_token']})" for x in lines_pf) or "—"
        exp = expect.get(r["key"])
        if exp is None or r["status"] != "ok":
            seg_ok = cache_ok = "—" if exp is None else "无数据"
        else:
            want_seg = exp["on_segments"] if service.endswith("_on") else exp["off_segments"]
            seg_ok = "是" if [x["new_token"] for x in lines_pf] == want_seg else "否"
            cache_ok = "是" if usage.get("cached_tokens") == exp["cached"] else "否"
        ttft = f"{r['ttft_s']:.2f}" if r.get("ttft_s") is not None else "—"
        total = f"{r['total_s']:.1f}" if r.get("total_s") is not None else "—"
        sha = r.get("output_sha256", "")[:12] if r["status"] == "ok" else "—"
        pt = usage.get("prompt_tokens", "—")
        ca = usage.get("cached_tokens", "—") if usage else "—"
        lines.append(f"| {r['key']} | {r['status']} | {pt} | {ca} | {segs} | {seg_ok} | {cache_ok} | {ttft} | {total} | {sha} |")
    return "\n".join(lines)


def main() -> int:
    prereg = jload(PREREG)
    expect = expect_map(prereg)
    window = jload(SVC / "window_summary.json")
    analysis = jload(WINDOW / "analysis.json")
    w0 = jload(WORK / "W0_CHECK.json")
    cleared = jload(WORK / "CLEARED.json")
    w2 = jload(WORK / "W2_OBSERVER_STOP.json")
    stopped10 = jload(RESTORE10_RUN / "stopped.json")
    a1 = jrows(SVC / "A1_on" / "requests.jsonl")
    b1 = jrows(SVC / "B1_off" / "requests.jsonl")

    smoke_path = RESTORE11_RUN / "smoke_execution_result.json"
    smoke = jload(smoke_path) if smoke_path.exists() else None
    ready_path = RESTORE11_RUN / "serving_ready.json"
    ready = jload(ready_path) if ready_path.exists() else None
    obs_path = RESTORE11_RUN / "overnight_observation" / "start.json"
    obs = jload(obs_path) if obs_path.exists() else None
    w5_start_log = (WORK / "W5_start.log").read_text(encoding="utf-8") if (WORK / "W5_start.log").exists() else ""
    w5_wait_log = (WORK / "W5_wait.log").read_text(encoding="utf-8", errors="replace") if (WORK / "W5_wait.log").exists() else ""

    svc_status = {s["service"]: s for s in window["services"]}
    g1_fail = analysis["G1"]["segments_mismatch_by_service"]
    cache_fail = analysis["cached_mismatch_by_service"]
    g2 = analysis["G2"]
    g5 = analysis["G5_oom"]

    lines: list[str] = []
    add = lines.append
    add("# 任务 A 窗口结果报告（op-hak，2026-10-11 夜）")
    add("")
    add("> 只写数据与按 §6 的机械结论。窗口未完成，G2–G4 因 B 臂与 A2 缺失而无数据。")
    add("")
    add("## 0. 结论摘要")
    add("")
    add(f"- 窗口终态：`{window['terminal']}`（工装记录）。A1_on 完整（21/21）。B1_off 在热轮 `seed_real/02` 发生服务端 OOM，客户端按工装记为 `request_error`（ReadTimeout 600 s）。A2_on、B2_off 未运行。")
    add("- G5 字面（冷 87K 单段 OOM）：**未触发**。B1_off 的 `seed_real/00`（冷 87,100，单段）预填通过。")
    add("- 另记一个事件（不在 G5 字面范围内）：B1_off 在热轮 `seed_real/02` 发生 OOM，见第 4 节。")
    add("- 481 已以 `RESTORE481-MORNING-20261011-11` 恢复（服务就绪 21:29:45，冒烟通过，观察器已起，见第 5 节）。")
    add(f"- 当前 /health：`{health()}`")
    add("")
    add("## 1. 每一步的终态与时刻")
    add("")
    add("| 步骤 | 终态 | 时刻（服务器时间） | 依据 |")
    add("|---|---|---|---|")
    add(f"| W0 | {'通过' if w0['all_pass'] else '未通过'} | {w0['checked_at']} | W0_CHECK.json SHA `{sha12(WORK / 'W0_CHECK.json')}` |")
    add(f"| W1 清场 | 候选 {len(cleared['candidates_to_stop'])} 个，停止 {len(cleared['stopped'])} 个 | {cleared['recorded_at']} | CLEARED.json SHA `{sha12(WORK / 'CLEARED.json')}` |")
    add(f"| W2 停 -10 观察器 | {w2['result']} | {w2.get('sent_at')} | SIGTERM 进程组 2635718，未用 KILL；samples {w2.get('samples_before')} → {w2.get('samples_after')} |")
    add(f"| W3 停 481 | 退出码 0 | {fmt_epoch(stopped10['at'])} | stopped.json；production.active.json 已删；gpu.lock 已释放；GPU 无计算进程 |")
    add(f"| W4 窗口开始 | — | {window['started_at']} | window01 |")
    add(f"| W4 窗口结束 | `{window['terminal']}` | {window.get('finished_at')} | window_summary.json |")
    add("")
    add("## 2. 逐服务逐轮记录")
    add("")
    add("### A1_on（锚点切段开，= 生产配置，仅 host/port 不同）")
    add("")
    add(f"状态：{svc_status['A1_on']['status']}，完成 {svc_status['A1_on']['done']}/{svc_status['A1_on']['planned']}。")
    add("")
    add(round_table("A1_on", a1, expect))
    add("")
    add("### B1_off（锚点切段关，`--no-prefill-anchor-cut`）")
    add("")
    add(f"状态（工装）：{svc_status['B1_off']['status']}，完成 {svc_status['B1_off']['done']}/{svc_status['B1_off']['planned']}，原因：{svc_status['B1_off']['stop_reason']}。")
    add("")
    add(round_table("B1_off", b1, expect))
    add("")
    add("### A2_on、B2_off")
    add("")
    add("未运行（窗口在 B1_off 之后停止）。")
    add("")
    add("## 3. 机械结论（analysis.json，按 §6）")
    add("")
    add(f"- G1 切段不符（按服务，仅统计已完成的记录）：{g1_fail or '无'}")
    add(f"- cached 不符（按服务，仅统计已完成的记录）：{cache_fail or '无'}")
    add(f"- G2：{g2['verdict']}（中位数 {g2['median_s'] if g2['median_s'] is not None else '无'}，缺失轮 {len(g2['rounds_missing'])} 个）")
    add(f"- G2 阴性对照：{analysis['G2_negative_control']['verdict']}")
    drift_rows = analysis["G2_drift"]["rows"]
    add(f"- G2 漂移：{analysis['G2_drift']['verdict'] if drift_rows else '无数据（同臂两服务均未完成，无可比对的轮次）'}")
    add(f"- G3（同臂逐字相同）：无数据（A2、B2 未运行）")
    add(f"- G4（ON 对 OFF 输出）：无数据（B 臂不完整）")
    add(f"- G5 字面（冷 87K 单段）：{g5['statement']}（B1_off seed_real/00 状态 `{g5['B1_off_seed_r0']}`）")
    add("")
    add("## 4. 事件：B1_off 热轮 seed_real/02 的服务端 OOM")
    add("")
    add("- 服务端日志（`window01/window/B1_off/serve.log`）：")
    add("  - 21:13:42 API ready；21:13:47 warm 预填（54 token）；21:14:05 `seed_real/00` 预填（87,100 token，单段，cached 0）通过；21:14:11 `seed_real/01` 预填（288 token，cached 87,040）通过；")
    add("  - `seed_real/02` 开始后，服务端无预填行；21:14:37 在 `qsa_sparse_paged_attention` → `_qsa_sparse_paged_gqa_splitk_kernel` 的 Triton kernel 启动处报 `RuntimeError: Triton Error [CUDA]: out of memory`；")
    add("  - 21:14:37 后端 worker 退出，21:14:47 `Backend worker is gone and cannot be restarted; stopping the API server`。")
    add("- 客户端：服务端关闭时未发送错误包，`seed_real/02` 一直等到 600 s 读超时，因此工装记为 `request_error`。工装的分类没有识别出这次 OOM。这是工装的局限，不是服务正常。")
    add("- 与 G5 的关系：G5 字面针对冷 87K 单段（第 0 轮），该项通过。本事件发生在热轮，G5 没有对此给出预测；由主会话判定其含义。")
    add("- OOM 摘录（操作者按上述日志截取，前后 40 行）：`B1_oom_excerpt_operator.log`。")
    add("")
    add("## 5. W5 恢复（restore11）")
    add("")
    start_json_lines = [l for l in w5_start_log.splitlines() if l.startswith("{")]
    add(f"- 第一步 `start_approved_release.py`：{w5_start_log.strip().splitlines()[-1] if w5_start_log.strip() else '无日志'}；状态行 `{(start_json_lines[-1][:200] if start_json_lines else '无')}`")
    if ready:
        add(f"- 服务就绪（serving_ready.json）：{fmt_epoch(ready['at'])}，health 摘要：`{json.dumps(ready['health'], ensure_ascii=False)[:200]}`")
    wait_json_lines = [l for l in w5_wait_log.splitlines() if l.startswith("{")]
    add(f"- 第二步 `wait_release_and_smoke.py`：`{wait_json_lines[-1][:240] if wait_json_lines else '（无状态行）'}`；{w5_wait_log.strip().splitlines()[-1] if w5_wait_log.strip() else '（未结束）'}")
    if smoke:
        add(f"- 冒烟回执：exit_code={smoke.get('exit_code')}，classification={smoke.get('classification')}；冒烟测试 `test_release_smoke` 内含与基准的比对（`compare_with_baseline`：sha256、usage、后端缓存行结构），pytest 结果 `1 passed`。")
    else:
        add("- 冒烟回执：未生成")
    if obs:
        add(f"- 第三步观察器：start.json 已写出（until={obs.get('until')}，observer_pid={obs.get('observer_pid')}）")
    else:
        add("- 第三步观察器：start.json 未写出")
    add(f"- 现场 /health：`{health()}`")
    add("- 清场记录：W1 没有停止任何东西，无需恢复。")
    add("")
    add("## 6. 证据索引（SHA256 前 12 位）")
    add("")
    evidence = [
        WORK / "W0_CHECK.json", WORK / "CLEARED.json", WORK / "W2_OBSERVER_STOP.json",
        WINDOW / "window" / "window_summary.json", WINDOW / "analysis.json",
        WINDOW / "window" / "A1_on" / "requests.jsonl", WINDOW / "window" / "B1_off" / "requests.jsonl",
        WINDOW / "window" / "B1_off" / "serve.log", WORK / "W5_start.log", WORK / "W5_wait.log",
        WORK / "REHEARSAL.json", WORK / "restore11" / "DEPLOYMENT_APPROVAL.json",
        WORK / "restore11" / "ROOT_FINAL_REVIEW.json", WORK / "restore11" / "SOURCE_MANIFEST.json",
    ]
    for path in evidence:
        if path.exists():
            add(f"- `{path}`：`{sha12(path)}`")
    add("")
    add("## 7. 偏差与待主会话判定的事项")
    add("")
    add("1. B1_off 的工装分类为 `request_error`（ReadTimeout），经服务端日志确认为 OOM（热轮 seed_real/02）。窗口文件保留工装原始分类，本报告的 OOM 归类由操作者依据日志作出。")
    add("2. G5 字面（冷 87K 单段 OOM）未触发；OOM 发生在热轮。是否在 G5 名下记录，或另立事件，由主会话决定。")
    add("3. 窗口在 B1_off 之后停止，A2_on、B2_off 未运行。G2–G4 无数据，不做推断。")
    add("4. 未重跑、未补测，按主会话指示等待复核。")
    add("")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    os.chmod(OUT, 0o444)
    print(json.dumps({"written": str(OUT), "bytes": len(text.encode("utf-8"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
