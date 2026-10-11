# 独立全文审查（arXiv 英文稿）

- 审查时间：2026-10-09T23:29:01+08:00
- 范围：`manuscript.md`、`main.tex`、`references.bib`、`CLAIM_EVIDENCE_MAP.md`、`README.md`；并与中文 v5.2 的标题和多卡范围作文本核对。
- 方法：只读静态文本、引用键/环境/大括号检查；未运行 TeX、GPU、HTTP、服务、编译或下载。
- 结论：**SUBMISSION_BLOCKED（本轮不得提交或发布）**。

## 投稿阻碍（必须修复或取得缺失证据）

### [HIGH] 当前 R067d 终态没有写入英文稿与证据表

位置：`manuscript.md:101-112`、`main.tex:41-43`、`CLAIM_EVIDENCE_MAP.md:12-13`。

这些位置仍只记录 D09/D10 为 pending，未纳入今晚 R067d 的实际终态：原始结果为 `failed_harness`（产品异常信号后 root 停轮）、独立语义为 `not_met`；只发生 3 个服务、7 次调用，没有冷态 A/B cells，D12 条件不满足。因而该轮不能构成 D09 GPU 测量、T16/T17 acceptance 或 D12 通过；CPU approval 也不能替代它们。

修复：在 Markdown、TeX 和 claim map 同步加入一条简短的历史/终态说明，并明确它是失败的 GPU harness 轮，不引入任何性能数值或 acceptance 结论。保留 D09/D10/Strata 的 pending 表述。

### [HIGH] 九条被引用的书目记录仍自标为投稿前待核验

位置：`references.bib:7,15,30,38,46,53,60,67,74`；`README.md:11,38-44`。

九个已被正文引用的条目仍含 `VERIFY BEFORE SUBMISSION`。这会使出处、版本或 URL 无法独立复核；README 也把书目确认列为提交前条件。

修复：逐条从原始论文、正式项目页或可复现的仓库 revision 核实作者、标题、年份、eprint/URL 和访问日期，补全记录后删除该占位标记；不要编造 DOI。

### [HIGH] 渲染后的投稿 PDF 尚未产生和审阅

位置：`README.md:38-44`。

本地无 `pdflatex`/`bibtex`，且本审查按限制未安装或编译，因此只能确认源文件静态结构，不能确认文献样式、断行、表格和 PDF 交叉引用。README 将最终渲染 PDF 的独立审阅列为提交前条件。

修复：在允许的干净 TeX/arXiv 环境生成 PDF 后，独立核阅成品；本轮不执行该动作。

## 必须保留的证据边界（审查通过）

- 标题与中文 v5.2 相同；多卡始终写为推导/方案，没有把 1×TP4、2×TP2 或 4×TP1 说成实测，也没有新增 KTransformers 或 llama.cpp 基线。
- R045 的四路实测负结果保持为 `22.030--22.531` decode tok/s per lane，且明示低于严格 `>30` 目标；没有宣称 compute overlap 或多卡扩展（`manuscript.md:152-176`，`main.tex:11`）。
- D09 仍为预测，D10 明示只有命令计划、尚无 server/CUDA/测量（`main.tex:41-43`）。D09 v4 sealed prediction 的 SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9` 不得描述为实测。
- Strata v0.1.41 S1/S2 均明确无 GPU 结果、仍 pending（`main.tex:66,69`）；没有预写 S1/S2 结果。
- 历史 T17 仅限既有结构的历史记录，未由 CPU 检查升级为本轮 T16/T17 acceptance。

## 中等问题与措辞建议

### [MEDIUM] D09 的证据地图没有绑定 sealed prediction 的精确 SHA

位置：`CLAIM_EVIDENCE_MAP.md:12`。

目前地图指向可变的 `CURRENT_PREDICTION.json`，虽已正确标为 proposed，却未把 v4 sealed prediction 的 SHA-256 绑定到主张。补入上述 `edd863…e7cfa9` 和“预测，非实测”可防止后续文件漂移被误读为测量证据。

### [LOW] Markdown 与 TeX 的叙事深度不同，但核心结论一致

TeX 是压缩版；投稿定稿前应把新增 R067d 终态以同一语义加入两份源文件，避免摘要稿与全文状态漂移。

## 静态验证结果

- 正文 `\\cite{...}` 的 10 个 key 都在 `references.bib` 中；没有未使用的 bib key。
- `\\begin`/`\\end` 环境多集一致、花括号平衡为 0、没有 `\\ref`/`\\label` 缺失。
- 使用的宏包均为常见 `article`/`amsmath`/`booktabs`/`hyperref` 组合；这是静态可编译性判断，不等同于已编译成功。
- 未发现硬编码凭据、外部执行、静默降级或将 CPU/预批准状态冒充 GPU acceptance 的文字。

## 建议顺序

1. writer/root 先补 R067d 的失败终态与 D09 sealed SHA 绑定；不得改变其失败含义。
2. 完成九条引用的来源核验。
3. 在允许环境渲染并独立审阅 PDF。
4. 三项完成后再由 root 写入最终 admission；本收据不授权提交或发布。
