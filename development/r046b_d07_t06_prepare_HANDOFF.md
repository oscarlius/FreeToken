# R046b §11 本地源码与 CPU 交付

## 最新§12 v4：实际封存schema与模型配置归档

真实只读字段核对确认：R046a immutable round `01c9dd…` 为 `ft_round/v2`，候选在 `base.commit=effb996…`，没有顶层candidate_commit；pin为 `ft_closed_round_pin/v1`，candidate_commit/verdict/round+manifest SHA完整。v4只接受这一实际结构，绑定base.commit与pin candidate及原SHA，不新增legacy reader、不改原round。共享writer644修复继续保留。源v3/98PASS与第二FILEDRY失败回执 `ed3e7ecd218cc5cd9a5f10edad8267a23b00971c30dc1a9e73d916d42a399fca` 均保留为旧证据。

真实九归档来源已只读逐项核：六胶囊代码、canonical writer、候选tokenize.py均普通文件；唯一overlay配置链接为 `/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json` → `/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json.qwen4_exp.orig`。CLI MODEL_PATH不变，仅runtime_sources使用严格resolve后的普通配置源；归档basename为 `config.json.qwen4_exp.orig`。packet/dry receipt/startup review的 `model_config_source` 需包含且严格绑定 `requested_path`、`resolved_path`、`sha256`。其余来源仍拒绝symlink；没有修改链接、配置或权重，无新增依赖。

当前dry固定为 `/data2/_shared/runs/ft_rounds/.dryrun_R046b_v4_E2-R046b/dry_run_receipt.json`，schema `ft_r046b_dry_run/v4`。R review目录为 `/data2/FreeToken/runs/dev_R046/reviews/E2-R046b-v4`，review schema `ft_r046b_source_startup_review/v4`，pin schema `ft_r046b_review_pin/v4`。正式preflight/result授权文字改为第十二节最新用户裁定，科学配置/门/队列及route manifest/v1不变。旧dry/review schema与错误config映射拒绝。

本机guard26 PASS/19 POSIX skip（Linux单B目标45项），AST2 PASS，CVD空、torch未加载。新回归采用实际round/pin字段形状，拒wrong base/pin/schema及仅顶层candidate；配置普通源与真实POSIX链接解析、requested→resolved映射、归档源/复制路径和SHA均有tmp fixture。旧Linux98不替代新版Linux/第三真实FILEDRY/R；第三次真实FILEDRY若失败按§8停止报告，不继续循环重试。本泳道未执行实际dry或服务。

最终新code身份（RAW=LF，交付后不再修改）：

```text
r046b_d07_t06_prepare.py
2c9d9f4839dca60ab571018d12b7df0f9d400d971045eb2c6d3c48279c1a88ae
tests/test_r046b_d07_t06_prepare.py
bf784b6d8b9b8695ab2bc47174befaf1457d0c5b9f909958efcd9a785bc00e98
```

## 最新§12 v3：共享 canonical writer 权限窄修

根的 source_v2 真实 FILEDRY 在创建 dry sibling 前因共享 `/data2/FreeToken/scripts/round_json_append.py` 为644被拒；SHA仍为67c36b2f…，旧R046a封存元数据全部RO。失败回执 `/data2/FreeToken/runs/dev_R046/r046b_section12_real_path_dry_v2/report.json`（d3a22578…）只读保留；0服务、0锁、0臂、无正式RID，不是测量失败。

`require_failed_r046a()` 现在分别检查封存目录/pin/round/MANIFEST及全部成员的RO、类型、非链接与原身份；外部canonical代码只要求普通文件、路径及父链非链接、既定SHA，再执行原外部D04 history check。644 writer可用，不chmod共享工具、不改旧源/旧轮次。性能比例、窗口、候选、seed和触窗协议不变。

新目录/schema防止旧回执和签名复用：dry为 `/data2/_shared/runs/ft_rounds/.dryrun_R046b_v3_E2-R046b/dry_run_receipt.json`、`ft_r046b_dry_run/v3`；review为 `/data2/FreeToken/runs/dev_R046/reviews/E2-R046b-v3/review.json`、`ft_r046b_source_startup_review/v3`，同目录pin为 `ft_r046b_review_pin/v3`。RID仍E2-R046b，controller/child沿用同一新冻结entry与`--dry-run`/`--run`。

本机guard targeted25 PASS、13 POSIX skip，torch未加载、CVD空；新版Linux目标38项。新增真实POSIX tmp权限用例覆盖644正例、writer漂移/缺失/目录/链接、目录/pin/round/MANIFEST及成员可写拒绝；新review/pin正例和旧schema拒绝。Windows不能证明这些Linux权限语义，根须新source_v3 Linux验证后真实FILEDRY/R签字；旧source_v2/86PASS保持旧证据。只修改本入口、targeted tests和本文，无新依赖，未远端冻结/空跑/服务/GPU。

