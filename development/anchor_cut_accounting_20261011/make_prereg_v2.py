"""PREREG_TASK_S_v2.json / PREREG_TASK_B_v2.json: corrections found in the pre-issue self-review (no data seen).

v1 files stay untouched. Runs on the server next to the v1 files and stall_seq_out.json.
"""
import datetime
import hashlib
import json
from pathlib import Path

D = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds")

# ---------------- task S
s1 = json.loads((D / "PREREG_TASK_S.json").read_text())
seq = {r["event"]: r for r in json.loads((D / "stall_seq_out.json").read_text())["rows"]}
assert seq["smoke_short"]["segments"] == [512] and seq["smoke_long"]["segments"] == [512, 7745], "smoke self-check"
events = []
for e in s1["events"]:
    r = seq[e["event"]]
    e2 = dict(e, segments_expected=r["segments"], cached_expected=r["cached"])
    if e["event"] == "T2/00":
        assert (r["cached"], r["segments"]) == (448, [64, 11931])
        e2["note"] = ("v1 写 cached 0、[512, 11931]；生产 22:46 的冒烟长请求与 T2/00 共享 8,193 个 token，"
                      "在 448 处留下快照，故 cached 448、[64, 11931]，仍为两段。预测值不改："
                      "少重算 448 个 token，按最慢冷预填 4,700 tok/s 计 < 0.1 s")
    elif e["event"] == "L64":
        assert (r["cached"], r["segments"]) == (0, [22272, 41728])
        e2["source"] = ("推导值：window01 S1 的 L64（带冷标记，64,028 token，切段 [22336, 41692]）总耗时 14.79 s "
                        "减 32 token 解码（按 28 tok/s）；该记录的 first_token_time_s 0.98 s 是空首分片，不可用")
        e2["cross_check_s"] = [round(64000 / 5100, 2), round(64000 / 4700, 2)]
        e2["cross_check_basis"] = "64,000 token ÷ 冷预填 4,700–5,100 tok/s；落在区间内"
    else:
        assert (r["cached"], r["segments"]) == (e["cached_expected"], e["segments_expected"]), e["event"]
    events.append(e2)
s2 = dict(s1)
s2.update({
    "schema": "ophak_task_s_prereg/v2", "written_at": now,
    "supersedes": {"file": "PREREG_TASK_S.json", "sha256": sha(D / "PREREG_TASK_S.json"),
                   "why": ["T2/00 的 cached / 切段按生产实际缓存（冒烟留下的快照）重算",
                           "L64 补上切段预测，来源标为推导值",
                           "零输出窗口起点由 B 发出后 0.2 s 改为 0.4 s：生产分词与反分词同进程（num_tokenizer=0），"
                           "B 分词期间 A 的输出被压住后集中到达；实测渲染加分词 L64 0.126 s、T2 0.02–0.04 s",
                           "结构检查分两级；混入检测按 stats.py 语义写成精确规则；开测前缓存状态前置条件"],
                   "data_seen_before_revision": False},
    "sources": dict(s1["sources"], **{"stall_seq_sim.py": sha(D / "stall_seq_sim.py"),
                                      "stall_seq_out.json": sha(D / "stall_seq_out.json")}),
    "preconditions": {"stats_before_start": {"completed": 2, "prompt_tokens_total": 8769},
                      "why": "只有 22:46 的两条冒烟；否则缓存里可能有别的快照，T2/00 的预期结构作废，先停下由主会话重算"},
    "gates": {
        "per_event_band": "stall ∈ [0.92·P, 1.10·P+0.10]",
        "structure": "一级：Prefill batch 行数（段数）与 segments_expected 相同 → 进入停顿判读；"
                     "二级：cached 与各段长度也相同 → 记“结构全中”。一级不符：该事件只报告",
        "aggregate": "n = 进入停顿判读且未混入的事件数，k = 其中落在区间内的个数："
                     "k ≥ ceil(11n/13) 成立；k ≤ floor(6n/13) 不成立；其余部分成立；n < 9 时只报告不判",
        "zero_output": "(t_d + 0.4 s, t_f − 0.2 s) 内 A 的非空输出数为 0（每个事件）",
        "contamination": "事件期间每 0.5 s 读一次 /v1/stats：任一读数 requests.active 大于我方在途请求数，"
                         "或事件前后 requests.completed 之差不等于我方在该区间完成的请求数 → contaminated",
    },
    "events": events,
})
(D / "PREREG_TASK_S_v2.json").write_text(json.dumps(s2, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------------- task B
b1 = json.loads((D / "PREREG_TASK_B.json").read_text())
b2 = dict(b1)
gates = dict(b1["gates"])
gates["G5_oom"] = ("待检验的推断，不是预测：冷 87K 的切段与开臂相同（22,272 + 64,828），显存峰值相同；"
                   "但热轮变成单段，形状与出过 E1 的关臂热轮相同，E1 根因未证。"
                   "B 臂任一服务 OOM：判“阈值策略未避开 E1”，该参数不进生产")
b2.update({
    "schema": "ophak_task_b_prereg/v2", "written_at": now,
    "supersedes": {"file": "PREREG_TASK_B.json", "sha256": sha(D / "PREREG_TASK_B.json"),
                   "why": ["G5 措辞过强：v1 以冷轮相同推出不 OOM，但 E1 发生在热轮",
                           "T2 冷轮（cold-changed）只报告；A2 中同类冷轮 Δ 为 3.545 s，不在 [2.0, 3.0]，原因未核实"],
                   "data_seen_before_revision": False},
    "gates": gates,
    "notes": {"T2_cold_changed": "A2 关臂对开臂冷轮 Δ 3.545 s，未落在 v1 的报告区间；本任务照实报告，不进判读"},
})
(D / "PREREG_TASK_B_v2.json").write_text(json.dumps(b2, ensure_ascii=False, indent=1), encoding="utf-8")

for f in ("PREREG_TASK_S_v2.json", "PREREG_TASK_B_v2.json", "stall_seq_sim.py", "stall_seq_out.json"):
    print(f, sha(D / f))
print([(e["event"], e["segments_expected"], e["cached_expected"], e["prefill_pred_s"], e["stall_band_s"]) for e in events])
