> 10-09晚间更新：D09/D10及X-STRATA-R002-mini已批准，GPU按[新队列](../plan/EVENING_DIRECTIVE_20261009.md)；mini在v0.1.39的无MTP HTTP服务被源码门阻塞，未测。推送仍待10-10 09:00观察报告后的申请与批准。下文“Strata未批”仅是旧状态。

# E2 发布方案（481d3a7已重新部署，冒烟通过）

**最终状态（2026-10-09晚间）：481已恢复serving，最终恢复冒烟1 passed/0 skipped、独审PASS，首次冷基准行结构/SHA/usage一致。** R045已完成4请求，decode22.42/22.53/22.03/22.21 tok/s，not_met。R067c原轮与两次工装重试均failed_harness，实际分别1/1、0/0、1/3，0可比较格，完整原始/D04封存；重试额度耗尽，不再自动GPU重试，≤64与论文C3仍待证。最终恢复审批RESTORE481-E2-R067c-20261009-03。只读观察已启动至2026-10-10 09:00，推送待观察后用户批准；Strata未批。详见[R045结果](R045_RESULT_20261009.md)、[R067c结果](R067C_RESULT_20261009.md)。

依据：[13:00 指令](../plan/RELEASE_DIRECTIVE_20261009_1300.md)。完整起停与分时步骤见[统一操作手册](DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)，[发布说明](RELEASE_NOTES_E2_DRAFT_20261006.md)只陈述已验范围。本次更新前的方案、回滚手册、说明、候选草稿与 README 已原字节归档至 `release_history/pre1430_20261009/`，不再把历史待批状态混入当前操作段。

| 项目 | 本次准备与证据 |
| --- | --- |
| 身份 | release/e2=481d3a7；保留 rollback `/data2/FreeToken/src/FreeToken`=184c965。工装 effb996、E3 8f6a912、D20 修复均不自动合入。 |
| 托管 | `setsid -f` 启动专用 supervisor；代码强制独立 session/group，处理 TERM/INT/HUP。服务也有独立进程组，使用冻结 D07 生命周期清理。 |
| 日志与 PID | 每次新建 `/data2/FreeToken/runs/production/<审批号>/`；`serve.log`、`owner.json`、`stopped.json`；supervisor 输出 `<审批号>.supervisor.log`；活动 PID/出生/PGID/session 文件 `/data2/FreeToken/run/production.active.json`。 |
| Restart/停止 | 外层 `Restart=no`；内部已验 OOM worker 恢复保持开启。TERM 120 秒，KILL 30 秒，操作命令总等候 220 秒；失败保留证据、写 quarantine 并阻断重启；finally 仅清理本次自有 lock/active，foreign lock 不碰，不启动回滚。 |
| 环境 | `os.environ.copy()` 后剔除所有 `FT_*`、`PYTHONPATH`、`CUDA_VISIBLE_DEVICES`，重设 FT venv、对应源码路径、GPU0、MASTER_PORT8096、unbuffered/禁写pyc；保留必要 CUDA/动态库及宿主环境。发布和回滚使用同一函数，不使用空环境。 |
| 发布配置 | 内网 `172.16.108.9:8095`，TCPStore8096；taskset1,3-47，offload NVFP4 Triton，PLE pinned，98304/.88，running/graph2，层优先4096，special-token checkpoint，mamba host slots0。 |
| GPU 分时 | supervisor 原子取得 `/data2/_shared/gpu.lock`，token含production owner/审批号/PID出生；E3共用锁存在即排队，禁8095/8096。生产常驻；已批准测试由Codex按16:30授权自行记录操作号→停止→测试→恢复481→与首次冷基准比较冒烟。无需逐次报批。 |
| 鉴权选择 | 按二选一要求选择内网地址绑定，未添加 key 或修改 iptables；不绑定0.0.0.0。内网地址并不提供用户级鉴权。 |
| 冒烟 | 维护独占时段，官方 SDK 采集沿用 R066；执行由 `run_smoke.py` 编排：health、512提示/128输出、8257提示/128输出；绑定活动记录、活PID、实际argv、日志，首轮日志无prefill；每次new/cached行数与token总量精确核对，cached缺失不填0。保存SSE、usage、正文SHA和冷日志窗口。 |
| 回滚 | 完整停止命令等待GPU计算进程/8095/8096/锁/PID记录全部释放，再启动184c965；普通8192、窗口49152，使用同样环境清理/内网绑定/托管。量化触发见手册。 |

最终 OPSv8 在本地和 FT venv Linux 均为 **65 passed，0 skipped**，H2 PASS 见 `development/deploy_conditional_20261009/H2_GATE_ALIGNED_RECEIPT.json`。当前运行使用 OPSv8，路径为 `/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2`。common manifest SHA 为 `a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18`：release 与 cold D20 仅共用 gate 精确匹配的 `_cpu_moe` `10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4`、`_pinned_tensor` `07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68` 两个实体；row_store 已从该 pinned 发布配方移除。此前三扩展只归档于 `/data2/FreeToken/runs/dev_release/binary_alignment_20261009_gate_v1/before_recompiled`。

row_store 是通用 disk 默认路径所需组件（`model.py:225/228`、`ple_disk.py:115` lazy import、`row_store.py:16`），但当前 pinned 发布配方只走 `model.py:256/258` 的 pinned load；其不在本次二进制 manifest。该限定由 `development/deploy_conditional_20261009/ROW_STORE_FROZEN_CPU_PROOF.json` 绑定，不外推至 generic default disk。

## 冒烟与失败即回滚

