# warm2 只读核查与发布门处置（2026-10-09）

**处置：按用户 08:30 的新口径，将 warm2 从本次正确性发布门移除；稳定专家命中与收益验证转 E3 / D15。** 依据是现有 warm 初始化没有建立“稳定槽命中”的前提；无稳定命中时，warm 与 cold 执行同一 split 预取流程、全部专家行走 host→GPU miss 拷贝，实际 warm_0 的统计符合此路径。不能据此宣告正命中分支已验收，也不能把零计数直接判成专家缓存失效。R040h canonical 仍为 `pending_review / indeterminate`；旧失败判词、raw、history 与 pin 保留，不改判。R056 原 `measured` 及性能数字不改。

**计数到底统计什么。** `prefill_hit_rows` 只在 `_prefetch_split` 中累加：每次预取一个 MoE 层，读取 chunk 开始时该层 **全部 E 个专家**的槽映射，`slot >= 2E` 的行数进入 hit；`prefill_total_rows` 加 E。它统计可以由稳定 GPU 槽向双缓冲 D2D 取数的专家权重行；不是 token 数、路由选择次数、驻留层数或 prefix cached tokens。槽位 `<2E` 是会被覆盖的双缓冲，一律视作 miss。`reset_stats()` 清零；不受 `moe_collect_stats` 开关控制。prefix 命中另取 `req.cache_handle.cached_len`。[1][2]

**默认及实物路径。** 源码类默认 `moe_prefill_hit_d2d=false`，但发布性能 R056 三个服务的真实参数均为 **true**，不能把源码默认当作发布配置。offload 启动将完整专家 banks 放在 host，使各层专家可用，再按预算分配 GPU slot pool；**CPU/host 全专家可用、GPU 某些专家驻留、稳定槽 hit 是三件事**，没有把所有专家预装 GPU；模型 warmup 结束还会 reset slot map。[3][4] R040h 人工 warm 先 reset，再每个 eligible 层仅装 expert 0：48 个专家行，不是 48 层的全部 24,576 个专家。cold 则只 reset；两者没有专用 warm/cold 计算入口，均通过 `begin_prefill → prefetch_prefill_layer → _prefetch_split`，由稳定槽映射决定 D2D hit / H2D miss。[1][5]

**R040h 能证明及不能证明的事。** 原统计是 hit=0、total=24,576（48×512），所以 split 确实执行；“计数器未启用”“整次都 fallback”“expert 0 没被 router 选中”不能解释本次零 hit。[1][6] 当前 LRU 源码 reset 后按 usage / 槽号选择低槽，因此该 48 行初始化预期落在 0–47，全部低于双缓冲阈值 1,024；这解释为何普通 residency 不等于稳定 hit。[7] 本次未加载原 residency tensor，也未读取原执行时依赖的冻结槽分布，故该低槽推导不升级为历史根因终审。若后续已有实物证明稳定槽本应命中却仍为零，则按用户口径登记 E3 / D15 性能问题，继续不阻塞本次正确性发布。**不新增 primer、collector、模型运行或 GPU 重跑要求。**

**来源（2026-10-09 只读；候选 481d3a7；计数、预取与 MoE 层源码和 R040h / R056 候选无 diff）：**

1. `/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/moe/offload_cache.py`：955–962（激活与 snapshot）、980–1009（分支）、1084–1088（唯一累加点）、1118–1148（miss 拷贝）、1249–1251（清零）；`/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/layers/moe.py`：432–443（统一入口）。
2. `/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/scheduler/prefill.py`：424–443（prefix cached tokens）。
3. `/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/engine/config.py`：47–52（默认）；`/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/engine/engine.py`：683–695、725–749（host banks / slot cache）、1375–1378（warmup reset）。
4. `/data2/_shared/runs/ft_rounds/E2-R056/production/serve_args.txt`、`/data2/_shared/runs/ft_rounds/E2-R056/cold87_0/serve_args.txt`、`/data2/_shared/runs/ft_rounds/E2-R056/cold87_1/serve_args.txt`：均第 2 行（实参 true）；`/data2/_shared/runs/ft_rounds/E2-R056/round.json`：135、151（measured / release_approved=false）。
5. `/data2/FreeToken/runs/dev_D16/r040h_v1_cpu_20261008_1610/runtime/d16_exact_service_startup.py`：222–261（warm/cold 初始化）、303–307（原统计）；`/data2/FreeToken/runs/dev_D16/r040h_v1_cpu_20261008_1610/runtime/d16_native_process_collection_v6.py`：377–387（原 warm 正命中谓词）。
6. `/data2/_shared/runs/ft_rounds/E2-R040h/dev_D16/native_cache/warm_0/capture/expert_cache/initialization.json`、`/data2/_shared/runs/ft_rounds/E2-R040h/dev_D16/native_cache/warm_0/capture/expert_cache/terminal_stats.json`：均第 1 行；`/data2/_shared/runs/ft_rounds/E2-R040h/round.json`：435、449–453、473–478（现判与历史保留）。
7. `/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/moe/offload_kernels.py`：19–39、239–246（LRU 调用 / reset）；`/data2/FreeToken/venv/lib/python3.10/site-packages/flashlib/kernels/slot_cache/triton/lru_ensure.py`：102–118、187–204（槽号 tie-break / 低槽分配）。

本页仅核对源码、已有封存小统计和参数；未访问 HTTP、加载权重或 tensor、运行业务测试、修改远端证据或产品。
