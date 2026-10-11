# D17 批次入口接线（PLAN §8.6）

R041 新入口：`plan/01_测试与调研/batches/batchNN_E2-R041_v3.sh`，调用现有实际 GPU 运行器。启动仍需要正式接受 T17、候选标签、实际分配的 batch 和一次启动前复核。

T20 新入口：`plan/01_测试与调研/batches/batchNN_E2-R040_continuation_v3.sh`，仅续算组件，不能作为完整 T20 交付。R041 原始证据有效才选4组，否则28组；普通冷包络4组。两个入口的 check 要求已有 FT_CPU_GUARD_ROOT 并隐藏 CUDA；run 不携带 CPU 网络隔离包。

## 实际检查

两个脚本服务器 bash -n 通过。host9 用已有 `d17_gate_cpu_72db5bbeb92c/source_tools` 与 `exact_startup_cpu_3cc07ea9a740/sources` guard 执行真实 dry plan：b9c9248 clean，祖先 E2-base 23f2e2c，原件输入90015…；返回0，续算28组、普通冷4组，reason=t20_r041_bitwise_closure_missing_or_invalid_all28，admitted/requests_sent=false，GPU锁字节未变。参数66仅作 dry 参数，未分配批次、启动服务。

初次将 D14 e45e2c2 误传为 Git 父提交，被实际 ancestry 检查拒绝。D17 cherry-pick 后 e45e2c2 不是其祖先；改用实际祖先23f2e2c后 dry通过。未改Git历史或旧产物。

## 尚未满足的实际启动条件

1. R036已failed_harness；新D14候选的T16、后续T17需正式接受，之后才能打E2-base.1标签。后文旧提交和dry数据为历史记录，当前候选见末尾2026-10-06更新。
2. 本地实际R041运行器已将冷控制改为E2-base 23f2e2c（e2base树），warm控制仍为D14 e45e2c2。preflight分别核实三棵树，冷结果记录两侧提交。已有回归检查实际调用的commit/绑定树及warm对照不变：20 PASS、1 Windows权限跳过，py_compile通过；CPU socket guard已启用。旧冻结包未修改，不可用旧包冒充本次修订；T17接受后再做一次实际启动前来源复核，Linux权限检查仍待该阶段。
3. R041执行器现已在全部测量通过后额外输出标准gate_batchNN.json：冷门parent_commit=23f2e2c、new_commit=b9c9248、warm_control_commit=e45e2c2，绑定result.json SHA，proposed_verdict=kept、admitted=false。producer不写独立review，也不写正式kept。现有20 PASS/1平台skip已检查实际产出字段与SHA。

   现有T20 v2 runtime已接入R041的 `ft_d17_r041_independent_audit/v1`，保持其 `kept_pending_independent_review` 判定，不将它冒充传统PASS。R041轮次结束后，R将实际复核写入 `review_batchNN.json`，包含rid/batch、candidate_commit、warm control_commit和result_sha256；D04 round.json绑定同一review SHA并由正式接受流程写kept。另需标准外部closure receipt绑定round/gate/review/manifest和cold parent/candidate。runtime重算这些封存SHA、检查冷控制/候选提交与真实冷结果，且R041不得用裸PASS替代此格式。sample4仍由已有选择器另行复算四组raw证据，失败则全部28。

   针对此运行器格式接线及已有入口的回归共27 PASS/6 Windows权限相关跳过，CPU socket guard已启用；没有新增fixture或冻结包。该数量不证明真实R041接受路径：没有实际完成的R041轮次，Linux封存和positive门禁验证仍待轮次结束后。所有旧冻结源保持不变。
4. 完整T20另有冷32K/64K、短解码、锚点冷热四格、D16冷/批槽/交错/停靠/缓存、60题及Agent三趟回放。续算组件不覆盖这些项；完整batchNN_E2-R040.sh尚未交付，不得视为整轮可启动。

不新增future读取器、fixture、CPU复核包或失败轮次全量快照/克隆。只推进实际批次接线。

## 实际启动依赖核对

host9 的 e2base/e2d14-schedule/e2base1 分别是23f2e2c/e45e2c2/b9c9248，tracked clean。使用FT venv实际导入的freetoken来源分别在自己的python树，socket guard启用、CUDA未初始化。三个树的 `_cpu_moe` SHA均为 `10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4`，`_pinned_tensor` 均为 `07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68`。不是只按glob推断扩展存在。

T20其余测量可复用的现有调用：t00_runner.run_baseline_arm生产臂已有冷32K四次、短解码三次、冷64K两次，tax臂已有冷热四格；t08_runner.p1已有三趟agent_trace回放及benchmark_client.phase3 60题。不能直接执行旧完整runner：它们固定旧RID/候选，且t00包含D0诊断、t08包含额外soak及quality optional行为。完整T20只接其实际所需测量调用，质量题失败不能optional放行。物理批槽/停靠/交错等仍需卡D16真实接线。

已在服务器直接重算下列现有文件（未执行请求）：

| 文件 | SHA256 |
|---|---|
| /data2/_shared/evaluator.py | 39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330 |
| /data2/_shared/benchmark_client.py | bebedf0b74ab234620d7206d8da58b72565f78c7407f56a2055f98dd3e5bc62a |
| /data2/_shared/test_prompts_60.json | bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad |
| /data2/FreeToken/scripts/agent_trace.py | 423feeb37bead3cacd2b066dc142a00cfb814f713ee1fcd766a456f64ce2cf17 |
| /data2/FreeToken/scripts/ft_perf_decomp.py | 949a18a521c8243cdd42d1deed0ab12544bc16e8e076b0dbb1251ac3dfb872cd |
| /data2/FreeToken/scripts/ft_probe_ckpt_tax.py | a67471a9d123c0c183f34d65066b86a35ce80e0832bc02f4ecfccc09b8c0a0c0 |
| /data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json | 055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899 |
| /data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json | 097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24 |

