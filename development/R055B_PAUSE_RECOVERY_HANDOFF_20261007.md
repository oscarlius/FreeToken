# R055b pause/cancel/recovery supplement

Entries: `development/r055b_owned_launch.py`, `development/r055b_gate_d06_prepare.py`, and `development/r055b_pause_recovery.py`. They consume only R055a's sealed
manifest, round SHA, history and R-v2 metadata; it does not reread old raw arms
or rerun the six cold arms. Pin before server work: `E2-R055a-gate-D06_v2.json`
(round `0c7467a2...`, R-v2 `10161a2f...`).

The model-serving process must construct `ModelProcessMemory` with its own
imported `torch`, then call `run_pause_cancel_recovery` using the same private
port callbacks used by R055a. It writes before/after/error JSONL records around
the cold-before, pause, cancel, and recovery requests. It records CUDA free,
total, allocated peak and reserved peak, UID, device and nanosecond timestamp.

`r055b_owned_launch.py` now replaces the inherited six-cold-arm execute with a
pause-only directory setup, then reuses the owned R055 lifecycle for one
`PAUSE_ON` service. Its arm-local `r055b_pause_observer.py` keeps pause backend
observations and hooks the real Engine constructor plus scheduler request and
delivery boundaries. Route trace is removed; `FT_DEV_PAUSE_ENDPOINT=1` remains.

The proposed sealed `round.results.cuda_memory_summary` contract is
`ft_r055b_cuda_memory_summary/v1`: one service birth/device, model-loaded and
request event rows, total/min-free/allocator peaks, and complete coverage of
cold-before, pause/cancel, and recovery. Error-only or mixed-birth evidence
must fail review.

CPU command: `python -m pytest -q development/tests/test_r055b_pause_recovery.py`.
Server file-only command (after source sealing): `python development/r055b_owned_launch.py --dry-run`.
Formal controller command: `python development/r055b_owned_launch.py --run`; it spawns the same file with `--owned-child`.

Freeze minimum: the three R055b files, `r055a_dryrun_base_v1.py`, frozen
`r055_owned_launch.py`, `r055_gate_d06_prepare.py`, `d07_g3g4_prepare.py`,
`t16_private_port_base_runner.py`, `t17_d14_runner.py`, and
`t17_d14_observe.py`. The new observer copy is writable only while it is
instrumented, then frozen `0444`. It disables route-trace by omission and
retains the pause endpoint via the inherited pause startup chain.
# 07:13 实际交付修订（优先于下方早期草稿）

用户第九节批准 E2-R055b-gate-D06 仅补 PAUSE_ON。正式入口为只读 `/data2/FreeToken/runs/dev_R055/r055b_real_path_source_v1/r055b_owned_launch.py`，cwd `/data2/FreeToken`、dell UID1000。`--dry-run` 和 `--run` 共用暂停臂 pre-Popen 文件准备，不执行六个已封存冷臂；R055a 最新 v2 pin／round／MANIFEST SHA 和 D04 history 固定绑定，原始 tensor 不再读。

冻结源 MANIFEST SHA256：`1f252bc8ac0150f395f2d222ef69a027274e171ec9d1e4cb12e7d329ceb21299`。Linux CPU 报告 `/data2/FreeToken/runs/dev_R055/r055b_real_path_cpu_v1/report.json`，SHA256 `9bca71af2ce9caac35fb8fae0966abfbca9b1b930073ea14260dddbd0ce3de26`，10 PASS。检查实际 exec 生成的 Engine／Scheduler 观察器、取消边界、文件写入路径、trace 关闭及缺失／错误原始内存记录的拒绝；实际 adapter import、native provenance、工具 MD5 和保留冷臂元数据检查通过。下方旧 callback 模块的 3 项测试不属于正式启动证据。

PAUSE_ON 在 GPU worker 记录 model_loaded、request_before／request_after、pause_before／pause_after、cancel_before／cancel_after 和失败事件。每行包含 owner service_birth 与实际 worker_birth、UID／request_id、device、time_ns、mem_get_info free／total、total-free、当前 allocator 占用与累计 allocator 峰值。峰值明确为 Torch 累计峰值及 driver 使用量的最大采样值。模型构造失败不会发 model_loaded；prefill 之前记录 request_before，完成回复后记录 request_after。

32K 原协议保持 built 32052、actual input 32064、max_tokens 128、memory-ratio 0.88。实际服务 clean_environment 强制 pause=1 并去除 route trace，包含生成观察器的输出路径。GPU loader 和每次实际请求均由服务进程观察，不能另起 CUDA 上下文替代。末尾 `cuda_memory_summary.json` 及 pause_gate 保存事件、案例和原始 JSONL SHA；后续 D04 将其纳入 round.results.cuda_memory_summary，以供 T06 仅读封存元数据计算配置。

下一步：R051 放锁后执行最终源 `--dry-run`（不启动模型／拿锁／分配 batch／创建正式目录），R 绑定实际回执及源码后签 `/data2/FreeToken/runs/dev_R055/reviews/E2-R055b-gate-D06_startup_review_v3.json`。只有之后才 `--run`。本段不声明已通过真实空跑、R 启动复核或 GPU 门。

