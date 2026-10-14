# 本地最终产品与收尾记录

依据：用户 2026-10-14 指令“本地分支合并一下，该删除的就删除。然后保持最终产品状态”。不新增 PR、不推送、不改变部署或论文内容。

## 最终入口

| 目录 | 保留分支 / HEAD | 含义 |
|---|---|---|
| `../../product/` | `release/e3` / `9db0ee776c25afa8d2719ab700b2de7ccc606142` | 已部署产品的精确源码副本 |
| `../../product/` | `release/e2` / `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` | 原产品源码回退点 |
| `../../upstream-flashml/` | `main` / `a7c24b27612769ff25929c39c7cf65ded34aeccc` | 上游 f02 加已交付 #688、#686 的本地合并，未部署 |
| `../../paper-en/` | `master` / `ce1105772d16323641547a080b8056d2a82f81d2` | 论文现有分支快进归一，内容未变化 |

E3 与新版上游贡献属于不同版本，不能把两个 PR 的独立 GPU 验收当作合并版本的 GPU 验收。E3 Git tree 为 `ad0ea70a37110c08c9a211bddf90b32eaa574698`，与线上导出一致。

## 已完成清理

- 退出 40 个旧工作树：39 个经 Git 移除，R067 旧主仓库的剩余目录移入归档。历史主工作树从 `development/e2d01/` 移到 `product/`，保留原对象库与 Git 元数据。
- 删除 51 个本地分支：历史引擎 44、上游引擎 3（含临时集成分支）、论文 4。R067 两个分支随旧仓库整体封存，不计入这 51 个分支。
- 研究仓库移除 40 个旧工作树 gitlink；三个独立的产品、上游、论文仓库保留清晰入口。
- 所有分支及 detached HEAD 在清理前已保存；历史引擎和上游引擎还保留 `archive/finalization-20261014/...` 标签。未提交的三处 D15 源码修改、各工作树审核记录、原有 bundle 均已压缩归档并逐项校验。
- 论文约 45 GB 的忽略数据、中文论文、冻结清单、原始运行证据、恢复包保持原处。未把 D05/D09/D10/D12/D15 等实验合入或启用到 E3。
- Windows 只读 Git pack 使 R067 主目录删除中断；直接递归删除被工具策略拒绝，随后将精确残留路径移到归档。完整 Git 元数据压缩包已在中断前校验，审核恢复临时目录也转入归档。

## 验证

- 合并顺序：`f02fbb1` 快进至 `a4ebbfd`（#688），再无冲突合并 `63858fa`（#686）。两个贡献提交均为最终合并提交的祖先。
- Linux、CUDA 隐藏、单 CPU 线程的相关回归：**1122 passed / 31 skipped**，见 `CPU_FINAL_RECEIPT.json` 与原始日志。
- 首次扩展到整个 `tests/engine`：1238 passed / 33 skipped / 2 failed。两个失败均要求当前测试环境未安装的 FlashInfer；在未修改的 `f02fbb1` 上逐项复现同样失败，见 `CPU_BASELINE_RECEIPT.json`。未安装新依赖、未修改测试来掩盖失败。
- 独立审核实际恢复了历史 bundle 上的 D15 未提交补丁；浅克隆上游也按浅历史恢复流程通过 checkout 与 connectivity fsck。清理脚本的备份校验、路径范围、删除前置条件经独审通过。
- 新增收尾代码、文档、JSON 及实际合并代码的 `diff --check` 通过。纳入版本管理的既有 SSE 原始记录含协议空行、原 patch 保留上下文空白、旧审核 Markdown 保留换行空格，原始 pytest 日志保留错误栈中的空白；全量归档检查会报告这些格式项，原件未格式化或重写。
- 四个保留仓库 `git fsck --connectivity-only` 通过；产品、上游、论文工作区干净；研究收尾记录随后本地提交。
- 17:29:08+08:00 查询现网：E3 身份、active JSON、实例 ID 均未改变，`maintenance=serving`、epoch=0、restart_attempts=0；Ollama 停止。整个收尾没有停服、生成调用或 GPU 测速。

## 归档与恢复

归档根目录：`../../archive/local_finalization_20261014/`。`ARCHIVE_MANIFEST.json` 对归档文件逐项绑定 SHA256；原件未删除。

| 子目录 | 保存内容 |
|---|---|
| `deployed_product/` | 从现网导出的 E3 bundle |
| `historical_engine/` | 历史引擎所有 refs、37 工作树的修改/未跟踪文件、补丁与回执 |
| `upstream_engine/` | 清理前 refs、两贡献工作树、最终合并 bundle、浅历史边界 |
| `r067_retry_engine/` | 独立 R067 仓库 bundle、完整 `.git` 压缩包、两工作树回执、残留目录 |
| `research/`、`paper/` | 清理前各仓库 refs、bundle 与状态 |
| `review_restore/` | 独审使用的恢复副本，留存于归档 |

完整历史 bundle 可以直接克隆；浅克隆的 `upstream_engine/integrated.bundle` 必须配套 `shallow.txt`，按独审实际验证的顺序恢复：

1. 在新的空目录执行 `git init`。
2. 将该备份非空 `shallow.txt` 原样复制为新仓库的 `.git/shallow`。
3. 在新仓库执行 `git bundle unbundle <bundle绝对路径>`。
4. 用 `git update-ref refs/heads/main <记录的HEAD>` 恢复分支，再 `git checkout main`。
5. 执行 `git fsck --connectivity-only`。

旧工作树的恢复：从对应 `all_refs.bundle` 恢复原 HEAD，参考 `receipt.json` 取回 `working_files.tar.gz` 中的文件；`index.patch`、`worktree.patch` 与 `head.patch` 保留原暂存状态及差异。不要把未验收的实验快照当作发布版本。

本目录脚本是这次收尾的执行记录，已消费，不能再次执行删除或服务导出步骤。