规范判卷器和60题库SHA与T20卡面相符。这些是来源核对，不是T20测量或完整批次交付。

## 完整 T20 接线的源码限制（2026-10-06）

已逐项对照卡面与实际调用。`t00_runner.BaselineRunner.run_baseline_arm` 的 production 分支覆盖冷32K×4、短解码×3、冷64K×2；tax 分支每个独立服务进程调用现有 ft_probe_ckpt_tax.py，复用 classify_tax 的一冷四热校验。不可直接运行旧 execute：它固定 E2-base、E2-R000 原始探针输出目录及 cold_id，并额外启动 D0。

`t08_runner.ProductionRunner.p1` 的三趟 agent_trace 调用可复用，编辑索引10、max_tokens=200；60题调用须取消 optional 放行并保存客户端SHA/max_tokens。不可直接运行 p1：它使用49152窗口、固定父树且加入DET/并发间隙/soak等非T20项。`e2_runtime.CardRunner.service` 也绑定模块级 e2base/23f2e2c，不可直接拿它冒充 e2base1 服务。

D16实际缺口有明确源码证据：development/d16_service_workloads.py 的 parking_or_interleave 返回 unverified/no supported native lifecycle trigger；批槽 collection 的 physical_batch_verified=false。完整批次必须接实际物理批槽、交错和主存停靠恢复，不能将串行请求、全局暂停或未验证返回值当作通过。现有 t16_candidate_runner_full_tail.py 主要是冷请求父子树比较，不能单独满足这五类套件。以上核对未启动服务、未连接监听端口，未修改运行中或冻结批次。

T20质量与回放组件已落地：batches/t20_measurements.py。由实际批次持有服务后调用，不提供独立启动入口；复用quality_summary/replay_summary，SHA绑定既有规范判卷器、客户端、60题及轨迹。客户端非零退出、逐题SHA不符、RUNTIME_ERROR或服务退出均停止；不将答错题当作工装故障。质量max_tokens=768来自已核实的固定SHA客户端，回放200、编辑索引10。只通过AST/compile语法检查，尚未执行客户端、未接完整T20服务生命周期与30分钟无输出监控、未做GPU验证，不能认定完整批次可启动。

T20质量/回放组件已补无输出监控：客户端独立会话进程运行，PYTHONUNBUFFERED=1，每秒检查日志文件增长、服务存活、总超时；连续1800秒没有输出即抛错停止。异常清理只终止本组件创建的客户端进程组，服务清理由外层批次负责，不重试。AST/compile通过。尚未在Linux实际服务生命周期中验证超时与清理；完整T20入口及D16套件仍未交付，不据此宣称可启动。此次未新增fixture或冻结包，未执行客户端。

T20 performance 组件已接冷32K×4（首枪单列）、短解码×3、冷64K×2，以及单个独立进程的一冷四热锚点测量。沿用原 probe_ft_cold32k.py/ft_perf_decomp.py/ft_probe_ckpt_tax.py 和 T00 validate_cold/classify_tax、T16 events/rows，不新增事件计数逻辑。冷请求用 E2-R040/臂名/序号生成新 cold_id，拒绝覆盖，核对原始输出并复制绑定SHA。三个实际探针SHA已在服务器只读重算，与组件固定值相符。CPU socket guard+CUDA隐藏下语法与实际import通过，没有调用客户端。外层还须完成候选树服务生命周期、生产口径校验和OFF/ON各三个独立进程；物理D16套件未接，完整batchNN_E2-R040.sh未交付。这不是GPU验证。

T20组件已加候选生产服务作用域与实际测量串联：仅接收E2-R040/T20的run作用域，先核实外层锁token/inode、owner/pid/card，再用既有Runner.gate核实e2base1完整commit/实际导入，并要求精确E2-base.1标签与每次启动GPU<=100MiB。参数沿用T00生产臂：taskset 1,3-47、层优先、73728、D0关闭，checkpoint按税格切换；服务独立进程组，核对解析参数/PID后缀及实际亲和性，finally复用Runner.stop。

run_baseline_measurements串起生产臂冷32K/短/64K、质量/回放以及OFF/ON各3个独立服务臂。输出baseline_measurements.json明确admitted=false、d16_suite=not_run，不能作为完整T20结果。外层正式T17/T16接受证明、批次预检、D16五类套件、正式round封存与历史对比仍待完成；服务作用域本身不授予正式接受权限。新增后在既有socket guard/CUDA隐藏下AST/compile及真实import通过，没有运行服务/客户端。Linux实际启停与异常清理未验证。

T20候选服务增加实际解析口径校验：kv_reserve_tokens=73728、max_running_req=2、cuda_graph_max_bs=2、memory_ratio=0.88、moe_cache_auto/moe_prefill_hit_d2d=True、offload、pinned、moe.nvfp4=triton；已按候选server/args.py字段及服务器原serve_args_diff.py的原始repr规则核对，guard导入通过，实际启动仍未验证。

D16 native_process_collection调用owner.service(name,operation,health_only=True,max_running_requests=4)，与T20当前生产作用域的capacity=2和contextmanager接口不同，需要专属D16服务臂；不可硬接为生产臂。候选scheduler._restore_linear_states的from_host路径是前缀检查点主存恢复，不代表正在解码的会话停靠。现有parking_or_interleave返回unverified，不能据此承诺T20全套可启动。本轮只读查源码，没有改候选产品树或启动新服务。

