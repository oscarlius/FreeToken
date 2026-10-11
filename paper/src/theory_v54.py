"""v5.4 理论值重算：两路内容不同时的每路失误率代入 §4.7 模型。

公式（论文 §4.3/§4.4/§4.7）：
  F(B,L) = t0 + k*L + t_req*(B-1)      ms, L 以千 token 计
  X(m)   = m * S_tok / B_P             ms
  R_serial  = 1000 / (F + B*X)
  R_overlap = 1000 / max(F, B*X)
  R_link    = 1000 / (B*X)             (u=0)

失误率来源：
  - 单路发布配置 24.13%（b163 D0 臂稳态均值，v5.3 已用）
  - 两路同/近内容：沿用单路 m（路由高度重合）
  - 两路不同内容：G_two 实测 D0 去重口径 42.6%；
    two_lane_share_sim.py 轨迹重放：G_two 40.39–40.52%，
    seed_real×seed12k 42.91–42.95%（共享 2700 槽）
  - 两路分区缓存（各 1350 槽）：模拟 54.52–55.01%；b162 实测 lane1 52.2%
  - 窗口 A/B CPU review_r4：2700 槽 38.59%，2400/2401 槽 41.38%

输出打印后附 SHA256 留证。python paper/src/theory_v54.py
"""
import hashlib

T0 = 13.1      # ms
K = 0.032      # ms / 千 token
T_REQ = 5.3    # ms
S_TOK_MS = 1331 / 24300 * 1000  # 每 token 全失误搬运时间 ≈ 54.7737 ms

lines = []


def F(B, L):
    return T0 + K * L + T_REQ * (B - 1)


def row(name, B, L, m):
    f = F(B, L)
    x = m * S_TOK_MS
    bx = B * x
    r_ser = 1000 / (f + bx)
    r_ov = 1000 / max(f, bx)
    r_link = 1000 / bx
    lines.append(
        f"{name:<44} B={B} L={L}K m={m*100:6.2f}%  F={f:6.2f} BX={bx:6.2f} "
        f"serial={r_ser:6.2f} overlap={r_ov:6.2f} link={r_link:6.2f}"
    )
    return r_ser, r_ov, r_link


row("单路 32K（发布配置稳态，b163 D0）", 1, 32, 0.2413)
row("两路 32K 同/近内容（m 取单路值）", 2, 32, 0.2413)
# 终稿口径：两路不同内容取并发 2 闭环 X 组 D0 实测 38.24%（1.2K 输入；32K 属外推）
row("两路 32K 不同内容（闭环 X 实测 m，正文采用）", 2, 32, 0.3824)
row("两路 1.2K 不同内容（闭环 X 实测 m，对照实测 16.95/17.01）", 2, 1.2, 0.3824)
row("两路 0.07K R045 原提示（闭环 Y 实测 m，对照 21.57/22.75）", 2, 0.07, 0.2770)
row("两路 32K 分区缓存（b162 lane1 实测 52.2%，正文采用）", 2, 32, 0.522)
# 以下为敏感性参考（开环模拟与去重口径，独立复核有保留，正文不作主数值）
row("两路 32K 不同内容（G_two sim 低端）", 2, 32, 0.4039)
row("两路 32K 不同内容（G_two 实测 D0 42.6%）", 2, 32, 0.426)
row("两路 32K 不同内容（seed_real×seed12k sim）", 2, 32, 0.4295)
row("两路 32K 分区缓存各1350槽（sim 低端）", 2, 32, 0.5452)
row("两路 32K 分区缓存各1350槽（sim 高端）", 2, 32, 0.5501)
row("8 路 32K（发布配置 m，外推）", 8, 32, 0.2413)

# 达到每路 30 tok/s 的失误率条件（两路）
m_ov = (1000 / 30) / (2 * S_TOK_MS)
m_ser = (1000 / 30 - F(2, 32)) / (2 * S_TOK_MS)
lines.append(f"两路每路30条件：理想重叠需 m <= {m_ov*100:.2f}%；串行需 m <= {m_ser*100:.2f}%")

# 22:36 闭环替代模型：R = 1000 / (18.4 + 2*m*54.77)，F 取实测 bs=2 批计算 18.4 ms
for m in (0.4039, 0.4295):
    r = 1000 / (18.4 + 2 * m * S_TOK_MS)
    lines.append(f"闭环模型(F=18.4实测) 两路 m={m*100:.2f}% -> {r:.2f} tok/s/路")

# G_two 在 3600 槽的去重失误率 32.65%，仍高于 30.43%
r = 1000 / max(F(2, 32), 2 * 0.3265 * S_TOK_MS)
lines.append(f"G_two 3600槽 m=32.65% 理想重叠上界 -> {r:.2f} tok/s/路（仍 < 30）")

# b162 原型设计（分区缓存 m≈52%）的理想上限
r = 1000 / (2 * 0.52 * S_TOK_MS)
lines.append(f"b162 分区缓存 m≈52% 链路上界 -> {r:.2f} tok/s/路（< 串行）")

text = "\n".join(lines)
print(text)
print("SHA256:", hashlib.sha256(text.encode()).hexdigest())
