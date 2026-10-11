"""论文 v4.0 / v5.0 的配图：原理图与数据图都由本文件生成，保证坐标与数据一致。

原九图沿用 FTD-20261003-1 或 pass_queue_model 的推导；v5 的 T06 段长与 T17 修复面板引用 FTD-20261009-1。
颜色只用三个分类槽（已用 dataviz 校验器在浅色底上验证）与中性色。
"""
from html import escape

INK = "#1a1a19"
MUTED = "#6b6a65"
GRID = "#e6e5e1"
SOFT = "#f4f3ef"
S1 = "#2a78d6"   # 蓝：开关关 / 实测主序列 / 搬运
S2 = "#eb6834"   # 橙：开关开 / 额外一遍 / 计算
S3 = "#1baf7a"   # 青：第三序列（对比度偏低，必须配直接标注）
FONT = "font-family:inherit"


def _svg(w, h, body, label):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}" '
            f'style="max-width:{w}px;{FONT}" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _t(x, y, s, size=12, color=INK, anchor="start", weight="normal", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{escape(str(s))}</text>')


def _rect(x, y, w, h, fill, stroke="none", rx=0, dash=None, sw=1, title=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    tt = f"<title>{escape(title)}</title>" if title else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}>{tt}</rect>')


def _line(x1, y1, x2, y2, color=MUTED, sw=1, dash=None, marker=None):
    """marker 传完整 id（含图前缀）。"""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{sw}"{d}{m}/>'


def _arrow_defs(px):
    return ('<defs>'
            f'<marker id="{px}ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker>'
            f'<marker id="{px}ahb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{S1}"/></marker>'
            '</defs>')


def _bar_top_round(x, y, w, h, fill, title):
    """柱顶 4px 圆角、底边贴基线的直角柱。"""
    r = min(4, w / 2, h)
    p = (f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
         f"L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} L{x + w:.1f},{y + h:.1f} Z")
    return f'<path d="{p}" fill="{fill}"><title>{escape(title)}</title></path>'