服务器Linux只读检查通过：本地当前T20组件SHA047118b9d886fff563f483253ccd31101005a53ddfa767f590ecefb4bb0385c6通过stdin在FT venv内compile/import，未落盘/生成冻结包。Python启动时指定既有3cc07ea9a740 sources/sitecustomize.py，核实guard实际文件与socket.connect补丁身份，CUDA隐藏、禁止pyc写入；verify_sources重算9个既有原始依赖，全部符合，Linux killpg/sched_getaffinity存在。requests_sent=false、services_started=false、gpu_admitted=false。

首次尝试只在进程内修改sys.path，但Python预加载的sitecustomize不是指定guard，检查在执行组件前失败；改为启动时设置PYTHONPATH后通过。没有绕过guard、发送请求或修改运行批次。检查只证明Linux导入/来源，不证明实际启停、30分钟超时清理、完整T20或D16接受。

## 2026-10-06：新 D14 候选后的预集成更新

当前 D14 候选 a9dca443cd07e1f60d1533e0a678935a09d21636，T16 E2-R037-gate-D14/b66 运行中。预集成在本地新分支 e2/base.1-ordinary-rewind，以 a9dca443 为基础保留原 D06 → D07 → D16 的 11 个提交；当前候选 0aa23431e5b800797543bdecbf35a01045131d7d，tree=4dbd3aa93c854f441a81770e51d887796b34f8e3。旧 b9c9248 分支和服务器树保留。此次从旧组装树到新树的文件差异只含 D14 新修复的 4 个文件。

服务器新专属树 /data2/FreeToken/wt/e2base1-ordinary-rewind；compiled extensions 链接既有同源构建，未启动服务。现有 socket guard + CUDA hidden、真实导入来源核对后，覆盖 D14 admission/engine、开关默认值、D06 pause/API、D07 route guard、既有 D16 equiv suite：149 PASS / 1 SKIP，5.71 秒。SKIP 是 tests/layers/test_route_trace_guard.py 的 CUDA D2H abort 检查，须排正式 GPU 队列；CPU 结果不代替它。证据 development/d17_ordinary_preintegration_0aa23431e5b8_cpu.json，服务器 CPU report SHA43a725764f2e9a771c95187061921a53962fa52a3b9b0a2e9278237472f2c66c。

现有 d17_gate_case / batchNN_E2-R041_v3.sh 已更新到新候选和工作树；warm control 为 a9dca443，cold control 仍为 E2-base 23f2e2c。现有执行器相关本地 guard 检查 20 PASS / 1 Windows 权限 SKIP。T20 runtime 的 R041 warm-control 绑定同步为 a9dca443；真实 R041 接受链验证仍待实际轮次。未打 E2-base.1 标签、未新增 R041 冻结包或 fixture。后续 T17 正式接受及 R041 启动前复核仍是必需前置。

T20实际生产组件的候选工作树已同步为 /data2/FreeToken/wt/e2base1-ordinary-rewind；历史SHA047118b9对应此前版本，不作为当前源绑定。当前仅完成语法检查，未启动服务或新增冻结包。

D16停靠能力复核纠正：不改产品文件的启动wrapper可包装 Scheduler._reply_dev_pause 的 accepted 安全点，枚举 decode_manager.running_reqs，保留 uid/table_idx/linear_slot_idx。在 engine_stream_ctx 内按顺序执行 to_host/from_host；四態是 conv_states、recurrent_states、slot_states[ple_conv]、slot_states[ple_ngram_ctx]，KV页归属另作结构不变量。只允许现有空host槽充足时预留；ensure_mamba_host_slots 不足时可能驱逐缓存，不可称无副作用。H2D完成后才能free临时host槽，不挂Req.mamba_host_tracks。以上为源码能力结论，尚无实际停靠wrapper接线或GPU证明；不得把已有全局pause或unverified返回值当成停靠通过。T17正式接受前不新增未来capture/reader/fixture。

T20实际续算入口 batchNN_E2-R040_continuation_v3.sh 的 candidate-worktree 和 Python 导入路径已统一到 e2base1-ordinary-rewind，与候选0aa及测量组件一致；通过服务器 bash -n（标准输入检查，未创建冻结包、未启动服务）。完整T20仍缺D16套件，不能视为整轮可启动。

2026-10-06 07:37:51：现有 continuation Run.execute 增加仅实际 E2-R040/T20 允许的 after_cases 回调（在GPU锁、原try/finally及服务清理范围内）；正常T17不执行，错误RID/card在锁前拒绝，后续测量失败不写提前成功result。新增CPU检查覆盖锁不释放、回调失败/服务停止/释放顺序及T17禁止回调。R038服务器封存源未变。

现有 t20_measurements.run_full_measurements 组合生产1-4/6-7、双槽/四槽、停靠、缓存、交错；S-cold复用缓存cold两次新进程控制。D16短输入仅取已封存目标tokenizer原始矩阵的不同512-token切片并记录source_case/SHA/切片坐标，避免四条完整长输入超过原生49,152 KV容量。长输入使用已有4096<len<=16384真实query；没有新生成fixture或改token预算/模型。已有native_workloads用于生产者测量（稳定重复+首分叉/top2包络），unverified即停止；不会把batch-vs-alone合法包络当not_met，也不会把生产者结果当独立接受。

