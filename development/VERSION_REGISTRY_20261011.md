# 版本登记表（2026-10-11，KIMI 阶段 1 步骤 1.2）

- 数据源：服务器 `/data2/FreeToken/wt/` 现场只读采集（`version_registry_raw.tsv`，63 个工作树）+ 本地 `plan/02_开发任务/`、`plan/COORDINATION_LOG.md`、`plan/01_测试与调研/` 按提交号交叉检索（`version_registry_xref.json`）。
- 规则：查不到档案记录的字段写"待核"，不推测；不修复、不清理任何工作树。
- "包含 481/bd57"指对应提交是否为 HEAD 的祖先（merge-base --is-ancestor）。

## 0.5 节四个关键版本核对

| 名称 | 工作树 | 手册预期提交 | 实测 HEAD | 干净 | 含 481 | 含 bd57 | 一致 |
|---|---|---|---|---|---|---|---|
| 发布版 481 | release-e2 | 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9 | 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9 | 是 | yes | no | ✅ |
| D05 修复 | d05-decode-align-481-20261011 | 730b58c9（前缀） | 730b58c96527fe5bf117d1f3c2430e405173d28b | 是 | yes | no | ✅ |
| D09 修复 | d09_fix_20261011 | 7d8d389e（前缀，应含 bd57） | 7d8d389ee5d85de7e4f8e533f35c27f4c4c02690 | 是 | yes | yes | ✅ |
| D09 页守恒 | d09-page-conservation-20261010 | bd57cfdccc2a935d46cb0a89b8b36be7a18706de | bd57cfdccc2a935d46cb0a89b8b36be7a18706de | 否（3 处） | yes | yes | ✅ |

结论：4 个版本的提交号均与 0.5 节一致；D09 修复确含 bd57。注意 D09 页守恒树**当前不干净**（3 处改动），batch163 执行时它是干净的，此处按现状记录。

## 全量登记表（63 个工作树）