# ---------------------------------------------------------------- 图 1 系统与共享资源
def fig_architecture():
    w, h = 780, 360
    b = [_arrow_defs("f1-")]
    # 主存
    b.append(_rect(20, 30, 300, 240, SOFT, INK, 6))
    b.append(_t(170, 52, "主存（约 251 GiB，双路 NUMA）", 13, INK, "middle", "bold"))
    for nx, nm in ((35, "node0（偶数号核）"), (175, "node1（奇数号核）")):
        b.append(_rect(nx, 66, 130, 120, "#ffffff", MUTED, 4))
        b.append(_t(nx + 65, 84, nm, 10.5, MUTED, "middle"))
        b.append(_rect(nx + 10, 94, 110, 34, "#e8f0fb", S1, 3))
        b.append(_t(nx + 65, 115, "专家池（交错放置）", 11, INK, "middle"))
        b.append(_rect(nx + 10, 136, 110, 34, "#ffffff", MUTED, 3, dash="3 2"))
        b.append(_t(nx + 65, 157, "PLE / N-gram 表", 11, MUTED, "middle"))
    b.append(_t(170, 205, "路由专家 68.14 GB（63.46 GiB），唯一真相", 11.5, INK, "middle"))
    b.append(_t(170, 223, "STREAM：交错 46.6 GB/s · 只绑 node1 110.8 GB/s", 11, MUTED, "middle"))
    b.append(_t(170, 243, "共享资源 ①：主存读带宽", 10.5, S2, "middle"))
    b.append(_t(170, 259, "（DMA、CPU 计算、NCCL 中转共用）", 10.5, S2, "middle"))
    # CPU
    b.append(_rect(20, 290, 300, 52, "#ffffff", INK, 6))
    b.append(_t(170, 311, "2 × Xeon Silver 4310（AVX-512 VNNI，无 AMX）", 12, INK, "middle"))
    b.append(_t(170, 330, "共享资源 ②：CPU 专家执行（hybrid 支路）", 10.5, S2, "middle"))
    b.append(_line(170, 290, 170, 274, MUTED, 1.2, marker="f1-ah"))
    # GPU 与 PCIe 总线
    gx, bus = 496, 360
    ys = [30 + i * 80 + 31 for i in range(4)]
    b.append(_line(320, 150, bus, 150, S1, 1.6))
    b.append(_line(bus, ys[0], bus, ys[-1], MUTED, 1.2))
    b.append(_line(bus, ys[0], bus, 150, S1, 1.6))
    labels = ["GPU0 RTX 4090 24 GB（本文实测）", "GPU1（多卡方案，未测）", "GPU2（多卡方案，未测）", "GPU3（多卡方案，未测）"]
    for i, lab in enumerate(labels):
        gy = 30 + i * 80
        planned = i > 0
        b.append(_rect(gx, gy, 240, 62, "#ffffff", S1 if not planned else MUTED, 6,
                       dash=None if not planned else "5 3", sw=1.6 if not planned else 1))
        b.append(_t(gx + 120, gy + 20, lab, 11.5, INK if not planned else MUTED, "middle", "bold" if not planned else "normal"))
        b.append(_t(gx + 120, gy + 39, "专家缓存（单卡约 12.8% 槽）· KV / GDN 状态", 10.5, MUTED, "middle"))
        b.append(_t(gx + 120, gy + 55, "非专家权重常驻", 10.5, MUTED, "middle"))
        b.append(_line(bus, ys[i], gx - 4, ys[i], S1 if not planned else MUTED, 1.6 if not planned else 1,
                       dash=None if not planned else "4 3", marker="f1-ahb" if not planned else "f1-ah"))
    mid = (bus + gx) / 2
    b.append(_t(mid, 92, "PCIe 4.0 x16", 10.5, S1, "middle"))
    b.append(_t(mid, 107, "B_P = 24.3 GB/s / 卡", 10.5, S1, "middle"))
    b.append(_t(mid, 172, "共享资源 ③", 10.5, S2, "middle"))
    b.append(_t(mid, 187, "每卡 PCIe 链路", 10.5, S2, "middle"))
    b.append(_t(mid, 252, "NCCL 经主存中转", 10.5, S2, "middle"))
    b.append(_t(mid, 267, "与 ①③ 争用", 10.5, S2, "middle"))
    b.append(f'<path d="M{gx + 244},{70} C{gx + 258},{150} {gx + 258},{250} {gx + 244},{311}" fill="none" stroke="{S2}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    b.append(_t(gx + 268, 176, "无 P2P", 10.5, S2, "start", extra='writing-mode="tb"'))
    return _svg(w, h, "".join(b), "系统与共享资源示意")


# ---------------------------------------------------------------- 图 2 遍数原理
def fig_pass_principle():
    w, h = 780, 300
    x0, sc = 150, 25.0          # 每秒 25 px，24 s = 600 px
    b = []
    rows = [
        ("4096 分块（冷 32K）", 50),
        ("层优先（冷 32K）", 120),
        ("短后缀，一段", 190),
        ("短后缀，锚点切成两段", 240),
    ]
    for name, y in rows:
        b.append(_t(x0 - 10, y + 15, name, 11.5, INK, "end"))
    # 分块：8 遍，每遍 2.86 s 搬运 + 约 0.3 s 计算（与搬运重叠，绘在条内）
    for i in range(8):
        xs = x0 + i * 2.86 * sc
        b.append(_rect(xs, 50, 2.86 * sc - 2, 22, S1, rx=3, title=f"第 {i + 1} 遍：整池搬运约 2.86 s"))
        b.append(_rect(xs + 2, 74, 0.3 * sc, 6, S2, rx=1, title="本块 MoE 计算约 0.3 s（藏在搬运内）"))
        b.append(_t(xs + 2.86 * sc / 2, 65, f"遍{i + 1}", 10, "#ffffff", "middle"))
    b.append(_t(x0, 96, "8 遍 × 2.86 s ≈ 22.9 s（实测 21.1–24.6 s）；每块 MoE 计算约 0.3 s，藏在搬运之内", 11, INK))
    # 层优先：一遍，计算 6.3 s 主导，搬运 2.86 s 藏在计算下
    b.append(_rect(x0, 120, 6.3 * sc, 22, S2, rx=3, title="逐层计算合计约 6.3 s（每层约 131 ms）"))
    b.append(_t(x0 + 6.3 * sc / 2, 135, "逐层计算（受计算限制）", 10.5, "#ffffff", "middle"))
    b.append(_rect(x0, 144, 2.86 * sc, 8, S1, rx=2, title="整池搬运一遍 2.86 s（每层 59 ms，与计算重叠）"))
    b.append(_t(x0 + 2.86 * sc + 6, 152, "搬运一遍，与计算重叠", 10.5, S1))
    b.append(_t(x0 + 6.3 * sc + 6, 135, "≈ 6.5 s（实测 6.07–6.60）", 11, INK))
    # 短后缀：一段 / 两段
    b.append(_rect(x0, 190, 2.8 * sc, 22, S1, rx=3, title="一遍整池搬运，计算可忽略"))
    b.append(_t(x0 + 2.8 * sc + 6, 205, "≈ 2.7–2.9 s（一遍）", 11, INK))
    b.append(_rect(x0, 240, 2.8 * sc - 2, 22, S1, rx=3, title="第一段：一遍"))
    b.append(_rect(x0 + 2.8 * sc, 240, 2.8 * sc, 22, S2, rx=3, title="锚点处切段：额外一遍"))
    b.append(_t(x0 + 2.8 * sc + 2.8 * sc / 2, 255, "额外一遍", 10.5, "#ffffff", "middle"))
    b.append(_t(x0 + 5.6 * sc + 6, 255, "≈ 5.3–6.0 s（两遍）", 11, INK))
    # 时间轴
    ya = 280
    b.append(_line(x0, ya, x0 + 24 * sc, ya, MUTED, 1))
    for s in range(0, 25, 4):
        b.append(_line(x0 + s * sc, ya, x0 + s * sc, ya + 4, MUTED, 1))
        b.append(_t(x0 + s * sc, ya + 16, f"{s} s", 10, MUTED, "middle"))
    # 图例
    b.append(_rect(x0, 16, 12, 10, S1, rx=2) + _t(x0 + 16, 25, "整池搬运（PCIe）", 11, INK))
    b.append(_rect(x0 + 140, 16, 12, 10, S2, rx=2) + _t(x0 + 156, 25, "计算 / 额外一遍", 11, INK))
    return _svg(w, h, "".join(b), "专家流遍数原理")


# ---------------------------------------------------------------- 通用坐标轴
def _axes(b, x0, y0, pw, ph, xticks, yticks, xfmt, yfmt, xlabel, ylabel, xpos, ypos):
    for v in yticks:
        y = ypos(v)
        b.append(_line(x0, y, x0 + pw, y, GRID, 1))
        b.append(_t(x0 - 6, y + 4, yfmt(v), 10.5, MUTED, "end"))
    for v in xticks:
        x = xpos(v)
        b.append(_line(x, y0 + ph, x, y0 + ph + 4, MUTED, 1))
        b.append(_t(x, y0 + ph + 17, xfmt(v), 10.5, MUTED, "middle"))
    b.append(_line(x0, y0 + ph, x0 + pw, y0 + ph, MUTED, 1))
    b.append(_t(x0 + pw / 2, y0 + ph + 34, xlabel, 11, MUTED, "middle"))
    b.append(_t(x0 - 42, y0 + ph / 2, ylabel, 11, MUTED, "middle",
                extra=f'transform="rotate(-90 {x0 - 42:.1f} {y0 + ph / 2:.1f})"'))


# ---------------------------------------------------------------- 图 3 Agent 轮次两档
def fig_agent_tiers():
    import math
    w, h = 720, 330
    x0, y0, pw, ph = 80, 30, 560, 230
    lo, hi = math.log10(30), math.log10(1200)
    xpos = lambda v: x0 + (math.log10(v) - lo) / (hi - lo) * pw
    ypos = lambda v: y0 + ph - v / 6.5 * ph
    b = []
    _axes(b, x0, y0, pw, ph, [30, 50, 100, 200, 500, 1000], [0, 1, 2, 3, 4, 5, 6],
          lambda v: f"{v}", lambda v: f"{v}", "该轮重算 token 数（对数轴）", "首 token（s）", xpos, ypos)
    for v, lab in ((2.80, "一遍 = P/B_P ≈ 2.80 s"), (5.60, "两遍 ≈ 5.60 s")):
        b.append(_line(x0, ypos(v), x0 + pw, ypos(v), MUTED, 1, dash="4 3"))
        b.append(_t(x0 + pw - 4, ypos(v) - 5, lab, 10.5, MUTED, "end"))
    rec = [64, 60, 52, 45, 48, 633, 909, 663, 529, 62, 108]
    tt = [2.66, 2.66, 2.66, 2.66, 3.50, 5.31, 5.31, 2.69, 5.31, 2.68, 2.68]
    for i, (r, t) in enumerate(zip(rec, tt)):
        jitter = (i % 3 - 1) * 3
        b.append(f'<circle cx="{xpos(r) + jitter:.1f}" cy="{ypos(t):.1f}" r="5" fill="{S1}" stroke="#ffffff" stroke-width="2">'
                 f'<title>T1 第 {i + 1} 轮：重算 {r} token，首 token {t} s</title></circle>')
    b.append(_t(xpos(48) + 10, ypos(3.50) + 4, "第 5 轮 3.50 s：残差个案，未解释", 10.5, INK))
    b.append(_t(xpos(663) - 6, ypos(2.69) + 18, "重算 663 → 一遍", 10.5, INK, "middle"))
    b.append(_t(xpos(529) - 4, ypos(5.31) + 20, "重算 529 → 两遍", 10.5, INK, "middle"))
    return _svg(w, h, "".join(b), "T1 轨迹每轮重算量与首 token")


# ---------------------------------------------------------------- 图 4 开关四格
def fig_four_cell():
    w, h = 720, 330
    x0, y0, pw, ph = 80, 40, 600, 220
    groups = [("冷 · 层优先\nbatch14/16（7 条消息）", 5.43, 2.80),
              ("冷 · 分块\nbatch16（7 条消息）", 5.73, 2.90),
              ("冷 · 层优先\nbatch17（13 条消息）", 5.864, 3.054),
              ("热 · 层优先\nbatch17（rep1–4 中位数）", 2.944, 2.943)]
    ypos = lambda v: y0 + ph - v / 7 * ph
    b = []
    for v in range(0, 8):
        y = ypos(v)
        b.append(_line(x0, y, x0 + pw, y, GRID, 1))
        b.append(_t(x0 - 6, y + 4, f"{v}", 10.5, MUTED, "end"))
    b.append(_t(x0 - 42, y0 + ph / 2, "首 token（s）", 11, MUTED, "middle",
                extra=f'transform="rotate(-90 {x0 - 42} {y0 + ph / 2})"'))
    b.append(_line(x0, ypos(2.80), x0 + pw, ypos(2.80), MUTED, 1, dash="4 3"))
    gw = pw / len(groups)
    bw = 46
    for i, (name, on, off) in enumerate(groups):
        cx = x0 + gw * i + gw / 2
        for j, (v, col, lab) in enumerate(((on, S2, "开"), (off, S1, "关"))):
            bx = cx - bw - 1 + j * (bw + 2)
            b.append(_bar_top_round(bx, ypos(v), bw, y0 + ph - ypos(v), col, f"{name.replace(chr(10), ' ')}：开关{lab} {v} s"))
            b.append(_t(bx + bw / 2, ypos(v) - 5, f"{v:.2f}" if v < 5.85 or v > 5.87 else "5.86", 10.5, INK, "middle"))
        l1, l2 = name.split("\n")
        b.append(_t(cx, y0 + ph + 17, l1, 11, INK, "middle"))
        b.append(_t(cx, y0 + ph + 32, l2, 10, MUTED, "middle"))
    b.append(_line(x0, y0 + ph, x0 + pw, y0 + ph, MUTED, 1))
    b.append(_rect(x0, 12, 12, 10, S2, rx=2) + _t(x0 + 16, 21, "锚点检查点开（本树含 D3 预填锚封顶）", 11, INK))
    b.append(_rect(x0 + 300, 12, 12, 10, S1, rx=2) + _t(x0 + 316, 21, "锚点检查点关", 11, INK))
    b.append(_line(x0 + 420, 17, x0 + 446, 17, MUTED, 1, dash="4 3") + _t(x0 + 452, 21, "一遍 ≈ 2.80 s", 11, INK))
    return _svg(w, h, "".join(b), "锚点检查点开关的冷热四格")


# ---------------------------------------------------------------- 图 5 PCIe 预算：一遍对 L 个解码 token
def fig_pcie_budget():
    w, h = 720, 300
    x0, y0, pw, ph = 150, 30, 520, 200
    Ls = [100, 233, 600, 1500]
    pas, per = 2.80, 0.01201
    xmax = 28
    xpos = lambda v: x0 + v / xmax * pw
    b = []
    for v in range(0, 29, 4):
        b.append(_line(xpos(v), y0, xpos(v), y0 + ph, GRID, 1))
        b.append(_t(xpos(v), y0 + ph + 16, f"{v}", 10.5, MUTED, "middle"))
    b.append(_t(x0 + pw / 2, y0 + ph + 34, "每轮占用的 PCIe 时间（s）：一遍预填 + L × 每 token 未命中搬运", 11, MUTED, "middle"))
    bh, gap = 30, 20
    for i, L in enumerate(Ls):
        y = y0 + 10 + i * (bh + gap)
        d = L * per
        b.append(_t(x0 - 8, y + 20, f"输出 L = {L} token", 11.5, INK, "end"))
        b.append(_rect(xpos(0), y, xpos(pas) - xpos(0) - 1, bh, S1, rx=3, title=f"一遍预填 2.80 s"))
        b.append(_rect(xpos(pas) + 1, y, xpos(pas + d) - xpos(pas) - 1, bh, S2, rx=3, title=f"解码未命中 {L} × 12.0 ms = {d:.2f} s"))
        b.append(_t(xpos(pas + d) + 6, y + 20, f"{pas + d:.1f} s（解码占 {d / (pas + d) * 100:.0f}%）", 11, INK))
    b.append(_rect(x0, 8, 12, 10, S1, rx=2) + _t(x0 + 16, 17, "一遍预填（68.14 GB / 24.3 GB/s）", 11, INK))
    b.append(_rect(x0 + 260, 8, 12, 10, S2, rx=2) + _t(x0 + 276, 17, "解码未命中（292 MB / token）", 11, INK))
    return _svg(w, h, "".join(b), "PCIe 时间预算与 L*")


# ---------------------------------------------------------------- 图 6 遍数排队 P95
def fig_queue():
    w, h = 720, 330
    x0, y0, pw, ph = 80, 40, 560, 220
    lams = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.8]
    data = {
        "每遍容量 1（各搬一遍）": ([4.48, 5.24, 6.77, 8.71, 12.25, 19.95, 53.73, None, None, None, None], S2),
        "每遍容量 2": ([4.32, 4.83, 5.03, 5.15, 5.26, 5.63, 6.18, 6.72, 8.39, 12.24, None], S3),
        "容量不限（理想化）": ([4.31, 4.80, 4.97, 5.04, 5.08, 5.11, 5.13, 5.14, 5.16, 5.17, 5.18], S1),
    }
    ymax = 20
    xpos = lambda v: x0 + v / 0.8 * pw
    ypos = lambda v: y0 + ph - min(v, ymax) / ymax * ph
    b = []
    _axes(b, x0, y0, pw, ph, [0, 0.2, 0.4, 0.6, 0.8], [0, 5, 10, 15, 20],
          lambda v: f"{v:g}", lambda v: f"{v}", "轮次到达率 λ（轮 / s）", "首 token P95（s）", xpos, ypos)
    b.append(_line(x0, ypos(2 * 2.66), x0 + pw, ypos(2 * 2.66), MUTED, 1, dash="4 3"))
    b.append(_t(x0 + 6, ypos(5.32) - 5, "2D ≈ 5.3 s", 10.5, MUTED))
    for name, (vals, col) in data.items():
        pts = [(xpos(l), ypos(v), l, v) for l, v in zip(lams, vals) if v is not None]
        path = " ".join(("M" if k == 0 else "L") + f"{x:.1f},{y:.1f}" for k, (x, y, _, _) in enumerate(pts))
        b.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2"/>')
        for x, y, l, v in pts:
            if v > ymax:
                b.append(f'<path d="M{x - 6:.1f},{y + 8:.1f} L{x:.1f},{y - 2:.1f} L{x + 6:.1f},{y + 8:.1f} Z" fill="{col}">'
                         f'<title>{name}，λ={l}：P95 {v} s（超出纵轴）</title></path>')
            else:
                b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{col}" stroke="#ffffff" stroke-width="2">'
                         f'<title>{name}，λ={l}：P95 {v} s</title></circle>')
        lx, ly = pts[-1][0], pts[-1][1]
        if name.startswith("每遍容量 1"):
            b.append(_t(lx + 10, y0 + 10, "▲ λ=0.35 时 53.7 s（超出纵轴）；λ ≥ 0.376 发散", 10.5, INK))
            b.append(_t(xpos(0.22), ypos(15), name, 11, INK, "end"))
        elif name == "每遍容量 2":
            b.append(_t(lx + 6, ly + 4, name, 11, INK))
        else:
            b.append(_t(lx - 2, ly + 18, name, 11, INK, "end"))
    return _svg(w, h, "".join(b), "遍数排队仿真的首 token P95")