生产环境显式清除FT_T17/FT_D16/FT_DEV/FT_D3/FT_D0诊断继承，D16独立启动移除续算operator环境；D16 worker从reviewed wrapper.parent先加载既有冻结观察/读取器，产品FreeToken仍来自候选WT。源码SHA：legacy bf0a01324ef8f63a6d49e08d84ec76e972df5a5e52ba89a6e483007f8dc45b98，T20 0a2e99590321d3ee9593cf6355cb20d13250dde2001883fc9a9ecf1aa3f5c24b。guard CPU检查59 PASS/14 Windows平台/无torchSKIP，含完整组件的全部测量项调用、不同输入要求、未验证包络拒绝。只是本地实际代码接线；CLI/模板传递完整模式和D16来源回执、实际Linux启动验证尚未接完，完整R040仍不可宣称可启动。没有新冻结包/未来工具链。
2026-10-06 07:41:58：完整入口 plan/01_测试与调研/batches/batchNN_E2-R040.sh 已创建，调用既有续算模板并显式 FT_T20_FULL=1。runner v2增加 --t20-full/--d16-source-review/--d16-source-review-sha256，仅E2-R040/T20允许；未声明完整模式不得夹带D16回执，回执缺失或SHA格式错误在读输入前拒绝。preflight要求测量组件、既有D16采集/读取源码、两模板在实际CPU inventory内，并核对既有D16 source-review。runtime在取锁前重算这些源码与回执绑定，之后把完整测量绑定到原after_cases生命周期；续算后再次核对原始inputs SHA，避免后续组件读取变更输入。

runner SHA256 bb73d5820541550002dfa170c132456a6164c6b41a64fb597ca58675b8d8ca3f；runtime SHA256 df43900bee4df8e5b5e0d591de3670935ae2d2492019db6061ed6cd7eace2c27。两个模板服务器标准输入bash -n PASS；既有guard CPU回归65 PASS/14 SKIP（新增模式路由、caller SHA、default28、缺源码拒绝检查）。没有上传/创建实际T20冻结包或fixture；T17/R041正式接受尚缺。当前T17 source-admission仍专用于a9候选，T20实际0aa来源包和CPU绑定不能直接冒用1dd61d；须在真正轮到T20启动时按现有CPU/来源机制交付并做一次R启动前复核。CLI接通不等于整轮可启动或GPU通过；真实Linux/服务完整模式仍未验证。R038已封存源未改。
### 2026-10-06 07:46:50：T20 完整回调接线验证

在现有 tests/test_t17_continuation_runner_v2.py 补充三个实际 runtime→保留生命周期→测量回调检查：正常完成、续算期间输入改变、测量异常。使用隔离临时文件与替代测量组件，不创建服务或冻结包；执行原锁获取/释放代码及原 try/finally。证明完整测量在 result.json 写入前且原锁内执行，输入改变不会调用测量，失败保存 failed_harness 并先 stop 再 release，不产生成功结果。

CUDA_VISIBLE_DEVICES 为空并加载现有 socket guard，相关四份测试合计 68 PASS / 14 SKIP。跳过为本地缺 Torch/POSIX 条件，不构成 Linux/GPU 验收。实际 T20 候选来源包仍须绑定 0aa23431；现有 a9 来源包不得沿用。R036 复算 PID 1291049 本次核实仍运行，未签发沿用许可。

### 2026-10-06 07:49:18：R041 实际候选来源绑定修正

现有 d17_gate_cpu_stage.py 和 d17_source_admission.py 仍使用旧 b9c9248/e45 工作树，已修正为 0aa23431/a9dca443 与各自 ordinary-rewind 工作树；真实冷参照保持 E2-base@23f2e2c。现有 R041 批次模板纳入来源清单。CPU socket guard 单独存放 cpu_guard/sitecustomize.py，仅加入 CPU 子进程 PYTHONPATH，避免 GPU 入口自动加载 guard。导入检查同时核对实际 FreeToken 来源、CUDA 未初始化及 socket guard 生效。

候选脚本来源清单已验证可读取（修正时 43 文件、14 份候选 Git blob，随后纳入实际 R041 模板）；没有创建服务器来源包。三份现有 D17 测试 45 PASS / 1 SKIP（Windows symlink 条件）。同时修正跨平台证据绝对路径拒绝行为。仍需 T17 正式接受、候选标签及实际来源包 CPU 执行后的一次启动前 R 复核，不能宣称 R041 已可正式启动。

补充验证（2026-10-06 07:49:51）：四份 R041 相关测试 49 PASS / 3 SKIP。修正现有 helper 删除缺失原件测试在 Windows 下需先解除文件只读属性的问题，仅影响临时测试文件。未执行 Linux 来源包、实际服务或 GPU。

### 2026-10-06 08:04:58：R036 沿用许可已核验

泳道 R 已封存 /data2/FreeToken/runs/dev_D16/r036_retained_cases_review_r_overlap/review.json，SHA 9bb40368c6fb0406d3bbdfe29c9f2dbd36da8aad11710fab90c6203fef0508f4。root 重算回执 SHA 并核验只读属性、schema、reuse_permitted=true、e45→a9 候选绑定、positions 1–14，以及 admitted/model_accepted=false。R038 将测量剩余 14 组；当前等待唯一一次实际启动前 R 复核，T17 全部 28 组尚未接受。

### 2026-10-06 08:11:37：R038/batch67 实际启动

实际使用冻结 /data2/FreeToken/runs/dev_D16/t17_startup_cpu_1dd61d5458fe/source_tools/t17_continuation_launch_v3.py --launch。独立 source review SHA 39a22b71c631a6c037de7577963c62f47460db1b588c60320cb7837f7ef92c6e；launcher review SHA 14fe3172354427aae3856ff6068cb02a1ac8455a01382b9767a8b2f5b05c13a4。启动回执 /data2/FreeToken/runs/dev_D16/launch_E2-R038.json SHA 4281d151514a85762485ca3c412e0c84e24ee8aa2b24dddfb824eec9d1d648e1。控制进程 PID 1569424/start_ticks 133994698 已现场核验存活，回执 case_mode=remaining、reuse SHA=9bb40368c6fb0406d3bbdfe29c9f2dbd36da8aad11710fab90c6203fef0508f4。冻结选择器已验证仅 prefixes12736/18944 的14组、冷参照仅12736-tail8193/18944-tail4097。刚启动时锁与状态仍待初始化，不能据此宣称请求/测量通过。已通知 R 仅等轮末复算与 D04 封存；全28正式接受仍待本轮完成并合并已许可前14证据。

