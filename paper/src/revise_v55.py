"""One-shot v5.5 text revision: body_v54.html -> body_v55.html (exact replacements, each asserted once)."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, DST = HERE / "body_v54.html", HERE / "body_v55.html"

EDITS = [
    # title block
    ("预印本草稿 · v5.4 · 2026-10-10 · 数据版本 FTD-20261009-1 ＋ 附录 A.5 的 2026-10-10 轮次",
     "预印本草稿 · v5.5 · 2026-10-11 · 数据版本 FTD-20261009-1 ＋ 附录 A.5 的 2026-10-10/11 轮次"),
    # abstract: L*
    ("<li>在当前失误率下，一遍预填的链路时间约等于 233 个解码 token 的未命中搬运（$L^{*}=E/(k\\,m)$）。</li>",
     "<li>一遍预填的链路时间约等于 $L^{*}=E/(k\\,m)$ 个解码 token 的未命中搬运。$L^{*}$ 与失误率成反比：第 0 代标定（$m=21.93\\%$）为 233，真实 agent 内容（$m\\approx38.6\\%$）约 133（§4.4）。</li>"),
    # abstract: content-specific miss rate
    ("以发布配置实测失误率 24.13% 计，单路 32K 理论值约 36.6 tok/s。",
     "失误率随内容变化：32K 合成重复文本上为 24–25%，真实 agent 内容为 35–39%；按同内容实测失误率，单路理论值分别约 36.6 与 27–31 tok/s，串行模型在真实内容上为实测的 97.6–104.1%（§4.7、§8.3）。"),
    ("每路 30 在两路不同内容下不可达，除非每路失误率降到 30.4% 以下。8 路每路上界约 9.5。",
     "每路 30 在两路不同内容下不可达，除非每路失误率降到 30.4% 以下。这一上界只约束经 PCIe 搬运的未命中：同一窗口内，hybrid 让大部分未命中专家在 CPU 上原地计算，两路实测每路 25.33–25.48 tok/s，高于 offload 的 16.95–17.01（+49%）及其链路上界 23.9；单路 33.83 对 30.17（+12%）（§7.7）。8 路每路上界约 9.5。"),
    ("按 95% 判据只有一组单路 32K（93.9%）略低，87K 为 88%，未达到（§8.3）。</li>",
     "按 95% 判据只有一组单路 32K（93.9%）略低；v5.4 判 87K「未达到（88%）」是代入了合成文本的失误率所致，改用同内容实测失误率（38.59%）后，87–95K 真实会话为理论值的 104.1%（§8.3）。与 Strata 同输入约 1.8 倍的解码差距，主要来自执行结构与 CPU 执行器效率，量化次要（§8.4，推算）。</li>"),
    ("M5（短后缀按需搬运）默认关闭门已过，启用路径因前置轮次未通过而冻结（§11）。</p>",
     "M5（短后缀按需搬运）默认关闭门已过，启用路径因前置轮次未通过而冻结（§11）。hybrid 不属于 M1–M6，它是继承自 FreeToken 的执行器：本版在同一窗口内测得正收益，但输出与 offload 不逐位一致（CPU/GPU 舍入不同，§7.7）。</p>"),
    # English abstract
    ("At the measured release miss rate (24.13%), the single-stream 32K value is about 36.6 tok/s.",
     "The miss rate depends on content: 24–25% on a synthetic repeated 32K text and 35–39% on real agent content, giving single-stream values of about 36.6 and 27–31 tok/s; with content-matched miss rates the serial model is within 97.6–104.1% of measurements on real content."),
    ("by the 95% criterion only one 32K run (93.9%) falls slightly short, and 87K reaches 88%.",
     "by the 95% criterion only one 32K run (93.9%) falls slightly short; the v5.4 87K shortfall (88%) came from a miss rate measured on synthetic text, and with the content-matched rate (38.59%) the 87–95K replay reaches 104.1%. In the same window, the hybrid executor (misses computed on the CPU) reaches 25.33–25.48 tok/s per lane for two distinct streams versus 16.95–17.01 offload, above the offload link bound of 23.9, but its output is not bit-identical to offload."),
    # Table 1, C5
    ("当前 FreeToken hybrid 执行器的负结果；Strata v0.1.41 同构 S1/S2/S3/S4 测量子集（同构建不开 MTP 的 S1 与本文发布配置单路在 32K 负载上相差约 1.8 倍，量化/执行路径未隔离，非因果比较）",
     "hybrid 执行器：旧负结果与同窗口复测正结果（单路 +12%、两路每路 +49%，§7.7）；Strata v0.1.41 同构 S1/S2/S3/S4 测量子集（同构建不开 MTP 的 S1 与本文发布配置单路在 32K 合成输入上相差约 1.8 倍，按执行结构、CPU 执行器效率与量化三项的分解见 §8.4，属推算）"),
    # §4.4 L*
    ("一轮输出超过约 233 个 token 时，这一轮解码搬运所耗的链路时间，就超过它的一遍预填（图 3）。",
     "一轮输出超过约 233 个 token 时，这一轮解码搬运所耗的链路时间，就超过它的一遍预填（图 3）。$L^{*}$ 与 $m$ 成反比：真实 agent 内容（R046g seed_real D0 实测 $m=38.59\\%$）时约为 $512/(10\\times0.3859)\\approx133$；233 只对第 0 代标定的失误率成立（重算见 <code>paper/src/theory_v55.py</code>）。"),
    # §4.7 R_link
    ("<li>$R_{link}$ 是链路上界，只取决于失误率；任何执行结构都不能超过它（下表取 $u=0$）。</li>",
     "<li>$R_{link}$ 是链路上界，只取决于失误率与经链路的未命中比例。对所有经 PCIe 搬运未命中的结构（offload、M4），任何执行方式都不能超过它（下表取 $u=0$、$\\phi=0$）。若一部分未命中在 CPU 上原地计算（比例 $\\phi$，§4.4），上界变为 $R_{link}/(1-\\phi)$；hybrid 两路实测 25.33–25.48 高于 $\\phi=0$ 的 23.9，与此一致（§7.7）。</li>"),
    ("<li>单路：发布配置理论值 36.6 tok/s，高于 30。</li>",
     "<li>单路：发布配置理论值 36.6 tok/s，高于 30；这是 32K 合成文本的失误率，真实内容约 27–31，与 30 相当（见下段）。</li>"),
    ("<p>因此，本文改为看一个实现是否达到其执行结构的理论值。",
     "<p><b>失误率随内容变化（v5.5）。</b>同一模型、同一槽数下，失误率从合成重复文本的约 25% 到真实 agent 会话的约 39%，理论值必须代入同内容实测的 $m$。代入后，串行模型在真实内容上为实测的 97.6–104.1%（表 5b，重算见 <code>paper/src/theory_v55.py</code>）。因此单路 32K 理论值 36.6 只代表重复文本，真实 agent 负载的单路理论值约 27–31 tok/s；b163、R048b 与 Strata S1–S4 的 32K 数字都在同一份合成输入上测得（§12）。</p>\n"
     "<table class=\"booktabs small\"><caption>表 5b　按内容取失误率的单路理论值与实测（tok/s）</caption><thead><tr><th>负载</th><th>内容</th><th>槽数</th><th>$m$（来源）</th><th>$R_{serial}$</th><th>实测</th><th>实测 / 理论</th></tr></thead><tbody>"
     "<tr><td>单路 32K（b163）</td><td>合成：约 100 字一段重复数百遍</td><td>2,700</td><td>25.27%（同轮 D0）</td><td>35.8</td><td>35.42 / 35.64</td><td>99.1% / 99.7%</td></tr>"
     "<tr><td>单路 1.2K（retry2 offload）</td><td>X 组第 0 条，模板生成的长提示</td><td>2,700</td><td>35.08%（同窗口 D0）</td><td>30.9</td><td>30.17</td><td>97.6%</td></tr>"
     "<tr><td>单路 87–95K（窗口 A/B W98K）</td><td>seed_real 真实 agent 会话 8 轮重放</td><td>2,700</td><td>38.59%（R046g D0，54,000 次层调用）</td><td>26.9</td><td>28.045</td><td>104.1%</td></tr>"
     "<tr><td>单路 87–95K（W128K）</td><td>同上</td><td>2,400</td><td>41.38%（同内容回放）</td><td>25.9</td><td>26.867</td><td>103.9%</td></tr>"
     "</tbody></table>\n"
     "<p>因此，本文改为看一个实现是否达到其执行结构的理论值。"),
    # §5.2 M3
    ("<p><b>M3 的取舍</b>　干扰期要让其他会话每秒前进 $r$ 个解码步、每步约 26 ms。在固定步长、整步串行插入的情景下，预填时间放大为\n$$T'_{prefill}\\approx\\frac{T_{prefill}}{1-r\\,t_{step}}.$$\n$r$ = 1、10、30 时，放大倍数分别为 1.03、1.35、4.55。所以「停顿 ≤ 1 s、预填只多约 0.2 s」只在其他会话几乎停住时成立。这个式子是情景估计：冷长预填时 PCIe 约有 55% 空闲，可能使实际放大更小；切换成本可能使它更大。</p>",
     "<p><b>M3 的取舍（v5.5 修正）</b>　干扰期要让其他会话每秒前进 $r$ 个解码步。插入一步对预填的边际代价 $c$ 只计被占满的那份资源：短后缀遍受搬运限制、GPU 大部分时间空闲，插入步的计算可藏在等待中，$c\\approx X\\approx21$ ms（真实内容 $m\\approx38.6\\%$）；冷长预填受计算限制、PCIe 大部分时间空闲，插入步的搬运可藏在空闲链路中，$c\\approx t_0\\approx13$ ms。预填时间放大为\n$$T'_{prefill}\\approx\\frac{T_{prefill}}{1-r\\,c}.$$\n$r=10$ 时短后缀遍放大 1.27 倍、冷遍 1.15 倍；v5.4 按整步 26 ms 计为 1.35 倍，偏悲观。以停顿为目标：一遍约 2.8 s 的短后缀遍插入 5 步，即可把其他会话的最长停顿压到 0.5 s 以下，预填多约 0.11 s（+3.8%）；冷 87K 遍（约 18 s）插入 36 步达到同一停顿，预填多约 0.47 s（+2.6%）。吞吐方面，每个插入的 token 只省下 $t_{step}-c$（短后缀遍 8.6–13.1 ms、冷遍 16.3–20.8 ms）；限定被插入一方的首 token 最多慢 10%，按 seed_real 轨迹（1 个冷遍、7 个短后缀遍）推算吞吐上限约 +5.6%，以短后缀遍为主的长会话约 +1.6–2.4%。所以 M3 是停顿公平性机制，不是提速机制。以上均为推算，未计切换开销、缓存分区引起的失误率上升与整步 CUDA Graph 约束（<code>plan/D11_DECISION_20261011.md</code>）。</p>"),
    # §7.7
    ("<h3>7.7 负结果：hybrid（当前 CPU 执行器）<span class=\"ev m\">实测</span></h3>",
     "<h3>7.7 hybrid：旧负结果与同窗口复测 <span class=\"ev m\">实测</span></h3>\n"
     "<p><b>同窗口复测（v5.5，D08 retry2，2026-10-11 凌晨）。</b>在 ollama 停止之后，同一窗口内依次起 offload 与 hybrid 服务（同候选 481d3a7；hybrid 只改 <code>--moe-strategy hybrid</code> 与绑核前缀 <code>numactl --interleave=all taskset -c 1,3-23,25,27-47</code>），用同一组 X 提示（约 1.2K 输入、256 token）测得：单路 hybrid 33.83 对 offload 30.17 tok/s（+12%）；两路每路 25.33 / 25.48 对 16.95 / 17.01 tok/s（+49% / +50%），预注册 H1 成立〔development/d08_d10_gpu_retry2_20261011 窗口01，新增于 FTD-20261009-1 之后〕。两路 hybrid 高于 offload 两路的链路上界 23.9，是因为大部分未命中专家改在 CPU 上计算、不经 PCIe（§4.4 的 $\\phi$）。<b>数值边界：</b>hybrid 属精确计算，不丢弃或近似任何专家，但与 offload 输出不逐位一致：单路在全文第 872 个字符、两路在第 871 / 806 个字符起分叉，源于 CPU 与 GPU 的舍入差异；作为对照，offload 自身由单路改两路时在第 454 个字符即分叉（批效应，§10.3）。因此 hybrid 的验收门改为自身可复现、质量不低于 offload 减 3 题（quality60）与本条披露；2026-10-11 的复验正在进行。</p>\n"
     "<p><b>旧负结果的成因。</b>下文 R048b 的 V0/A/B/S 臂与「另一配置」的 offload 36.61（32K 合成文本，失误率约 25%）比较，不是同窗口、同负载的对照；V0 臂还受 ollama 抢核影响。下文保留为该配置下的历史测量。</p>"),
    ("两路时链路是硬约束，而 hybrid 是唯一让失误专家不经链路的机制，其两路价值尚未测量。</li>",
     "两路时链路是硬约束，而 hybrid 是唯一让失误专家不经链路的机制（v5.5：两路价值已测，见本节首段）。</li>"),
    # §8.1 trailing sentence
    ("§7.7 的 hybrid 负结果只适用于当前 FreeToken 执行器；下面的 Strata 无 MTP 子集不外推为「hybrid 在本机不可行」。",
     "§7.7 的旧 hybrid 负结果只适用于当时的执行器与配置（v5.5 同窗口复测见 §7.7）；Strata 无 MTP 子集见 §8.2，差距分解见 §8.4。"),
    # Table 12
    ("<caption>表 12　体验线与模型给出的界（v5.4：两路界按内容是否相同分行）</caption>",
     "<caption>表 12　体验线与模型给出的界（v5.5：解码按内容分行，加入 hybrid）</caption>"),
    ("<tr><td>其他会话停顿</td><td>第 1 代未测；第 0 代 16.69 s</td><td>约等于预填时长</td><td>M3 / G2</td></tr>",
     "<tr><td>其他会话停顿</td><td>第 1 代未测（D11-P0 测量待执行）；第 0 代 16.69 s</td><td>约等于预填时长：短后缀遍约 2.8 s、冷 87K 约 18 s（推算）</td><td>M3 / G2</td></tr>"),
    ("<td>发布配置 32K：同配置 35.42–35.64，扩展窗口实验 34.33；64K 35.645；87K 30.3（§8.3）</td><td>$R_{serial}$ 36.6（32K）；无未命中时约 71</td>",
     "<td>32K 合成文本：同配置 35.42–35.64，扩展窗口实验 34.33；64K 35.645。真实内容：1.2K 30.17，87–95K 28.05（W98K）。hybrid 单路 33.83（§7.7、§8.3）</td><td>$R_{serial}$：32K 合成文本 36.6，真实内容 27–31；无未命中时约 71</td>"),
    ("不同内容闭环实测（X 组，约 1.2K 输入）16.95–17.01，为模型预测的 102–103%</td>",
     "不同内容闭环实测（X 组，约 1.2K 输入）16.95–17.01，为模型预测的 102–103%；hybrid 同窗口 25.33–25.48（§7.7）</td>"),
    ("CPU 补带宽只在单路测过且为负，两路未测（§7.7）；首个 M4 原型判实现无效、机制未检验（§8.1）</td>",
     "上界只约束经链路的未命中，hybrid 两路已超过 offload 链路上界（§7.7）；首个 M4 原型判实现无效、机制未检验（§8.1）</td>"),
    # §8.3 table rows
    ("<tr><td>单路 87K（扩展窗口实验，any-delta）</td><td>24.13%（取 b163 稳态）</td><td>34.4</td><td>30.3</td><td>88.2%</td><td>未达到</td></tr>",
     "<tr><td>单路 87K（扩展窗口实验，any-delta）</td><td>24.13%（取 b163 稳态，内容不符）</td><td>34.4</td><td>30.3</td><td>88.2%</td><td>v5.4 判未达到；v5.5 改用同内容 $m$，见下两行</td></tr>"
     "<tr><td>单路 87–95K，seed_real 8 轮重放（窗口 A/B W98K）</td><td>38.59%（同内容 R046g D0，2,700 槽）</td><td>26.9</td><td>28.045</td><td>104.1%</td><td>达到</td></tr>"
     "<tr><td>同上（W128K，2,400 槽）</td><td>41.38%（同内容回放）</td><td>25.9</td><td>26.867</td><td>103.9%</td><td>达到</td></tr>"
     "<tr><td>单路 1.2K，X 组第 0 条（retry2 offload）</td><td>35.08%（同窗口 D0）</td><td>30.9</td><td>30.17</td><td>97.6%</td><td>达到</td></tr>"
     "<tr><td>单路 / 两路每路 1.2K，hybrid（retry2）</td><td>—（大部分未命中走 CPU）</td><td>未建模</td><td>33.83 / 25.33–25.48</td><td>—</td><td>两路高于 offload 链路上界 23.9（§7.7）</td></tr>"),
    ("<li><b>单路达到理论值。</b>同轮同配置的 b163 三组为理论值的 95–100%，扩展窗口实验的 64K 为 101%。扩展窗口实验的 32K 为 93.9%，略低于判据；它的失误率不是同轮测得，而是取 b163 的值代入。</li>",
     "<li><b>单路达到理论值。</b>同轮同配置的 b163 三组为理论值的 95–100%，扩展窗口实验的 64K 为 101%。扩展窗口实验的 32K 为 93.9%，略低于判据；它的失误率不是同轮测得，而是取 b163 的值代入。这几组都在合成重复文本上测得（§12）；真实内容见表 5b 与本表新增三行（97.6–104.1%）。</li>"),
    ("<li><b>87K 未达到（88%）。</b>可能的原因有两类，都未验证：87K 用 any-delta 口径，计入思考与工具调用输出；$k$ 只在 32K–64K 拟合，87K 是外推。</li>",
     "<li><b>87K：v5.4 的「未达到」源于失误率代入错误。</b>该行代入的是 32K 合成文本上的 24.13%；真实会话 seed_real 的同内容实测失误率为 38.59%（R046g D0，54,000 次层调用），按它计算，87–95K 重放为理论值的 104.1%（W98K）与 103.9%（W128K）。any-delta 口径与 $k$ 外推仍是次要误差来源。</li>"),
    ("当前实现在单路（≤ 64K）和两路同/近内容上都已达到所在执行结构的理论值。",
     "当前实现在单路（≤ 64K）和两路同/近内容上都已达到所在执行结构的理论值；按同内容失误率，真实内容的单路（1.2K、87–95K）也达到（97.6–104.1%）。"),
    ("以及让失误专家不经链路（hybrid 的两路形态，§7.7，未测）。</p>",
     "以及让失误专家不经链路（hybrid 的两路形态，v5.5 已测得每路 +49%，§7.7）。</p>\n"
     "<h3>8.4 与 Strata 的差距分解 <span class=\"ev m\">实测</span> / <span class=\"ev d\">推导</span></h3>\n"
     "<p>同一台机器、同一份 32,064 token 输入（合成重复文本）、都不开 MTP：Strata v0.1.41 S1 解码 61.40–63.35 tok/s，本文发布配置 35.42–35.64 tok/s，相差约 1.76 倍。逐项事实见表 12g。</p>\n"
     "<table class=\"booktabs small\"><caption>表 12g　同输入下的执行事实（S1 数字取自其引擎 stderr 与 argv）</caption><thead><tr><th>项</th><th>FreeToken 481（offload）</th><th>Strata v0.1.41 S1</th></tr></thead><tbody>"
     "<tr><td>专家格式与单专家字节</td><td>NVFP4，2.77 MB</td><td>IQ3_S，2.04 MB（17.45 GiB ÷ 9,196，少 26.5%）</td></tr>"
     "<tr><td>GPU 专家槽</td><td>2,700（约 7.5 GB；KV 为 98,304 窗口 bf16）</td><td>9,196（17.45 GiB；KV int8，常驻 32,768，其余从主存流式读取）</td></tr>"
     "<tr><td>解码失误率（同一输入）</td><td>25.27%（LRU）</td><td>34–38%（命中 62.0–63.0%；静态画像，自适应冻结）</td></tr>"
     "<tr><td>未命中专家在哪里计算</td><td>经 PCIe 搬到 GPU，与其余计算串行</td><td>CPU 在主存原地计算，与 GPU 并行（<code>--pcie-frac 0</code>）</td></tr>"
     "<tr><td>每步时间</td><td>27.97 ms = 14.13（固定）+ 13.84（搬运）</td><td>约 16.0 ms</td></tr>"
     "<tr><td>冷 32K 首 token</td><td>6.07–6.60 s</td><td>7.997–8.385 s</td></tr></tbody></table>\n"
     "<p><b>分解（推算）。</b>Strata 各请求的速度随命中率变化：短提示三条命中 65.8% / 63.4% / 61.7%，对应 66.4 / 64.6 / 60.6 tok/s。线性拟合得每个 CPU 计算的专家约 0.071 ms（单专家 2.04 MB，等效约 29 GB/s），截距约 3.3 ms；说明 Strata 处在 CPU 受限区间，GPU 的固定部分大部分藏在 CPU 计算之后（三点拟合，未做服务时间分解）。据此把约 1.8 倍拆成三项：</p>\n"
     "<ol>\n"
     "  <li><b>执行结构（主因）。</b>本文 offload 每步的 13.84 ms 搬运与 14.13 ms 固定部分串行相加；Strata 让失误专家在主存原地计算，并与 GPU 并行。若本文保持 NVFP4 与自己的失误数（每步约 121 个），只改成这种并行结构，且 CPU 执行器达到 Strata 的每专家效率（2.77 MB 按 29 GB/s 约 0.097 ms），CPU 部分约 11.7 ms，低于 GPU 固定部分 14.1 ms，步长约为固定部分加同步开销，约 55–65 tok/s。</li>\n"
     "  <li><b>CPU 执行器效率（代码实现）。</b>本文 hybrid 执行器已是这种结构，但同窗口单路只有 33.83 tok/s（§7.7）。按 T09 的计数（每层 CPU 算 2.43 个、PCIe 搬 0.62 个专家）推算，它每个 CPU 专家约 0.20–0.24 ms，等效 11–14 GB/s，约为 Strata 的一半：NVFP4 在 CPU 上没有原生指令、需逐块反量化，Strata 则用 ggml 的 AVX-512 IQ 内核和自有线程池。这一项解释了本文 hybrid 单路只快 12%、而不是接近 70% 的原因。</li>\n"
     "  <li><b>量化（次要）。</b>IQ3_S 单专家比 NVFP4 少 26.5% 字节。在本文的 PCIe 结构下，只换字节可把搬运项从 13.84 降到约 10.2 ms，步长约 24.3 ms，约 41 tok/s（+15%）；同显存能放的槽数多约 36%，在真实内容上还能再降几个百分点失误率。在 Strata 的并行结构下，只有 CPU 受限时字节才影响步长。</li>\n"
     "</ol>\n"
     "<p><b>结论。</b>约 1.8 倍的差距主要来自「未命中专家在哪里计算」这一执行结构，其次是本文 CPU 执行器的实现效率；量化在本文的 PCIe 结构下约贡献 15%，不是主因。本文的冷预填快于 Strata（6.07–6.60 s 对 8.0–8.4 s；层优先预填与 NVFP4 张量核）。MTP（S2 较 S1 ×1.2–1.3）是另一独立因素，本文冻结未做。以上分解基于单台机器、单一合成输入与少量样本，属推算；要证实，需要对本文 hybrid 做每层服务时间分解（D08 后续）。重算见 <code>paper/src/theory_v55.py</code>。</p>"),
    # §11
    ("<li><b>PCIe 时间</b> <span class=\"ev d\">推导</span>：预填遍与解码未命中共用一份 PCIe 时间，一遍约等于 233 个解码 token。</li>",
     "<li><b>PCIe 时间</b> <span class=\"ev d\">推导</span>：预填遍与解码未命中共用一份 PCIe 时间，一遍约等于 $L^{*}$ 个解码 token（第 0 代标定 233，真实内容约 133）。</li>"),
    ("以发布配置实测失误率计，单路 32K 理论值约 36.6 tok/s；两路同/近内容",
     "失误率随内容变化：32K 合成文本单路理论值约 36.6 tok/s，真实 agent 内容约 27–31 tok/s，串行模型在真实内容上为实测的 97.6–104.1%；两路同/近内容"),
    ("除一组单路 32K（93.9%）外都达到 95% 判据；87K 为 88%。原“每路 &gt; 30”目标由此替换（§4.7、§8.3）。</li>\n</ul>",
     "除一组单路 32K（93.9%）外都达到 95% 判据；87K 按同内容失误率为 104.1%。原“每路 &gt; 30”目标由此替换（§4.7、§8.3）。</li>\n"
     "  <li><b>hybrid</b> <span class=\"ev m\">实测</span>：同窗口单路 +12%、两路每路 +49%，两路超过 offload 的链路上界；输出与 offload 不逐位一致，复验进行中（§7.7）。与 Strata 约 1.8 倍的差距主要来自执行结构与 CPU 执行器效率，量化次要（§8.4，推算）。</li>\n</ul>"),
    ("<b>各机制当前状态（2026-10-10 终）：M1–M6、G1–G5 尚无一项测出收益。</b>",
     "<b>各机制当前状态（2026-10-11）：M1–M6、G1–G5 尚无一项测出收益。</b>"),
    ("启用路径 T17 为 failed_harness（batch164，cached-token 契约不等），等价性未接受；</li>",
     "启用路径 T17 为 failed_harness（batch164，cached-token 契约不等），等价性未接受；修复候选 D09fix（7d8d389e）默认关闭 T16 已过（batch167 kept，2026-10-11），启用路径 T17 与收益回放 T2 待测；</li>\n"
     "  <li>M3（D11）：未立项。v5.5 推演显示它是停顿公平性机制，吞吐上限约 +1.6–5.6%（§5.2）；立项条件见 <code>plan/D11_DECISION_20261011.md</code>；</li>"),
    ("<p>M2、M6 和 M3 未进入当前验证计划；",
     "<p>M2、M6 未进入当前验证计划，M3 按上条暂不立项；"),
    # §12
    ("<li>Strata 跨系统差异未隔离 MTP/量化/执行路径因素；",
     "<li>Strata 跨系统差异的三项分解（执行结构、CPU 执行器效率、量化）是基于单一合成输入与少量样本的推算（§8.4），没有逐层服务时间分解；"),
    ("是否同源未归因。该项影响续算的重算量，修复未实施。</li>",
     "是否同源未归因。该项影响续算的重算量。修复已实现并默认关闭（D05 候选 730b58c9，由环境变量开启），其默认关闭门 T16 已过（batch168 kept，2026-10-11）；D09 的同类症状由 D09fix 处理（batch167 kept）。缺口是否确实补上，待 T11 复测。</li>\n"
     "  <li><b>合成负载。</b>b163、R048b 与 Strata S1–S4 的 32K 数字使用同一份冻结输入（32,064 token），它是约 100 字的一段文字重复数百遍拼成的合成文本；R046g 的 G_seed12k 也是同类合成文本。合成文本的路由高度重复，失误率（约 25%）显著低于真实内容（35–39%），这些 32K 数字不代表真实长文本的解码速度（§4.7）。</li>\n"
     "  <li><b>hybrid 数值。</b>hybrid 与 offload 输出不逐位一致（§7.7）；若 hybrid 进入发布路径，§9 的逐位等价门须改为对 hybrid 自身的可复现性门。</li>"),
    # Appendix C
    ("<h2>附录 C　版本变更说明（v4 → v5.4）</h2>", "<h2>附录 C　版本变更说明（v4 → v5.5）</h2>"),
]

APPENDIX_V55 = (
    "<p><b>v5.5（2026-10-11）。</b>按主会话对 v5.4 的逐条审查一次改写，不新增测量承诺：（1）失误率按内容取值——v5.4 把 32K 合成重复文本上的 24.13% 当作单路通用值，真实 agent 内容为 35–39%；新增表 5b，串行模型在真实内容上为实测的 97.6–104.1%，单路理论值改为“合成文本 36.6、真实内容 27–31”（摘要、§4.7、表 12、§11）；（2）87K「未达到（88%）」改判为失误率代入错误，同内容 38.59% 下为 104.1%（§8.3）；（3）$L^{*}$ 注明与 $m$ 成反比，真实内容约 133（§4.4、§11）；（4）$R_{link}$ 限定为经链路的未命中，加入 $\\phi$（§4.7）；（5）§7.7 改写为 hybrid 旧负结果与同窗口复测：单路 +12%、两路每路 +49%，并披露与 offload 不逐位一致；C5 同步（表 1）；（6）新增 §8.4 与 Strata 的差距分解（执行结构、CPU 执行器效率、量化，推算）；（7）§5.2 M3 代价公式按边际资源修正，并给出停顿与吞吐的推算；（8）§12 新增合成负载与 hybrid 数值两条局限，更新 D05（batch168 kept）与 D09fix（batch167 kept）状态；§11 更新机制状态。重算脚本 <code>paper/src/theory_v55.py</code>，改写脚本 <code>paper/src/revise_v55.py</code>。</p>\n"
)


def main():
    text = SRC.read_text(encoding="utf-8")
    for old, new in EDITS:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected exactly one match, got {count}: {old[:80]!r}")
        text = text.replace(old, new)
    anchor = "</section>"
    head, sep, tail = text.rpartition(anchor)
    if "附录 C　版本变更说明（v4 → v5.5）" not in head[-6000:]:
        raise SystemExit("appendix C is not the last section")
    text = head + APPENDIX_V55 + sep + tail
    DST.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {DST.name}: {len(EDITS)} replacements + appendix entry")


if __name__ == "__main__":
    main()
