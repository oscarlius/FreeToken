"""D10 batch162 逐步分解（主会话复核，只读）。

用法：在 9 号机 run 目录下执行
  /data2/FreeToken/venv/bin/python -I b162_step_decompose.py <run_dir>
输出：步长 / CPU 派发 / GPU 完成分位数，两路命中与搬运量，链路时间对照。
"""
import json
import statistics as st
import sys
from pathlib import Path

WARM = 16                       # 与独审口径一致：排除前 16 个成对解码步
EXPERT_BYTES = 2_772_480        # 每专家字节（与 h2d_bytes / misses 实测一致）
FULL_MISS_MS = 54.77            # §4.7：单路全失误每步搬运时间 → B_P ≈ 24.3 GB/s
B_P = 480 * EXPERT_BYTES / (FULL_MISS_MS / 1e3)


def pct(xs):
    xs = sorted(xs)
    return "p5=%.1f p50=%.1f p95=%.1f mean=%.1f" % (
        xs[len(xs) // 20], xs[len(xs) // 2], xs[len(xs) * 19 // 20], st.mean(xs))


def main(run):
    steps = [json.loads(l) for l in open(run / "raw_d10_steps.jsonl")]
    samples = [json.loads(l) for l in open(run / "raw_d10_samples.jsonl")]
    win = [s for s in steps if s["step"] >= WARM]
    cpu = [s["cpu_dispatch_ns"] / 1e6 for s in win]
    gpu = [s["gpu_completion_ms"] for s in win]
    wall = [(s["monotonic_end_ns"] - s["monotonic_start_ns"]) / 1e6 for s in win]
    print("step0 cpu_dispatch ms %.1f" % (steps[0]["cpu_dispatch_ns"] / 1e6))
    print("cpu_dispatch ms", pct(cpu))
    print("gpu_completion ms", pct(gpu))
    print("gpu - cpu ms", pct([g - c for g, c in zip(gpu, cpu)]))
    total = 0
    for lane in (0, 1):
        hits = sum(s["lanes"][lane]["hits"] for s in win)
        look = sum(s["lanes"][lane]["lookups"] for s in win)
        miss = sum(s["lanes"][lane]["misses"] for s in win)
        byts = sum(s["lanes"][lane]["h2d_bytes"] for s in win)
        total += byts
        ids = [x["tokens"][lane]["token_id"] for x in samples]
        print("lane %d hit=%.4f misses/step=%.1f MB/step=%.1f distinct_tokens=%d"
              % (lane, hits / look, miss / len(win), byts / len(win) / 1e6, len(set(ids))))
    secs = sum(wall) / 1e3
    link_ms = total / len(win) / B_P * 1e3
    print("H2D %.1f GB / %.1f s = %.2f GB/s (B_P %.1f GB/s)" % (total / 1e9, secs, total / 1e9 / secs, B_P / 1e9))
    print("link time/step at B_P %.1f ms vs step mean %.1f ms" % (link_ms, st.mean(wall)))
    for lo, hi in [(1, 5), (16, 100), (100, 200), (200, 300), (300, 400), (400, 511)]:
        seg = [s for s in steps if lo <= s["step"] < hi]
        m = st.mean(sum(l["misses"] for l in s["lanes"]) for s in seg)
        print("steps %3d-%3d misses/step=%.0f cpu_ms=%.1f" % (lo, hi, m, st.mean(s["cpu_dispatch_ns"] / 1e6 for s in seg)))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