### 2026-10-06 08:35:26：R041 来源包目录参数接线修正

现有 batchNN_E2-R041_v3.sh 传 --source-cpu-stage 为来源包目录，但 d17_gpu_gate_runner.verify_execution_admission 原先将目录直接传给要求 cpu_validation.json 文件的现有 verifier，真实启动会在构造服务前拒绝。修正为 stage/source_tools/cpu_validation.json，复核路径和 caller SHA 原样传递；未放宽 own CPU package 校验。现有测试补覆盖此接口，socket guard + CUDA 隐藏下四份检查 50 PASS / 3 SKIP。仅本地实际批次接线修复，未创建冻结包或连接服务；R038 冻结依赖不变。Linux 来源包及正式 R041 启动仍待 T17 接受与标签。


### 2026-10-06 08:50:02 CST：T20 卡面判定覆盖核对
对照 T20 §3 与现有 t20_measurements.py、t08_runner.py：performance_measurements 保存各次原始值，quality_summary 只汇总 passed/category，replay_summary 只校验输入并汇总 TTFT/cache。尚无历史性能≤7%对比、规范重判47/60逐题变化及续算相关多轮题清单、Agent历史输出分叉定位。这三项仍属于实际 T20 交付缺口；已有原始文件保存不等于对比已完成。按干预规则本次仅核对现有接线，不新增未来读取器、复核器、fixture 或冻结包，不执行 GPU 客户端。T20完整可启动状态尚未证明，后续使用实际轮次数据完成对比与正式判定。


### 2026-10-06 08:52:29 CST：现存 T20 历史对比来源定位
已只读核实 E2-R009 规范重判逐题文件 /data2/_shared/runs/ft_rounds/E2-R009-regrade/E2-R009.regraded.jsonl，60行，SHA256=dd66f3d0ad5f32a1638c70bf92f37063e8087dc181ebf0e24849bc2cf6a8e5e6；规范状态字段为 status（并非当前客户端 graded_status），含 question_id/category/response/thinking/evaluator_sha256/question_sha256。原判分保存在 historical_passed，不得拿它替代规范重判状态。
既有回放 /data2/_shared/runs/ft_rounds/E2-R009/P1/agent_coldfirst.json、agent_warm.json、agent_edit.json；warm 文件 SHA256=79bab0c338ba44da6f0984861ac80589e941918c124bc8661654cd6e87c877d7。rounds 含 messages_sha、trace_messages_sha、parts/content_parts/text/tool_calls/finish_reason；必须先核对请求、回放参数、相同负载再比较。现有 agent_trace compare 使用流片段前缀及验收门，不直接提供全文首字符分叉；流片段数不能冒称 token ID 数。没有生成新的对比程序或测量结果。


### 2026-10-06 09:07:36 CST：既有 T20 函数补齐逐题历史比较
现有 t20_measurements.py 的 run_quality_and_replays 内直接增加逐题历史比较，没有新增读取器入口/fixture/冻结包。SOURCE_HASHES 绑定前述 E2-R009 规范重判文件 SHA；核对60题集合、逐题规范evaluator/category/model/题面SHA，规范status与passed一致且历史为47/60。输出 quality60.historical_comparison 含60题前后状态、正文/思考/finish_reason相等性、changed_questions及15道long_multiturn清单；仅标候选续算关联，cache_hit_proven=false，不冒称实际命中证据。性能≤7%与Agent分叉报告仍未接通，整轮可启动尚未证明。
Linux FT venv以标准输入编译当前源码及提取其实际比较语句执行，既有socket guard启用、CUDA隐藏。基于原始历史数据的5项内存检查PASS：同数据47/60不变、单题状态/正文变化、status/flag矛盾拒绝、缺题拒绝、类别变化拒绝。未连接服务、未上传源码、未写fixture或源包、未启动GPU。当前源码SHA256=72b52565672e64f7431a507b45f40ad85beb479ffe03397e34bf4423a30b31a4。


### 2026-10-06 09:09:51 CST：既有T20函数补齐Agent历史分叉报告
三趟E2-R009回放原文件SHA纳入SOURCE_HASHES。每趟使用既有replay_summary验证原始历史负载，再核对model/thinking/thinking_mode/max_tokens/temperature/rounds/edit_at_idx及每轮请求摘要/编辑标记。现有测量函数输出historical_comparison：逐轮text、parts合并文本、content_parts合并文本、tool_calls、finish_reason差异及首个字符/工具列表索引。流片段不当作token ID；admitted=false，不自作正式kept判定。当前源SHA256=611595db76bb6a4fa5d0fd43f4ba389a10a0b58a543fabdf6222127f6d6ff262。
Linux FT venv既有socket guard、CUDA隐藏下，执行实际比较语句：三趟历史各与自身比较无变化；正文首字符定位；工具调用列表变化定位；请求摘要差异拒绝；预算差异拒绝，合计7检查PASS。初次AST检查挑中了逐题循环而非回放循环，StopIteration；仅修正临时检查定位，未改测量源码后通过。全部使用内存输入，无服务请求、GPU、上传源码或新增fixture/包。性能历史≤7%仍缺，完整启动尚未证明。


