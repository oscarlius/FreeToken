"""主会话快速核查：层循环感知替换 vs LRU（只读 review_r4/stream_G_*.pkl，CPU）。

语义与 sim_d15.CacheSim 的 lru 模式一致：每次 ensure = (层, 解码步)，路由去重，
命中先刷新，未命中按升序 id 依次取受害者；prefill 清空 [0, 1024)。
策略：
  lru    : 受害者 = argmin (usage_call_clock, slot)            —— 复现生产语义
  cycle  : 受害者 = argmax (错过的本层访问次数, 到下次本层访问的距离)
           即同"错过次数"内先踢掉下一次访问最远的层（Belady 式平局规则）
  lru2   : 受害者 = argmin (倒数第二次使用的 clock；只用过一次的视为 -1, 再按最近使用)
"""
import pickle
import sys
from pathlib import Path

import numpy as np

E, NL, PF = 512, 48, 1024
BIG = np.int64(1) << 60


def run(ops, size, policy, trunc=None):
    id_of_slot = np.full(size, -1, np.int64)
    slot_for_id = np.full(NL * E, -1, np.int64)
    last_call = np.zeros(size, np.int64)   # 最近一次使用的调用时钟
    prev_call = np.full(size, -1, np.int64)  # 倒数第二次使用（lru2）
    last_step = np.full(size, -1, np.int64)  # 最近一次使用的解码步
    slots = np.arange(size, dtype=np.int64)
    crf = np.zeros(size, np.float64)
    alpha = np.log(2.0) / float(policy[4:]) if policy.startswith('lrfu') else 0.0
    clock = 0
    step = -1
    miss = active = 0
    n_steps = None
    if trunc:
        n_steps = trunc[0] + (1 if trunc[1] else 0)
    segs = []
    seg_m = seg_a = 0
    for op in ops:
        if op[0] == "p":
            if seg_a:
                segs.append((seg_m, seg_a)); seg_m = seg_a = 0
            old = id_of_slot[:PF]
            slot_for_id[old[old >= 0]] = -1
            id_of_slot[:PF] = -1
            last_call[:PF] = 0
            prev_call[:PF] = -1
            last_step[:PF] = -1
            continue
        step += 1
        if n_steps is not None and step >= n_steps:
            break
        ids = op[1]
        layers = range(NL)
        if trunc and trunc[1] and step == trunc[0]:
            layers = trunc[1]
        for l in layers:
            clock += 1
            d = np.unique(ids[l]).astype(np.int64)
            base = l * E
            s = slot_for_id[base + d]
            hit = s >= 0
            hs = s[hit]
            prev_call[hs] = last_call[hs]
            if alpha:
                crf[hs] = 1.0 + crf[hs] * np.exp(-alpha * (clock - last_call[hs]))
            last_call[hs] = clock
            last_step[hs] = step
            active += d.size
            seg_a += d.size
            misses = d[~hit]
            miss += misses.size
            seg_m += misses.size
            if misses.size == 0:
                continue
            if policy == "lru":
                key = last_call * 4096 + slots
            elif policy == "lru2":
                key = prev_call * (BIG >> 24) + last_call  # 先比倒数第二次，再比最近一次
            elif policy == "cycle":
                lay = np.where(id_of_slot >= 0, id_of_slot // E, -1)
                # 本步中层 lay 是否已被访问（lay <= l 视为已访问；lay == l 即当前调用）
                visited = (lay <= l).astype(np.int64)
                missed = step - last_step - (1 - visited)
                dist = np.mod(lay - l, NL)
                dist = np.where(dist == 0, NL, dist)
                key = -(missed * 64 + dist)
                key = np.where(id_of_slot < 0, -BIG, key)  # 空槽最先用
            elif policy.startswith('lrfu'):
                key = crf * np.exp(-alpha * (clock - last_call))
                key = np.where(id_of_slot < 0, -1.0, key)
            else:
                raise ValueError(policy)
            key = key.copy()
            key[hs] = np.inf if key.dtype.kind == 'f' else BIG  # 本次命中的槽受保护
            for e in misses:
                v = int(key.argmin())
                old = id_of_slot[v]
                if old >= 0:
                    slot_for_id[old] = -1
                id_of_slot[v] = base + e
                slot_for_id[base + e] = v
                prev_call[v] = -1
                last_call[v] = clock
                last_step[v] = step
                key[v] = np.inf if key.dtype.kind == 'f' else BIG
                crf[v] = 1.0
    if seg_a:
        segs.append((seg_m, seg_a))
    return miss, active, segs


def main():
    root = Path(sys.argv[1])
    groups = sys.argv[2].split(",")
    policies = sys.argv[3].split(",")
    sizes = [int(x) for x in sys.argv[4].split(",")]
    for g in groups:
        blob = pickle.load(open(root / f"stream_{g}.pkl", "rb"))
        ops, meta = blob["ops"], blob["meta"]
        for size in sizes:
            for p in policies:
                m, a, segs = run(ops, size, p)
                print(f"{g:12s} size={size} {p:6s} miss={m/a*100:7.3f}% turns={len(segs)} per_turn=" + ",".join(f"{sm/sa*100:.2f}:{sa//480}" for sm, sa in segs), flush=True)


if __name__ == "__main__":
    main()
