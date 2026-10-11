"""Strata 0.1.42 STRATA_ROUTE_TAIL_SKIP 在本机轨迹上的效果估算（主会话 CPU 快速核查，只读 review_r4 轨迹）。

语义：
- LRU 部分与 sim_d15 / cycle_policy_sim 的 lru 模式一致：每次 ensure = (层, 解码步)，路由去重，
  命中先刷新，未命中按升序 id 依次取受害者 argmin(usage, slot)；prefill 清空 [0, 1024)。
- 尾部跳过（Strata 0.1.42）：未命中的专家如果在本窗口内所有路由它的 token 中排名都 >= R
  （1 起算，10 为最低），就不搬、不算、不插入缓存；排名 < R 的未命中照常插入。
- 轨迹中每层的 id 按路由权重降序排列（freetoken/kernel/triton/moe_router.py 是 K 次顺序 argmax）；
  两路轨迹每层 20 个 = lane0 的 10 个 + lane1 的 10 个。两路时按"所有路由它的 lane 排名都 >= R"判定
  （Strata 在 --batch 下默认不开，这里只是上界估计）。
输出：搬运失误率 m_xfer = 插入数 / 去重路由数（对应 §4.7 的 m），以及被跳过的专家占全部路由实例的比例。
"""
import pickle
import sys
from pathlib import Path

import numpy as np

E, NL, PF, K = 512, 48, 1024, 10


def best_rank(ids):
    """返回 (去重 id, 每个 id 在各 lane 中的最好排名，1 起算)。"""
    a = np.asarray(ids).astype(np.int64)
    ranks = np.tile(np.arange(1, K + 1), a.size // K)
    order = np.lexsort((ranks, a))
    a, ranks = a[order], ranks[order]
    first = np.r_[True, a[1:] != a[:-1]]
    return a[first], ranks[first]


def run(ops, size, R, static_k=0):
    """static_k>0：确定性变体，每个 lane 始终只取前 static_k 名（不依赖缓存状态）；m 的分母仍用原始 top-10 去重数。"""
    id_of = np.full(size, -1, np.int64)
    slot_of = np.full(NL * E, -1, np.int64)
    use = np.zeros(size, np.int64)
    slots = np.arange(size, dtype=np.int64)
    clock = inserted = skipped = active = routed = 0
    for op in ops:
        if op[0] == "p":
            old = id_of[:PF]
            slot_of[old[old >= 0]] = -1
            id_of[:PF] = -1
            use[:PF] = 0
            continue
        for l in range(NL):
            clock += 1
            raw = np.asarray(op[1][l])
            routed += raw.size
            d0, _ = best_rank(raw)
            if static_k:
                raw = raw.reshape(-1, K)[:, :static_k].reshape(-1)
                skipped += (raw.size // static_k) * (K - static_k)
            d, br = best_rank(np.pad(raw.reshape(-1, static_k or K), ((0, 0), (0, K - (static_k or K))), constant_values=-1).reshape(-1)) if static_k else best_rank(raw)
            if static_k:
                keep = d >= 0
                d, br = d[keep], br[keep]
            flat = d + l * E
            s = slot_of[flat]
            hit = s >= 0
            use[s[hit]] = clock
            active += d0.size
            miss_ids, miss_rank = flat[~hit], br[~hit]
            if R:
                skip = miss_rank >= R
                skipped += int(skip.sum())
                miss_ids = miss_ids[~skip]
            if miss_ids.size == 0:
                continue
            key = use * 4096 + slots
            key[s[hit]] = np.int64(1) << 60
            for e in miss_ids:
                v = int(key.argmin())
                if id_of[v] >= 0:
                    slot_of[id_of[v]] = -1
                id_of[v] = e
                slot_of[e] = v
                use[v] = clock
                key[v] = np.int64(1) << 60
                inserted += 1
    return inserted / active, skipped / routed


def main():
    root = Path(sys.argv[1])
    groups = sys.argv[2].split(",")
    ranks = [x for x in sys.argv[3].split(",")]
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 2700
    for g in groups:
        # 输入是本项目 review_r4 自产并封存的轨迹（与 sim_d15 同源），不是外部数据。
        ops = pickle.load(open(root / f"stream_{g}.pkl", "rb"))["ops"]
        for spec in ranks:
            if spec.startswith("top"):
                m, sk = run(ops, size, 0, static_k=int(spec[3:]))
            else:
                m, sk = run(ops, size, int(spec))
            print(f"{g:12s} size={size} {spec:>5s} m_xfer={m*100:7.3f}%  skipped/routed={sk*100:6.2f}%", flush=True)


if __name__ == "__main__":
    main()