# ---------------------------------------------------------------- 图 7 D14 错相位重叠
def fig_d14():
    w, h = 780, 250
    x0, sc = 150, 8.5     # 每 ms 8.5 px
    b = []
    b.append(_t(x0 - 10, 52, "串行（当前实现）", 11.5, INK, "end"))
    b.append(_rect(x0, 38, 19.4 * sc, 22, S2, rx=3, title="非传输部分 19.4 ms（B=2 批内）"))
    b.append(_t(x0 + 19.4 * sc / 2, 53, "计算 19.4 ms", 10.5, "#ffffff", "middle"))
    b.append(_rect(x0 + 19.4 * sc + 2, 38, 24.0 * sc, 22, S1, rx=3, title="两路未命中传输 24.0 ms"))
    b.append(_t(x0 + 19.4 * sc + 2 + 24 * sc / 2, 53, "未命中搬运 24.0 ms", 10.5, "#ffffff", "middle"))
    b.append(_t(x0 + 43.4 * sc + 8, 53, "43.4 ms → 每路 ≈ 23 tok/s", 11, INK))
    # 重叠
    b.append(_t(x0 - 10, 112, "错相位 · 路 A", 11.5, INK, "end"))
    b.append(_t(x0 - 10, 152, "错相位 · 路 B", 11.5, INK, "end"))
    for k in range(3):
        base = x0 + k * 24.0 * sc
        b.append(_rect(base, 98, 12.0 * sc - 2, 22, S1, rx=3, title="A 的未命中搬运（12.0 ms）"))
        b.append(_rect(base + 12.0 * sc, 98, 9.7 * sc, 22, S2, rx=3, title="A 的计算（≈ 9.7 ms）"))
        b.append(_rect(base + 12.0 * sc, 138, 12.0 * sc - 2, 22, S1, rx=3, title="B 的未命中搬运（12.0 ms）"))
        b.append(_rect(base, 138, 9.7 * sc, 22, S2, rx=3, title="B 的计算（≈ 9.7 ms）"))
    b.append(_t(x0 + 72 * sc / 2, 185, "理想步长 24.0 ms（两路共用固定开销）→ 每路 ≈ 41.6 tok/s；两路各自发射：28.2 ms → ≈ 35.5 tok/s", 11, INK, "middle"))
    b.append(_t(x0 + 72 * sc / 2, 203, "情景推算：系数为第 0 代拟合；未计气泡与争用；单路内「路由→搬运→计算」不能自我重叠", 10.5, MUTED, "middle"))
    ya = 222
    b.append(_line(x0, ya, x0 + 72 * sc, ya, MUTED, 1))
    for ms in range(0, 73, 12):
        b.append(_line(x0 + ms * sc, ya, x0 + ms * sc, ya + 4, MUTED, 1))
        b.append(_t(x0 + ms * sc, ya + 16, f"{ms} ms", 10, MUTED, "middle"))
    b.append(_rect(x0, 10, 12, 10, S1, rx=2) + _t(x0 + 16, 19, "PCIe 未命中搬运", 11, INK))
    b.append(_rect(x0 + 150, 10, 12, 10, S2, rx=2) + _t(x0 + 166, 19, "GPU 计算（非传输部分）", 11, INK))
    return _svg(w, h, "".join(b), "D14 错相位重叠解码")


