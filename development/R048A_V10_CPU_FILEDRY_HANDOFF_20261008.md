# R048a/v10：CLI契约修复与首次补跑

2026-10-08 09:30:55 已启动 batch106。实际 child `2051222:151754425` 与GPU锁一致；09:31 V0/performance参数解析及API启动通过，09:32正在加载模型。尚无完整测量或D04结论。

R048/b105在CLI分派前失败，0模型服务/0请求/0完成臂，已按独立R终审原地封存。R048a使用交接书§8.4的第一次测量前自主补跑额度，并继续绑定§8.7的R049b固定队列例外。v10只从观察器参数中移除重复的ft可执行路径，传入 `serve` 及原参数；新增R048 failed_harness门，所有既有门、候选、配置和判据保留。

源码为 `development/r048_t09_v10/r048_t09_prepare_v10.py`。新回归直接使用 `write_service_plan` 的输出调用真实 `r046c_t06_ordinary_startup_v4.main`，再由fake CLI检查实际 `sys.argv`；新调用为 `['ft','serve',…]`，旧重复ft调用被拒。Linux完整测试集125通过（包含继承测试），本地113通过/12 POSIX跳过。

| 证据 | 位置或SHA-256 |
|---|---|
| Linux源码目录 | `/data2/FreeToken/runs/dev_R048/r048a_v10_cpu_20261008T012432Z/source` |
| v10入口 | `78ce793e2890b0d3527a97666474d1871430a960caf5e974d0e8ca181343f72a` |
| source.SHA256 | `28b36db9b2e65d9540ca14a1fd7a7da7d0aa7c336bbdf249bc4eeccda043db7d` |
| cpu_stage_report.json | `d1b84620f49b055fcc086adefe20ca938638e0e461fc5d7e073512151d85f691` |
| 默认FILEdry | `/data2/_shared/runs/ft_rounds/.dryrun_E2-R048a_98304_v10/dry_run_receipt.json` |
| FILEdry SHA | `b4c049e367a6fe9bdde458894e9c9578f04b2b79550056067803de16266a28fe` |
| 独立启动复核 | `/data2/FreeToken/runs/dev_R048/reviews/E2-R048a_startup_review_98304_v10.json` |
| 启动复核SHA | `21310f9e69774f55355aae22e6146d6e60d084f060d2fb7849a5c58683ca9063` |
| 实际启动回执 | `/data2/FreeToken/runs/dev_R048/launch_E2-R048a_batch106.json` |
| 启动回执SHA | `3b92f9f6f5f5038f9df3d5f21849274689b45bdb9ea87deac7c688a3befe4326` |

CPU使用FreeToken venv、空CUDA可见设备和现有cpu_guard。FILEdry在正式cwd `/data2/FreeToken`、同用户、同冻结入口和精确默认路径执行；R与root均实际无参调用 `require_file_dry_run()`、`admission()`、`require_launch_review()`通过。CPU、空跑和启动签不替代GPU原始测量与终审封存。

## Terminal update — 2026-10-08 09:53:49 CST

Batch106 ended after six V0 performance requests; V0 diagnostic failed during CUDA Graph capture at layers/moe.py:425 (stream synchronization unsupported). No A/B/C/S or diagnostic requests completed. Independent terminal review SHA `713c83b9386f9f98a34b7835535408e72b2e5bb9982d11a8f40f991b0694be65` validates partial observations and failure only. D04 failed_harness closed in place; all 67 original files unchanged and readonly. Closure receipt: `R048A_D04_FAILED_CLOSURE_20261008.json`. Any GPU retry requires new explicit approval and all five arms/two phases in one new round.
