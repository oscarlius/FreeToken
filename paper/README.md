> **当前 v5.8（10-11 晚）**：[HTML](FreeToken_MultiGPU_CoExec_v5.8.html)。用户确认“每路 30 tok/s”没有理论依据：§4.7 改为按执行结构给出可达值（表 5c，三资源模型），offload 两路每路上界 23.9；CPU 路径实测边际吞吐 65–74 GB/s（PCIe 的 2.7–3.1 倍），无损的“固定 GPU 专家集 + CPU fp32”结构推算两路每路约 27–31、单路约 38–47；单卡上限两路每路约 54、单路约 76。另并入三条已核实勘误：撤回 J4 的 hybrid 特有归因、两路 hybrid 失误率预测失败（43.1%）、window01 OOM 实测；§9 写入无损定义。重建：`python paper/src/build_v58.py`；改写 `paper/src/revise_v58.py`；推算 `paper/src/theory_v58.py`。

> **当前 v5.7（10-11 下午）**：[HTML](FreeToken_MultiGPU_CoExec_v5.7.html)。更正「hybrid 属精确计算」：本机 CPU 路径走 W4A8（激活量化为每 16 元 int8），是数值近似；§8.4 写入 KIMI 代码调研证据（池内往返 0.075 ms、每专家 0.072 ms、单核每字节差 25–32%、Strata 多 token 合并流权重）。重建：`python paper/src/build_v57.py`。待独立终审。

> **当前 v5.6（10-11 午后）**：[HTML](FreeToken_MultiGPU_CoExec_v5.6.html)。更正 v5.5 的事实错误：retry2 的 hybrid 对 offload 是跨窗口的历史参照，不是同窗口；写入 window02 真正的同窗口 A/B（单路 +21%、两路每路 +55%；hybrid 同服务重复不逐位一致；offload 87K OOM ×2）；§8.4 按逐层结构更正 Strata 差距（主因为每层 CPU 固定开销与 GPU 串行部分，可达约 44–50 tok/s）；§4.4 加最优取数拆分。重建：`python paper/src/build_v56.py`；改写脚本 `paper/src/revise_v56.py`。待独立终审。

> **当前 v5.5（10-11）**：[HTML](FreeToken_MultiGPU_CoExec_v5.5.html)。主会话逐条审查 v5.4 后改写，没有新增测量承诺：失误率按内容取值（合成 32K 文本约 25%，真实 agent 内容 35–39%；串行模型在真实内容上为实测的 97.6–104.1%）；87K「未达到」改判为失误率代入错误；L* 真实内容约 133；R_link 限定为经链路的未命中；§7.7 改为 hybrid 同窗口正结果（单路 +12%、两路 +49%，不逐位）；新增 §8.4 Strata 差距分解；M3 代价公式修正；§12 加合成负载与 hybrid 数值两条局限。重建：`python paper/src/build_v55.py`；改写脚本 `paper/src/revise_v55.py`；重算 `paper/src/theory_v55.py`。v5.4 及更早源码与 HTML 原字节保留。本版待独立终审。

> **当前 v5.4（10-10 晚）**：[HTML](FreeToken_MultiGPU_CoExec_v5.4.html)。按当日新测量与复核一次修订：两路理论值修正（v5.3 误把单路失误率代入两路；两路不同内容串行约 15.0–15.7、理想重叠上界约 21.3–22.6，每路 30 不可达）；D10 b162 改判「实现无效，机制未检验」；闭环 X/Y 已闭合（P1 102.3–102.7% 成立、P2 低 10.5pp 成立、X 上界 23.87 关闭每路 30）；补 R044b、T03b、87K 外点、D09 T16/T17、窗口 A/B、R067e 与 M5 冻结；Strata 更新为 S1–S4 已独审子集。用 `python paper/src/build_v54.py` 重建（重算脚本 `paper/src/theory_v54.py`）；v5.2/v5.3 源码与 HTML 原字节保留。本版待独立终审；英文 arXiv 稿尚未同步。

# 论文目录

## 当前版本

| 项 | 值 |
| --- | --- |
| 版本 | v5.8（2026-10-11 晚，按执行结构给出可达值，取代“每路 30”参照；并入三条已核实勘误；v5.7 保留） |
| 正文 | [FreeToken_MultiGPU_CoExec_v5.8.html](FreeToken_MultiGPU_CoExec_v5.8.html)，单文件 HTML |
| 作者 | 刘尚锋 |
| 数据版本 | [FTD-20261009-1](../plan/data_releases/FTD-20261009-1.json) ＋ 附录 A.5 轮次名单（FTD-20261010-1 草案，待服务器清单封存） |
| manifest SHA256 | cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840（FTD-20261009-1） |
| HTML SHA256 | 11b53f9d16007a69684de776912adb567cdf5161007bfd850a6c35091f5f7892（v5.8） |
| 证据边界 | 尚无一项机制测出收益（C4/C5）；D10 b162 为「实现无效，机制未检验」；offload 结构两路每路上界 23.87（闭环 X）；无损 CPU 路径结构 27–31 为推算、未实现；多卡未实测 |
| 历史版本 | v5.3/v5.2/v5.1/v5.0 的 HTML 与 body/build 源码原字节保留 |
| 独立终审 | 本版待独审；v5.1 终审见 [REVIEW_v5.1_20261009.md](REVIEW_v5.1_20261009.md)，不沿用于本版 |