# ---------------------------------------------------------------- 图 8 多 GPU 组级执行器
def fig_multigpu():
    w, h = 780, 380
    b = []
    # 左：三种运行区间
    b.append(_t(20, 22, "(a) 配置与运行区间（G0 容量估算，未经分配器核实）", 12, INK, "start", "bold"))
    cfgs = [("1 × TP4", "专家驻留 81–100%", "卸载区间基本消失 → 研究剩余瓶颈", S1),
            ("2 × TP2", "专家驻留 33–46%", "仍以卸载为主 → 遍数预算按组适用", S3),
            ("4 × TP1（共享主存池）", "专家驻留 4–14%", "四卡并发整池流 → 主存带宽成瓶颈", S2)]
    for i, (n, r, s, c) in enumerate(cfgs):
        y = 36 + i * 62
        b.append(_rect(20, y, 330, 52, "#ffffff", c, 5, sw=1.6))
        b.append(_t(34, y + 21, n, 12.5, INK, "start", "bold"))
        b.append(_t(220, y + 21, r, 11.5, INK))
        b.append(_t(34, y + 41, s, 11, MUTED))
    # 右：主存预算下的遍令牌调度
    b.append(_t(390, 22, "(b) 组级执行器：按主存预算发放「遍令牌」", 12, INK, "start", "bold"))
    x0, sc = 440, 36.0
    for g in range(4):
        b.append(_t(x0 - 8, 60 + g * 34, f"GPU{g}", 11, INK, "end"))
    sched = [(0, 0.0), (1, 0.0), (2, 2.92), (3, 2.92), (0, 5.84)]
    for g, t0 in sched:
        b.append(_rect(x0 + t0 * sc, 46 + g * 34, 2.92 * sc - 2, 20, S1, rx=3, title=f"GPU{g} 一遍整池流，起点 {t0} s，约 2.92 s"))
    b.append(_t(390, 200, "示例：k = 2 条整池流并行，每卡分得 B_M/2 ≈ 23.3 GB/s，每遍约 2.92 s；", 10.5, MUTED))
    b.append(_t(390, 215, "约束：Σ 并行流带宽 ≤ B_M（本机交错 STREAM 46.6 GB/s 仅作参考）", 10.5, MUTED))
    ya = 182
    b.append(_line(x0, ya, x0 + 8.8 * sc, ya, MUTED, 1))
    for s in range(0, 9, 2):
        b.append(_line(x0 + s * sc, ya, x0 + s * sc, ya + 4, MUTED, 1))
        b.append(_t(x0 + s * sc, ya - 4, f"{s} s", 9.5, MUTED, "middle"))
    # 下：公式框
    b.append(_rect(20, 236, 740, 128, SOFT, MUTED, 6))
    lines = [
        "字节守恒（TP-n，每片只取一次）：一遍的主存读字节仍为 P(1−h)，与 n 无关 ⇒ T_pass ≥ max( P(1−h) / (n·B_P),  P(1−h) / B_M )",
        "归并边界（诊断式，非预测式）：T_boundary ≈ max_r T_ready,r + T_comm,exposed —— 只优化非关键 rank 不会提前边界",
        "主存预算（组内所有卡共享）：Σ_i 预填流字节_i + Σ_i 解码未命中字节_i + NCCL 中转字节 ≤ ∫ B_M dt",
        "执行器动作：G1 遍令牌准入 · G2 关键 rank 的缺失传输优先 · G3 按 G0 选择配置 · G4 会话亲和（4×TP1） · G5 专家池 NUMA 就近放置",
        "证据等级：以上全部为方案与推导；多 GPU 无实测。B_M、拓扑、P2P/NCCL 路径须在目标节点测量。",
    ]
    for i, s in enumerate(lines):
        b.append(_t(34, 260 + i * 22, s, 11, INK if i < 4 else S2))
    return _svg(w, h, "".join(b), "多 GPU 组级协同执行方案")