### 2026-10-06 09:12:50 CST：既有T20函数补齐历史性能比较
run_performance production分支已内联T00及E2-R009对比。T00原始4冷32/2冷64/3短解码记录及R009两次冷32记录共9文件SHA纳入SOURCE_HASHES。首枪当前/历史分别保留，冷32中位数只用后3次；短3次/冷64两次分别取中位数，生成5项T00及2项R009观测（原始值、中位数、有符号/绝对相对偏差、7%限、源SHA）。prompt/completion/cached token负载集合不一致则within_7_percent=null，不假设同类合同；R009窗口49152与T00/当前73728差异显式标注。超7%只记录观察，不自作最终kept/not_met；OOM仍待正式轮末复核。
Linux FT venv标准输入验证当前源码实际比较语句：同历史数据5个主指标零偏差及中位数、首枪极端值不影响中位数、7%边界、8%超限、负载变化不给判定、NaN拒绝，6检查PASS。当前22依赖SHA全部核实；现有socket guard、CUDA hidden，无请求/服务/GPU/新增fixture/冻结包。当前源码SHA256=d56be489a80fe64791599fc14cc5056acc3f07cb2d1103aa6d2e7ac874c66ed8。逐题5检查和回放7检查另见前文，合计18项针对比较逻辑检查；不是新候选GPU结果或端到端接受。实际T20来源准入仍需在获T17/R041正式证据后按候选0aa绑定，不可冒用R038 a9冻结包。

### 2026-10-06 16:43:15 CST：R041 消费实际 14＋14 证据的待修接线

只读核对现有 development/d17_gate_case.py：verify_accepted_t17 固定要求 ft_t17_continuation_independent_audit/v1、单轮 cases=28、review.rid/review.batch；_recompute_closed_t17 又调用旧 continuation reviewer.audit 重算单轮28。实际 PLAN §8.7 沿用汇总为 ft_t17_r036_r038_combined_28_review/v1、R036 retained14＋R038 recomputed14，故现有入口会拒绝真实接受证据。T17 正式封存前本次只记录现有接口缺口，不修改或新增未来工具。封存通过后须修正现有准入代码，验证 canonical D04/history、独立汇总与每组绑定、R036 reuse许可、R037前置、候选a9及精确28覆盖；不得伪造单轮28字段或再次重复全部原始复算。实际R041仍须来源CPU包、标签与一次R启动前复核。

### 2026-10-06 17:08:04 CST：T17 正式接受已具备

R038 canonical D04 kept、OS exit=0、146681份原始文件SHA不变、manifest全量复验/整树只读/历史链通过；R03614＋R03814精确覆盖28组。接收入口为 /data2/_shared/runs/ft_rounds/E2-R038/round.json 与同轮 combined_review.json；封存回执 /data2/FreeToken/runs/dev_D16/r038_d04_closure_20261006/closure_receipt.json（SHA b3bd6001cf67eb9ec38fd789ee4b1a13c4bb29b584f97adf29b30ca1397cebba）。现有 d17_gate_case.py 对单轮28/schema的硬编码仍须修正；不得伪造旧单轮审计、再次复算全部状态或改动原始证据。R041实际CPU来源包、标签与启动前R复核尚未完成，不得宣称正式可启动。

### 2026-10-06 17:20:45 CST：R041 实际 14＋14 消费接线与启动来源

现有 d17_gate_case.py 增加 PLAN §8.7 combined schema 分支，外部接受 pin 固定为本次退出0的 R038 round/summary/manifest SHA；继续核对 D04/history、精确 ordered positions1–28、R036许可及改动范围、每组当前case/input/schedule与归档R038原始复算报告。保留旧单轮28审计分支；不伪造旧schema、不重跑已通过状态复算。现有大文件SHA函数改为8MiB分块读取，避免一次载入整个张量文件。源码SHA d4d595a99a859f3a5a587ed59f7bfbefa113e3f9f1c3bc96125c5b783b4d7baa；测试SHA 6084fd576357098a683322502af4e9ce688262a543a0e4736943f6a34d6e13db。

服务器真实28组轻量绑定检查PASS，socket guard＋CUDA hidden，无请求。新增拒绝缺组、沿用许可失效、状态/token/text不一致、schedule变更及未被外部接受pin绑定的伪汇总等测试；本地4份针对性测试54PASS/2平台skip。实际来源CPU包 /data2/FreeToken/runs/dev_D16/d17_gate_cpu_0e33a49343a0；cpu_validation.json SHA f9f0059888df99487a8b030921b59dfe631d9f3dac7c57f5c1c75a4d97a67e79，Linux61PASS无skip、6个进程生命周期场景PASS、导入正确候选且CUDA未初始化、来源结构检查PASS。只证明source readiness，非R041/GPU接受。

候选标签 E2-base.1@0aa23431 已本地创建，git bundle 同步到远端专属WT并fetch为同提交0aa23431；候选/控制工作树HEAD与tracked-clean均核实。泳道R独立 /root/r_overlap_review 已收到本次唯一一次R041启动前复核任务（含来源、标签、实际参数、14＋14消费和已有原子launcher）。待回执与SHA后才启动；batch号按原子账本分配，预计68，不预占轮次、不创建GPU服务、不改封存证据。

### 2026-10-06 17:23:40 CST：R036失败原轮次只读保护

确认 /data2/_shared/runs/ft_rounds/E2-R036/status_batch65.json 为 failed、batch_pid3851074 当前不存在。原树此前未整轮D04封存且可写，现仅清除整树写权限：145010路径、144980处模式变更，所有内容保持原字节，无克隆/快照。R036沿用许可与R038 accepted 14＋14判定不变；整轮R036失败封存仍待处理，不标成kept。已通知当前R041唯一启动复核Agent。