首次部署先限制业务方访问，待启动/健康维护状态为serving后执行两条冷请求。生产running/graph2的 `cold_baseline.json` 是首次现场基准，本次实际冷基准文件SHA为df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97；short/long SHA与usage见重新部署结果，不以R066历史graph4 SHA替代。恢复同一发布配置时逐项比较首次冷SHA和usage；回滚模式独立基准，不跨版本比较正文。任何HTTP/SDK/finish/usage/非法字符/缓存证据/身份或配置检查失败，都停止放量，按已批准手册回滚；原失败文件保留。它验证明确的两条接口契约，不代替业务任务合规。

## 已知限制与默认值

- T17逐位证据覆盖已测现算尾段≥65；≤64（含1）与同结构冷参照的GPU正确性仍待证。D20 CPU调度修复在独立开发树，未合入481，不改变发布范围。
- 并发或前缀命中时，temperature0正文不保证与独立冷请求相同。冷可复现、同结构热冷、并发无串号分别记录；R066c分类c的五条回复均有字面文法异常，不能声称普遍任务合规。
- 双会话已测最低剩余约378MiB（R058场景采样377.7MiB），由OOM恢复兜底；该数不是任意业务下的连续最低保证。R056 87K单请求约0.357GiB样本另列，不能混用。
- OOM故障注入只在chat路由做过一次（R061f），其余公开路由测试不能当成分别做过故障注入。R061f绑定481，现场发布树和候选树默认均为队列上限128、ready等待900秒；R061f结果显式timeout900，实际观测排队1。此为默认值一致，不是128并发压测。[默认值回读](/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340/evidence/oom_defaults_readback.json)。
- 98304窗口上限仍拒绝越界；R056完整87100提示已测。32K解码中位34.33tok/s，对历史73728窗口38.30下降约10.4%，只作跨窗口披露。
- 旧not_met/failed_harness及原FTD03/04/erratum保留。FTD-20261009-1和论文v5/v5.1交付不构成部署批准。

## OPSv2 生命周期、H1 和 H2

当前服务器封存 OPSv8 位于 `/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source`；CPU65 passed/0 skipped覆盖 H1、M1–M4、LOW、H3 和工作树白名单。启动前 `validate_worktree` 精确绑定路径/commit/manifest：仅允许 `__pycache__`、`.pytest_cache`、`*.egg-info`，以及 manifest 中相对路径加 SHA 的普通实体 `.so`；任何其他 ignored/untracked、tracked 变动、路径逃逸或 symlink 均拒绝。正、反 rollback 冒烟均独立导出七变量（含campaign），资源释放最多60秒，停止全程220秒；signal先于lock，finally仅清own lock/active，失败quarantine阻断新启动。

H2 已通过：release 与 rollback 在相同白名单下完成 before/after 验证，允许缓存条目与 hash 绑定实体扩展，未清理工作树；完整回执为 `release_e2_ops_v2/h2_allowlist_evidence_v2/h2_receipt.json`。rollback `stream_completion_chunks` 保留 `include_usage` gate，CPU模拟确认 include_usage=true 产生三字段 usage；68 条历史 Prefill 正则仅是日志解析证据，不能当作 HTTP/API usage 证据。

## D20 与 GPU 队列

R067 的 b132/b133 保持历史 failed_harness。E2-R067b/batch134 实际启动 1 个 service，但复制 artifact 时内层 `for name` 覆盖 controller service name；根代理在加载阶段按已验证 PID 出生身份 TERM controller，未发 generation。终态为 failed_harness（累计 3 service、1 request attempt、0 valid generation/0 comparable cell），cleanup_errors[]、GPU 4MiB/compute PID 空、锁已释放。原始、独审和 D04 封存于 `/data2/_shared/runs/ft_rounds/E2-R067b`，MANIFEST SHA `758cfe94af76300fe8b9289073abf2ec20a0e274e82a11bf71816afd17821235`、round SHA `6191e46d2a4011f97ca48eb5737147ff65a9b8cd0e95e37e22f70d03f5b35149`。artifact_name 修复只形成新 CPU v2 文件，local/Linux 各5项和独审通过，未改冻结旧工装；本轮已消耗 1 service，完整重跑需10 additional、超原后缀cap；用户已批准新R067c独立10/14范围；16:30取消逐次停服报批，b135已运行并因seed日志序列计数工装错误failed_harness，1/1、0可比较格，生产恢复及首次基准冒烟通过。retry1/b136因旧argv摘要失败0/0；retry2/b137经新CPU/独审准入后1/3，服务切换bind错误failed_harness。两个工装重试额度用完，三轮D04封存、481三次恢复及首次冷基准冒烟通过；不再自动GPU重试。≤64 与论文 C3 继续待证。详见[R067实测报告](../plan/01_测试与调研/results/T20-E2-R067_20261009.md)及[部署复核](DEPLOY_REVIEW_20261009_1430.md)。

R045 的旧 v18 已在 reserve 前被 R040g canonical `failed_harness` 阻断，实际0服务/0调用、无批次/锁/GPU，原件停止保留。替代R045按16:30指令直接打既有481服务，2组×2并发共4调用，已完成并独审not_met；decode22.03–22.53 tok/s，生产未停。Strata 22服务/345调用仍未批准。

发布门绑定见[E2闭合记录](E2_RELEASE_GATE_CLOSURE_20261009_v2.json)、[候选链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)、[R066c报告](../plan/01_测试与调研/results/T20-E2-R066c_20261009.md)。

本次重新部署冻结源码及当时手册快照保留在OPSv8/source；当前文档的现场状态更新不覆盖冻结源码。生产使用source_manifest SHA029add4d8ca253ae64a8a34350f2287ab9e72acd631f049cc362d7e4921d5429。
