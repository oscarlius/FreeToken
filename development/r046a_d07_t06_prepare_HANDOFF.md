# R046a §十本地 draft 交付

依据 `plan/CODEX_HANDOFF_20261006.md` §十（10-07 08:40），R055 到此结束，R055a/R055b 保持 `failed_harness`。默认路径依据仍是 R055a 的六个逐位冷臂；暂停开关由 R046a 的四个 T06 臂全程打开作首次实际验证，完整暂停/取消/恢复交给 R045 D06 G3/G4。

本交付只改本地 `r046a_d07_t06_prepare.py`、它的测试与本文；协调日志仅追加。未修改远端 source_v4、任何封存轮次或锁，未发 HTTP、未启动 GPU/服务。服务器读取仅为 date、失败 pin、小型独立 review、R055a round.json 的封存元数据。新 source_v5 的 Linux 冻结、CPU、真实路径空跑、R 签字与启动由根执行负责人独占。

## 准入与真实接线

- 去掉 R055b kept、完整暂停 summary 的前置。沿用 R055b owner 的 `require_retained_cold`，核 R055a v2 pin、round/MANIFEST、六冷臂 PASS、D04 history；R055b 使用 `failed_harness` 的元数据封存检查。R050/R041 等既有前置继续保留。
- 小 review 固定为 `/data2/FreeToken/runs/dev_R055/reviews/E2-R055b-gate-D06_failed_independent_raw_review_v1.json`，SHA `eada9f216bfc91a90a82b891eb83358f7d6e4d3a0027ba5cc03216f90923e7f5`。只读其中的已复核显存样本，不重新打开旧 observer、JSONL 或业务原始文件。
- `load_pause_observer()` 实际执行已复核 `r055b_pause_harness_v2.install(owner)`，冻结的新 observer 在真实 `UserMsg` 边界记 `request_before`；`model_loaded`、每次请求后的显存与累计峰值继续由同一 GPU worker 采集。
- 每个 T06 服务通过真实加载余量门后，实际调用新 helper `pause_request(port, 1.0, 5.0)`，保留 `pause_completed.json` 再执行已有业务 client。有效 HTTP504 timeout/request_id JSON 会保存，但正常暂停必须 `accepted`。否则标 `pause_chain_failure` 和 `user_disposition_required`，保留原始数据并停止；不将 timeout 当成功，不增加取消/恢复臂。
- T06 新摘要要求请求前后 UID 一一对应、时间有序、同一 service/worker/device、加载样本及暂停 request_id 绑定；seed 至少 12 请求、two 至少 2 请求。原始采样、摘要、暂停回执和 serve_args_diff 进入 manifest。
- service birth 只比较稳定五键 `pid/start_ticks/execution_id/pgid/session`，并核类型、正数及 private group/session；owner 的 `state` R/S 不参与身份比较。任何稳定字段漂移仍拒绝。

## T06 显存预算

R055b 小 review 的真实 total 是 **25,250,627,584 B**（23.516479 GiB），min-free 是 **1,144,717,312 B**。R055a `round.json` 固定 SHA `0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3`；其 verdict_history 原文为 `628 MiB request / 625.69 MiB free`。625.69 MiB 是 OOM 时的剩余，不是缺口。

整数预算如下（625.69 MiB 的字节换算向下取整）：

| 项 | 字节 |
|---|---:|
| R055a OOM 剩余 | 656,083,517 |
| 已有 route 占用估计：R055b min-free − OOM 剩余 | 488,633,795 |
| OOM 未满足分配：628 MiB | 658,505,728 |
| 上两项合计 route 估计 | 1,147,139,523 |
| 额外保守缓冲：256 MiB | 268,435,456 |
| 总 route 预算 | 1,415,574,979 |
| 目标剩余：1.5 GiB | 1,610,612,736 |

`decrement = ceil(100 × max(0, target + route_budget − min_free) / actual_total) = 8`，所以四个 T06 臂的 `memory_ratio = 0.88 − 0.08 = 0.80`。扣完整预算后的预计剩余 **1,749,192,539 B（1.629063 GiB）**；0.81 仅为 **1,496,686,263 B（1.393898 GiB）**，不足目标。`calculate_t06_ratio` 可验证不同 route 成本输入；需要低于 0.80 时直接拒绝并要求用户裁定。

这是跨轮次保守估计，不能当作精确 route 开销或 GPU 证明。T06 模型加载后的真实 worker 样本必须 ≥1.5 GiB 才能调用暂停/业务 client；真实 total 也须吻合。route trace 和暂停开关均持续开启。G3/G4 在 ratio 修改前执行，保持 **0.88**；任何性能测量保持 0.88。每臂 `serve_args_diff.json` 声明 `target_keys.memory_ratio` 并记录以上数值、R055a round SHA、R055b review SHA。

## 冻结所需文件与命令

实际运行包只需以下六个同目录文件，其中最后一个是相对 source_v4 新增的依赖：

```text
r046a_d07_t06_prepare.py
r046_seed_agent_trace.py
d07_g3g4_prepare.py
d07_r046a_file_prepare_v1.py
r055b_owned_launch.py
r055b_pause_harness_v2.py
```

