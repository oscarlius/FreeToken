# 独立全文复审 v2（arXiv 英文源码）

- 复审时间：2026-10-09T23:39:32+08:00
- 范围：修订后的 `manuscript.md`、`main.tex`、`references.bib`、`CLAIM_EVIDENCE_MAP.md`、`README.md`、`CITATION_VERIFICATION.md`、`SELF_CHECK.md`、`REVISION_LOG.md`，以及 `archive/pre_revision_20261009_2330/`。
- 方法：只读文本和静态结构检查；未启动 GPU、HTTP 模型/服务、TeX 编译、远程构建、上传或下载。

## 结论

- **SOURCE_READY：是。** 前次源码/证据问题已修复，当前英文源码可以作为后续受控 TeX/arXiv 渲染的输入。
- **SUBMISSION_BLOCKED：是。** 最终 PDF 尚未构建和独立审阅；本收据不授权提交或发布。

## 已关闭的前次阻碍

1. **R067d 失败记录已完整保留。** Markdown `manuscript.md:114-116`、TeX `main.tex:127-132` 与 claim map `CLAIM_EVIDENCE_MAP.md:14` 一致写明 raw `failed_harness`、独立语义 `not_met`、3 个服务/7 次生成调用、6 次 hot completion、无 cold A/B cell、cleanup 完成而 D12 不满足。三处均明确它不构成 D09 GPU measurement、T16/T17/D12 acceptance 或吞吐结果；CPU-only `c17` 也没有被升级为 GPU 证据。
2. **D09 seal 绑定已补齐。** TeX `main.tex:119` 和 claim map `CLAIM_EVIDENCE_MAP.md:12` 绑定 v4 SHA-256 `edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9`，并写明这是 pre-engine prediction、非 measurement；D10 同样仍是条件推导/命令计划，无 CUDA 或测量。
3. **书目占位已关闭。** `references.bib` 的 10 个 key 均被引用且均有 primary URL；`CITATION_VERIFICATION.md` 记录 10/10 原始页面与访问日期，当前源码没有 `VERIFY BEFORE SUBMISSION` 占位。
4. **前版保存可核验。** `archive/pre_revision_20261009_2330/ARCHIVE_MANIFEST.md` 列出五个前版可写源文件的 SHA-256，归档文件存在。

## 证据边界复核（通过）

- R045 四条每路负结果仍为 22.030–22.531 decode tok/s，低于严格 `>30`；没有被表述为 compute overlap 或多卡扩展（`manuscript.md:160-169`，`main.tex:180-199`）。
- 多卡 1×TP4、2×TP2、4×TP1 始终为方案/推导，尚无 target multi-GPU measurement（`manuscript.md:15,136`，`main.tex:20,148`）。
- Strata v0.1.41 S1/S2 仍是 pending，尚无 GPU result；没有把 upstream MTP option 文档当作本地实测（`manuscript.md:171-175`，`main.tex:201-206`）。
- 未加入 KTransformers 或 llama.cpp baseline；未将 CPU approval 或失败 harness 伪装为 T16/T17 acceptance。

## 静态诊断（通过）

- 10 个 `\\cite` key 全部解析到 10 个 BibTeX 条目；没有缺失或未使用条目。
- TeX `\\begin`/`\\end` 环境匹配、TeX 与 BibTeX 花括号余额均为 0、没有缺失 `\\ref`/`\\label`。
- TeX 为 ASCII，preamble 仅使用 `article`、`geometry`、`amsmath`、`booktabs`、`hyperref`、`url`；这支持静态可编译性判断，不替代真实渲染。

## 非阻断建议

### [LOW] D09 的精确 SHA 尚未逐字写入 Markdown

位置：`manuscript.md:106` 对应 `main.tex:119` 与 `CLAIM_EVIDENCE_MAP.md:12`。

TeX 和 authoritative claim map 已正确绑定 digest，Markdown 也维持相同 prediction-only 边界，因此不影响本次 source-ready 结论。下一次同步编辑时可将同一 SHA 加入 Markdown，以取得逐字证据同构。

## 仍阻断提交的唯一事项

`README.md:38-46`、`SELF_CHECK.md:22-29` 已如实说明：本机无 `pdflatex`/`bibtex`，本轮未安装或编译，最终 PDF 的版式、参考文献输出、表格适配和交叉引用尚未独立审阅。完成允许环境中的 clean render 和 PDF review 前，状态必须保持 `SUBMISSION_BLOCKED`。
