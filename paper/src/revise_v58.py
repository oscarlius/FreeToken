"""Write body_v58.html from body_v57.html.

(1) Replace the empirical "30 tok/s per lane" reading with structure bounds and achievable values (§4.7, table 5c);
(2) retract the hybrid-specific J4 attribution; (3) note the failed two-lane hybrid miss-rate prediction;
(4) add the window01 OOM measurements; (5) add the user-approved lossless definition to §9.
Every edit asserts that its anchor occurs exactly once. Numbers come from paper/src/theory_v58.py.
Run: python paper/src/revise_v58.py
"""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
SRC, DST = HERE / "body_v57.html", HERE / "body_v58.html"

EDITS = [
    # header
    ("预印本草稿 · v5.7 · 2026-10-11", "预印本草稿 · v5.8 · 2026-10-11"),
    # abstract (zh)
    ("按此失误率，即使理想错相位重叠，链路上界也只有约 23.9——每路 30 在两路不同内容下不可达，除非每路失误率降到 30.4% 以下。"
     "这一上界只约束经 PCIe 搬运的未命中：hybrid 让大部分未命中专家在 CPU 上原地计算，同窗口 A/B（2026-10-11）中两路每路 25.96–26.27 tok/s，"
     "offload 为 16.81–16.98（+55%），高于 offload 的链路上界 23.9；单路 35.55–36.59 对 29.62–30.19（+21%）；但 hybrid 在同一服务内重复同一请求，"
     "输出也不逐位一致（§7.7）。8 路每路上界约 9.5。",
     "按此失误率，未命中经 PCIe 搬运的结构（offload，含理想错相位重叠）每路上界为 $B_P/(2mS_{tok})\\approx23.9$，这是该结构的硬上限。"
     "越过它只能让未命中不经链路：本机 CPU 路径处理专家权重的实测边际吞吐为 65–74 GB/s，是 PCIe 的 2.7–3.1 倍（§4.7）。"
     "hybrid 同窗口 A/B（2026-10-11）两路每路 25.96–26.27 tok/s，offload 为 16.81–16.98（+55%）；单路 35.55–36.59 对 29.62–30.19（+21%）；"
     "但它的 CPU 路径用 W4A8，取数又依赖缓存历史，不属于无损（§7.7、§9）。按资源模型推算，固定 GPU 专家集、其余专家在 CPU 上以 fp32 计算的无损结构，"
     "两路每路约 27–31、单路约 38–47 tok/s（推算，§4.7 表 5c）；单卡上限由 GPU 串行部分决定，两路每路约 54、单路约 76。8 路每路链路上界约 9.5。"),
    ("但输出不逐位一致：既与 offload 不同，同一服务内重复请求也不同，即受缓存状态影响；",
     "但输出不逐位一致：与 offload 不同，且受缓存历史影响（新起服务与已预热服务的同一冷请求从第 600 字符起分叉）；"),
    # abstract (en)
    ("at that miss rate even ideal staggered overlap is capped by the link at about 23.9 tok/s: 30 tok/s per lane is unreachable "
     "for distinct-content pairs unless the miss rate falls below 30.4%.",
     "at that miss rate any structure that moves misses over PCIe, ideal staggered overlap included, is capped at "
     "$B_P/(2mS)\\approx23.9$ tok/s per lane. Only computing misses off the link exceeds this: the CPU path processes expert "
     "weights at a measured marginal 65–74 GB/s, 2.7–3.1× PCIe. A lossless structure with a fixed GPU expert set and the remaining "
     "experts computed on the CPU in fp32 is projected at about 27–31 tok/s per lane for two streams and 38–47 single-stream; "
     "the GPU serial part caps a single card at about 54 per lane (two streams) and 76 (single)."),
    ("its output is neither bit-identical to offload nor reproducible across repeated requests in the same service.",
     "it uses W4A8 activations on the CPU and its output depends on cache history (a fresh and a warmed service diverge on "
     "the same cold request), so it is not lossless."),
    # §1.1
    ("v5.3 起不再作为目标，只在 §4.7 中作为参考点，说明达到它需要什么条件。",
     "v5.8 起正文不再以它为参照，§4.7 按执行结构给出可达值与约束资源。"),
    # §4.4
    ("要满足峰值 8 路 × 30 tok/s，每 token 未命中字节需降到约 101 MB（失误率约 7.6%）。两路 × 30 tok/s 只需 17.5 GB/s，"
     "所以在 $u\\le28\\%$ 时，链路本身不排除这一目标。这两个数只说明链路条件；以 30 tok/s 为参考点的完整推算见 §4.7。",
     "它按单路失误率计算；多路内容不同时会话之间互相挤占缓存，失误率上升，合计上界随之下降。各执行结构的可达值见 §4.7。"),
    # table 6 (M4 row)
    ("<td>重开须改为共享缓存加图化；按当前失误率上界仍 &lt;30，须先降失误率</td>",
     "<td>重开须改为共享缓存加图化；即使完美实现，上界也只有 23.9（offload 结构的硬上限），已低于 hybrid 实测</td>"),
    # table 12
    ("理想重叠上界约 23.9，每路 30 不可达。上界只约束经链路的未命中，hybrid 两路已超过 offload 链路上界（§7.7）",
     "理想重叠上界约 23.9（offload 结构的硬上限）。该上界只约束经链路的未命中，hybrid 两路已超过它（§7.7）；无损的 CPU 路径结构推算约 27–31（§4.7 表 5c）"),
    ("<td>串行 6.4；上界 9.5；每路 30 在单卡上不可达（外推，§4.7）</td>",
     "<td>offload 串行 6.4、链路上界 9.5（外推，§4.7）；CPU 路径结构未推算</td>"),
    # §8.1
    ("机制在当前失误率下即使完美实现也达不到每路 30；重开开发须先降失误率，",
     "机制即使完美实现，上界也只有约 23.9，已低于 hybrid 同窗口实测；重开开发须先降失误率，"),
    # §8.3
    ("按预注册，本次不同内容负载在 2,700 槽下的公式理想上界为 23.87 tok/s/路，<b>每路 30 的目标就此关闭</b>；这不表示所有提示的上界都低于 30（Y 的公式上界为 32.95）。",
     "按预注册，本次不同内容负载在 2,700 槽下的公式理想上界为 23.87 tok/s/路，这是 offload 结构在该负载下的硬上限（Y 组近重复提示为 32.95）。"),
    ("原目标「两路每路 &gt; 30」在该负载下高于链路上界，仅靠 M4 不可达，必须先把每路等效失误率降到 30.4% 以下；8 路每路 30 在单卡上按模型不可达。",
     "这是未命中经链路的结构所能达到的全部；越过它要让未命中改在 CPU 上计算，无损结构推算两路每路约 27–31（§4.7 表 5c）。"),
    ("远不足以把两路 m 从 38% 降到 30.4%。",
     "对链路上界的改变也很小（两路 m 每降 1 个百分点，上界约 +0.6 tok/s）。"),
    # §8.4
    ("单路约 40–46 tok/s、两路每路约 28–31 tok/s（推算，按 window02 重新标定；v5.6 写的 44–50 / 27–32 偏高）",
     "单路约 40–46 tok/s、两路每路约 28–31 tok/s（推算，按 window02 重新标定；v5.6 写的 44–50 / 27–32 偏高。两路数值依据的 hybrid 两路失误率预测 29–31% "
     "在 window01 实测为 43.1%（引擎口径），不成立，两路可达值待按实测失误率重拟）"),
    ("可达值约 40–46 tok/s（两路每路约 28–31）", "可达值约 40–46 tok/s（两路待重拟）"),
    # §7.7 J4 retraction
    ("window02 中，<b>同一 hybrid 服务内重复同一请求</b>也在第 454 个字符起分叉，两路重复在第 599 / 149 个字符起分叉，"
     "新起服务与已预热服务在第 600 个字符起分叉（预注册 J4：affected）。offload 在热服务、新服务、单路重复上都逐字相同。",
     "window02 曾判「同一 hybrid 服务内重复同一请求在第 454 个字符起分叉」（预注册 J4：affected），v5.8 撤回这一归因：那两次请求一冷一热"
     "（热请求命中 1,152 / 1,179 token），offload 在同样的冷对热比较中也从第 454 个字符分叉（window02 的 O1、O2 与 window01 的 S1 三个服务一致），"
     "属 §10.2 的已知类别。hybrid 依赖缓存状态的直接证据是：新起服务与已预热服务的同一冷请求在第 600 个字符起分叉；offload 的计算与缓存状态无关（按构造）。"
     "window01 的取数为 0 变体（GPU 缓存保持冷，路由专家全部在 CPU 上算）在已测的同类比较上与 offload 同等可复现（热对热相同；fp32 版跨服务冷对冷相同），确认测试待做。"),
    # §11
    ("原“每路 &gt; 30”目标由此替换（§4.7、§8.3）。",
     "offload 结构两路每路上界 23.9；无损的 CPU 路径结构推算约 27–31，单卡上限约 54（§4.7 表 5c）。"),
    ("输出不逐位一致，同一服务内重复请求也不一致（J4 affected），按预注册只能作为可选性能模式",
     "输出不逐位一致且受缓存历史影响（新起服务与预热服务的同一冷请求从第 600 字符起分叉），不满足 §9 的无损定义，按预注册只能作为可选性能模式"),
    ("且两路不同内容时理想重叠上界约 23.9，达不到每路 30，重开须先降失误率（§4.7）；",
     "且两路不同内容时理想重叠上界约 23.9，已低于 hybrid 实测，重开须先降失误率（§4.7）；"),
    # §12
    ("X 的公式理想上界 23.87 tok/s 确认不同内容两路的每路 30 目标不可达。",
     "X 的公式理想上界 23.87 tok/s 即 offload 结构在该负载下的硬上限。"),
    ("它与 offload 输出不逐位一致，同一服务内重复请求也不一致（§7.7，J4 affected）；",
     "它与 offload 输出不逐位一致，且受缓存历史影响（§7.7）；"),
    # appendix A.5
    ("X 公式理想上界 23.87 tok/s，每路 30 目标就此关闭</td>",
     "X 公式理想上界 23.87 tok/s，即 offload 结构的硬上限</td>"),
]