| 工作树 | HEAD | 提交时间 | 标题 | 干净 | 含481 | 含bd57 | 关联卡片 | T16/T17 状态（批次） | 实测效果/负结果 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|
| d05-decode-align-481-20261011 | `730b58c9` | 2026-10-11 01:58:17 +0800 | test(cache): emit D05 bound lifecycle receipt  | 是 | yes | no | D05 | 未测（本轮 T16 候选 1，见 PHASE2_INTEGRATION_PLAN_20261011） | CPU 修复已交付：16 项 CPU 测试通过，复用位置 13,376→13,504（2026-10-11 凌晨主会话/用户结论）；默认关闭 | 基于 481d3a7 新建，与 D09 分支解耦（D05_D09_FIX_DIRECTIVE 第 64 行裁定）；系谱主会话 10-11 核实：HEAD=730b58c96527fe5bf117d1f3c2430e405173d28b，在 481d3a7 之上恰好 5 个提交（bb7cf6d4→72171f4a→89d3816d→181a510c→730b58c9），相对 481 共改 6 个文件（README、core.py、env.py、scheduler/cache.py、scheduler/scheduler.py、测试），工作树干净 |
| d05_hbug_candidate_20261010 | `bd57cfdc` | 2026-10-10 10:25:08 +0800 | test: verify D09 boundary PLE slot states against CPU cold reference  | 是 | yes | yes | D05 | 待核（本树 HEAD=bd57，即 D09 页守恒提交） | 无独立实测 | D05_D09_FIX_DIRECTIVE 指出此树挂在 bd57 上会让 D05 依赖 D09，已改为基于 481 另建 d05-decode-align-481-20261011；本树不再作 D05 候选 |
| d09_fix_20261011 | `7d8d389e` | 2026-10-11 01:31:40 +0800 | fix(d09): retain radix ownership for exact boundary  | 是 | yes | yes | D09 | 未测（本轮 T16 候选 2，见 PHASE2_INTEGRATION_PLAN_20261011） | CPU 修复已交付：35 项 CPU 测试及真实回放通过，复用位置 20,160→20,282（2026-10-11 凌晨结论）；默认关闭 | 包含 bd57（页守恒） |
| d09-message-boundary-v1 | `c17b69a4` | 2026-10-09 23:02:49 +0800 | test: repeat D09 exact page owner replacement  | 是 | yes | no | D09 | T17 batch153 failed_harness（3 服务 4 调用；热臂 P 边界状态与冷不同）——D09 卡片 07:55 修订记录 | 候选 c17b69a4 的旧边界方案未过 T17 | 已被 bd57 页守恒方案取代 |
| d09-page-conservation-20261010 | `bd57cfdc` | 2026-10-10 10:25:08 +0800 | test: verify D09 boundary PLE slot states against CPU cold reference  | 否(3) | yes | yes | D09 | T16 batch163 kept（E2-D09-T16-reapply-bd57-20261010，8 服务 100 调用，8 臂 sequence/h2d 全 SAME，2026-10-10 20:49 独审封存）；T17 batch164 failed_harness（cached-token 期望 20,282 实际 20,160） | T16 通过、T17 未过；T17 缺口即本次 D09 修复（7d8d389e）的动机 | 现状不干净（3 处改动）；batch163 执行时为洁净状态，本表按现状如实记录 |
| d10-cache-persistent | `54955f73` | 2026-10-10 07:57:12 +0800 | fix: retain D10 lane cache across decode steps  | 是 | yes | no | D10 | batch155 完成首个真实 AIPerf 组（1 服务 2 有效请求），资格门 true，判定 NOT_MET——D10 卡片记录 | 错相位分支已进入但收益未达标 |  |
| d10-eta-481-20261011 | `481d3a70` | 2026-10-09 01:33:38 +0800 | fix restart admission for protocol routes  | 是 | yes | no | D10 | 不适用（HEAD=481d3a7，即基线代码） | D10 η 测量用树；2026-10-11 凌晨 η 工装失败（缓存映射未稳定），无有效 η，不能判断机制 | 与 release-e2 / e2oom-protocol-restart 同一代码 |
| d10-staggered-v1 | `22ff3a38` | 2026-10-10 00:07:30 +0800 | fix: retain pinned PLE ownership in D10  | 否(4) | yes | no | D10 | 待核 | 待核 | 不干净（4 处改动）；另有 4 个 d10-staggered-*.bundle 见 bundle 表 |
| d10-step-metrics-20261010 | `8735b816` | 2026-10-10 10:07:44 +0800 | feat(moe): add opt-in D10 step metrics  | 否(1) | yes | no | D10 | 待核 | 待核 | 步进指标序列 v1；不干净（1 处改动） |
| d10-step-metrics-20261010-v2 | `1fbe8fad` | 2026-10-10 10:21:57 +0800 | feat(moe): defer D10 pair metrics collection  | 是 | yes | no | D10 | 待核 | 待核 | 步进指标序列 v2 |
| d10-step-metrics-20261010-v3 | `c739ecd8` | 2026-10-10 10:22:22 +0800 | docs(d10): bind deferred metrics source hashes  | 是 | yes | no | D10 | 待核 | 待核 | 步进指标序列 v3 |
| d10-step-metrics-20261010-v4 | `041db6e5` | 2026-10-10 10:22:40 +0800 | test(moe): model deferred D10 cache snapshot cleanup  | 是 | yes | no | D10 | 待核 | 待核 | 步进指标序列 v4 |
| d10-step-metrics-20261010-v5 | `12e5b357` | 2026-10-10 10:22:54 +0800 | docs(d10): refresh CPU test source binding  | 否(1) | yes | no | D10 | 待核 | 待核 | 步进指标序列 v5；不干净（1 处改动） |
| d10-step-metrics-20261010-v6 | `77c7c85e` | 2026-10-10 10:23:36 +0800 | fix(moe): return only newly collected D10 pairs  | 是 | yes | no | D10 | 待核 | 待核 | 步进指标序列 v6 |
| d10-step-metrics-20261010-v7 | `a51009eb` | 2026-10-10 10:23:45 +0800 | docs(d10): bind incremental collector source hashes  | 否(3) | yes | no | D10 | batch162 clean 测量（2026-10-10 13:06–13:13）：not_met / valid_negative | 两路各 512 实际输出，预热 16 步后 495 共同 token/路，95.707 s，每路 5.172 tok/s，未严格 >30；正式负结果，不归因为实现缺陷（D10 卡片终态） | D10 原型阶段已结束 |
| d15_lag1_cpu_20261010 | `2831f90c` | 2026-10-10 19:25:15 +0800 | feat(moe): stage D15 lag-one adaptations  | 是 | no | no | D15 | 待核 | 待核 | D15 lag-one CPU 适配序列；不包含 481 |
| d15_lag1_cpu_20261010_76826f8 | `76826f81` | 2026-10-10 19:59:42 +0800 | Fix lag-one step protection and record adaptation copy costs  | 是 | no | no | D15 | 待核 | 待核 | lag-one 修复提交 |
| d15_lag1_cpu_20261010_7eba574 | `7eba574a` | 2026-10-10 20:00:48 +0800 | Assert transferred byte counter in CPU adaptation integration test  | 是 | no | no | D15 | 待核 | 待核 | lag-one 测试加固提交 |
| d15_lag1_cpu_20261010_v2 | `7ba09911` | 2026-10-10 19:52:23 +0800 | test(moe): cover lag-one raw miss reservation  | 是 | no | no | D15 | 待核 | 待核 |  |
| d20_short_tail_v1 | `d50be0f8` | 2026-10-09 13:06:46 +0800 | test: use supported short-tail rewind geometry  | 是 | yes | no | D20 | 待核 | 待核 | 短尾 rewind 几何测试 |
| e1ms | `23f2e2ca` | 2026-10-04 01:00:43 +0800 | fix(moe): seal GPU timeline before counters and JSONL writes  | 是 | no | no | E2 基线 | 同 e2base（同 HEAD 23f2e2ca） | 同 e2base | 与 e2base 同提交 |
| e1r000 | `3c8f2241` | 2026-10-03 09:45:15 +0800 | D3: FT_D3_TRACE donation trace  | 是 | no | no | 早期 E1 | 待核 | 待核 | 与 upstream 同提交 3c8f2241 |
| e1r000b | `40fd5d4d` | 2026-10-03 13:47:33 +0800 | fix(scheduler): declare the d-series switch defaults on the classes  | 是 | no | no | 早期 E1 | 待核 | 待核 |  |
| e1r001 | `184c9659` | 2026-10-03 11:53:14 +0800 | test(kernels): compile the NVFP4 GEMMs at a ragged K in the cross-arch gate  | 是 | no | no | 早期 E1 | 待核 | 待核 |  |
| e1r001b | `80943fde` | 2026-10-03 13:49:22 +0800 | test(kernels): compile the NVFP4 GEMMs at a ragged K in the cross-arch gate  | 是 | no | no | 早期 E1 | 待核 | 待核 |  |
| e1r003 | `c721c743` | 2026-10-03 14:25:21 +0800 | feat(kvcache): keep prefill-chunk GDN checkpoints in a pinned host bank  | 否(3) | no | no | 早期 E1 | 待核 | 待核 | 不干净（3 处改动） |
| e1r003sd | `97bc62c7` | 2026-10-03 19:26:23 +0800 | fix(instrument): serialize dumps with torch.save (bf16 has no numpy scalar type)  | 是 | no | no | 早期 E1 | 待核 | 待核 |  |
| e1r003st | `c30ae0d7` | 2026-10-04 09:46:12 +0800 | fix(tools): support explicit cross-process state uid selection  | 是 | no | no | D03 | T16 E2-R002-gate-D03（候选 c30ae0d7）；T16 R018-gate-D03 以其为父树 | T04 R014/R015、T10 R013/R016/R017 工具轮次均以此为代表 | D03 状态层工具 |
| e1r008 | `f91054ba` | 2026-10-03 23:46:35 +0800 | test(scheduler): verify anchor cut independence and telemetry alignment  | 是 | no | no | T03 | T03 E2-R008 切段开关冷热四格（基线为 E2-base） | 待核 |  |
| e2base | `23f2e2ca` | 2026-10-04 01:00:43 +0800 | fix(moe): seal GPU timeline before counters and JSONL writes  | 是 | no | no | D00/E2 基线 | 作为父树/基线出现在 T16 R002/R021/R022/R041 等门；自身经 T00 E2-R000 立项测量 | E2-base@23f2e2c：T03 R008、T04 R002、T08 R009、T10 R006 等多轮基线 | 第 2 代统一基线 |
| e2base1 | `b9c9248f` | 2026-10-05 19:22:59 +0800 | fix(d16): bound scheduler batch observer receipts  | 是 | no | no | D17 | 无 T16/T17（CPU 复核 PASS：b9 observer CPU/默认关闭范围，协调日志 2026-10-05 19:32） | D17 预集成 observer 树 |  |
| e2base1-ordinary-rewind | `0aa23431` | 2026-10-06 06:01:50 +0800 | fix(d16): bound scheduler batch observer receipts  | 是 | no | no | D17/E2-base.1 | T16 E2-R041-gate-D17 候选（warm/cold 控制同列）；R050/R051/R055/R060b/R064 各门的比较基础 | 前生产基线 E2-base.1@0aa23431；R058 并发显存测量（87K+32K 等三组合） | 后被 481d3a7 取代 |
| e2base1-p1 | `effb9969` | 2026-10-07 01:09:22 +0800 | fix(scheduler): process ordinary messages outside dev pause windows  | 是 | no | no | D06 | T16 R055a-gate-D06 候选（六冷臂逐位复算通过）；T06 R046a（全程开暂停） | 暂停修复测量树 effb996；亦作 R050a/R063 等门的父版本 | T20 R040i/R040j 质量轮候选 |
| e2d03-continuation | `f5067bbe` | 2026-10-04 14:50:59 +0800 | fix(scheduler): retain dev restore metadata across prefill chunks  | 是 | no | no | D03 | T16 E2-R018-gate-D03 候选 | D03 修复候选（Linux 26 PASS 记录于卡片） |  |
| e2d06 | `03692633` | 2026-10-04 15:41:02 +0800 | feat: add multisession probe and development pause control  | 是 | no | no | D06 | T16 E2-R024-gate-D07 的父树 | D06 多会话工装候选（交付记录 D06） |  |
| e2d07 | `fefb19cb` | 2026-10-04 17:23:26 +0800 | feat(trace): export request-bound moe routes  | 是 | no | no | D07 | T16 E2-R024-gate-D07 候选 | 路由轨迹导出钩子 |  |
| e2d07-trace-backpressure | `4fc2320d` | 2026-10-07 19:30:19 +0800 | fix(trace): wait for bounded writer queue without dropping records  | 是 | no | no | D07 | T16 E2-R062-gate-D07：候选 4fc2320 对父 151ee718 在 trace/pause 关闭时 T16 通过 | T06 E2-R046g 候选（12,660 输入 ID 逐位一致 CPU 回归后启动） |  |
| e2d07-trace-lm | `151ee718` | 2026-10-07 15:06:02 +0800 | fix(trace): preserve layer-major route coverage  | 是 | no | no | D07 | T16 E2-R059-gate-D07 候选；R062 中作为父树 | layer-major 预填分块 trace 保留 |  |
| e2d08 | `8bf0ad39` | 2026-10-07 04:23:51 +0800 | feat(moe): observe hybrid task completion  | 是 | no | no | D08 | T16 E2-R051-gate-D08 候选（对父 effb996）；T09 E2-R048/R048a 均 failed_harness | hybrid 任务完成观察候选 |  |
| e2d08-capture-trace | `76af7584` | 2026-10-08 10:06:35 +0800 | test(moe): cover hybrid trace lifecycle ordering  | 是 | no | no | D08 | T16 E2-R051a（父 effb996 对 76af7584）；T09 E2-R048b batch111 判定 measured（独立 R 确认，D04 封存） | hybrid trace 生命周期采集 |  |
| e2d12-short-suffix | `8f6a912e` | 2026-10-08 15:19:16 +0800 | perf(moe): collect unique routed ids only for diagnostics  | 是 | no | no | D12 | T16 E2-R063/R063a（候选 8f6a912e 对父 effb996，4 服务 48 调用，E3 独立分支，独立终审+D04 封存） | 短后缀按需搬运（threshold 0） | 未合入 481 发布候选 |
| e2d13-dense-tp | `7e3db703` | 2026-10-08 16:38:27 +0800 | test(moe): cover NVFP4 TP2 production bank reconstruction  | 是 | no | no | D13 | 待核（GPU 门待 G0） | Linux 50 PASS/1 skip（含真实 build_expert_banks TP2/TP4）——开发卡记录 | dense TP 原型 |
| e2d14 | `e4f32022` | 2026-10-04 20:48:47 +0800 | fix: preserve layer-major prefix checkpoint plan and context  | 是 | no | no | D14 | T16 E2-R021/R022-gate-D14 候选；T17 R023 及 R025/R027/R029/R030/R031 诊断轮 | 层优先快照计划与前缀续算修复 |  |
| e2d14-ordinary-rewind | `a9dca443` | 2026-10-06 05:48:29 +0800 | fix(scheduler): preserve tracked ordinary donor rewind geometry  | 是 | no | no | D14 | T17 E2-R037 kept（R038 记录：retractions=[]）；T17 R038 通过（四类状态逐位一致） | 普通 donor rewind 几何保留 | 亦作 R041 的 warm 控制 |
| e2d14-schedule | `e45e2c21` | 2026-10-05 02:09:40 +0800 | feat(engine): replay observed prefill schedules with equivalence readers  | 是 | no | no | D14 | T16 E2-R032-gate-D14 候选（T17 R033 的前提门）；T17 R033/R034/R034a/R035（含两轮 failed_harness 修复史） | 预填调度回放与等价 reader |  |
| e2d15 | `988c9e18` | 2026-10-07 02:44:45 +0800 | docs(moe): clarify D15 candidate gates  | 是 | no | no | D15 | T16 E2-R050-gate-D15 候选；T21 R049/R049b/R049c 画像轮（R049b PA1 失败后清理通过） | D15 预算/候选门 |  |
| e2d15-adapt-lag1 | `82565530` | 2026-10-08 15:16:31 +0800 | test(moe): verify rollback after adaptive map publication  | 是 | no | no | D15 | T16 E2-R050a-gate-D15 候选（82565530 对父 effb996，四臂 b118） | 自适应 map 发布回滚验证 | 与 e2d15-adapt-slot-move 同 HEAD |
| e2d15-adapt-slot-move | `82565530` | 2026-10-08 15:16:31 +0800 | test(moe): verify rollback after adaptive map publication  | 是 | no | no | D15 | 同 e2d15-adapt-lag1（同 HEAD 82565530） | 同左 |  |
| e2d15-budget-guard | `988c9e18` | 2026-10-07 02:44:45 +0800 | docs(moe): clarify D15 candidate gates  | 否(3) | no | no | D15 | 同 e2d15（同 HEAD 988c9e18） | 同左 | 不干净（3 处改动） |
| e2d15-core-baseline | `23f2e2ca` | 2026-10-04 01:00:43 +0800 | fix(moe): seal GPU timeline before counters and JSONL writes  | 是 | no | no | D15/E2 基线 | 同 e2base（同 HEAD 23f2e2ca） | 同 e2base |  |
| e2d16-readers | `37d46a07` | 2026-10-05 20:03:23 +0800 | stabilize batch envelope fork fixture  | 是 | no | no | D16 | 待核 | D16 batch observer / DevPause lookup 交付（协调日志 2026-10-05 20:03） |  |
| e2d16-tools | `e9ee6aac` | 2026-10-05 02:39:49 +0800 | feat(testing): orchestrate same-structure continuation references  | 是 | no | no | D16 | 待核 | 待核 |  |
| e2oom-openai-restart | `d577e32f` | 2026-10-09 01:25:59 +0800 | fix openai restart admission  | 是 | no | no | OOM | T16 E2-R064-gate-OOM 记录其为 481d3a7 的直接父 | openai 路由重启准入修复 | 自身独立结果待核 |
| e2oom-protocol-restart | `481d3a70` | 2026-10-09 01:33:38 +0800 | fix restart admission for protocol routes  | 是 | yes | no | OOM | 同 release-e2（同 HEAD 481d3a70） | 同 release-e2 | 481 的原始开发树 |
| e2oom-recovery | `608251f0` | 2026-10-07 19:01:56 +0800 | fix: use configured OOM restart readiness timeout  | 是 | no | no | OOM | T16 E2-R060b-gate-OOM：608251f0 对 0aa23431，D0 与生产口径全文/分段一致 | OOM 重启就绪超时修复 |  |
| e2oom-recovery-r061fix | `4c878f6b` | 2026-10-08 05:09:53 +0800 | fix scheduler DEV OOM receipt request binding  | 是 | no | no | OOM | 待核 | 待核 | 名称指向 R061 修复 |
| r047-anchor-debug-20261010 | `b60973dc` | 2026-10-10 01:28:36 +0800 | fix(r047): bind SSE turns and shutdown D0 flush  | 否(7) | no | no | R047 | 待核 | 待核 | 不干净（7 处改动） |
| r067d-retry2-hook | `b86190d7` | 2026-10-10 08:10:31 +0800 | test: bind all donor logical state  | 是 | yes | no | D12/R067e | R067e 系列：batch165 pre_gpu_failed（0 服务 0 调用不扣额度，错误信息称 approved 候选 b86190d）；batch166 failed_harness（3 服务/7 派发/6 完成，donor@P 前置哈希不等） | donor 逻辑状态绑定钩子 | D12 启用路径冻结中；与 r067e-20261010 同 HEAD |
| r067e-20261010 | `b86190d7` | 2026-10-10 08:10:31 +0800 | test: bind all donor logical state  | 是 | yes | no | D12/R067e | 同 r067d-retry2-hook（同 HEAD b86190d7） | 同左 |  |
| release-e2 | `481d3a70` | 2026-10-09 01:33:38 +0800 | fix restart admission for protocol routes  | 是 | yes | no | 发布基线 | T16 E2-R064-gate-OOM 候选（对 0aa23431）；OOM-E2-R061f batch122 注入式 OOM 恢复验收 measured 封存（2026-10-09 独审） | 当前生产版本：RESTORE481-MORNING-20261011-07 运行中（172.16.108.9:8095）；T20 R065/R066a/b/c SDK 系列均以此为代表 | 本轮 T16 的父版本与 hybrid 基线 |
| t03b-rolling64 | `dc951c69` | 2026-10-10 08:14:30 +0800 | test(t03b): inspect the selected track slot after prefill reuse  | 否(3) | no | no | T03b | 待核 | 待核 | 不干净（3 处改动） |
| t03b-uid-source-20261010 | `dc951c69` | 2026-10-10 08:14:30 +0800 | test(t03b): inspect the selected track slot after prefill reuse  | 否(8) | no | no | T03b | 待核 | 待核 | 不干净（8 处改动）；与 t03b-rolling64 同 HEAD |
| upstream | `3c8f2241` | 2026-10-03 09:45:15 +0800 | D3: FT_D3_TRACE donation trace  | 否(3) | no | no | 上游 | 待核 | 待核 | 上游快照（D3 trace 提交 3c8f2241）；不干净（3 处改动） |