R046a 使用 owner 的冻结 observer 和 metadata-only 六冷臂检查，不调用 owner `_legacy()` 或 R055 retry/controller。`install` 为 `_legacy` 绑定闭包但不会执行它；暂停 HTTP 直接调用新 helper，因此此实际执行链不需要 `r055_owned_launch.py` 等旧 R055 controller 依赖。

新版本目标：`runs/dev_R046/r046a_real_path_source_v5/`；空跑 sibling：`.dryrun_R046a_v5_E2-R046a`；独立启动签名：`runs/dev_R046/reviews/E2-R046a-v4/{review.json,pin.json}`。不要覆盖 v4 source、旧 dry sibling 或旧签名。新签名必须绑定六个实际运行源、`e2_launch.py`、候选 client/analyzer，以及同一路径/用户的精确 dry receipt SHA。

根冻结并完成 Linux CPU 后，以正式用户、正式 cwd 执行（本文不执行）：

```bash
cd /data2/FreeToken
/data2/FreeToken/venv/bin/python runs/dev_R046/r046a_real_path_source_v5/r046a_d07_t06_prepare.py --dry-run
# 独立 R 复核并写入新的 E2-R046a-v4 review/pin 后：
/data2/FreeToken/venv/bin/python runs/dev_R046/r046a_real_path_source_v5/r046a_d07_t06_prepare.py --run
```

本地关键回归：`test_r046a_d07_t06_prepare.py` 与 `test_r055b_pause_harness_v2.py`，并需同目录 `test_r055b_owned_launch.py` 提供 fake-product fixture（后者无需执行整套）。harness 测试的 actual scheduler 在本地 `e2r046_pausefix/python/...`；Linux fallback 为 `/data2/FreeToken/wt/e2base1-p1/python/...`。

本机 CPU 采用 `CUDA_VISIBLE_DEVICES=''`、`socket.socket.connect` 与 `socket.create_connection` 全拒守卫，连同既有 D07/client 回归为 **58 passed / 6 skipped**；6 项仅因 Windows 不支持 POSIX readonly binding。未运行 Linux CPU、真实路径空跑或 GPU；这些仍由根执行。源文件可以直接 `ast.parse` 验语法，无需生成 pyc。

交付 SHA：

```text
r046a_d07_t06_prepare.py
1f433a3ec64bdbb8529aad1cd3650f89a258f47f21676b5d1a3fb6efa4434ab6
tests/test_r046a_d07_t06_prepare.py
68d0ba1e285d6ea6ff08c6e52e0b522c0ad788b120cabd26ab76b0573527a587
r055b_pause_harness_v2.py（只读复用）
709f7004ca654e902fbf5d1e4ae59d3b27f68d86513d8439fa27e81c75ddb6fd
新冻结 observer 内容
cd52524f6b3accf994d7745743f4982ddda1790babd08f749d46fb76337115f6
```


## 根集成：实际执行入口以此节为准

原拟v5包装缺少CPU回归使用的冻结dry依赖，未起服务/取锁/分配批号；其source/report只读保留。最终source_v6仅补该依赖，运行源码不变。实际源 `/data2/FreeToken/runs/dev_R046/r046a_real_path_source_v6`；MANIFEST `4ef7031e42ded1283bc147ea3bd4e7da8dc6baf4c3cc5e943045f29748b97c7f`。Linux89 PASS，报告 `/data2/FreeToken/runs/dev_R046/r046a_real_path_cpu_v6/report.json` SHA `d87afaee263e26b85cb7d985e75b8e6781719ddbf6733351504774b28a6c4209`。

08:46同用户dell/UID1000、cwd /data2/FreeToken，以source_v6入口实际 `--dry-run` 完成；回执 `/data2/_shared/runs/ft_rounds/.dryrun_R046a_v5_E2-R046a/dry_run_receipt.json` SHA `4c4aa768fcb894aded9042c2bc7600c4b74a3a6e7b82a25a7a3b8ad2c3885780`，禁止副作用字段全false。保留原计划dry sibling名称v5；它绑定的是实际source_v6入口，名称不构成源码版本证明。memory_plan预测0.80、256MiB估计缓冲后余量1749192539B（1.629GiB），仅预算，正式请求需真实模型余量样本。

正式执行命令是 `/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/dev_R046/r046a_real_path_source_v6/r046a_d07_t06_prepare.py --run`，必须先匹配独立R的E2-R046a-v4 review/pin与本回执。新运行只补G3-on/G4+T06；旧G3-off及R055a六冷臂保留，不重跑，不把R055失败改判kept。
 
## 根交接：batch80 失败后停止

E2-R046a / batch80 已因 G3-on ratio=0.88 的实际 CUDA OOM，按 D04 原地封存为 failed_harness。新完成臂为 0，T06 未启动；队列等待用户裁定，不使用现有 --run 再启动同一轮次。完整证据见 `../plan/01_测试与调研/results/T06-E2-R046a_20261007.md`。

独立 R 提醒：旧 d07.require_closed_round 的 history-checker 缺失回退仅覆盖 failed R040/R046，R046a 本轮没有归档该 checker。若获准补跑，在新执行源码里绑定并调用既有 canonical D04 writer（SHA `67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff`）核验本轮；不得给已封存 R046a 树补文件或改其 SHA。该事项只登记，当前不实施新批次工装或配置改动。
