# R046 暂停调度修复候选及正式验证影响

可审查开发候选：`fix/e2r046-dev-pause-flow@effb9969706922ddad9e59b96377e46469ebe97f`，父提交为已定版 `0aa23431e5b800797543bdecbf35a01045131d7d`。独立本地工作树为 `development/e2r046_pausefix/`。定版工作树保持 0aa 且干净；未推送、未同步生产、未激活模型服务。

唯一源码变化是 `python/freetoken/scheduler/scheduler.py::_receive_dev_messages`，16 行新增、4 行删除。先处理同批 pause/cancel 控制消息；只有暂停正在活动或有 pending pause 时暂存普通消息，其余直接处理。没有暂停时普通请求不会再永久等待。

最初的补丁文本 hunk 格式错误，实际 `git apply --check` 拒绝。新 `development/r046_pause_scheduler_fix_draft_v2.patch` 从实际 Git diff 生成；原补丁及旧冻结证据保留。新回归每例先实际应用该 patch，再核对仅这一函数变化，随后运行实际候选调度器方法。六项 Linux CPU 回归通过，覆盖普通流、同批暂停控制优先、活动窗口、单次释放、实际取消、过期恢复。新报告：

`/data2/FreeToken/runs/dev_D07/r046_actual_patch_cpu_20261007_0111/report.json`

SHA：`4adbbbd53773eb91064788a4f9411799e3ae331c4ab3e866189b2cf42b774c6e`。

正式验证影响：

1. 现有 T17 28/28 kept、R041 kept 和 R040 已测部分均绑定 0aa，不自动变成 effb996 的证据。R040 的 failed_harness 与发布依据裁定保持原样。
2. scheduler 属于 T20 五个受约束目录之一，因此新候选不能使用「五目录无改动」的四组减测条件；如将修复提交作为正式新候选，应按计划重新确定完整续算验证及对应前置门。
3. 队列工装的候选 SHA、精确 tag、清洁工作树、前置 round pin 以及 D08/D15 的基线绑定均需重新核对。不能只替换某个脚本的 CANDIDATE 常量，然后沿用原轮次放行。
4. 新正式轮次号、队列调整和是否采用新验证候选须用户裁定。当前不分配新 GPU 批次、不启动 R046a 或后续门。
5. 若维持 0aa 定版而另用开发工装修复暂停路径，须明确记录运行时适配器及其原语义等价证据，并先经独立 R 复核；目前没有该方案的启动放行。

目前只有开发候选与 CPU 修复证据，尚无 GPU 行为验证或发布放行。
