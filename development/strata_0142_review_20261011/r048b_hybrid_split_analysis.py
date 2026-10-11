"""R048b S 臂 hybrid 诊断数据的分流与开销分析（主会话，只读）。

用法（9 号机）：/data2/FreeToken/venv/bin/python -I r048b_hybrid_split_analysis.py \
    /data2/_shared/runs/ft_rounds/E2-R048b/batch111/S/diagnostic
注意：诊断模式开启 trace，会改变时序（同臂单路：性能模式 31.3 ms/步，诊断模式 41.6 ms/步），
绝对值只作参考，比例和回归斜率更可信。steps[i] 与 trace 的 decode_observation_sequence i+1 对应（两者都是 1339 条）。
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

WARM = 16


def main(base: Path) -> None:
    steps = [json.loads(line) for line in open(base / "d0_decode_steps.jsonl")]
    trace = [json.loads(line) for line in open(base / "d0_hyb_trace.jsonl")]
    by_seq = defaultdict(dict)
    for rec in trace:
        by_seq[rec["decode_observation_sequence"]][rec["layer"]] = rec

    for bs in (1, 2):
        sel = [s for s in steps if s["bs"] == bs and s["step"] >= WARM]
        miss = st.mean(m for s in sel for m in s["missing_per_layer"])
        cpu = st.mean(c for s in sel for c in s["cpu_experts_per_layer"])
        dts = sorted((b["t"] - a["t"]) * 1000 for a, b in zip(sel, sel[1:])
                     if b["step"] == a["step"] + 1 and b["rids"] == a["rids"])
        p50 = dts[len(dts) // 2]
        print("bs=%d 每层失误 %.2f，CPU %.2f，PCIe %.2f（PCIe 份额 %.3f）；每路 m=%.3f；诊断模式步长 p50 %.1f ms，每路 %.1f tok/s"
              % (bs, miss, cpu, miss - cpu, (miss - cpu) / miss, miss / (10 * bs), p50, 1000 / p50))

    xs, ys = [], []
    for i, s in enumerate(steps):
        layers = by_seq.get(i + 1)
        if layers is None or s["bs"] != 1 or s["step"] < WARM:
            continue
        for layer, n_cpu in enumerate(s["cpu_experts_per_layer"]):
            rec = layers.get(layer)
            if rec is None:
                continue
            xs.append(n_cpu)
            ys.append((rec["cpu_task"]["end_ns"] - rec["cpu_task"]["start_ns"]) / 1e6)
    mx, my = st.mean(xs), st.mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    print("bs=1 回归：每层 CPU 任务 = %.3f ms 固定 + %.3f ms × CPU 专家数（n=%d）" % (my - slope * mx, slope, len(xs)))
    pcie = [r["pcie_copy"]["event_elapsed_ms"] for r in trace if r["decode_observation_sequence"] > WARM]
    print("PCIe 每层拷贝均值 %.3f ms" % st.mean(pcie))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