T20 下一轮准入修正：development/t20_r041_sample4_closure.py 的 warm control 从旧 e45 更正为 R041 实际 a9；real_inputs 的原字节 SHA 90015a…及 origin=e45 保留，通过 sealed input_provenance 将 runtime target=a9 分列绑定。不改变 R038、R041 冻结脚本或原始文件。新增来源/目标/输入SHA/沿用来源/范围错绑拒绝检查。
Windows 专项 17 PASS、2平台跳过；Linux CPU source stage /data2/FreeToken/runs/dev_D17/t20_input_binding_cpu_abc22fe4346e，19 PASS、零跳过，cpu_validation.json SHA fd488ec3ebb4e1899b10fab9e73d2221ffe2c0e58b0dd9f7223739606f5ab45e。GPU隐藏、socket guard，无网络请求。首次 Linux 包漏装 d17_gate_case.py，10失败/9通过，失败包 0d35ff90e60a 原样保留；补齐后新版本通过。此 CPU 专项不代替 R041 实测/轮末复核，也不授权 T20 启动；T20完整来源包、一次启动前 R 复核及真实测量仍待。

T20 实际执行来源准入已接线：t17_source_admission.for_run 使用独立模块，按显式 run_kind 固定 T20 candidate=0aa23431、cold parent=23f2e2c、WT=e2base1-ordinary-rewind，并使用独立 CPU/review schema；不从CPU报告选择候选，不改变T17旧profile。runner preflight和runtime复验均传递run_kind，T20必须包括完整测量/D16依赖清单。现有 t17_startup_cpu_stage.py 新增 --run-kind t20，包含sample4读取器、执行前重核、D16 workload/native专项、真实输入原字节及旧三生命周期场景。旧CPU原始数据仅引用，不新增快照或克隆。
本地专项51PASS，5个Linux/真实输入场景跳过。实际 Linux CPU stage /data2/FreeToken/runs/dev_D16/t20_startup_cpu_bf8db29bad11 已开始；源生产器PID3171955/start_ticks137458737，工具session21505。当前正在 _verify_snapshot 的原始数据哈希读取（D态，read_bytes增长），尚无import.log/测试终态，不能宣称CPU包通过或T20可启动。下一步等待同一进程终态，失败时原样封存后只修实际问题；通过后仍需一次实际T20启动前R复核，以及R041正式原始复算/D04 kept。R041运行冻结包未修改。

T20 Linux来源CPU终态：t20_startup_cpu_bf8db29bad11，253 PASS、零跳过；success/request_error/stop_error三场景PASS；实际候选import=0aa ordinary-rewind、CUDA未初始化、动态fixture socket guard、真实GPU锁未改变。结构检查返回0/source_execution_ready=false/model_admitted=false。startup_cpu_report.json SHA 7dde1ec671bd7b298e25a280c6561b62205026f552ab2dbf7ab11cab0f0eff4b；真实外层工具exit=0，session21505终态。冻结包产生后只新增本地一项旧T17 review schema拒绝测试（35本地PASS），不改变已冻结执行源码、不重复253套件。

D16启动CPU复验已改用实际0aa候选WT，exact_startup_cpu_3080618d3c77先60PASS，但native_workloads与T20冻结包CRLF/LF字节不同，不能据该包签来源回执。随后现有stage保留实际执行读取器原字节，另建exact_startup_cpu_5de0e05bc692：真实CPU spawn probe证明scheduler/engine/reply/input观察安装、cuda_initialized=false；60PASS、零跳过，外层exit=0。cpu_validation.json SHA 9fdb24454296d004086311f4b99b633dc9d19ef35977620ac42e478d6889b5f8。14个D16执行依赖已逐个核对与T20 bf8冻结文件/CPU报告原始sources清单SHA一致，绑定记录 development/t20_d16_dependency_binding_5de0e05bc692.json。旧包保留，不改冻结执行包。独立R启动前复核、R041正式kept、实际T20测量/D04接受仍待，CPU通过不授予模型接受。

T20实际启动脚本 development/t20_actual_launch_20261006.py 已完成并冻结到 /data2/FreeToken/runs/dev_D17/t20_actual_launch_20261006.py，SHA 1f910a7c29484c20b266ec89ca0ac2c2569d0fe9edd3bb765fbfb11586fd60b3；复用既有 atomic next_batch/reserve_process，实际R040、0aa候选/23f2冷父树、完整--t20-full、4组选择由既有sealed R041证明读取器决定。要求主来源R回执、D16来源R回执、R041实际review/SHA和closure binding；未产生的值不得伪造。CPU针对实际冻结辅助文件做参数构造及missing R041 kept拒绝--run两项检查通过、无GPU/无请求、未预占batch或创建R040；小回执 development/t20_actual_launch_20261006_cpu.json。这些使用占位review参数的负测不是实际review通过，完整startup仍待R041封存证据。

实际argv检查发现旧bf8包缺少sample4读取器直接使用的 root serve_args_diff.py/round_json_append.py；已修改现有stage/source admission inventory另建T20 source stage t20_startup_cpu_5d485bd933e4，旧包不修改。Linux254PASS/零跳过，success/request_error/stop_error三场景PASS，structural check=0、source_execution_ready=false，startup_cpu_report.json SHA 063d0ba8e8916d2479c692d971a6dce15d2ad8de001c98aa0ec819efee99d1fe，外层tool session4334实际exit=0。当前launcher已准确绑定新包及report SHA。本地关联回归69PASS/7平台或冻结输入缺失跳过。独立R /root/r_overlap_review 正在做下一实际T20启动唯一一次来源复核及D16同字节回执，不复核其他future包。R041 actual kept、正式参数和测量/D04接受未完成。