## .bundle 文件（只记文件名与 SHA256）

| 文件 | SHA256 |
|---|---|
| d10-staggered-3e7a329.bundle | `d04f4cc7bec4a65b20a4d24998cb3c48289de7150ccea6e0a7df577baec4ce96` |
| d10-staggered-5b59f29.bundle | `ccd7ffa734097e9ae0b2cd4fe6b7b7e91f59c5a78ec2fffeea62279f8b235450` |
| d10-staggered-625c8cc.bundle | `8be2d8eab0af55e9f1cf1fa8ad9306fe2c1dbeefec2f13d60b1f809553aa81f7` |
| d10-staggered-d4f1016.bundle | `1a191848a71fcd5647dacfbd81a59004f1852bdbf07a78036f810bb4c58326bc` |
| d10-step-metrics-20261010.bundle | `2674009f18bd935d9cb91e9785be7c53567e98eebd7eae19786f2f3802cc00e8` |
| d10-step-metrics-20261010-v2.bundle | `62a7bc1ec6419361f16f6093e60ebc6f4c2381652fe969a040ab4b14be25baee` |
| d10-step-metrics-20261010-v3.bundle | `067d854410078c9b5bf5c7368919ab2cc3fd63301efffa52bbd78403ad3539da` |

## 完整 40 位哈希对照

