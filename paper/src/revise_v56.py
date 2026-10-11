"""v5.6 revision: body_v55.html -> body_v56.html.

Corrects the v5.5 "same window" wording for the retry2 hybrid comparison, adds the 2026-10-11 window02 same-window
A/B (incl. hybrid self-reproducibility J4 and the offload 87K OOM), rewrites §8.4 with the per-layer step structure
from plan/HYBRID_ALGORITHM_RESEARCH_20261011.md, and adds the fetch-split rule to §4.4. Each replacement must match once.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, DST = HERE / "body_v55.html", HERE / "body_v56.html"

S84_START = '<p><b>分解（推算）。</b>Strata 各请求的速度随命中率变化'
S84_END = '重算见 <code>paper/src/theory_v55.py</code>。</p>'

S84_NEW = (
    "<p><b>一步的结构（v5.6 更正）。</b>单路解码时，第 $l$ 层的 CPU 专家计算只能与同一层 GPU 上的 MoE 计算并行，不能与注意力等串行部分并行：FreeToken 每层「提交 CPU → 取数 → GPU 计算 → 等待 CPU → 相加」在同一条流上（<code>layers/moe.py:328-383</code>），Strata 源码注释也写明其 CPU 工作约 96% 暴露（<code>expert_cache.hpp</code>）。因此一步耗时应写成\n"
    "$$t_{step}\\approx S_{GPU}+\\sum_{l}\\max\\big(G_l+f_l\\,t_P,\\ O_C+(n_l-f_l)\\,t_C\\big),$$\n"
    "其中 $S_{GPU}$ 为 GPU 串行部分，$G_l$ 为同层 GPU 的命中计算，$n_l$、$f_l$ 为本层未命中数与经 PCIe 取到 GPU 的个数，$t_P$、$t_C$ 为每个专家经 PCIe、在 CPU 上的时间，$O_C$ 为每层 CPU 路径的固定开销。v5.5 用 $\\max(F,\\,C)$ 把 CPU 计算当成能与整步并行，偏乐观，本版更正。</p>\n"
    "<p><b>分解（推算）。</b>用 retry2 的 hybrid 单路与两路实测标定上式（<code>plan/HYBRID_ALGORITHM_RESEARCH_20261011.md</code>）：FreeToken hybrid 每层 CPU 路径的固定开销约 0.19–0.26 ms（每步 9–12.5 ms），每个 CPU 专家的边际代价约 0.04–0.07 ms；以 R048b S 臂作样本外检查，推算 33.5、实测 31.94。Strata 每个 CPU 专家的边际代价按同一日志的不同子集拟合为 0.036–0.071 ms，样本少、斜率不稳。据此：</p>\n"
    "<ol>\n"
    "  <li><b>每层固定开销（FreeToken 的主因）。</b>FreeToken 的 CPU 线程池每次派任务都以条件变量唤醒工作线程、再以条件变量等待完成（<code>cpu_moe_ext.cpp</code> 约 1870–1968 行），每层两次睡眠与唤醒；Strata 的工作线程在有流量时自旋。按上式，把固定开销压到约 0.05 ms，单路约 44–50 tok/s、两路每路约 27–32 tok/s（推算）。</li>\n"
    "  <li><b>GPU 串行部分。</b>FreeToken 的固定步长约 13.1 ms；要接近 Strata S1 的约 16 ms/步，还需把 GPU 串行部分削减约 4 ms（注意力、GDN 等内核与 KV 格式，未逐项分解）。</li>\n"
    "  <li><b>单专家带宽与量化（次要）。</b>FreeToken 的 CPU 内核本身带宽不差（本机 benchbw：单独 47.62 GB/s，与 PCIe 并发时 40.85 GB/s）；IQ3_S 单专家少 26.5% 字节，在 PCIe 结构下只换字节约 +15%。</li>\n"
    "</ol>\n"
    "<p><b>结论。</b>v5.5 把差距主因归为「执行结构」、次因为「每专家 CPU 效率」，并估计改结构后可达 55–65 tok/s。按更正后的一步结构，FreeToken hybrid 与 Strata 是同一类结构，差距主要在每层固定开销与 GPU 串行部分，可达值约 44–50 tok/s，再往上取决于 GPU 串行部分。另外，S1 是 Strata 的可复现配置（<code>--pcie-frac 0</code>、自适应冻结），其文档写明这一设置会降低解码速度，默认配置会把一部分未命中经 PCIe 取到 GPU；所以「约 1.8 倍」是相对其可复现配置而言。本文的冷预填快于 Strata（6.07–6.60 s 对 8.0–8.4 s）。MTP 是另一独立因素。以上均为推算，要证实，需要对 hybrid 做逐层时间戳与计数（<code>--moe-collect-stats</code>）。重算见 <code>paper/src/theory_v55.py</code> 与上述研究报告。</p>"
)

S77_START = '<p><b>同窗口复测（v5.5，D08 retry2，2026-10-11 凌晨）。</b>'
S77_END = '2026-10-11 的复验正在进行。</p>'

S77_NEW = (
    "<p><b>跨窗口参照（D08 retry2，2026-10-11 凌晨）。</b>retry2 窗口只起了 hybrid 服务：单路 33.83、两路每路 25.33 / 25.48 tok/s（同一组 X 提示，约 1.2K 输入、256 token），与此前测得的 offload 参照（单路 30.17，retry1；两路 16.95 / 17.01，10-10 夜闭环 X 组；均在 ollama 停止之后）相比，分别 +12% 与 +49%。原报告写明这是历史参照比较，不是同窗口的因果隔离〔development/d08_d10_gpu_retry2_20261011 窗口01，新增于 FTD-20261009-1 之后〕。v5.5 把它写成「同窗口」，有误，本版更正。</p>\n"
    "<p><b>同窗口 A/B（2026-10-11 午间，window02）。</b>同一窗口依次起 O1（offload）→ H1（hybrid）→ H2（hybrid，新起服务、不预热）→ O2（offload），同候选 481d3a7；hybrid 只改 <code>--moe-strategy hybrid</code> 与绑核前缀，取数比例为自动档 27.7%；除 H2 外，每个服务先做两次不计成绩的 SDK 预热。结果：单路 X，hybrid 35.55 / 36.59 对 offload 29.62–30.19（+21%）；两路每路，hybrid 25.96–26.27 对 offload 16.81–16.98（+55%）；前后两个 offload 服务的两路均值漂移 0.20%（预注册 ≤5%，成立）。新起不预热的 H2 单路为 30.81。87K 真实会话（LC1）：hybrid 两次分别输出 93 / 101 token 后正常停止，速度 26.96 / 28.52 tok/s（短于 128 token，按预注册不计入判定）；offload 的两个服务在先跑过 X 单路与两路之后，该请求都触发 CUDA OOM（申请 48 MiB 时仅剩 21.69 MiB），OOM 恢复机制重启 worker、API 未退出，因此没有 offload 长上下文读数（§12）。quality60：H1 为 49/60（通过 49、截断 9、答错 2）；O1 因上述 OOM 中止、未跑 quality60，同窗口质量对照缺失（历史 offload 参照 47/60，T20，跨窗口）〔runs/dev_hybrid_verify_20261011/window02，新增于 FTD-20261009-1 之后〕。</p>\n"
    "<p><b>数值边界。</b>hybrid 属精确计算，不丢弃或近似任何专家，但输出不逐位一致：retry2 中与 offload 在全文第 872 个字符（单路）、第 871 / 806 个字符（两路）起分叉；window02 中，<b>同一 hybrid 服务内重复同一请求</b>也在第 454 个字符起分叉，两路重复在第 599 / 149 个字符起分叉，新起服务与已预热服务在第 600 个字符起分叉（预注册 J4：affected）。offload 在热服务、新服务、单路重复上都逐字相同。推断：同一专家命中时由 GPU 计算、未命中时由 CPU 计算，两者舍入不同，而命中与否取决于缓存的历史状态，所以 hybrid 的输出随服务历史变化。按预注册读法，hybrid 只能作为可选的性能模式，是否进入发布路径由用户裁定。</p>"
)

EDITS = [
    ("预印本草稿 · v5.5 · 2026-10-11", "预印本草稿 · v5.6 · 2026-10-11"),
    ("这一上界只约束经 PCIe 搬运的未命中：同一窗口内，hybrid 让大部分未命中专家在 CPU 上原地计算，两路实测每路 25.33–25.48 tok/s，高于 offload 的 16.95–17.01（+49%）及其链路上界 23.9；单路 33.83 对 30.17（+12%）（§7.7）。",
     "这一上界只约束经 PCIe 搬运的未命中：hybrid 让大部分未命中专家在 CPU 上原地计算，同窗口 A/B（2026-10-11）中两路每路 25.96–26.27 tok/s，offload 为 16.81–16.98（+55%），高于 offload 的链路上界 23.9；单路 35.55–36.59 对 29.62–30.19（+21%）；但 hybrid 在同一服务内重复同一请求，输出也不逐位一致（§7.7）。"),
    ("与 Strata 同输入约 1.8 倍的解码差距，主要来自执行结构与 CPU 执行器效率，量化次要（§8.4，推算）。",
     "与 Strata 可复现配置同输入约 1.8 倍的解码差距，按推算主要来自 FreeToken hybrid 每层 CPU 路径的固定开销与更大的 GPU 串行部分，单专家带宽与量化次要（§8.4）。"),
    ("本版在同一窗口内测得正收益，但输出与 offload 不逐位一致（CPU/GPU 舍入不同，§7.7）。",
     "同窗口 A/B 测得正收益（单路 +21%、两路每路 +55%），但输出不逐位一致：既与 offload 不同，同一服务内重复请求也不同，即受缓存状态影响（§7.7）。"),
    ("In the same window, the hybrid executor (misses computed on the CPU) reaches 25.33–25.48 tok/s per lane for two distinct streams versus 16.95–17.01 offload, above the offload link bound of 23.9, but its output is not bit-identical to offload.",
     "In a same-window A/B, the hybrid executor (most misses computed on the CPU) reaches 25.96–26.27 tok/s per lane for two distinct streams versus 16.81–16.98 offload (+55%), above the offload link bound of 23.9, and 35.55–36.59 versus 29.62–30.19 single-stream (+21%); its output is neither bit-identical to offload nor reproducible across repeated requests in the same service."),
    ("hybrid 执行器：旧负结果与同窗口复测正结果（单路 +12%、两路每路 +49%，§7.7）",
     "hybrid 执行器：旧负结果、跨窗口参照与同窗口 A/B 正结果（单路 +21%、两路每路 +55%），以及输出不可逐位复现（§7.7）"),
    ("按执行结构、CPU 执行器效率与量化三项的分解见 §8.4，属推算", "差距分解见 §8.4，属推算"),
    ("hybrid 两路实测 25.33–25.48 高于 $\\phi=0$ 的 23.9", "hybrid 两路同窗口实测 25.96–26.27 高于 $\\phi=0$ 的 23.9"),
    ('<h3>7.7 hybrid：旧负结果与同窗口复测 <span class="ev m">实测</span></h3>',
     '<h3>7.7 hybrid：旧负结果、跨窗口参照与同窗口 A/B <span class="ev m">实测</span></h3>'),
    ("按发布配置失误率重算的值见 §4.7。</li>\n</ol>",
     "按发布配置失误率重算的值见 §4.7。</li>\n</ol>\n"
     "<p><b>取数拆分规则（v5.6）。</b>上游 [1] 令经 PCIe 取数与 CPU 原地计算的用时相等，得 $q^{*}\\approx m\\,B_P/B_H$，并要求每层每步至少取 1 个专家，使缓存持续预热；发布代码改用并发带宽比 $r=B_P^{ov}/(B_P^{ov}+B_C^{ov})$（本机自动档 27.7%），每层未命中 ≤2 时可取 0 个；<code>benchbw.py</code> 中「CPU 带宽 &gt; 2 × PCIe 带宽才选 hybrid」的阈值只在代码中，不在 [1]，本机比值 1.962 因而判为 offload，与 §7.7 的实测相反。计入每层 CPU 路径固定开销 $O_C$ 与同层 GPU 计算 $G$ 后，使该层耗时最小的取数个数为 $$f^{*}=\\mathrm{clip}\\Big(\\frac{O_C-G+n\\,t_C}{t_P+t_C},\\,0,\\,n\\Big),$$ 取 $O_C=G=0$、$t_C=S/(B_H-B_P)$ 时即为 [1] 的 $q^{*}$；该层 hybrid 优于 offload 的条件为 $O_C<G+n\\,t_P$（推导；$O_C$、$G$ 待逐层计数标定，§8.4）。</p>"),
    ("<tr><td>单路 / 两路每路 1.2K，hybrid（retry2）</td><td>—（大部分未命中走 CPU）</td><td>未建模</td><td>33.83 / 25.33–25.48</td><td>—</td><td>两路高于 offload 链路上界 23.9（§7.7）</td></tr>",
     "<tr><td>单路 / 两路每路 1.2K，offload（window02 同窗口）</td><td>35.08% / 38.24%（同提示 D0）</td><td>30.9 / 16.6</td><td>29.62–30.19 / 16.81–16.98</td><td>95.8–97.7% / 101.4–102.4%</td><td>达到</td></tr>"
     "<tr><td>单路 / 两路每路 1.2K，hybrid（window02 同窗口）</td><td>—（大部分未命中走 CPU）</td><td>见 §8.4 一步结构</td><td>35.55–36.59 / 25.96–26.27</td><td>—</td><td>两路高于 offload 链路上界 23.9（§7.7）</td></tr>"),
    ("hybrid 单路 33.83（§7.7、§8.3）", "hybrid 单路同窗口 35.55–36.59（§7.7）"),
    ("hybrid 同窗口 25.33–25.48（§7.7）", "hybrid 同窗口 25.96–26.27（§7.7）"),
    ("<li><b>hybrid</b> <span class=\"ev m\">实测</span>：同窗口单路 +12%、两路每路 +49%，两路超过 offload 的链路上界；输出与 offload 不逐位一致，复验进行中（§7.7）。与 Strata 约 1.8 倍的差距主要来自执行结构与 CPU 执行器效率，量化次要（§8.4，推算）。</li>",
     "<li><b>hybrid</b> <span class=\"ev m\">实测</span>：同窗口 A/B 单路 +21%、两路每路 +55%，两路超过 offload 的链路上界；输出不逐位一致，同一服务内重复请求也不一致（J4 affected），按预注册只能作为可选性能模式，是否进入发布路径待用户裁定（§7.7）。与 Strata 可复现配置约 1.8 倍的差距，按推算主要来自每层 CPU 路径的固定开销与更大的 GPU 串行部分（§8.4）。</li>"),
    ("（GPU 搬到 GPU，与其余计算串行</td>", "（GPU 搬到 GPU，与其余计算串行</td>"),
    ("<td>CPU 在主存原地计算，与 GPU 并行（<code>--pcie-frac 0</code>）</td>",
     "<td>CPU 在主存原地计算，与同层 GPU 计算并行（<code>--pcie-frac 0</code>，可复现配置；默认配置把一部分未命中经 PCIe 取到 GPU）</td>"),
    ("<li><b>hybrid 数值。</b>hybrid 与 offload 输出不逐位一致（§7.7）；若 hybrid 进入发布路径，§9 的逐位等价门须改为对 hybrid 自身的可复现性门。</li>",
     "<li><b>hybrid 数值。</b>hybrid 与 offload 输出不逐位一致，同一服务内重复请求也不一致（§7.7，J4 affected）；若 hybrid 进入发布路径，§9 的逐位等价门不适用，需另定质量与可复现性的验收口径。</li>\n"
     "  <li><b>offload 长上下文 OOM。</b>window02 中，发布配置的 offload 服务在先跑过 X 单路与两路之后，87K 真实会话请求在两个服务上都触发 CUDA OOM（申请 48 MiB 时仅剩 21.69 MiB），由 OOM 恢复机制重启 worker；同一请求在新起服务上重放（窗口 A/B W98K）时未出现。触发条件与根因未查明，属于生产配置在目标负载上的风险。</li>"),
    ("（v5.5 同窗口复测见 §7.7）", "（v5.6：跨窗口参照与同窗口 A/B 见 §7.7）"),
    ("<h2>附录 C　版本变更说明（v4 → v5.5）</h2>", "<h2>附录 C　版本变更说明（v4 → v5.6）</h2>"),
]

APPENDIX_V56 = (
    "<p><b>v5.6（2026-10-11 午后）。</b>（1）更正 v5.5 的事实错误：retry2 的 hybrid 对 offload 是跨窗口的历史参照比较（原报告原文），v5.5 写成「同窗口」，摘要、表 1、§4.7、表 12、§7.7、§8.3、§11 均改；（2）写入 2026-10-11 window02 的真正同窗口 A/B：单路 +21%、两路每路 +55%，offload 两服务漂移 0.20%，hybrid 同服务重复不逐位一致（J4 affected），quality60 H1 49/60、O1 缺失，offload 87K OOM ×2（§7.7、§8.3、§12）；（3）§8.4 按算法研究报告更正一步结构，把差距主因从「执行结构 / 每专家效率」改为「每层 CPU 固定开销 + GPU 串行部分」，可达值由 55–65 改为 44–50 tok/s，并注明 S1 为 Strata 可复现配置；（4）§4.4 新增取数拆分规则与最优拆分 $f^{*}$，区分 [1]、代码与本文。改写脚本 <code>paper/src/revise_v56.py</code>。</p>\n"
)


def main():
    text = SRC.read_text(encoding="utf-8")
    for start, end, new in ((S77_START, S77_END, S77_NEW), (S84_START, S84_END, S84_NEW)):
        i, j = text.find(start), text.find(end)
        if i < 0 or j < 0 or j < i or text.count(start) != 1:
            raise SystemExit(f"block anchors not found once: {start[:40]!r}")
        text = text[:i] + new + text[j + len(end):]
    for old, new in EDITS:
        if old == new:
            continue
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected exactly one match, got {count}: {old[:80]!r}")
        text = text.replace(old, new)
    head, sep, tail = text.rpartition("</section>")
    if "附录 C　版本变更说明（v4 → v5.6）" not in head[-9000:]:
        raise SystemExit("appendix C is not the last section")
    DST.write_text(head + APPENDIX_V56 + sep + tail, encoding="utf-8", newline="\n")
    print(f"wrote {DST.name}")


if __name__ == "__main__":
    main()