# ---------------------------------------------------------------- 图 9 状态层逐层误差
def fig_state_layers():
    w, h = 720, 320
    x0, y0, pw, ph = 80, 30, 560, 220
    conv = [0.24, 0.52, 1.85, 1.14, 0.89, 1.05, 0.97, 1.05, 0.97, 1.68, 1.62, 1.55, 1.54, 1.65, 1.82, 2.34, 2.01, 1.85, 2.71,
            3.32, 4.26, 8.47, 16.78, 20.31, 22.86, 25.52, 28.17, 26.72, 14.9, 12.2, 12.79, 11.77, 14.59, 11.69, 10.89, 8.5]
    rec = [0.4, 1.12, 1.04, 0.79, 0.82, 0.84, 0.58, 0.96, 1.35, 1.11, 1.51, 2.74, 2.19, 2.8, 2.84, 2.98, 1.76, 0.94, 1.46, 2.56,
           3.96, 2.18, 6.04, 10.02, 8.64, 11.83, 12.51, 17.73, 7.88, 4.14, 6.05, 3.18, 14.23, 3.62, 8.21, 9.71]
    xpos = lambda i: x0 + i / 35 * pw
    ypos = lambda v: y0 + ph - v / 30 * ph
    b = []
    _axes(b, x0, y0, pw, ph, [0, 5, 10, 15, 20, 25, 30, 35], [0, 5, 10, 15, 20, 25, 30],
          lambda v: f"{v}", lambda v: f"{v}%", "GDN 层序号（共 36 层）", "相对 L2 误差 ‖A−B‖/‖B‖", xpos, ypos)
    for name, vals, col in (("conv_states", conv, S2), ("recurrent_states", rec, S1)):
        path = " ".join(("M" if i == 0 else "L") + f"{xpos(i):.1f},{ypos(v):.1f}" for i, v in enumerate(vals))
        b.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2"/>')
        for i, v in enumerate(vals):
            b.append(f'<circle cx="{xpos(i):.1f}" cy="{ypos(v):.1f}" r="7" fill="transparent">'
                     f'<title>{name}，第 {i} 层：{v}%</title></circle>')
    b.append(_t(xpos(26) + 6, ypos(28.17) - 4, "conv_states（峰值第 26 层 28.2%）", 11, INK))
    b.append(_t(xpos(28.4), ypos(19.5), "recurrent（峰值第 27 层 17.7%）", 11, INK))
    b.append(_t(xpos(0) + 6, ypos(4), "第 0 层：conv 0.24%，recurrent 0.40%", 10.5, MUTED))
    b.append(_rect(x0, 8, 14, 3, S2) + _t(x0 + 18, 14, "conv_states", 11, INK))
    b.append(_rect(x0 + 120, 8, 14, 3, S1) + _t(x0 + 138, 14, "recurrent_states", 11, INK))
    return _svg(w, h, "".join(b), "恢复路径对整段重算的逐层状态误差")