最终新code身份（RAW=LF，交付后不再修改）：

```text
r046b_d07_t06_prepare.py
78d39b7e8d0a3eb25ad0f8b43cae4b4e0d964e72e1b82c38d49284b74db62e40
tests/test_r046b_d07_t06_prepare.py
f3c069f54fd84e460b4d2a2cbd898d8518ccfe14c3b7aed7203809f270d1cbae
```

AST2 PASS；guard namespace身份和8095连接前拒绝另1 PASS。所有文件操作均tmp fixture；共享writer与旧metadata未操作。

## 最新§12窗口与实际客户端链（SSH9 2026-10-07 11:30）

用户已否决剪seed并批准98,304发布窗口，本块优先于下文所有49,152/静态预算阻塞描述。当前开发入口令六个D07/T06服务统一 `--kv-reserve-tokens 98304 --max-seq-len-override 98304 --memory-ratio 0.80`。seed_real原SHA `8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3` 和文件内容保持；seed_45k实际首提示12,434、seed自身约1.2万token，名称不改。

新 `r046_seed_agent_trace_v2.py` 替代活跃seed wrapper，旧客户端未改。每轮在dispatch之前调用候选实际 `TokenizeManager.tokenize()`（内部 `render_prompt`、tools/thinking/effort sanitation、encode路径），不是比较文件名或首轮估计。完整输入超过96,256就不发送本轮，保存completed_k、window_hit.request_k=k+1、window_hit_count=1、未发送payload完整messages、实际IDs SHA/长度、输出预算与seedSHA；恰为96,256允许发送，预留2,048输出。原seed bytes解码后直接拼原TASK，不trim/改行尾。新binding schema为 `ft_t06_seed_trace_binding/v2`；manifest仍 `ft_r046b_route_manifest/v1`，新增精确window和各seed的completed_k/window_hit。分析器业务UID/完成数及observer期望数用真实completed_k，正常触窗不因不足12轮失败。

新wrapper只在hash-pinned原generate/replay两循环的payload构造后插入guard/break，原科学工具/历史/结果字段和ACK companion继续执行；有限PIN为332a187…，任何raw变化拒绝。自然触窗时取消旧“少于10轮”警告，原summary的真实轮数事实保留。frontend元数据绑定实际候选renderer SHA以及模型config/tokenizer_config/chat_template小文件SHA；没有模型权重加载。seed subprocess隐藏CUDA，实际服务observer仍采同一worker。

旧49K/628MiB增长预测门及旧最长预算JSON读取已删除，predicted/estimated字段为null。628历史OOM保留为历史事实，route快照位置明确CPU pinned。新的packet/memory_plan/actualdry先要求 **R056 canonical measured+D04**；根/R必须先证明11次测量完整有效（含真实87K两次）、无服务/输入/显存失败并独立原始复算，不用partial/历史窗口观察替代。保留既有R055b observer/hash、加载后≥1.5GiB门和每个请求before/after、正常pause采样；运行峰值由现场记录，不制造静态PASS。.80已是本轮下限；开测后失败将 `user_disposition_required=true` 交根停问。

CPU：Windows三套targeted **85 PASS + 1 POSIX skip in 2.16s**（client5、R046b25+1skip、R04955），AST6 PASS，network guard身份/CVD空/插件关闭、torch未导入。测试使用未改候选TokenizeManager类方法、hash-pinned原客户端循环及合成tokenizer/CPU IDs/SSE：87100→96256→96257完成2/第3轮前止；保原seed CRLF字节、真实R049 timed replay和相同blocked IDs、错误producer IDs拒绝；实际producer→consumer 98304接口及旧49K拒绝通过。**不是本机重读真实seed/模型前端或GPU显存证明**。新Linux/最终路径真实模型CPU/real-dry/R仍由根执行；旧Linux27/52/54全部保留为旧来源。

小闭包：当前producer、v2 client、D07/file_prepare、既有R055b observer/pause helper；CPU测试另需原 `test_r055b_owned_launch.py` fixture及其旧闭包。candidate的agent_trace/raw、tokenizer/tokenize.py参与新client回归；实际frontend还需FT venv的transformers/torch和模型tokenizer/config小文件（不读权重）。runtime_sources现绑定外部canonical writer、候选tokenize.py与model config，替换旧预算JSON；源/test六项raw/LF SHA见SECTION11_QUEUE_OOM_AUDIT§12。未同步服务器、实际dry、正式route画像build、取锁/分batch/服务/GPU。

按 `plan/CODEX_HANDOFF_20261006.md` §11（10-07 09:55）新增 R046b 专属入口。只新增本入口、其 CPU 测试、本文；协调日志只追加。未改旧 R046a 源、任何冻结源、封存轮次、其他泳道文件或科学输入。

