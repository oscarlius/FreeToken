"""两路缓存共享方式对每路等效失误率的影响（主会话 CPU 快速核查，只读 review_r4 轨迹）。

语义同 sim_d15 lru：每次 ensure 去重、命中先刷新、受害者 argmin(usage, slot)。
模式：
  batched  : 串行批处理，同层两路 20 个 id 一次 ensure（发布路径语义，复现 G_two D0）
  stagger  : 共享 2700 槽，A 在第 l 层时 B 在第 (l+24)%48 层，逐路 ensure；
             上一次调用（另一路在途层）用到的槽受保护
  partition: 每路独占 size//2 槽
每路等效 m = 失误数 / (路数 × 480)；链路上界 R = 1000 / (每步失误 × 54.77/480)。
"""
import pickle, sys
import numpy as np

E, NL, PF = 512, 48, 1024
BIG = np.int64(1) << 60
MS_PER_MISS = 54.77 / 480


class LRU:
    def __init__(self, size):
        self.size = size
        self.id_of = np.full(size, -1, np.int64)
        self.slot_of = np.full(NL * E, -1, np.int64)
        self.use = np.zeros(size, np.int64)
        self.clock = 0
        self.prev = np.empty(0, np.int64)

    def clear_prefill(self):
        n = min(PF, self.size)
        old = self.id_of[:n]
        self.slot_of[old[old >= 0]] = -1
        self.id_of[:n] = -1
        self.use[:n] = 0

    def ensure(self, flat_ids, protect_prev):
        self.clock += 1
        d = np.unique(flat_ids)
        s = self.slot_of[d]
        hit = s >= 0
        self.use[s[hit]] = self.clock
        miss = d[~hit]
        key = self.use * 4096 + np.arange(self.size)
        key[s[hit]] = BIG
        if protect_prev and self.prev.size:
            key[self.prev] = BIG
        used = list(s[hit])
        for e in miss:
            v = int(key.argmin())
            if self.id_of[v] >= 0:
                self.slot_of[self.id_of[v]] = -1
            self.id_of[v] = e
            self.slot_of[e] = v
            self.use[v] = self.clock
            key[v] = BIG
            used.append(v)
        self.prev = np.asarray(used, np.int64)
        return miss.size


def lanes_of(ids_l):
    a = np.asarray(ids_l)
    return [a[:10], a[10:20]] if a.size == 20 else [a[:10]]


def run(steps, mode, size, prefills):
    """steps: list of per-step [layer][lane] -> ids；prefills: 在哪些步之前清 [0,PF)"""
    misses = lane_tokens = 0
    if mode == "partition":
        caches = [LRU(size // 2), LRU(size // 2)]
    else:
        caches = [LRU(size)]
    for t, st in enumerate(steps):
        if t in prefills:
            for c in caches:
                c.clear_prefill()
        nl = len(st[0])
        lane_tokens += nl
        if mode == "batched":
            for l in range(NL):
                misses += caches[0].ensure(np.concatenate(st[l]) + l * E, False)
        elif mode == "partition":
            for l in range(NL):
                for k in range(nl):
                    misses += caches[k].ensure(st[l][k] + l * E, False)
        else:  # stagger: B 落后半步
            for l in range(NL):
                misses += caches[0].ensure(st[l][0] + l * E, True)
                if nl > 1:
                    lb = (l + NL // 2) % NL
                    src = st if lb >= NL // 2 else (steps[t - 1] if t > 0 else None)
                    if src is not None and len(src[lb]) > 1:
                        misses += caches[0].ensure(src[lb][1] + lb * E, True)
    m = misses / (lane_tokens * 480)
    per_step_two = 2 * m * 480 * MS_PER_MISS
    return m, 1000 / per_step_two


def load_two(path):
    ops = pickle.load(open(path, "rb"))["ops"]
    steps, pre = [], set()
    for op in ops:
        if op[0] == "p":
            pre.add(len(steps))
            continue
        steps.append([lanes_of(op[1][l]) for l in range(NL)])
    return steps, pre


def load_pair(pa, pb):
    """两条单路轨迹逐步配对成两路（取较短者长度），模拟不同内容的两个会话。"""
    def dec(p):
        out = []
        for op in pickle.load(open(p, "rb"))["ops"]:
            if op[0] != "p":
                out.append([np.asarray(op[1][l])[:10] for l in range(NL)])
        return out
    a, b = dec(pa), dec(pb)
    n = min(len(a), len(b))
    return [[[a[t][l], b[t][l]] for l in range(NL)] for t in range(n)], {0}


if __name__ == "__main__":
    root = sys.argv[1]
    sets = {"G_two(实测两路)": load_two(f"{root}/stream_G_two.pkl"),
            "seed_real×seed12k(配对)": load_pair(f"{root}/stream_G_seed_real.pkl", f"{root}/stream_G_seed12k.pkl")}
    for name, (steps, pre) in sets.items():
        for mode in ("batched", "stagger", "partition"):
            m, r = run(steps, mode, 2700, pre)
            print(f"{name:24s} {mode:9s} 每路等效m={m*100:6.2f}%  链路上界(两路满载)={r:5.1f} tok/s/路", flush=True)