R036旧失败原树仅维持只读未封存：R已按root指令终止唯一154GiB审计读取进程3188088/start137489778，避免争用R041加载I/O。外部中止回执 /data2/FreeToken/runs/dev_D16/r036_d04_audit_aborted_r_overlap/review.json SHA e94ab366f5df00025a47e1316b25efa2eb351d48cb31ea7d617791da0324aa56；144798raw无symlink/可写项，旧文件未改。既有canonical closer明确要求GPU idle，R041终态/锁释放后再封存；不使用中止读取作为完整SHA proof，不宣称R036已D04。

独立R启动前来源回执已通过、服务器当前SHA复核一致：T20 /data2/FreeToken/runs/dev_D16/t20_source_review_r_overlap/review.json SHA 07cdc15a5bb45430acdb5f9443ec59a21076dc945d70a7498159c9325fb64291，现有source verifier --run-kind t20 --review 返回0/source_execution_ready=true；D16 /data2/FreeToken/runs/dev_D16/d16_collector_source_review_r_overlap/review.json SHA 32dbcc01d6bb975fa91d0d02a1c8080cdd25dd7569431c0a4f4dea21999f89da，14依赖source/CPU byte binding实际verify RC0。回执scope仅owned-gpu-test-startup-only，R041 D04 kept/实际raw review与closure绑定仍待，未启动T20。

R041实际终态D04编排 development/r041_actual_d04_close_20261006.py 已冻结到FT专属 runs/dev_D17，同SHA b9c578564f0965b0be10f26a59c16190f0b2e9bad26d89db44a7b9be66fbd918；只用于实际cold＋4 warm整轮PASS且独立IR的本轮，失败分类保留并另处理，不套用R038的14＋14/T17口径。实际Linux负测：controller3105554仍在时 --close 拒绝于第一步，无GPU查询/原始变更/round metadata。尚未执行真实封存。终态后R作四组原始复算，root归档review_batch68.json、调用已pin的canonical round_close/round_json_append；形成只读history/manifest和R040所需closure_binding。小负测回执 development/r041_actual_d04_close_20261006_cpu.json 不代表实际IR通过。

### 2026-10-06：batch70 终态后新版本启动修复

旧 batch70 与冻结依赖保留。新 T20 来源补齐实际 t20_measurements → t08_runner → e2_runtime 导入链，T20 CPU 验证不再借用外部旧来源目录。R041/R038 已封存前置改为登记 MANIFEST/round.json SHA、只读权限与 D04 history 核对；真实 combined_review 的 14+14 coverage 字典与 four_roles_bitwise_equal 字典按已封存 SHA 绑定。显式 all28 模式保留，sample4 缺许可不得悄悄启动 all28。

实际 Linux stage `/data2/FreeToken/runs/dev_D16/t20_startup_cpu_44fbfb4f499d`：254 PASS、零跳过，success/request_error/stop_error 三生命周期 PASS，实际候选导入和结构检查 RC0；startup_cpu_report SHA `ef1ebd1885543eca37480213578f555098965f861ad0083f65485cda23641727`。真实闭包 metadata-only permit=true，四组 input SHA 绑定，耗时 2.38465 秒。

新 launcher `/data2/FreeToken/runs/dev_D17/t20_actual_launch_20261006_v3.py`，只读，SHA `986e8da4e79ebb27a7ccfbe98ab839010b59a6900c69280b7d1c0f0dc09a78eb`。交泳道 R 做本次唯一启动前复核与真实 no-run；批次号由实际 allocator 分配，不预占，不以 CPU 证据宣称 T20 接受。

实际 v3 runner.preflight 在 R041 branch 触发 `UnboundLocalError: importlib`，未启动 GPU，也未建立 round。仅将局部 `import importlib.util` 提到 verify_t16 入口，新版本 `/data2/FreeToken/runs/dev_D16/t20_startup_cpu_ba6a7281b047`：254 PASS 零 skip、3 生命周期 PASS、结构检查 RC0；report SHA c646a2dbb0e03e2403299958abf504768491cc8797bf744bd4874232ba130fa2。该包 verify_t16 真实 R041 PASS，绑定 e9ef50 round、0e6414 manifest、fadbc5 closure。v4 launcher SHA 26f04eb8fe072bf732ea50695a733cbf4dd0fc5be1359802e2b1d28cf44301be，旧 v3/source/review 留存。R 按此次实际 startup 续办修复行与新 report 绑定，之后须真实 runner.preflight 再 launch。

T20 后段 production_service 的 tag 检查将 candidate[:7] 修正为既定候选 tag 的 [:8]（E2-base.1@0aa23431），避免续算后服务启动失败。最终 stage `/data2/FreeToken/runs/dev_D16/t20_startup_cpu_5deba0293ed3`，Linux254 PASS/零skip、三生命周期PASS、结构RC0；report SHA `0bdee2876a4c66957e4a99c1713c7f901055a7443b78b2d9fc34e5bd5db94461`。从此冻结源实际 verify_sources 检查22脚本/小基线SHA PASS，0.1586秒。

最终 v5 launcher `/data2/FreeToken/runs/dev_D17/t20_actual_launch_20261006_v5.py` SHA `9d92a10daf7378125c700dce760dc26acc91cac2ceffbe6222ba04457d6c60bc`。D16 的严格 origin 绑定需要新外置回执，不能因源字节相同直接使用旧路径回执；CPU inventory和14依赖仍相同，不重复D16 CPU套件。旧v3/v4回执及所有包保留，等待当前startup复核完成后真正runner.preflight并执行。
