# 条件部署二进制前置核验

审批号：`DEPLOY-E2-20261009-COND-01`。前置仅 CPU 执行，PASS；真实部署/冒烟结果另行记录。

release-e2 和 D20 冷树均复制 gate e2oom-protocol-restart 中的两个普通实体，并比较完整 bytes 和 SHA256：

| 扩展 | SHA256 |
| --- | --- |
| `_cpu_moe` | `10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4` |
| `_pinned_tensor` | `07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68` |

两树 `_row_store` 已移除。三份重编译实体只在 `/data2/FreeToken/runs/dev_release/binary_alignment_20261009_gate_v1/before_recompiled/` 和原构建目录归档，不用于本发布。

481d3a7 的源码核对（路径均位于 `/data2/FreeToken/wt/release-e2/`）：

- `python/freetoken/models/qwen4_exp/model.py:225` 判断 `ple_backend == "disk"`，`:228` 导入 DiskRowTable，`:243` 构造 disk 实现；`:256`、`:258`、`:262` 为 pinned 表装载和附加路径。
- `python/freetoken/models/qwen4_exp/ple_disk.py:106` 的 DiskRowTable 构造器在 `:115` 才导入 kernel.row_store，属于功能分支内延迟依赖。
- `python/freetoken/kernel/row_store.py:16` 直接导入 `_row_store`。该模块自身不支持缺失扩展后的回退；选择 disk 时扩展必需。
- `python/freetoken/engine/config.py:35`、`:36` 的通用默认值为 disk。本次实际发布 argv 由 `release_config.py` 显式传入 `--ple-backend pinned`，不能省略该参数。

移除后 CPU 阻断两个 row_store 导入入口，真实 CLI/model/其余扩展导入成功；执行实际 load_host_tables 源码方法的 pinned 分支（小型 CPU bank 替身），只导入 ple/weight，未触发 disk/row_store，CUDA 未初始化。因此它对本次显式 pinned 发布配方是可选依赖，通用 disk 配方不适用本结论。

共用 manifest SHA256：`a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18`。OPS v6.1 本地/Linux 全套各48 passed、0 skipped；H2 PASS，rollback usage 判据保留。独立前置审查 PASS。

证据：[对齐回执](ALIGNMENT_RECEIPT_EXACT.json)、[源码/CPU 证明](ROW_STORE_FROZEN_CPU_PROOF.json)、[H2](H2_GATE_ALIGNED_RECEIPT.json)、[独立审查](INDEPENDENT_PREFLIGHT_REVIEW.json)、[已有条件批准记录](DEPLOYMENT_APPROVAL.json)。