| 工作树 | HEAD（完整） |
|---|---|
| d05-decode-align-481-20261011 | `730b58c96527fe5bf117d1f3c2430e405173d28b` |
| d05_hbug_candidate_20261010 | `bd57cfdccc2a935d46cb0a89b8b36be7a18706de` |
| d09_fix_20261011 | `7d8d389ee5d85de7e4f8e533f35c27f4c4c02690` |
| d09-message-boundary-v1 | `c17b69a46cd512fbf3d127d3879bce92caae457b` |
| d09-page-conservation-20261010 | `bd57cfdccc2a935d46cb0a89b8b36be7a18706de` |
| d10-cache-persistent | `54955f7343fe11c5c0936d18570cfbd826c0f155` |
| d10-eta-481-20261011 | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| d10-staggered-v1 | `22ff3a389eae3724cdca9a45f2e19577082a2032` |
| d10-step-metrics-20261010 | `8735b816baf08761fc6f54b59b70859df47f9802` |
| d10-step-metrics-20261010-v2 | `1fbe8fad34a2ea993e6cb9735dd30633d0a0fd4f` |
| d10-step-metrics-20261010-v3 | `c739ecd8098a6c186ccc75dc58c7e126a6cf9f99` |
| d10-step-metrics-20261010-v4 | `041db6e5fbf3eb6b70fb04af46888a1a02a2f5a9` |
| d10-step-metrics-20261010-v5 | `12e5b357c4bb8f34bee53f255bdfe1290b75531b` |
| d10-step-metrics-20261010-v6 | `77c7c85eb1846dbb77e3432375e15a3a7d016410` |
| d10-step-metrics-20261010-v7 | `a51009eb4fc5ab5864648abe9484ba645a8f88b5` |
| d15_lag1_cpu_20261010 | `2831f90cb5d1969c8131da0a2e5e806098152b82` |
| d15_lag1_cpu_20261010_76826f8 | `76826f81e0abd77544e8f2e4ae5f610e161149a7` |
| d15_lag1_cpu_20261010_7eba574 | `7eba574a740217e0a61f46cf3cb432612bbacadf` |
| d15_lag1_cpu_20261010_v2 | `7ba099112d0faa598ed444142e505425dbcda14d` |
| d20_short_tail_v1 | `d50be0f8f84ab1105f788be8f1354773ad539b63` |
| e1ms | `23f2e2caa3395837c9474735ffc83321f3b9b5a1` |
| e1r000 | `3c8f2241f8f0b462071bb1576086f32135cec7ad` |
| e1r000b | `40fd5d4d1d817124d5b3ba40fcc28de7b283e2b7` |
| e1r001 | `184c965964b5f79deaecf1b1e3e0eda3187c829d` |
| e1r001b | `80943fde81eea41bbadda3523f4d1a666a1f9b49` |
| e1r003 | `c721c743f3808606df41cf7eb2f4b9e8d5a060f8` |
| e1r003sd | `97bc62c7e560c7954ab8d2b3a61d42069ad233b8` |
| e1r003st | `c30ae0d7003c3bbbf56867ce74da797332fa7ed5` |
| e1r008 | `f91054baa615994d82ca43005f9b61bd0d385ae3` |
| e2base | `23f2e2caa3395837c9474735ffc83321f3b9b5a1` |
| e2base1 | `b9c9248f910e8e2f0560087683e761d436fe8522` |
| e2base1-ordinary-rewind | `0aa23431e5b800797543bdecbf35a01045131d7d` |
| e2base1-p1 | `effb9969706922ddad9e59b96377e46469ebe97f` |
| e2d03-continuation | `f5067bbe05da51d5f78185213435a8be095a684a` |
| e2d06 | `03692633df48456fb0baa78de7b64e5628a12ab1` |
| e2d07 | `fefb19cbac6bb1cb08835c411c895310600b3677` |
| e2d07-trace-backpressure | `4fc2320dc0a29422ab61e383e5e1579460e9926e` |
| e2d07-trace-lm | `151ee718b88882b57dba75317bb53c697d5f235f` |
| e2d08 | `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8` |
| e2d08-capture-trace | `76af7584d7595d9cc52dcd60deff3aacdae1d9d6` |
| e2d12-short-suffix | `8f6a912ea6066f192c37dc74435efc9da0c7591c` |
| e2d13-dense-tp | `7e3db7030eb6d4515c19d75fa9a55f43eb6040aa` |
| e2d14 | `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42` |
| e2d14-ordinary-rewind | `a9dca443cd07e1f60d1533e0a678935a09d21636` |
| e2d14-schedule | `e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7` |
| e2d15 | `988c9e183c8dca4415fd9b5d02318b26664da619` |
| e2d15-adapt-lag1 | `825655305d69df94d3d2f79c3f416234bfe890e6` |
| e2d15-adapt-slot-move | `825655305d69df94d3d2f79c3f416234bfe890e6` |
| e2d15-budget-guard | `988c9e183c8dca4415fd9b5d02318b26664da619` |
| e2d15-core-baseline | `23f2e2caa3395837c9474735ffc83321f3b9b5a1` |
| e2d16-readers | `37d46a078dd458bbe663d8d12dc36bdee6fef600` |
| e2d16-tools | `e9ee6aac1786485bb447579f224b0927d8b15cab` |
| e2oom-openai-restart | `d577e32f695019fbeafb0f20ed7eaac08ec547b7` |
| e2oom-protocol-restart | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| e2oom-recovery | `608251f00deea85a0b12b31cc1f43725f45fbf9b` |
| e2oom-recovery-r061fix | `4c878f6b3251cca273d8548e7f5cf58a56711d3a` |
| r047-anchor-debug-20261010 | `b60973dcd5bb5ea8b235ee7581b907f94e5d6a42` |
| r067d-retry2-hook | `b86190d78be3b1b4b55f989c98ce963630e425dd` |
| r067e-20261010 | `b86190d78be3b1b4b55f989c98ce963630e425dd` |
| release-e2 | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| t03b-rolling64 | `dc951c6918ae0fab4ef8f6152c6de198f0f7f858` |
| t03b-uid-source-20261010 | `dc951c6918ae0fab4ef8f6152c6de198f0f7f858` |
| upstream | `3c8f2241f8f0b462071bb1576086f32135cec7ad` |