当前阻塞：独立 R 的真实候选 tokenizer 检查发现 `seed_real` 加 TASK/tools 后首请求 **87,100 token**，超过固定 `--kv-reserve-tokens 49152` / `--max-seq-len-override 49152`。原始 seed SHA 仍是 `8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3`。`seed_45k` 是原文件名，其实际首提示为 **12,434 token**；`seed12k` 首提示为 **12,660 token**。禁止截断/更换 seed、扩 KV 或启动绕过；需要用户裁定科学输入。

## 已实现的有限分支

- 新 RID 为 `E2-R046b`，启动签名目录为 `runs/dev_R046/reviews/E2-R046b-v1`，新的 dry sibling 为 `.dryrun_R046b_v1_E2-R046b`。旧 R046a schema、RID、源码 SHA 或入口/用户不同的回执均拒绝。真实路径空跑仍只能由根执行。
- D07 在新的轮次内实际重跑 `g3_off/cold.json`，再跑 `g3_on/cold.json` 与原 G4 两趟 trace；同一科学输入及 cold_id、同一候选、同一 0.80 比较。OFF 不启 route trace。旧 R046 的 0.88 OFF 只登记其封存 round/MANIFEST 的路径和 SHA，不读旧 cold payload，也不参与比较。
- D07 的 OFF/ON 与四个 T06 服务一开始就用 0.80，复用现有 D07 科学参数。每臂 `serve_args_diff.json` 将 `memory_ratio` 声明为目标键；未创建或调整任何性能臂，性能规则仍为 0.88。
- 全部六个服务都通过已复核的 `r055b_pause_harness_v2.install(owner)` 冻结 observer。真实 UserMsg 前记录 `request_before`，真实最终 DetokenizeMsg 后记录 `request_after`，采样来自同一 GPU worker；OFF 也接线。加载余量需 ≥1.5 GiB，服务及 worker birth/device/observer SHA 一致后才调用业务 client。摘要要求每个 UID 前后完整且时间有序；T06 另保留正常暂停回执及 pause_after request_id。
- T06 route trace 与暂停开关全程开启；正常暂停只接受 `accepted`。有效 HTTP504 timeout/request_id JSON 保留原回执并停止，不将 timeout 改成成功。无效 JSON、错误 status、空 request_id、cancel enqueue error 拒绝。
- R046a/batch80 保持 failed_harness，round SHA 固定为 `01c9dd48367878b9ec742de0c43608bebe2b897638e9bc6e428520b616cea356`。在新入口内单独校验其封存元数据，使用外部 canonical `/data2/FreeToken/scripts/round_json_append.py`（SHA `67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff`）执行 D04 `check`；不向旧 RID 补 checker。
- 所有 owned-process cleanup 仍由既有生命周期处理。首次 startup cleanup 失败向上保留 owned_process/lock，不重试清理以掩盖失败。冻结 readonly 原源复制到新工作输出时显式 `chmod(0600)`，原源不变。

## 最长输入与预算绑定

入口要求独立 R 的只读 JSON 与精确 SHA。`packet()` 在候选检查/动态端口之前验证全部真实输入；`memory_plan()` 在余量计算之前再次验证，任一真实首提示 token 数达到或超过 49,152 时精确拒绝（候选 scheduler 的拒绝条件是 `>=`）。覆盖角色为 `g3_off_cold`、`g3_on_cold`、`g4_agent_trace`、`seed12k`、`seed_45k`、`seed_real`、`two_left-0`、`two_right-0`。不得把 seed 文件名当 token 数。

旧 R046a 的 route delta + 628 MiB 推算不作为新预算依据。R 发现 route capture 是 CPU pinned 内存；628 MiB OOM 涉及整提示 eager 的 GDN 临时 contiguous 分配，不能把它再次计成 GPU route buffer。新预算由 R 提供实际输入/参数和内存估计，工装只核 exact 0.80 与完整预算后 ≥1.5 GiB。预算预测不算 GPU 证明。

独立报告已绑定 `/data2/FreeToken/runs/dev_R046/r046b_memory_budget_v1.json`，SHA `71dfde4f5ae90aa8c0f3c3beb3635b20933af1a18a5af2ab0a6e6e323ea4be6b`；执行回执 SHA `c758e0d29fc3ee15fefbd32ec1a480438f497b4aaf68b5e444878c1987bf32e5`。报告 schema 为 `ft_r046b_input_window_independent_review/v1`，verdict 为 `BLOCKED_INPUT_WINDOW`，`predicted_free_bytes=null`、`memory_margin_verified=false`。新入口先读取 actual_first_request 的真实首提示 87,100 并拒绝，不伪称这是后续全部12轮提示的上界。完整预算放行还要求独立 PASS、真实完整输入上界、`lower <= actual_first_request <= upper`、memory_margin_verified 与 exact 0.80 的整数余量；当前报告无法满足。本交付不提供启动准入，不执行真实 dry、GPU、HTTP、8095、取锁、分 batch 或创建正式 RID。

