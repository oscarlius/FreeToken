# 论文目录

## 当前版本

| 项 | 值 |
| --- | --- |
| 版本 | v5.1（2026-10-09，仅文字修订，无重测） |
| 正文 | [FreeToken_MultiGPU_CoExec_v5.1.html](FreeToken_MultiGPU_CoExec_v5.1.html)，单文件HTML，11幅SVG、19张表 |
| 作者 | 刘尚锋 |
| 数据版本 | [FTD-20261009-1](../plan/data_releases/FTD-20261009-1.json)，服务器只读清单与本地逐字节相同 |
| manifest SHA256 | cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840 |
| HTML SHA256 | d52a2c7ca046839636404eb9103f33c8d5e57afe6f6fe595d5c1f7de49537d6a |
| 证据边界 | T17许可14+新测14，七个已测尾段≥65；≤64正确性待证；冷可复现、同结构热/冷一致、并发不保证分开报告；多卡未实测 |
| 历史版本 | v5.0 HTML及body_v5/build_v5/figures源码原字节保留；原v4 HTML原位保留；[完整源码/HTML归档](archive/v4.0_source_20261009/SHA256.json)按原始SHA保留 |
| 验证 | build字节可复现；桌面1280及窄屏390无页面溢出、内部链接/数学/SVG有效；[渲染回执](../development/paper_v51_revision_20261009/render_validation.json) |
| 独立终审 | [本版逐条要求及结果](REVIEW_v5.1_20261009.md)，15/15 PASS；[本版独立审阅记录](../development/paper_v51_revision_20261009/independent_review.json)，绑定v5.1最终HTML，不沿用旧版PASS |

## 修改与重建

- v5.1正文在src/body_v51.html；配图在src/figures_v51.py的V5注册表；组装与排版在src/build_v51.py。v5.0的三份原源码保持不变。
- 在FreeToken目录执行python paper/src/build_v51.py，不手改生成HTML。
- 原ALL九图注册表保留；v5增加T06请求/段分布与K1修复验证面板。旧图9只作K1修复前历史，不伪造修复后零误差曲线。
- 新科学数字引用〔轮次ID｜FTD-20261009-1〕；旧FTD03/04/erratum按新清单绑定继承，旧hypothesis不会被新冷请求测量追认。
- 数据发布不可改；更正另发FTD。旧版本与完整源码不删除。原作者和上游贡献者继续列致谢，不自行改变署名。

## 终审流程

今后每版遵循[论文终审清单](REVIEW_CHECKLIST.md)：必须逐条记录用户对本版的要求、处理结果与位置，不能只核对数字。本版见[15项处理表](REVIEW_v5.1_20261009.md)；v4→v5主版本变化的科学理由及本次文字变更见论文附录C。

## 版本历史

| 版本 | 日期 | 文件 | 要点 |
|---|---|---|---|
| v5.1 | 10-09 | FreeToken_MultiGPU_CoExec_v5.1.html | 15项文字修订：计数口径、M5正确性前置、批不变性、窗口取舍与官方引用；无重测 |
| v5.0 | 10-09 | FreeToken_MultiGPU_CoExec_v5.0.html | K1修复与同结构28/28；T03/T06/T07/T09；98304/87K；三类正确性与已知限制；11图18表 |
| v4.0 | 10-03 | `FreeToken_MultiGPU_CoExec_v4.0.html` | 主题改为多 GPU 协同执行；新增多卡字节守恒、主存预算、组级执行器、原理图；arXiv 排版 |
| v3.2 | 10-03 | `archive/freetoken-4090-agents_v3.2.md` | 开关四格重读；状态层等价；回复 Grok 与 GPT-6 的合并审阅 |
| v3.1 | 10-03 | `archive/freetoken-4090-agents_v3.1.md` | 回复 GPT-6 对 v3 的审阅：条件上界、重叠模型、D14 |
| v3 | 10-03 | `archive/freetoken-4090-agents_v3.md` | 首个终稿：遍数后果、PCIe 预算、排队 |
| v2 / v1 | 10-03 | `archive/` | 早期草稿；GPT-6（Astro）方向稿与协议稿也在 `archive/` |

外部审阅意见在 `openai/` 与 `archive/openai opp/`。其中 `openai/README.md` 与 v3.2 逐字节相同，不含新增意见。我们的逐条回复在 `../research/REPLY_*.md`。