def fig_t06_segments():
    """Frozen D12 counts: requests versus actual MoE execution segments."""
    w, h, x0, y0, pw, ph = 760, 330, 66, 45, 650, 210
    labels = ["≤64", "65–128", "129–256", "257–512", "513–1024", "1025–2048", "2049–4096", "4097–8192", ">8192"]
    requests = [0, 1, 9, 6, 2, 6, 3, 2, 0]
    segments = [15, 11, 9, 4, 1, 7, 2, 2, 0]
    b = [_line(x0, y0 + ph, x0 + pw, y0 + ph), _line(x0, y0, x0, y0 + ph)]
    for i, label in enumerate(labels):
        x = x0 + i * (pw / 9) + 7; bw = 25
        for value, offset, color in ((requests[i], 0, S1), (segments[i], 28, S2)):
            bh = value * 10
            b.append(_rect(x + offset, y0 + ph - bh, bw, bh, color, title=str(value)))
            if value: b.append(_t(x + offset + bw / 2, y0 + ph - bh - 5, str(value), 10, INK, "middle"))
        b.append(_t(x + 28, y0 + ph + 17, label, 9, MUTED, "middle"))
    b += [_rect(x0, 17, 12, 12, S1), _t(x0 + 17, 27, "REQUEST suffix", 11, INK),
          _rect(x0 + 150, 17, 12, 12, S2), _t(x0 + 167, 27, "SEGMENT", 11, INK),
          _t(x0, h - 18, "≤256：35 个实际 MoE segments 对 10 个 requests；计数不预测 cache hit 或收益。", 11, MUTED)]
    return _svg(w, h, "".join(b), "T06 冻结的请求后缀与实际 MoE 段计数")