TABLE_5C = """<p><b>按执行结构的可达值（v5.8，取代以 30 tok/s 为参照的读法）。</b>“每路 30 tok/s”是早期的经验设定，没有理论依据，本节不再以它为参照。每一步要完成三类工作：GPU 串行部分 $F(B,L)$；经 PCIe 搬运的未命中 $B\\,m_{link}S_{tok}/B_P$；在 CPU 上计算的未命中 $A_C+B\\,m_{cpu}S_{tok}/B_C$，其中 $A_C$ 是 CPU 路径每步的固定部分（每层派任务与交接），$B_C$ 是 CPU 处理专家权重的边际吞吐。串行结构中三者相加；理想错相位重叠时，最慢的资源决定步长。$A_C$ 与 $B_C$ 用 window01 取数为 0 的服务拟合（这类服务的路由专家全部在 CPU 上算）：fp32 路径 $B_C=$ 65–74 GB/s、$A_C=$ 11.8–17.0 ms（同配置新起服务与预热服务的单路相差 8%，取两者为区间）；W4A8 路径 $B_C\\approx39$ GB/s。<b>CPU 路径的边际吞吐是 PCIe（24.3 GB/s）的 2.7–3.1 倍，这是越过链路上界的物理依据。</b>重算见 <code>paper/src/theory_v58.py</code>。</p>
<table class="booktabs small"><caption>表 5c　按执行结构的每路可达值（tok/s；两路为不同内容、约 1.2K 输入，2,700 槽）</caption><thead><tr><th>执行结构</th><th>无损（§9）</th><th>约束资源</th><th>两路，每路</th><th>单路</th><th>依据</th></tr></thead><tbody>
<tr><td>offload，串行（发布配置）</td><td>是</td><td>PCIe（占步长约 69%）</td><td>16.6（实测 16.81–17.01）</td><td>30.9（实测 29.62–30.19）</td><td>模型 / 实测</td></tr>
<tr><td>offload，理想错相位重叠（M4）</td><td>是</td><td>PCIe 跑满</td><td>23.9</td><td>—（单路无法自我重叠）</td><td>上界</td></tr>
<tr><td>路由专家全部在 CPU 上算，fp32（取数为 0）</td><td>候选，确认测试待做</td><td>CPU 路径</td><td>18.9（实测 18.86–18.96）</td><td>28.6–30.9（实测）</td><td>拟合点</td></tr>
<tr><td>固定 GPU 专家集，其余在 CPU 上算，fp32</td><td>是（分配固定，与服务历史无关）</td><td>CPU 路径</td><td>约 27–31</td><td>约 38–47</td><td>推算，未实现</td></tr>
<tr><td>hybrid 默认（动态取数，W4A8）</td><td>否</td><td>CPU 路径</td><td>25.96–26.27（实测；模型 23.0，偏低约 12%）</td><td>35.55–36.59（实测）</td><td>实测</td></tr>
<tr><td>无未命中（全部专家驻留，单卡做不到）</td><td>—</td><td>GPU 串行部分 $F$</td><td>54.2</td><td>76.1</td><td>上限</td></tr>
</tbody></table>
<ul>
  <li>固定专家集的失误率取 D15 回放的结论：静态画像比 LRU 高 11.5–16.0 个百分点，两路取 49.7–54.2%、单路取 46.6–51.1%，属外推。模型在默认 hybrid 上偏低约 12%，所以该区间偏保守。该结构需要代码：启动时按画像装入固定专家集、此后不再取数；尚未实现。</li>
  <li>默认 hybrid 的取数依赖缓存历史，同一冷请求在新起服务与已预热服务上从第 600 字符起分叉，不满足 §9 无损定义的第二条；它的 CPU 路径又用 W4A8，不满足第一条。</li>
  <li>单卡上限由 GPU 串行部分决定；要接近它，必须同时消除未命中的暴露时间，属远期。8 路：offload 串行 6.4、链路上界 9.5（外推）；CPU 路径结构未推算。</li>
</ul>"""

