"""Generate PREREG_TASK_S.json (stall) and PREREG_TASK_B.json (cut threshold) from sealed data. Runs on the server."""
import hashlib
import json
from pathlib import Path

D = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011")
W2 = Path("/data2/FreeToken/runs/dev_ophak_task_a2_20261011/window02/window")
pre_a = json.loads((D / "PREREG_TASK_A.json").read_text())
sim = json.loads((D / "sim_out_v2.json").read_text())


def ttft(svc, key):
    for line in (W2 / svc / "requests.jsonl").read_text().splitlines():
        d = json.loads(line)
        if d["key"] == key:
            return d["ttft_s"]
    raise KeyError(key)


sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

# ---- task S: stall = prefill time of the other request (production = anchor cut on)
events = []
for r in pre_a["trajectories"]["T2"]["rounds"]:
    k = f"T2/{r['round']:02d}"
    if r["round"] == 0:
        p, src = ttft("A2_on", k), "window02 A2_on（A1_on 冷轮含首服务效应，未用）"
    else:
        p, src = (ttft("A1_on", k) + ttft("A2_on", k)) / 2, "window02 A1_on/A2_on 均值"
    events.append({"event": k, "segments_expected": r["on_segments"], "cached_expected": r["cached"],
                   "prefill_pred_s": round(p, 3), "source": src,
                   "stall_band_s": [round(0.92 * p, 3), round(1.10 * p + 0.10, 3)]})
l64 = 14.79 - 32 / 28.0
events.append({"event": "L64", "segments_expected": None, "cached_expected": 0, "prefill_pred_s": round(l64, 3),
               "source": "window01 S1 L64 总耗时 14.79 s 减 32 token 解码（按 28 tok/s）",
               "stall_band_s": [round(0.92 * l64, 3), round(1.10 * l64 + 0.10, 3)]})
s_doc = {"schema": "ophak_task_s_prereg/v1", "written_at": "2026-10-11T23:30:00+08:00",
         "claim": "另一请求预填期间，正在输出的会话完全停顿；停顿 ≈ 该请求的预填时长",
         "basis": "scheduler.py:1043-1046 预填优先；分段预填的续段仍在预填队列，两段之间不插解码",
         "sources": {"PREREG_TASK_A.json": sha(D / "PREREG_TASK_A.json"),
                     "window02_A1_on": sha(W2 / "A1_on" / "requests.jsonl"),
                     "window02_A2_on": sha(W2 / "A2_on" / "requests.jsonl")},
         "gates": {"per_event_band": "stall ∈ [0.92·P, 1.10·P+0.10]",
                   "aggregate": "13 个事件中 ≥ 11 个落在区间内：成立；≤ 6 个：不成立；其余：部分成立",
                   "zero_output": "B 发出后 0.2 s 至 B 首 token 前 0.2 s 之间，A 的非空输出数为 0（每个事件）"},
         "events": events}
(D / "PREREG_TASK_S.json").write_text(json.dumps(s_doc, ensure_ascii=False, indent=1), encoding="utf-8")

# ---- task B: threshold policy (anchor cut only when remain > 32768)
b_rows = {}
for name, t in sim["trajectories"].items():
    rows = []
    for k, (on, th) in enumerate(zip(t["policies"]["prod"], t["policies"]["thresh32k"])):
        assert on["cached"] == th["cached"]
        changed = len(on["segments"]) != len(th["segments"])
        cls = ("cold-" if on["cached"] == 0 else "") + ("changed" if changed else "unchanged")
        row = {"round": k, "prompt_tokens": on["prompt_tokens"], "cached": on["cached"],
               "on_segments": on["segments"], "thresh_segments": th["segments"], "class": cls}
        if cls == "changed":
            row["delta_band_s"] = [2.3, 3.0]
        elif cls == "unchanged":
            row["delta_band_s"] = [-0.3, 0.3]
        elif cls == "cold-changed":
            row["delta_band_s_report_only"] = [2.0, 3.0]
        else:
            row["delta_band_s_report_only"] = [-1.0, 1.0]
        rows.append(row)
    b_rows[name] = rows
b_doc = {"schema": "ophak_task_b_prereg/v1", "written_at": "2026-10-11T23:30:00+08:00",
         "policy": "只有本次待预填的 token 数（remain_len）超过 32768 时才按锚点切段；默认 0 时与现行为逐位相同",
         "threshold_derivation": "一遍 2.7775 s ≈ 重算 13.6–14.2K token（冷预填 4,700–5,100 tok/s）；值得切的条件为预计省下的重算 > 14K ÷ P(改写)；取 32K，对应 P(改写) ≳ 0.43",
         "simulator": {"file": "segment_sim_v2.py", "sha256": sha(D / "segment_sim_v2.py"),
                       "output_sha256": sha(D / "sim_out_v2.json")},
         "gates": {"T16_lite": "候选默认参数对 release-e2：两服务 20 条 payload 的切段、cached、输出全文逐字相同",
                   "G1": "切段与 cached 与本文件逐轮相同",
                   "G2_changed": "Δ 中位数 ∈ [2.3, 3.0] 且每轮 ≥ 1.8：成立；中位数 < 1.0：不成立；其余：部分成立",
                   "G2_unchanged": "|Δ 中位数| ≤ 0.3：成立",
                   "G3": "同臂两服务同轮输出逐字相同",
                   "G5_oom": "预测不 OOM：冷 87K 的切段与生产相同（22,272 + 64,828）"},
         "trajectories": b_rows}
(D / "PREREG_TASK_B.json").write_text(json.dumps(b_doc, ensure_ascii=False, indent=1), encoding="utf-8")
for f in ("PREREG_TASK_S.json", "PREREG_TASK_B.json"):
    print(f, sha(D / f))
print("S events:", [(e["event"], e["prefill_pred_s"]) for e in events])
for n, rows in b_rows.items():
    print("B", n, {c: sum(r["class"] == c for r in rows) for c in set(r["class"] for r in rows)})