def fig_k1_repair():
    w, h = 760, 205
    b = [_t(42, 30, "BEFORE K1 FIX", 12, S2, weight="bold"), _t(420, 30, "K1 repaired path", 12, S1, weight="bold"),
         _rect(42, 50, 286, 39, "#fdeee6", S2, 4), _t(185, 75, "donor pingpong plan recreated", 12, INK, "middle"),
         _rect(42, 112, 286, 39, "#fdeee6", S2, 4), _t(185, 137, "cached_len origin lost → fresh branch", 12, INK, "middle"),
         _line(340, 101, 403, 101, S1, 2, marker="url(#arrow)"),
         _rect(420, 75, 284, 52, "#e8f0fb", S1, 4), _t(562, 98, "R038: 28/28 same-structure", 12, INK, "middle", "bold"),
         _t(562, 116, "cold reference: four states, token, text", 11, INK, "middle")]
    return _svg(w, h, _arrow_defs(S1) + "".join(b), "K1 修复与 R038 同结构验证边界")


ALL = {
    "arch": fig_architecture,
    "pass": fig_pass_principle,
    "agent": fig_agent_tiers,
    "fourcell": fig_four_cell,
    "budget": fig_pcie_budget,
    "queue": fig_queue,
    "d14": fig_d14,
    "multigpu": fig_multigpu,
    "state": fig_state_layers,
}

V5 = {**ALL, "t06segments": fig_t06_segments, "k1repair": fig_k1_repair}