LOSSLESS = """<p><b>无损的定义（2026-10-11 用户确定）。</b>一项改动若同时满足以下两条，本文称其为无损：（1）计算本身不打折扣：不跳过专家、不改 top-k、激活精度不低于 bf16；（2）可复现程度不劣于 offload：一律做同类比较（冷对冷、热对热、相同历史对相同历史），并在同一窗口设 offload 对照臂；offload 自己也做不到的判据（例如冷对热逐位相同）不作为门槛。按此定义，默认 hybrid（W4A8、动态取数）不是无损；取数为 0 的 fp32 变体是无损候选。</p>
"""

HISTORY = """<p><b>v5.8（2026-10-11 晚）。</b>（1）用户确认“每路 30 tok/s”没有理论依据，正文不再以它为参照：§4.7 新增按执行结构的可达值（表 5c）与三资源模型，CPU 路径参数由 window01 取数为 0 的服务拟合（fp32 边际 65–74 GB/s，为 PCIe 的 2.7–3.1 倍）；摘要、§1.1、§4.4、表 6、表 12、§8.1、§8.3、§11、§12、附录 A.5 中“每路 30 不可达”的表述改为结构上界与可达值；（2）撤回 J4 的 hybrid 特有归因（冷对热比较，offload 同样分叉），依赖缓存状态的证据改为新起服务对预热服务的第 600 字符（摘要、§7.7、§11、§12）；（3）§8.4 注明两路 hybrid 失误率预测（29–31%）不成立（实测 43.1%）；（4）§12 写入 window01 的 OOM 实测；（5）§9 写入用户确定的无损定义。推算脚本 <code>paper/src/theory_v58.py</code>，改写脚本 <code>paper/src/revise_v58.py</code>。</p>
"""

