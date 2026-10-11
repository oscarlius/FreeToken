# T10 / T03b 关闭链 CPU 修复交接

当前状态：Linux 82 PASS，包含 8 项真实 POSIX spawn/双 SIGTERM 对照。只证明 CPU 源码与工装行为；正式 FILEdry、启动复核、目标模型 GPU 测量均尚未完成，仍需实际前置轮次通过。

## 新入口与修复

| 轮次 | 当前本地入口 | 关键变化 |
|---|---|---|
| E2-R044 / T10 | `development/r044_runtime_v6/r044_prepare_v6.py` | 运行时复制并执行 `t10_capture_startup_v3.py`，关闭回执 schema v3；实际消费者同步验证 v3 |
| E2-R047 / T03b | `development/r047_runtime_v11/r047_prepare_v11.py` | 复制并执行包内 `r052_d0_shutdown_startup_v2.py`，字节与已验证 R052a v7a wrapper 相同 |

两个 wrapper 在 scheduler 运行后只将首次 SIGTERM 转成 KeyboardInterrupt，让原 scheduler/capture 关闭路径执行；重复 SIGTERM 在清理及关闭回执 fsync 完成前被吸收，随后才恢复旧 handler。真实异常仍产生失败回执，外部有界 owned-process 停止机制保留。

RID、候选 `0aa23431e5b800797543bdecbf35a01045131d7d`、98,304/.88 和原测量判据不变。旧运行源及失败开发 stage 不改写。

## 前置修正

T10 原来要求 `E2-R052 measured`，但该轮已永久封存为 `failed_harness`。新入口要求旧 R052 失败元数据 + `E2-R052a measured`，并直接要求 `E2-R040f measured` 来落实任务卡的 T20 完成前置。不能用 T11 的独立 §8.7 顺序例外代替 T20。

T10 的 FILEdry、controller、child 都在继续前检查这些前置。T03b 保留 R041、R040 失败元数据、R046g、R045 和 R044 的门，并直接增加 `E2-R040f measured`，无需依赖尚未产生的 R045 终态文件是否转存了上游 SHA。

## 实际 Linux 证据

最终冻结根：`/data2/FreeToken/runs/dev_shutdown_fixes/root_sigterm_cpu_v2/source`，分别包含 `r044_runtime_v6/` 与 `r047_runtime_v11/`。运行环境为 FreeToken venv、`CUDA_VISIBLE_DEVICES=''`，网络只允许测试进程自建的 CPU fixture listener。

- source manifest SHA：`fe9c12a64fdd9dc16d8147f614de9121b3cf7bbdee0cd64bf49433b020eee42e`。
- 8 项 spawn 回归日志 SHA：`3bb409a224c95529691cdf283fce27a683360b3464206ac01fe26e147a129ae7`。
- 完整 82 项日志 SHA：`cb7e60952e070bdeef71075eefdac4456dc89beefef2445f27edfd4aaea428cf`。
- 本地回执：`development/TAIL_SHUTDOWN_CPU_STAGE_20261008.json`。

T10 回归执行实际候选的 `install_scheduler_capture` 与 `run_scheduler` 函数 AST，替换 GPU 协作者；父进程在 scheduler shutdown、capture finalize、receipt fsync 三个时点分别发送第二次真实 SIGTERM。旧 v2 对照在前两处失败、在 fsync 处被已恢复的默认 handler 终止；新 v3 三处均完整退出并保留终态回执。T03b 对照经过实际新入口的 runtime copy，再执行包内 v2；旧 v1 失败、新 v2 完成。

首个 root 开发 stage 的测试夹具使用 multiprocessing Event 释放 cleanup；旧 wrapper 在 fsync 恢复默认 handler 后被终止，留下夹具共享锁，导致父测试卡住。root 仅停止了验证过 PID/出生标识的该次 CPU pytest，保留失败报告。最终夹具改用文件作为释放信号，不持有可能被 SIGTERM 中断的共享锁；没有改变被测 wrapper 来规避失败对照。

## 固定入口 SHA

- T10 entry：`561a023c8cf28c13b5a191c35938d77b552d794a1dd81d9ec18335dae75fa91d`。
- T10 wrapper v3：`982df2c2baf58632681358eff281755af12dd748ab808feb70109ea02f949690`。
- T03b entry：`05ddf2dbd8b0d3552deb53ef394f9d972686297c861caba9360a470f12c8fe03`。
- T03b / R052a 共用字节的 wrapper v2：`ca08c0aa82d05fd1b1dfa85d945b481eb98a78be2557fac8f92a71db2be0106d`。

以上仅为 CPU 交接，不授予 T10/T03b 正式启动资格。独立 R 已完成 CPU_SOURCE_ONLY PASS：`/data2/FreeToken/runs/dev_shutdown_fixes/reviews/t10_t03b_sigterm_cpu_review_v2.json`，SHA `d53881f492aea60e283c751dfe4c2412e75a5d63856c1ed04b3c27e0af80aa5b`，0444。R逐项核对24个冻结源文件，并独立复跑8项真实spawn均通过；正式FILEdry/启动/GPU资格仍为false。