## 修改与重建

- v5.4 正文在 src/body_v54.html；组装与排版在 src/build_v54.py；两路理论重算在 src/theory_v54.py。v5.3/v5.2/v5.1/v5.0 的源码保持不变。
- 在 FreeToken 目录执行 `python paper/src/build_v54.py`，不手改生成 HTML。
- 新科学数字引用〔轮次 ID｜FTD-20261009-1 或附录 A.5 名单〕；数据发布不可改，更正另发 FTD。旧版本与完整源码不删除。原作者和上游贡献者继续列致谢，不自行改变署名。

## 终审流程

今后每版遵循[论文终审清单](REVIEW_CHECKLIST.md)：必须逐条记录用户对本版的要求、处理结果与位置，不能只核对数字。主版本变化的科学理由及文字变更见论文附录 C。

## 版本历史

| 版本 | 日期 | 文件 | 要点 |
|---|---|---|---|
| v5.8 | 10-11 | FreeToken_MultiGPU_CoExec_v5.8.html | 按执行结构的可达值（表 5c）取代“每路 30”；J4 撤回；两路 hybrid 失误率预测失败；window01 OOM；无损定义；待独审 |
| v5.7 | 10-11 | FreeToken_MultiGPU_CoExec_v5.7.html | hybrid W4A8 更正（非逐位精确）；§8.4 写入代码调研微基准与批组织差异；待独审 |
| v5.6 | 10-11 | FreeToken_MultiGPU_CoExec_v5.6.html | 更正“同窗口”错误；window02 同窗口 A/B +21%/+55%；hybrid 不可逐位复现；offload 87K OOM；§8.4 逐层结构；§4.4 最优取数；待独审 |
| v5.5 | 10-11 | FreeToken_MultiGPU_CoExec_v5.5.html | 失误率按内容取值（真实内容 97.6–104.1%）；87K 改判；L*≈133；R_link 加 φ；hybrid 同窗口 +12%/+49%（不逐位）；§8.4 Strata 差距分解；M3 公式修正；合成负载与 hybrid 局限；待独审 |
| v5.4 | 10-10 | FreeToken_MultiGPU_CoExec_v5.4.html | 两路理论值修正；D10 b162 改判「实现无效，机制未检验」；闭环 X/Y 闭合（P1/P2 成立，每路 30 关闭）；R044b/T03b/87K 外点/D09/窗口 A/B/R067e；Strata S1–S4；附录 A.5 轮次名单；待独审 |
| v5.3 | 10-10 | FreeToken_MultiGPU_CoExec_v5.3.html | 当日测量一次修订（后被 v5.4 的两路理论修正取代） |
| v5.2 | 10-09 | FreeToken_MultiGPU_CoExec_v5.2.html | §8 增加 R045 四请求 22.03–22.53 tok/s 及串行模型对照，C5 保持；11 图 20 表 |
| v5.1 | 10-09 | FreeToken_MultiGPU_CoExec_v5.1.html | 15 项文字修订：计数口径、M5 正确性前置、批不变性、窗口取舍与官方引用；无重测 |
| v5.0 | 10-09 | FreeToken_MultiGPU_CoExec_v5.0.html | K1修复与同结构28/28；T03/T06/T07/T09；98304/87K；三类正确性与已知限制；11图18表 |
| v4.0 | 10-03 | `FreeToken_MultiGPU_CoExec_v4.0.html` | 主题改为多 GPU 协同执行；新增多卡字节守恒、主存预算、组级执行器、原理图；arXiv 排版 |
| v3.2 | 10-03 | `archive/freetoken-4090-agents_v3.2.md` | 开关四格重读；状态层等价；回复 Grok 与 GPT-6 的合并审阅 |
| v3.1 | 10-03 | `archive/freetoken-4090-agents_v3.1.md` | 回复 GPT-6 对 v3 的审阅：条件上界、重叠模型、D14 |
| v3 | 10-03 | `archive/freetoken-4090-agents_v3.md` | 首个终稿：遍数后果、PCIe 预算、排队 |
| v2 / v1 | 10-03 | `archive/` | 早期草稿；GPT-6（Astro）方向稿与协议稿也在 `archive/` |

外部审阅意见在 `openai/` 与 `archive/openai opp/`。其中 `openai/README.md` 与 v3.2 逐字节相同，不含新增意见。我们的逐条回复在 `../research/REPLY_*.md`。