OOM_OLD = re.compile(r"<li><b>offload 长上下文 OOM。</b>.*?属于生产配置在目标负载上的风险。</li>", re.S)
OOM_NEW = ("<li><b>offload 长上下文 OOM。</b>window02 中，发布配置的 offload 服务在先跑过 X 单路与两路之后，87K 真实会话请求在两个服务上都触发 CUDA OOM"
           "（申请 48 MiB 时仅剩 21.69 MiB）。window01（2026-10-11 晚）复测：预热过的服务 64K、80K、87K 通过，95K OOM；新起的服务第一条 95K 即 OOM，"
           "单个请求内部就产生约 148 MiB 碎片；新起服务能稳定处理的冷输入在 87,128 到 95,352 token 之间，低于 98,304 的窗口。显存斜率实测约 22.5 KB/token，"
           "与按隐藏状态估算的约 20 KB/token 相近，偏差主要在碎片项。每次 OOM 整模型重载约 235 s，每个进程只自动恢复 1 次。"
           "这是生产配置在目标负载上的风险，不属于本文的收益论证。</li>")


def main():
    body = SRC.read_text(encoding="utf-8")
    for old, new in EDITS:
        n = body.count(old)
        assert n == 1, (old[:60], n)
        body = body.replace(old, new)
    block = re.compile(r"<p><b>以 30 tok/s 为参考点的读法。</b></p>\s*<ul>.*?</ul>", re.S)
    assert len(block.findall(body)) == 1
    body = block.sub(lambda _m: TABLE_5C, body)
    assert len(OOM_OLD.findall(body)) == 1
    body = OOM_OLD.sub(lambda _m: OOM_NEW, body)
    anchor = "<p>改变执行路径的改动（例如用快照恢复状态代替整段重算）分四层准入。"
    assert body.count(anchor) == 1
    body = body.replace(anchor, LOSSLESS + anchor)
    tail = "</section>"
    idx = body.rfind(tail)
    assert body.count("<p><b>v5.7（2026-10-11 下午）。</b>") == 1 and idx > 0
    body = body[:idx] + HISTORY + body[idx:]
    leftovers = [m.start() for m in re.finditer(r"每路 30|每路30|30\.4%", body)]
    DST.write_text(body, encoding="utf-8", newline="\n")
    print("ok", len(body), "remaining '30' mentions at offsets:", leftovers)


if __name__ == "__main__":
    main()