## 源码闭包与 CPU 结果

实际运行源码需同目录六文件，均复用 v6 已有依赖；只第一项为新增：

```text
r046b_d07_t06_prepare.py
r046_seed_agent_trace.py
d07_g3g4_prepare.py
d07_r046a_file_prepare_v1.py
r055b_owned_launch.py
r055b_pause_harness_v2.py
```

另绑定外部 canonical D04 writer 和独立最长提示预算 JSON。`runtime_sources()`、dry receipt、独立 startup review 均覆盖这八项；startup review 还需绑定既有 `e2_launch.py` 及候选 `agent_trace.py`、`_agent_trace_original.py`、`route_analyze.py`、`multisession_probe.py`。不新增通用 reader 或冻结基础设施。

本地执行新 `tests/test_r046b_d07_t06_prepare.py`，使用已有 `d16_cpu_sitecustomize.py` socket guard，设置 `CUDA_VISIBLE_DEVICES=''`、`PYTHONDONTWRITEBYTECODE=1`：**26 passed / 1 skipped**，源码 `ast.parse` 通过。跳过的是需要 POSIX readonly directory 的 external D04 checker 回归；Windows 不能证明该 Linux 语义。实际服务 prepare/observer 代码、同配置 OFF 重跑/新 ON 比较、最长预算下界拒绝、87,100 输入拒绝、真实 UserMsg、严格504、加载余量门、完整前后UID、旧回执/source漂移拒绝、readonly复制与 owned cleanup 均有针对性回归。

未重跑旧 R046a 大套测试；本泳道未运行 Linux CPU、真实文件 dry 或模型/GPU；根独占后续 Linux 源码验证。这些结果仅证明新工装的 CPU 契约，不能下模型正确性、T06 测量完成或正式接受结论。


## 根冻结/验证所需的小闭包

本次 targeted CPU 只需上述六个源码文件、`tests/test_r046b_d07_t06_prepare.py`、复用 fixture helper `tests/test_r055b_owned_launch.py` 与已有 CPU socket guard。新测试只从 helper 导入 fake-product/UserMsg 工具，不执行旧 owner 的测试全集。不需要 `r055a_dryrun_base_v1.py`：fileprep 无此 import，entry 只调用 owner 的 `require_retained_cold` / `_freeze_pause_observer` 和安装修复；`_dry_base`、`_legacy`、owner source_hashes、旧 R055 controller 都不会执行。

生成的 `r055b_pause_observer.py` SHA 为 `cd52524f6b3accf994d7745743f4982ddda1790babd08f749d46fb76337115f6`；`r055b_pause_startup.py` SHA 为 `46706a1e0b6a9c646481475c25d7316a9455154a9f5ed964f17a6de2174e00c5`。startup 只导入同臂 observer 与候选 `freetoken.cli`；observer 安装候选 Engine/Scheduler/IO hook，torch 仅在真实模型 worker 采样，CPU 测试用 fake product。

未来实际 controller/service 的服务器既有依赖另由 D07 内置 SHA 预检，不复制或改写旧冻结树：`/data2/FreeToken/runs/dev_D16/t20_startup_cpu_5d485bd933e4/source_tools/t17_owned_launch_protocol.py`，该 source_tools 下的 `helpers/raw/cold_eq.py`、`helpers/raw/probe_ft_cold32k.py`，以及 `/data2/FreeToken/runs/plan_batches/e2_launch.py`。候选 client/analyzer 与候选 Python tree 保持 effb996。关闭轮次只读元数据和 canonical D04 writer 继续按原路径核验。

最终本地文件 SHA：

```text
r046b_d07_t06_prepare.py
4c4f5a8dda5574aa2da7faa0782c11688096749b7ac1e3183ade46f1006db1ab

tests/test_r046b_d07_t06_prepare.py
cc4f3efe80a8e2b8c66f680a109e804860ef49f4e89c3fbe25c5ed9f6532fa83
```

本地 CPU 命令在同一进程设置 `CUDA_VISIBLE_DEVICES=''` 后，通过 `runpy.run_path('development/d16_cpu_sitecustomize.py')` 安装 guard，再只执行新 targeted pytest 文件；guard 自检确认 8095 connect 被 PermissionError 拒绝。源 `ast.parse` 通过。根后续 Linux 验证可以证明上述 POSIX-only 测试；当前独立 BLOCKED 报告仍必须准确拒绝，不能继续真实 dry、签字或 GPU 启动。
