"""v5.7 revision: body_v56.html -> body_v57.html.

Corrects the "hybrid is exact computation" wording (the CPU path quantizes activations to per-16 int8, W4A8) and
adds the KIMI code-research evidence (development/hybrid_code_research_20261011) to §8.4. Each edit must match once.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, DST = HERE / "body_v56.html", HERE / "body_v57.html"

EDITS = [
    ("预印本草稿 · v5.6 · 2026-10-11", "预印本草稿 · v5.7 · 2026-10-11"),
    ("即受缓存状态影响（§7.7）。", "即受缓存状态影响；其 CPU 路径对激活做 int8 量化（W4A8），属数值近似（§7.7）。"),
    ("<p><b>数值边界。</b>hybrid 属精确计算，不丢弃或近似任何专家，但输出不逐位一致：",
     "<p><b>数值边界（v5.7 更正）。</b>hybrid 不丢弃任何专家，权重逐位保真；但本机 CPU 路径走 W4A8：由 CPU 计算的专家，其激活先量化为每 16 个元素一组的 int8（<code>cpu_moe_ext.cpp</code> 的 <code>quant_i8_pg16</code>，源码注释写明「only the int8 activation quant (W4A8) differs from bf16」），GPU 路径则用 bf16 激活。所以 hybrid 对激活是数值近似，不是逐位精确计算；v5.4–v5.6 的「精确计算」表述有误，本版更正。另有块尺度施加顺序、写回 bf16 的时机、部分和多一次 bf16 相加三处舍入差异（<code>development/hybrid_code_research_20261011/Q1_Q10_COMPARISON.md</code> Q10）。输出因此不逐位一致："),
    ("推断：同一专家命中时由 GPU 计算、未命中时由 CPU 计算，两者舍入不同，",
     "推断：同一专家命中时由 GPU 以 bf16 激活计算、未命中时由 CPU 以 int8 激活计算，两者数值不同，"),
    ("按上式，把固定开销压到约 0.05 ms，单路约 44–50 tok/s、两路每路约 27–32 tok/s（推算）。</li>",
     "D08 诊断实测每层 CPU 任务为 0.207 ms 固定加 0.084 ms × 专家数（协调日志 2026-10-11 00:29），与上述标定一致。把线程池与握手两部分都压缩后，固定开销现实上约 0.05–0.1 ms，单路约 40–46 tok/s、两路每路约 28–31 tok/s（推算，按 window02 重新标定；v5.6 写的 44–50 / 27–32 偏高）。代码调研的 CPU 微基准：线程池空任务往返下限 0.075 ms（24 线程），其余约 0.12–0.19 ms 推断来自每层的 3 次 D2H、1 次 H2D、提交握手与协调轮询，以及提交线程上单线程完成的激活预处理；hybrid 没有打断 CUDA Graph（读码确认）。</li>"),
    ("<li><b>单专家带宽与量化（次要）。</b>FreeToken 的 CPU 内核本身带宽不差（本机 benchbw：单独 47.62 GB/s，与 PCIe 并发时 40.85 GB/s）；IQ3_S 单专家少 26.5% 字节，在 PCIe 结构下只换字节约 +15%。</li>",
     "<li><b>两路与投机窗口的批组织。</b>Strata 把同一窗口内命中同一专家的多个 token 合并，权重只从主存流一遍（2 个 token 每专家只比 1 个贵 26%，微基准）；FreeToken 按 (token, 路由) 切分，同一专家对两个 token 各流一遍（代码注释列为待做）。两路时 CPU 侧流量可差近一倍，这是两路场景的重要结构差（读码确认，影响量为推断）。</li>\n"
     "  <li><b>单核效率与字节数（次要）。</b>每专家边际代价 FreeToken 0.072 ms（24 线程，微基准），与 Strata 的拟合区间 0.036–0.071 ms 重叠，「每专家慢 3 倍」不成立；单核每字节 FreeToken 0.373 ms/MB，Strata 0.253–0.296 ms/MB，差 25–32%（NVFP4-W4A8 每 16 元素乘一次块尺度，IQ 系每 256 值一次）；IQ3_S 单专家少 26.5% 字节，在 PCIe 结构下只换字节约 +15%。</li>"),
    ("<li><b>hybrid 数值。</b>hybrid 与 offload 输出不逐位一致，同一服务内重复请求也不一致（§7.7，J4 affected）；",
     "<li><b>hybrid 数值。</b>hybrid 的 CPU 路径对激活做 int8 量化（W4A8），不属于逐位精确计算；它与 offload 输出不逐位一致，同一服务内重复请求也不一致（§7.7，J4 affected）；"),
    ("差距主要在每层固定开销与 GPU 串行部分，可达值约 44–50 tok/s，再往上取决于 GPU 串行部分。", "差距主要在每层固定开销与 GPU 串行部分，可达值约 40–46 tok/s（两路每路约 28–31），再往上取决于 GPU 串行部分。"),
    ("以 R048b S 臂作样本外检查，推算 33.5、实测 31.94。", "以 R048b S 臂作样本外检查，推算 33.5、实测 31.94（跨窗口，hybrid 单路跨窗口相差约 7%，分辨力约 ±10%）。"),
    ("<h2>附录 C　版本变更说明（v4 → v5.6）</h2>", "<h2>附录 C　版本变更说明（v4 → v5.7）</h2>"),
]

APPENDIX_V57 = (
    "<p><b>v5.7（2026-10-11 下午）。</b>（1）更正 v5.4–v5.6 的「hybrid 属精确计算」：本机 CPU 路径走 W4A8，激活量化为每 16 元 int8，是数值近似（§7.7、§12、摘要）；（2）§8.4 写入代码调研（KIMI，<code>development/hybrid_code_research_20261011</code>）的证据：池内空任务往返 0.075 ms、每专家边际 0.072 ms、单核每字节差 25–32%、Strata 按专家合并多 token 而 FreeToken 按 token 重流、hybrid 未打断 CUDA Graph；可达值按 D08 实测与 window02 重新标定为单路 40–46、两路每路 28–31 tok/s。改写脚本 <code>paper/src/revise_v57.py</code>。</p>\n"
)


def main():
    text = SRC.read_text(encoding="utf-8")
    for old, new in EDITS:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected exactly one match, got {count}: {old[:80]!r}")
        text = text.replace(old, new)
    head, sep, tail = text.rpartition("</section>")
    if "附录 C　版本变更说明（v4 → v5.7）" not in head[-12000:]:
        raise SystemExit("appendix C is not the last section")
    DST.write_text(head + APPENDIX_V57 + sep + tail, encoding="utf-8", newline="\n")
    print(f"wrote {DST.name}")


if __name__ == "__main__":
    main()
