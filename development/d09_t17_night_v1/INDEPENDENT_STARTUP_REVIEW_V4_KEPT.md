# T17 final v4_kept 独立启动审查

- 审查时间：2026-10-09T23:56:36.6502458+08:00
- 范围：`d09_t17_runner_v4_kept.py`、其 T16/D07 依赖、候选工作树绑定，以及本地 FILEdry v7。未启动 GPU、模型服务或 HTTP，也未编译。
- 被审 runner SHA-256：`8c82c4343b5bb212517dc2f60fb7bdba91da7664a3c48613c05bfa237127f5d1`
- 本地与远端同名 runner SHA 一致。远端未见 `evidence_cpu_filedry_v7`，故 v7 仅为本地 CPU 证据。

## Code Review Summary

**Files Reviewed:** 6  
**Total Issues:** 2

### By Severity

- CRITICAL: 0
- HIGH: 2
- MEDIUM: 0
- LOW: 0

### 已闭合的上轮 P0

1. `check_admission()` 现在消费封存的 T16 `round.json` 与 `MANIFEST.sha256`，并验证二者哈希；远端纯 CPU 调用 `validate_candidate()` 已通过。
2. `validate_candidate()` 实际读取候选 worktree，校验 HEAD、已跟踪文件洁净、边界 checkpoint 参数、provenance 和两个 native extension 的字节哈希/大小。
3. 实际路径把每次响应、输入/观测/日志窗口绑定、cell 比较及运行目录 artifact 哈希写入 terminal 前的持久文件。

### Issues

[HIGH] 真实路径没有在进程组停止后重新绑定端口，`post_cleanup_closed` 因而不能证明端口已释放。  
文件：`d09_t17_runner_v4_kept.py:166-180`  
根因：清理只验证 `owned_group_alive(proc.pid)` 为假并写入 `cleanup.json`；没有对 `s['ports']` 执行停止后的 reserve/release 探测。`terminal.json` 仍会无条件写入 `post_cleanup_closed: true`。进程已退出不等于端口在终态可安全复用，也不能发现停止后遗留占用或竞争。  
影响：GPU 锁可能在端口仍被占用时释放，后续轮次会接管一个未被证明清理完成的服务面。  
修复：在确认 owned group 已死后，对该 arm 的两个端口再次原子 reserve，再 release；仅在该步骤成功后写入持久 `ports_released: true` 和 terminal 的 cleanup 成功状态。失败时保留 GPU 锁、记录失败并以非零退出。

[HIGH] FILEdry 未覆盖 controller/child 准入与生命周期控制链，不能证明新封存 T16 gate、原子 child receipt、D07 锁或失败清理在 CPU 路径可执行。  
文件：`d09_t17_runner_v4_kept.py:105-124,137-186`; `test_d09_t17_runner_v3.py:12-28`  
根因：`filedry_v3()` 直接构造 fake sender 和进程，未调用 `check_admission()`、`controller()`、`child()`、`require_closed_round()`、`take_d07_gpu_lock()` 或 child receipt 绑定。现有两项测试仅验证端口预留的正常/第二端口失败释放，不覆盖 v4 的准入或清理控制流。  
影响：本地 v7 的 6 fake process / 8 fake transport / 32-token 结果只能说明比较函数和 FILEdry 自身；不能作为 GPU 准入所要求的“CPU 真实控制链”证据，尤其不能发现封存 gate、receipt 或 cleanup 的回归。  
修复：增加不启动 GPU/服务/HTTP 的依赖替身测试，实际驱动 controller/child 的准入、sealed T16 哈希、原子 receipt、D07 owner lock、失败路径和 post-cleanup port probe。至少覆盖缺失/错配 T16 closure、候选源错配、foreign lock、错误 child receipt、清理失败与端口占用。

### 验证证据

- 本地 FILEdry v7 terminal SHA-256：`b459ca64a26bbcbb8c86df03c7d133888c31f77f71791cffc15f4dfb82e77bcb`；记录 6 个 fake process 已清理、8 calls、两组 cold A/B 和 hot 比较、每 call 32 tokens，并明确 `gpu_started/service_started/http_started/compile_started: false` 和 `product_acceptance: false`。
- 远端只读 CPU 复验显示 runner SHA 与本地一致；远端 `validate_candidate()` 返回候选 HEAD `c17b69a46cd512fbf3d127d3879bce92caae457b`、`tracked_clean: true`、feature flag 和两份 native extension 哈希。
- 现有 `test_d09_t17_runner_v3.py` 的两项端口预留测试通过，但它们不是 v4 控制链覆盖。

### Recommendation

**REQUEST CHANGES — GPU admission denied.** 上轮三个 P0 的源代码修复已验证；以上两个 HIGH/P0 准入条件未满足前，不能启动 T17 GPU 轮次。
