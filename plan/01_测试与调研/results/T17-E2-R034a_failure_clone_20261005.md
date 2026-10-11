# T17 R034a — 失败副本 D04 封存

记录时间：2026-10-05 18:30:25 Asia/Shanghai。判定：**failed_harness，非 T17 等价接受**。

原 R034a/batch63 TimeoutError 后已终止，GPU 锁与原服务进程消失。独立 R 审计 SHA `c3eeb108de07dd0854c5aff99e3ea95ce0007ff438dcfa3a6d7c93ff013fa99a` 复算失败判定。

完整快照独立核验 72,128 个文件 / 85,468,258,776 字节；另建非硬链接 mutable clone，经 R 全量 SHA/大小/类型/独立 inode 核验后，使用冻结 dacfc23cb00f 工具先 audit-first，再 D04 close。

- 新封存目录：`/data2/FreeToken/runs/dev_D16/r034a_close_clone_20261005_175316/E2-R034a`。
- round SHA：`4880d080a8b3dd84baaa7a86446ef860985bdad048f78622cee9e389cefb7509`。
- manifest SHA：`ef543b66223feeee9311259912362fbe6a5695dba2b15b4aef4c7adac91a738c`。
- D04 history check PASS，全部只读；工具重核原始 72,128 文件 SHA 无变化。
- 本地执行回执：`development/t17_r034a_clone_d04_execution.json`，RC0。
- 独立 R 封存后核验另行记录，不据此授予模型门接受。

原 `/data2/_shared/runs/ft_rounds/E2-R034a`、batch63.log、原冻结依赖和只读完整快照均不修改。本轮失败提示工装超时；实际 GPU 根因及优化有效性仍待新版 R035 证明。

## R封存后核验 2026-10-05 18:53:27

独立R复核PASS，仅适用新clone failed_harness。72128原始文件/85468258776字节对preparation map与manifest重核零差异；72157 manifest条目全部校验；只读、无symlink/硬链接；history/audit/stage/launch pins一致。原source身份与只读snapshot不变。外部只读回执 `/data2/FreeToken/runs/dev_D16/r034a_clone_d04_review_r_overlap_4880d080a8b3/review.json` SHA `b5e4eae2422b1a547625e64330309792fa4a8e66839ab5547b613eab22a8566d`。不授予目标模型/T17/T20接受，也不宣称原R034a目录已关闭。
