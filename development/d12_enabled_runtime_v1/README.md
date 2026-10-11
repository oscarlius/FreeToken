# D12 启用诊断适配器（准备中）

本目录归 FreeToken。当前包括专家bank/slot校验、outer prefill状态采集，以及复用既有D16 worker的窄接线。已有CPU协议与原生组件验证；正式CLI/API/spawn、四层完整数值门和GPU准入尚未完成。

`transfer_audit.py` 通过显式 `install_transfer_audit()` 安装到诊断 worker；普通导入不修改产品行为。包装器在 `prepare_prefill_routed_only()` 原方法执行前保留原专家号，原方法只调用一次，成功后逐项验证：

- `slot_for_id`、改写后的 ids、`id_of_slot` 的双向对应关系；
- GEMM实际bank views与待检查resident tensor一致；
- Triton NVFP4全部六个bank的每个被路由专家行，包括packed权重、FP8 block scale与FP16 global scale，源行与resident行全字节相同；
- 每次最多临时gather八个专家行，避免一次复制完整目标模型或整层cache。

已有resident命中与新搬运miss均校验内容；选中行数不能用作物理H2D字节。失败/fallback不会产出“相等”证据。CPU结果显式标为`cpu_protocol_only`，实际运行包装器要求CUDA；读取和同步会干扰时序，所以只允许诊断臂使用，不能把其耗时当性能。

当前 transfer audit 的 Linux 精确源码包为 `/data2/FreeToken/runs/dev_D12/transfer_audit_v2_cpu_20261008_1735/`：27 个 CPU 测试通过，同进程断言 CUDA 未初始化。report SHA `c19834ad38bf936aaaa6f7d7ea63d2f5eabd954c58447c293bf745600f33e1d5`。在 v1 的六 bank 字节、双向映射、实际 view 和调用协议检查之外，增加跨三个 gather 分块的完整字节核对、slot0/4 覆盖，以及 UID/outer segment/child 长度位置的必填契约。旧 v1 的 16PASS 回执和独立复核保留；v2 尚无独立复核或 GPU 接入证据。

`segment_capture.py` 使用原生 `LinearStatePool.dump_state` 采集 prefill 后四类状态。本地 9PASS/1skip；Linux 针对实际候选 `8f6a912` 已 10PASS，新增用真实 `LinearStatePool.dump_state` 与 CPU 状态张量回读四类文件，逐项核对内容、dtype、角色路径、完整 SHA、旁槽不变及 CUDA 未初始化。forward 仍是 CPU 协议夹具，这不证明真实模型 forward 或 GPU 状态。准确回执 `/data2/FreeToken/runs/dev_D12/segment_native_cpu_20261008_1816/receipt.json` SHA `994a0295df9f3aece458124d90d3fcc8aeeffa65a21e9170c1385f3a87abffe0`，本地副本 `../D12_SEGMENT_NATIVE_CPU_20261008.json`。当前没有完整四层数值验收结果；未读取模型权重、未跑 GPU。

待接线：为每个真实MoE子段绑定业务UID、outer segment和child长度/位置；将校验输出纳入D16现有封存生命周期；连接四类续算状态、固定后续token logits和普通SSE输出。T06开启route tracing时禁用layer-major；其历史forward段不能作为新服务全部MoE子段的当然分母。必须同时核对实际D0`subchunks`及当前forward上下文。

18:30源码定位增量（尚未安装/运行）：已有 `scripts/equiv_suite/service_capture_startup.py::run_scheduler` 在worker创建 `Scheduler(args)` 后、`sync_all_ranks()` 前提供capture安装边界。可复用该边界，先安装segment capture取得context provider，再安装transfer audit；无需修改模型、MoE或状态池。outer身份取真实Req的uid/cached_len/device_len/linear_slot_idx；layer-major模型循环在每个child前切换`ctx._batch`，child继承uid并携带实际cached_len/device_len，因此必须在MoE prepare调用内读取当前context。outer序号是本诊断包装器的关联号，不冒充生产调度字段。状态池dump是outer post-prefill状态，不能称为每个child的状态。

主诊断必须保持 `FT_DEV_ROUTE_TRACE` 关闭：候选 `engine.py::forward_batch` 的layer-major条件显式要求`tracer is None`。开启trace会落入普通prefill，不能用于此处layer-major目标路径的验收。此定位由独立只读Agent提供，真实worker安装、四层完整数值比较和GPU执行仍待完成。

## 19:00 worker 接线与CPU验证

`worker_capture.py` 是D12专用安装层，调用既有 `d16_native_capture_shutdown_v3.run_scheduler`；worker构造、就绪通知、运行循环、SIGTERM和D16最终记录继续由该实现负责。此处只复用native service/sampler capture与shutdown，不安装R040的exact-ID HTTP、parking、cold/warm缓存初始化层；设置后两种控制会直接拒绝。普通SSE输入与真实worker token IDs须按已有输入binding核对，不能把本接线当成exact-ID endpoint已安装。

启动配置在导入原生状态池之前校验并设置 `FT_DEV_STATE_DUMP=<FT_D16_SERVICE_CAPTURE_DIR>/d12_state`。若状态池已导入且路径不符，拒绝继续；不能在Scheduler构造后再改环境变量。诊断要求显式 `FT_D12_DIAGNOSTIC=1`、TP=1、native NVFP4、no-overlap、threshold为0或256、route trace关闭，以及正整数 `FT_D12_MAX_EVENTS`/`FT_D12_MAX_EVENT_BYTES`。D16原有expected-query、capture预算和执行身份仍须提供；本模块不自行生成这些准入输入。

原D16 installer创建adapter后才安装两个已有observer。`d12_events.jsonl`独占创建，逐事件绑定D16 registry内的物理admission ID、prompt token SHA和worker身份；原生四类状态文件仍写入d12_state。观察错误登记到原adapter并重新抛出；清理错误不遮盖原运行错误，原D16终态会记录failed。没有新增round或verdict格式；这些附加文件的正式整包清单/D04接线仍须验证。

最终Linux **51PASS**：27项bank审计、10项segment（含原生CPU状态池）及14项worker测试。真实D16 worker函数、ServiceCaptureAdapter、SamplerCapture和LinearStatePool实际执行；Scheduler、模型forward和硬件metadata是CPU夹具。正常夹具只产出`cpu_fixture_no_cuda` fallback和post-prefill状态；故意破坏wrapper ownership的夹具保留原始异常，D16终态failed。两者均shutdown恰好一次、CUDA未初始化、未声明bank equality。pickle回归仅证明函数可序列化，不是实际服务spawn验证。

准确源码包及保留的成功/故障夹具产物：`/data2/FreeToken/runs/dev_D12/worker_wiring_v5_cpu_20261008_1907/`，实际回执时间19:00:14（目录尾数是产物标识）。回执SHA `52e09a16dfc84413ae717136c6a2b70bd3055f82a9ddbf809040f3f1065e8ca1`，本地副本 `../D12_WORKER_WIRING_CPU_20261008.json`；worker源码SHA `c0af696da53ee6256195384eda7760d2cdfec953be7e25b5d4811fdbd0a952bf`。独立只读复核为PASS_LIMITED，范围同上。此前v1夹具inference_mode缺失及v3 Python3.10兼容失败产物保留；候选8f6a912和已准备R062均未修改。

后续仍需实际CLI/spawn路径验证、原始payload与admission/token绑定、真实CUDA bank完整性、状态/固定后续token logits/普通SSE输出四层比较；性能臂不安装这些同步读取observer。当前不能申请本功能性能已接受或称GPU tools-ready。

## 19:20 冻结输入与实际 admission 绑定

`replay_binding.py` 校验已冻结输入包 `binding.json` 的外部 SHA、三条原 payload 的完整文件 SHA 和 canonical JSON token IDs；不重写 tools 或其他请求字段。CLI `main()` 现在要求 `FT_D12_REPLAY_INPUT_DIR` 和 `FT_D12_REPLAY_INPUT_SHA256`。直调 worker 函数仍可用于明确不声明普通API输入的旧 CPU 夹具；正式普通SSE入口不得省略这两个变量。

guard 在原生 admission 前逐项检查 UID 0/1/2 的顺序、完整 input IDs、temperature=0、max_tokens=2048、ignore_eos=False、空 stop_strs；失败写入原 adapter 的 observer error 并拒绝该次绑定。成功后由原 adapter 建立物理 admission 身份。D12事件同时携带冻结包、payload文件及JSON token文件SHA；原D16 prompt SHA是int32字节编码，两种hash用途不同。payload SHA证明冻结文件原字节，实际token匹配证明worker输入；本轮没有HTTP实际发送字节证据。

Linux **67PASS / 14.55s**，准确源包 `/data2/FreeToken/runs/dev_D12/worker_binding_v2_cpu_20261008_1921/`，回执时间19:20:26；`receipt.json` SHA `d29d9d937750e080d73c158a411a8457bde92df18402e091529f4d3113f7c676`，本地 `../D12_REPLAY_BINDING_CPU_20261008.json`。三条真实冻结输入（12660/12905/12987 tokens）均通过实际D16 admission组件与worker函数的CPU夹具；模型forward/Scheduler仍是夹具，每条只产生事先声明的一枚测试token，不是原始请求的自然结束或正确生成。另覆盖token/UID/顺序/采样参数/重复admission错误，D16 expected_queries逐项保持原值，CUDA未初始化。候选8f6a912及旧R062包未改。

v1的63PASS/4FAIL保留：故障注入测试复制了封存源的只读文件mode，写测试副本失败；v2仅改变测试副本的复制函数，不修改原封存输入。原输入包、工具/原生依赖SHA在测试前后均一致。测试不重跑模型、不持有GPU锁。

本次发现的下一项实质缺口：原始三条请求都有tools，历史生成数140/58/113，API以tool_calls结束；这些是历史观察值。现有D16固定expected-generation契约不能直接用max_tokens=2048表示自然结束，也不能在观察实际输出后偷偷扩展/缩短expected列表。当前实现未改此语义，不能据此启动完整D12普通SSE验收。下一步需要显式区分“冻结UID/输入/生成上限与自然终止的采集完整性”及“control/enabled完整token/SSE输出等价”；复用现有组件时必须让reader识别该契约差异，不能让旧D16固定生成数reader误接受。自然终止契约、实际CLI/API/spawn、四层数值及性能仍未实现/验收。

## 19:36 显式自然终止采集契约

上一节定位的自然结束契约现已实现并通过CPU验证。`natural_capture.py::NaturalServiceCapture` 复用D16原生admission、sampler快照、实际发送观察和finalize生命周期，只覆盖完成条件与输出文件。每UID预先声明输入与生成上限（原payload为2048），实际发送必须逐token对齐物理sampler，连续从0计数，每UID至少一条、只有最后一条finished=True，terminal之后再交付立即失败。流水线多算出的physical sample仍保留为undelivered，不算作输出。

显式 `FT_D12_CAPTURE_POLICY=natural-terminal-v1` 配合已冻结的输入目录/SHA启用；CLI要求该模式。设置旧 `FT_D16_SERVICE_CAPTURE_EXPECTED_JSON` 会拒绝启动，不能混用两种契约。直接调用worker的既有fixed CPU夹具仍保留原路径；正式普通SSE诊断必须选自然模式。

采集前独占写入 `d12_natural_capture_policy.json`，结束或失败写入 `d12_natural_service_delivery.json`，schema为 `ft_d12_natural_service_capture/v1`。不创建旧 `service_delivery.json`，不发布fixed `expected_deliveries`，也不改变原D16源文件。自然模式仅在实例创建时使用不可变的generation上界表复用原token对齐检查，不从实际输出反写预期长度。

`read_natural_delivery` 要求调用方提供预先冻结的policy和owned worker process identity；复用原 `read_logits_receipt` 一次检查全部sampler文件/张量/历史，再交叉核对三条admission、实际输入/采样参数、每次delivery、terminal、上限及未交付physical样本。D03 probe固定SHA `7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7`。返回 `capture_complete=true` 时仍明确 `output_equivalence_verified=false`；该helper不执行D04封存，也不替代control/enabled数值或SSE等价比较。

最终Linux **87PASS / 25.39s**，独立复核PASS_LIMITED。源包 `/data2/FreeToken/runs/dev_D12/worker_natural_v1_cpu_20261008_1936/`；回执SHA `8e05cb3adbe12051831f1410f84682d0486eb9d6cba4636df99bea0d6c4e6a66`，本地 `../D12_NATURAL_CAPTURE_CPU_20261008.json`。natural源码SHA `ff86cca77a0d4a9ed7cc4fb6280bb6da1d80f8af575eb5677c91ef6936a613c6`，worker源码 `f7d746a5be9082237a04fc57010e76c9f17c0bb89bee88320dd0165930860f58`；11份本地源与服务器相同，6份既有依赖和原输入包在测试前后SHA一致。

五个实际D16入口CPU夹具含自然正常与清理故障：自然模式三UID分别发送1/2/3枚受控测试token，完整读取通过；故障模式保留原始异常并写failed。两者均不创建旧报告，旧reader明确拒绝，shutdown各一次，CUDA未初始化。专门覆盖terminal后交付、超上限、缺terminal、物理token不匹配、observer故障，以及policy/identity/admission/snapshot等12类reader负例。模型forward和Scheduler仍是CPU夹具，不能把这些token称为目标模型生成。

尚需实际CLI/API/spawn路径、正式调用方/D04接入这个明确的新报告与reader，以及bank/状态/固定后续token logits/普通SSE四层比较；特别是固定后续token比较不能用已分叉的自由生成轨迹替代。性能臂排除同步读取observer。候选8f6a912及R062固定包未变，当前仍非enabled GPU tools-ready。

## 20:00 CLI/spawn 入口与兼容性检查

真实候选 CLI `serve --help` 及真实 Python spawn 的主模块 worker 目标反序列化已通过 **2PASS / 9.59s**。spawn 测试使用真实 worker 脚本、真实候选导入与真实子进程，在 CLI dispatch 边界替换调用，并故意以 TP=2 触发 D12 的 TP=1 保护分支；子进程预期 exit=1，不创建 capture。该证据覆盖入口可导入与目标可跨 spawn 解析，不覆盖实际 ServerArgs 传递、Scheduler 构造、模型加载、API 服务或 GPU 推理。

准确源包 `/data2/FreeToken/runs/dev_D12/entry_v2_cpu_20261008_1958/`，回执实际时间19:54:47（目录尾数为产物标识），SHA `a30ad70f66a4398ce1ea7d826b206e30e20b269e41c1cb5839dad85b25351f3a`，本地 `../D12_ENTRYPOINT_CPU_20261008.json`。12份本地Python源与回执SHA匹配。此前v1为1PASS/1FAIL：测试及规划文档误用了 `--no-moe-prefill-overlap`；候选真实参数为 **`--disable-moe-prefill-overlap`**，修正后通过。旧失败包、冻结分析JSON及候选README原字节保留；当前规划文件已勘误。产品候选和R062未变。

固定后续token logits尚有候选兼容性缺口：D03原probe要求raw-token/dev_logits服务钩子，8f6a912没有这些钩子，不能仅复制客户端就运行。逐个请求P+X[:i+1]并读原D16 sampler可得到独立teacher-forced最后位置logits，但它改变分段/缓存过程，不能冒充同一P+X请求的tail-K或连续状态恢复证据。完整D16 exact installer还安装parking、batch geometry与状态控制；普通SSE臂不得整体复用该installer。需保留D03/T04原有数值判据并解决这个窄输入/采样边界后再提出enabled GPU范围。

普通SSE可复用v8原始wire采集，再使用已安装OpenAI SDK离线组装content、reasoning和分片tool_calls；Quality60文本专用projector会拒绝tools，不能用于此三条payload。D04原有整包manifest会收录新增常规文件，但正式调用方仍须先调用自然契约reader并完成四层比较；文件被列入manifest本身不证明语义验收。
## 20:10 普通 tools SSE 离线完整结果读取

`ordinary_sse.py::decode_ordinary_sse` 是单响应读取 helper，没有服务生命周期、请求循环或 round/verdict。调用方先用既有 `r046e_t06_ordinary_client_v8.ordinary_request` 保存原始 SSE；helper 校验外部给定的 payload/SSE SHA 和物理文件，复用 v8 的既有 metadata reader，再使用隔离环境的 OpenAI SDK 2.54.0 `chat.completions.stream` / `current_completion_snapshot` 拼接正文、reasoning、工具调用ID/名称/完整arguments、finish和usage。

SDK只连接 `httpx.MockTransport`，断言恰好一个语义与原payload相等的请求（tools/messages不变），`trust_env=False`、`max_retries=0`，不会联系模型端点或执行工具。原始 `.sse` 继续保留，负责完整wire、chunk边界及非标准字段证据；SDK final snapshot是规范化结果，不冒充逐字节wire或任意扩展字段的无损转换。返回值显式 `output_equivalence_verified=false`，尚未连接正式D04调用方或两臂输出等价判定。

Linux **15PASS / 1.03s**，独立只读复核 **PASS_LIMITED**。真实封存 R046g 的 G_seed12k UID0/1/2，140/58/113个completion tokens全部离线回放通过，三条均保留tool_calls终止及 `list_dir` arguments：`{"path":"."}`、`{"path":"python"}`、`{"path":"python/freetoken"}`，原tool ID、正文和reasoning均保留。该回放只验证读取兼容性，不是新候选生成、GPU或输出等价证据。

准确源包 `/data2/FreeToken/runs/dev_D12/ordinary_sse_v2_cpu_20261008_2008/`；回执实际时间20:06:44（目录尾数为产物标识），SHA `82c63e5ee8aa103f897463061b84f56dbb0a0f0f399ee9bd43e8e20e97c2775c`，本地 `../D12_ORDINARY_SSE_CPU_20261008.json`。源码SHA `661f731ca1b6f9d3ec2ddac5497cfd23eb58330158a41eb04c93173ae42e3516`；五份源/依赖与本地一致，12份封存binding/API/payload/SSE证据测试前后SHA不变。成功与故障测试的raw及三条历史decoded JSON均保留。

v1的14PASS/1FAIL原样保留：真实warm usage含nested cached_tokens，SDK附加audio_tokens/cache_write_tokens=null，造成直接字典比较假拒绝。v2对SDK usage使用递归生效的公开 `model_dump(exclude_unset=True)`，仍严格要求全部wire字段相等，并单独保留wire_usage。覆盖length/stop/tool_calls、split工具参数、reasoning拼接、缺失/重复/后续DONE、缺失/后续terminal、错误UID/choice、usage冲突/总数、损坏JSON和SHA拒绝；不调整原模型生成或验收判据。
## 20:38 同一普通请求的固定 prompt-tail logits

前述旧D03客户端不能直接用于候选的限制仍成立；本次在已有普通请求上复用D03采集组件，解决末尾K位置读取的接线。显式将每条冻结完整input定义为 `P=input[:-64]`、`X=input[-64:]`，两者相接仍是同一完整业务输入。没有新增P-only warm请求，没有把X称为新生成的后续回答，也不声明D03恢复臂或连续decode证明；自然SSE输出继续独立验证。

新 `prompt_tail.py` 包装实际模型最后一个decoder layer实例的forward与top mixer实例的mix，原方法照常执行，返回原tensor对象。最后子段保留原top-mixer的实际输出；较早且覆盖尾部位置的子段保留完整hidden，outer forward返回后用原top mixer按完整child形状计算，再截取目标位置。不能只对选中行执行top mixer而假定GPU逐位相同。原模型普通/层优先forward、子段顺序及LM-head最后一行的生产返回路径均未替换。

D03的 `capture_logits`、TP1 `ParallelLMHead.project_rows`、`LinearStatePool.dump_dev_tensors` 和 `logits_probe` 四份源码按固定SHA加载，不移植其完整服务端/parking框架。由D03原collector按绝对位置跨outer/child积累tail-K、投影完整词表fp32 logits，并使用原writer写五角色状态+logits格式；完整input SHA、K、长度和positions通过原reader回读。end-state来自已有D12 native post-prefill四角色文件及SHA，不宣称每child状态。

worker显式 `FT_D12_PROMPT_TAIL=1` 才安装；必须有冻结ordinary binding，并提供 `FT_D12_D03_ROOT=/data2/FreeToken/wt/e2d03-continuation` 和正整数 `FT_D12_TAIL_HIDDEN_BYTES`。`prepare_environment` 在native worker前检查D03源SHA并绑定 `FT_DEV_LOGITS_DUMP=<capture>/d12_prompt_tail`。该值约束保留hidden的字节，额外投影的临时张量与原模型内存仍须GPU实测，不能把它称为总显存上限。性能臂不得启用本observer。

既有state事件先追加到 `d12_events.jsonl`，随后调用prompt-tail observer，成功后追加logits事件；两者由同一worker emitter绑定实际admission身份、process identity和冻结输入。close检查全部声明UID完成；不完整记录observer error，仍按原生命周期执行清理及shutdown。最后layer/mixer实例恢复有ownership检查，旧自然/固定采集默认模式不变。

Linux完整回归 **97PASS / 33.22s**。准确源包 `/data2/FreeToken/runs/dev_D12/prompt_tail_v2_cpu_20261008_2035/`，回执实际时间20:31:31，SHA `1c30d2b8fa8fec35c04e7d64e84956110cfbb9808d03fc9590c612f39386f68b`，本地 `../D12_PROMPT_TAIL_CPU_20261008.json`。prompt-tail源SHA `1e6d3bc0f5e1b5ad7bfb4eb378ceb3bc9d4c70e99f82138b1683c0c35b4a35cf`，worker源SHA `9d0188e6acb931952db30c785553c69e78806b70cd3eeb6411e1d6ad0d93ff43`；16份本地Python源与回执一致，原生候选tracked clean，D03/既有依赖及冻结输入测试前后SHA不变。

CPU覆盖真实候选model loop、GatedResidual CPU math、ParallelLMHead和D03 collector/writer/reader；decoder层、权重与调度数据是受控夹具，未加载目标模型权重。普通、层优先及跨outer测试均取得位置8..11；layer-major测试验证额外mix使用完整五行child，非只选两行。worker installer夹具完成K64位置16..79，另验证不完整close注册错误/shutdown一次；原生D16完整生命周期的5个既有CPU夹具也通过，但它们没有开启新tail模式，不能混称新tail已通过完整native-worker端到端故障验证。

独立复核已通过SSH实际回读，结论 **PASS_LIMITED**。worker完整fixture的index SHA `116fa63bb6dc2f460ecafb28fa69b339ef4e17211f264a61eb8aafe666c39caf`，logits tensor SHA `f87bc2b5cd2841b86553d2d1bd5c0589e2aa0371d857b809c69c03a6b9b31b86`（CPU `[64,5] float32`），events SHA `fb3fd95a7c14f553a22010e650f74992e768d8ffca38b73a5423969b91a962d3`。额外完整child投影覆盖16..23、24..63，实际top-mixer覆盖64..79。早先仅基于源码/消息的复核不充作产物独立验证。

真实三请求的预声明policy另存 `../D12_PROMPT_TAIL_POLICY_20261008.json`，SHA `b119ceb3032dd1e887a01e7e08ec6c2651296b7689b8aba99751e5e0ecdb6755`；外部生成回执 `../D12_PROMPT_TAIL_INPUTS_20261008.json` SHA `478f8a5ad4b065f0627f2eec039fde7d58275d2b40803f046c21bad07b1717e6`。UID0/1/2的K均64，位置分别12596..12659、12841..12904、12923..12986，保留hidden上限512MiB。这是预先固定坐标与输入分区，尚未在目标GPU取得这些logits；新运行的实际分段/命中与内存仍须验证。

下一项是正式调用方独立读取并汇合bank、四角色状态、固定输入logits与完整SSE证据，完成control/合法重排/启用臂比较及D04封存接线。数值容差继续沿用D03/T04独立标定，不从D12误差生成。GPU正确性、真实服务/API及性能尚未验收；本轮不修改候选8f6a912、R062固定包或既有GPU授权范围。

## 20:56 状态与 prompt-tail 的独立消费

新增 `capture_reader.read_state_tail`，读取已经停止的 capture。调用方必须独立给定自然结束 policy、tail policy、worker process identity、完整词表大小和四角色状态的 shape/dtype/layer IDs，以及固定 D03 源目录；读取器不会用产物自报值补齐这些期望。先调用既有 natural reader 验证实际 admission、采样及交付，再将事件逐项关联到同一进程、物理 admission、原始输入和 payload SHA。

读取器逐项校验全局 outer 索引和每 UID 的连续 outer 几何、native state index 与事件的一一对应、全部状态文件的 SHA/字节数/布局、D03 tail index 与事件的一一对应、完整词表 fp32 logits、绝对末 K 坐标、投影所引用的实际 outer/child、外部 layer IDs。D03 tail 的四角色 tensor 还必须逐字节等于对应 native 最终 prefill 状态，不能只凭两份自报 SHA 一致放行。文件须为实际文件且始终保持原 SHA；缺失、额外、乱序、符号链接、跨进程/跨 admission 均拒绝。D03 的 source pin、binding 与 bit_equal 继续复用；没有新增服务循环或 round/verdict 系统。

Linux **117PASS / 34.25s**，源包 `/data2/FreeToken/runs/dev_D12/state_tail_reader_v2_cpu_20261008_2056/`，回执实际时间20:55:05，SHA `822aff655d9496ec5745a3d68998da095bb2150b0d197538f4bcd7b083adc1af`，本地 `../D12_STATE_TAIL_READER_CPU_20261008.json`。读取器源 SHA `13a8655248e79303e4f9cc4e93cea7cc528d3b3143ae3613e1db1cc190e7cc12`，18份本地Python源码均与测试回执一致；候选 tracked clean，D03/既有依赖和完整冻结输入测试前后 SHA 不变。

新增20项：一个联合组件正例和19个拒绝负例。三条真实冻结输入经同一个实际 D16 adapter、D12 worker installer、候选 model loop/HC/LM head 与 D03 组件，得到各自末64位置的 `[64,5]` logits、四角色状态及各一条测试采样交付。UID1 使用 layer-major 三个child，尾部跨两个child，分别来自完整child额外mix和实际top mixer；另外两个 UID 使用普通路径。decoder层、五词权重、argmax采样器、初始状态和 finished 信号仍是受控CPU夹具；该测试不是目标模型的自然生成、CLI/spawn或真实HTTP/API端到端证据。

19个拒绝负例包括修改外部期望、进程/admission/冻结输入、事件顺序、缺失/额外索引、outer几何、tensor损坏、投影位置和符号链接。尤其同时更新 tail tensor、其 SHA 和 index/event 的内部一致内容后，读取器仍因其与 native 最终状态不同而拒绝。v1原始 **97PASS / 20 setup ERROR** 保留，回执 `194619f14493b3ce25659ed5dedd6714bc07457b254e2104cc0e8dd6b6c31f4f`；原因是测试capture路径漏了worker要求的 `dev_D16` 目录，v2仅修正测试路径，未放宽生产检查。

独立源码复核及SSH实际产物复核均为 **PASS_LIMITED**。reader result SHA `ef124b6f588cb13e13b511689fe5ab1fd5557cb899f422e1f854f6c63a74830d`，events SHA `ad7acbe744a9b6d6fd5e91c55476a915d1d50c56c11cdff3f7c94583a3159872`，state index `7030fac0cfa139191284d7b756894a63926c2d12939a7674e544aa3db31b0400`，tail index `d55da695527bc869e1fc04624acf1933d5b3f5a53276bafba58678320f590a08`。实际三UID末64坐标分别12596..12659、12841..12904、12923..12986，已逐项核对产物清单。

本reader返回 `state_tail_bound=true`，同时保持 `bank_coverage_verified=false`、`prefill_schedule_verified=false`、`output_equivalence_verified=false`、`performance_eligible=false`。bank事件若存在，只检查其公共身份及outer/child关联；事件为零不能证明全部MoE调用已覆盖。初始cache命中、完整调度/调用分母和CUDA bank仍需与实际D0及模型布局独立关联。D0保留outer、subchunks和layer事件，但主诊断不能启用会禁用layer-major的route trace。

SSE跨臂比较的源码依据已核对：API `created` 为运行时钟、tool ID含服务生成UUID后缀；它们应保留原值并验证结构后，再由显式比较口径处理。冻结UID0/1/2仍须严格绑定，不能泛化成任意UID。完整生成token、正文、reasoning、工具名称/arguments、finish和usage的正式比较，以及bank分母、独立数值标定、D04调用方和GPU功能/性能，仍是后续任务；本次未启动新GPU范围。

## 21:11 普通 SSE 的源码绑定比较

新增 `sse_compare.read_native_sse` 与 `compare_native_sse`，继续调用既有 `ordinary_sse` 的v8 metadata检查和SDK组装。调用方给定固定payload SHA、两个SSE文件及各自SHA、预期UID0/1/2、候选API源码文件和已固定的ordinary client；API源必须匹配Linux raw SHA `37b2a0034288dddda25d06213e9f5d470c2f2a56c84b77aa32995f0763546801`。本地CRLF字节不同，不能用本地raw SHA冒充远端源证明。

本比较器只接收普通、未启用dev-stream、成功的native SSE。未知顶层/choice/delta/usage字段、`ft_dev`、错误frame及不符合源码格式的tool事件均拒绝。wire检查明确created为非负整数且允许每chunk变化，completion ID严格绑定预期UID，model匹配原payload。tool start必须按0起始的连续index出现，ID必须等于源码生成的函数名前缀、index和8位小写hex UUID；后续arguments片段只可继续当前tool index。opening、terminal、usage时序和既有单一最终DONE检查共同执行。

语义视图仅排除 `completion.created` 和tool ID最后的UUID部分；tool ID的函数名/index前缀、completion ID、正文、reasoning、函数名、完整arguments字符串、finish、usage及其cached_tokens均精确比较。arguments不做JSON重排或空白归一化。SDK负责跨chunk拼接，chunk切分差异本身不判语义不同。两侧完整原始SSE SHA、SDK completion、全部原tool IDs和每chunk时间戳仍保留。返回 `sse_semantics_equal`，`output_equivalence_verified` 始终false；逐token序列和数值门仍须由正式调用方分别验证。

Linux **46PASS / 1.39s**，在已安装的SDK评估环境执行；准确源包 `/data2/FreeToken/runs/dev_D12/ordinary_sse_compare_v2_cpu_20261008_2113/`，回执实际21:08:12，SHA `6ad1b5d018fb110689c5a8314f6a30cdc008957f48b9bae200abd7d4be49ee09`，本地 `../D12_SSE_COMPARE_CPU_20261008.json`。新比较器源 SHA `a39d289bda1d2ccb1669241c75e68c5ed299873cd7d6449c4ce38c8eba851381`，七份本地源码与远端一致；另绑定候选API源和12份原历史证据，测试前后均未变化。此前v1的43PASS原样保留，v2增加early-usage拒绝和无tool/双tool覆盖。

独立源码复核及SSH实物复核均 **PASS_LIMITED**，全部20份源/历史绑定重新计算通过。封存的三条G_seed12k响应在自有副本中仅修改运行时钟和UUID，原件不变，两侧SSE SHA不同但语义相等；140/58/113个completion tokens和warm cached_tokens12608/12864完整保留。八类正文/reasoning/arguments/arguments空白/name/finish/usage/cache差异负例均判不等；无tool、两个tool及不同arguments分片正例通过。该结果是历史响应离线消费，不是新候选输出或GPU验收。

服务器FT专属venv只读检查已确认同样存在 openai2.54.0 与httpx0.28.1，后续CPU正式调用方可在既有FT环境组合torch读取和SDK比较，无须混入KT环境或新增依赖。本轮尚未完成三臂数值、实际bank覆盖/D0调度分母和D04汇合，也没有新增GPU运行。

## 21:50 原生 D0 调用分母与 bank 事件完整性

显式 `FT_D12_D0_COVERAGE=1` 在worker启动前设置 `FT_DEV_D0=1` 和本capture独占的 `d12_d0` 路径；原生D0产生 `d12_d0_prefill.jsonl`。不改变decode timeline/graph设置：已固定候选的GraphRunner仅对decode使用CUDA Graph，普通prefill本来就是eager。route trace继续关闭，prefill overlap必须关闭，不能使用dev-prefill-schedule替换普通路径。

segment observer要求fresh D0文件，每个admitted outer forward完成后恰好追加一行，旧前缀不能改；在发布native state事件前绑定该行的offset/长度/SHA/原始record、真实cache device、层数与阈值。`d0_coverage.read_coverage`固定九份native调用链源码SHA，从完整外部MoE层IDs和D0实际subchunks推导所有层/child调用；既检查native完成记录的数量与顺序，也要求全部阈值命中调用恰好对应一份bank成功或fallback事件。分母不来自已观察到的bank事件。continuation的native cached_tokens可能为0，绝对位置仍取outer/subchunks。

完整reader通过可选但必须同时提供的 `expected_moe_layer_ids`、`expected_routed_only_threshold`、`candidate_root` 接入此检查，D0文件加入其稳定SHA清单。`eligible_bank_call_events_complete=true`仅表示全部应有事件齐全；bank覆盖/字节成功要求CUDA范围、至少一次命中、每次命中均有六bank完整字节校验且没有fallback。无命中、全回退、部分回退均不能声明bank已验证。独立审查指出旧flag仅看device的误接受风险，已修正并加入四个合成scope逻辑用例；这些用例修改的是CPU输入副本，不是CUDA证据。

最终Linux **170PASS / 35.78s**。准确源包 `/data2/FreeToken/runs/dev_D12/d0_coverage_v4_cpu_20261008_2201/`，回执实际时间21:46:03（目录尾数为产物标识），SHA `b287ceed1062d97d6497c776ad74258c4fd60dbc9c61861c2a789488cd42f5b9`，本地 `../D12_D0_COVERAGE_CPU_20261008.json`。22份本地Python源与回执一致；总计40份源/依赖及10份冻结输入测试前后SHA不变，候选8f6a912 tracked clean。reader源SHA `1eeb54baa397926cee9be9fc672b907e0a282694ba56ab1ee38bd2f687aaf1e1`。

覆盖普通64/600段、层优先300/256/44三child、threshold0/256、成功/回退及缺失/乱序/错误层/错误字节/SHA等拒绝。实际OffloadMoELayer分支与native D0 writer执行，copy/GEMM/CUDA events为受控CPU接缝。联合夹具再经实际D16 adapter、worker installer、candidate model loop、D03 collector与完整reader消费三条冻结input；D0模式threshold0取得UID0/1/2的2/6/2次调用，共10次、0 eligible，仍绑定四角色状态和各末64 logits。该结果不是目标权重、真实Engine调度/服务或CUDA计算。

v1的146PASS和v3的166PASS保留；v2原始146PASS/20setupERROR及回执 `a03f6c2fa9c64d1e40b81e7634f532e03d6ae37a4368b613195556e3ed512571` 保留。v2是测试prepare_environment直接写D0环境变量导致跨用例残留，v3修复monkeypatch的环境恢复与显式fixture配置，未放宽生产检查。

所有真实CPU产物仍保持prefill_schedule/bank_coverage/routed_bank_bytes/output_equivalence/performance为false。当前完成的是诊断接线与离线完整性逻辑；正式调用方仍须独立冻结目标模型布局、核对真实D0/短段覆盖、比较完整生成token/SSE及三臂状态/logits，并接入D04。D03/T04容差不由D12结果反推；CUDA正确性、真实API与性能仍未验收。

独立源码复核及SSH实物复核无剩余阻塞，结论限于上述CPU范围：重新计算40份源/依赖、10份输入、5份D0结果与2份state-tail结果全部一致。D0联合结果SHA `5629d161618d19fabfe81828723740c03e820ed221ee98b23831f7f32d1899ad`，2/6/2调用与零eligible、全部CUDA/bank字节验收flags为false已实际回读。

## 22:10 完整 token/SSE 与状态/logits 的成对消费

新增函数 `capture_compare.compare_capture_pair(reference, candidate, *, ...)`，没有新服务循环或轮次系统。每臂显式提供 `capture`、owned `process_identity`、`threshold` 和 `sse={uid: {path, sha256}}`；公共参数独立提供自然/tail policy、完整词表、四角色状态布局、MoE层IDs、D03/候选源码目录、三份原payload路径与既有ordinary client。两capture目录不得相同或相互包含，worker的pid/start_ticks必须不同，对应UID不得复用同一SSE路径。角色、独立重复与合法重排资格仍由正式调用方冻结，不能由差异结果推定。

两臂先各自执行完整 `read_state_tail`（包含D0分母检查），再从已验证的自然报告逐UID提取全部交付token，要求处于完整词表内。候选generation/tokenizer/scheduler四份源码固定SHA，建立usage链：每个DetokenizeMsg对应一个completion token，完整prompt在首次prefill记一次，cached_tokens对应第一outer的start。SSE prompt/completion/cache必须与实际admission/交付/首段一致，不用历史140/58/113或请求上限2048冒充实际长度。

普通SSE继续使用既有SDK与source-bound语义比较；完整token序列另行精确比较，报告首次分叉索引，不能用文本相同掩盖token不同。末64 logits使用固定D03 `metrics` 的逐位、top-1、top-2 margin、每位置KL和绝对输入位置；四角色最终状态使用其 `state_difference`，并由前置reader证明这些tensor等于同次native最终prefill状态。保留两侧原SSE/SDK结果、原随机IDs、全部token和artifact SHA。结束时再次校验采集文件、自然policy、sampler manifest/receipt/snapshot、SSE、payload与源文件，拒绝读取期间改变。

最终FT专属venv组合回归 **236PASS / 42.76s**，包含既有CPU/状态/D0和SDK历史回放。源包 `/data2/FreeToken/runs/dev_D12/capture_pair_v2_cpu_20261008_2230/`，回执实际时间22:08:15（目录尾数为产物标识），SHA `27db5a38cedd0212330796976d04e4a12844658aeead79e5d41ea7849a528ac6`，本地 `../D12_CAPTURE_COMPARE_CPU_20261008.json`；比较器源码SHA `3e62bf00b8280717093c6c857f0b44004d160a5024ed078ac00ac6daf53cceaf`。27份本地源码与回执一致，总61份源/历史证据与10份冻结输入测试前后SHA不变，候选tracked clean。v1的233PASS原样保留；v2补三token与同物理进程拒绝覆盖，没有放宽判据。

新增20项覆盖四个独立变化轴、usage/input/cache/身份/路径/SHA/阈值拒绝。多token夹具每UID通过实际sampler/history/Detokenize自然报告交付 `[4,4,4]`；另一独立CPU产物为 `[4,4,0]`，首差异严格等于2、两侧usage均3、同一prefill的tail仍相等。decode logits、decoder权重和SSE均受控生成；该测试没有执行候选真实decode、目标权重、HTTP服务或GPU，不能拿其SSE与token文本关系充作真实detokenizer证明。

数值结果只记录指标和严格相等，各臂整体的 `numerical_acceptance_verified`、`output_equivalence_verified`、`performance_eligible` 均保持false。权威T04卡顶部10-06 21:05块和PLAN §4.1已明确：S-007只给状态差异分布，合法重排包络不能单独放行。它当前的分布交付不应因缺放行阈值重新挂起；本README早先“沿用T04容差”的措辞不能被解释为已有可调用阈值。后续正式D12功能门须冻结适用的比较/复核规则，不能根据D12观测误差造容差，也不能把T17的恢复证明直接套给没有restore arm的本观察器。

当前已具备成对完整读取及差异计算；正式多臂调用方、实际调度/短段CUDA证据、真实API输出、功能判定与D04接线、性能测量仍未完成，旧R062默认关闭包和GPU范围不变。

独立源码与SSH实物复核已完成：61份源/历史、10份输入、7份pair结果及结果所引用的capture/SSE/payload SHA全部一致。七类变化各落在对应轴，所有正式接受flags为false；multi_late结果SHA `31cb14a169658a5cf8d7a3f44204681dcb7301dbdedac3e7fdc9fdf555ecdf91`，三UID的完整序列、位置2和usage3已实际回读。最初审查指出的单token覆盖不足和README缺项均已补齐。

## 22:26 目标模型的外部状态规格

新增 `target_model.verify_target_model`，为正式调用方冻结 `expected_vocab_size`、`expected_state_layout` 与 `expected_moe_layer_ids`。三项在返回的 `reader_arguments` 中，可传入既有 `read_state_tail` / `compare_capture_pair`；它们来自预先固定的目标规格，并与实际配置及原生 meta 状态池交叉核验，不从待验收 capture 推导。

实际服务的配置入口是 `/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json`，目标为 `/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json.qwen4_exp.orig`，SHA `deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80`。模型主目录同名 `config.json` 是另一个 `qwen3_next` 兼容配置，不能代替本次服务的原始 `qwen4_exp` 配置。验证器检查 alias 的解析目标和字节、12份native配置/状态池/模型/调用方源码，以及实际导入模块来源；前后重复核验文件稳定性。

本规格只支持调用方明确声明的目标名称、TP1、模型 bfloat16 与 SSM float32。SSM环境及已经导入的ENV值均须匹配，拼错后由native函数静默回退到float32也会被拒绝。实际worker/launch设置仍须由正式调用方绑定；调用参数本身不证明服务采用了它们。

| 状态 | 单请求落盘形状 | 类型 | decoder层号 |
|---|---|---|---|
| conv_states | `[36,1,10240,3]` | bfloat16 | 0..47排除3、7、…、47 |
| recurrent_states | `[36,1,48,128,128]` | float32 | 同上 |
| slot:ple_conv | `[1,1,10240,9]` | bfloat16 | `[1]`；配置`[2]`使用从1开始的编号 |
| slot:ple_ngram_ctx | `[1,1,2]` | int32 | `[-1]`，共享状态标记 |

完整词表为248,320；48个decoder层均调用MoE，512 experts、top10、NVFP4，D0分母的外部层IDs固定0..47。这里只核配置及原生几何，未读取或验证权重。调用原生 `parse_config` 和 `LinearStatePool` 时使用meta设备，不分配CPU/GPU状态存储。

Linux针对性 **15PASS / 3.51s**，源包 `/data2/FreeToken/runs/dev_D12/target_model_v1_cpu_20261008_2235/`（回执实际22:25），receipt SHA `3725e1570f3ee926cfe4e7e4a4b09e786953900fde1112cb01b22fa666dcac7f`，log SHA `d9b4709bbd148e4236d2cbd3d779accd62d764d63af4476b778edb6d9ce540db`。12份native源、2份新增源码和原始配置在测试前后SHA不变，候选8f6a912 tracked clean。覆盖真实目标metadata和14项错误设置/alias/字节/模块/原生几何拒绝；测试没有创建模型服务。既有236项比较器回归证据仍单独保留，此次未把二者合称一次251项运行。

本地回执 `../D12_TARGET_MODEL_CPU_20261008.json`；目标规格 `../D12_TARGET_MODEL_EXPECTATIONS_20261008.json` SHA `05ca10680f2a88dee5ccdfa92a188c914696f438af3287aaf75fea02038725b5`。只声明 `configuration_and_native_geometry_verified=true`；权重、实际服务设置、输出等价和性能标志均false。正式多臂调用方、独立终态复核与D04、GPU功能和性能验证仍需完成。

独立源码及SSH实物复核已完成，未发现可操作缺陷。复算15项当前源/配置SHA、receipt/log/目标规格SHA均一致，并重新核验overlay真实目标与候选8f6a912 tracked clean；结论限定为配置/原生meta几何兼容性。

## 23:05 普通 HTTP 采集与实际进程归属

新增 `ordinary_evidence.py`，仅接收已经启动的 owner，不创建服务、轮次、GPU锁或重试循环。调用方负责 health-only 就绪和 finally 停服；本适配器一次发送三份冻结原请求，复用已固定的 R049 v8 `ordinary_stream_request`，保留原payload SHA、实际请求body、raw SSE、API元数据及逐event时钟。读取时继续调用既有源码绑定的SDK比较入口，校验UID、usage、finish、raw/event内容和单调时钟，所有输入/源码在读取结束再次校验。

每个HTTP请求前后读取真实 `/proc`，把IPv4 loopback监听inode及其当前UID全部持有者与owner的PID/start_ticks/PGID/session/netns关联；不能先按PGID过滤，否则会漏掉继承socket后通过setsid脱离进程组的子进程。任一同inode持有者不属于owner即拒绝，当前UID的FD权限或身份读取失败同样拒绝。收据明确 `same_uid_listener_exclusivity_verified=true`、`global_listener_exclusivity_verified=false`，仅证明请求边界两个采样点的同UID观察，不证明跨UID或连续独占。

收到响应后，以本次实际admission中的worker身份对照新读取的 `/proc` 出生、PGID/session及预期execution `:tp0`；三个UID须保持同一worker。`record_stopped_worker`只接受外部SHA绑定的完整collection，再串联三份live-worker proof；只有原owner已停止、worker/frontend消失或同出生僵尸且受控进程组无存活成员时，才落盘停止证据。collection和所有proof的SHA保留到停止记录，不允许用另一服务的live记录拼接。

隔离Linux CPU验证 **21PASS / 27.60s**，目录 `/data2/FreeToken/runs/dev_D12/ordinary_owner_v3_isolated_cpu_20261008_2320/`（目录尾数为产物标识，实际完成约23:03）。receipt SHA `4916a01bcbd5ca386de8ea7b3077521d0a079cd1f2bc66f343a039be5f3a8603`，log SHA `48eaaddeeb0b99a5fa38a14d9a39715935c7b4fdd2b0b32fefedb27a37fba098`；36份源码/依赖、10份冻结输入前后不变。源码 `ordinary_evidence.py` SHA `baa992cd8466c616d68d23e0eaf53239e2cce706891581d9319ce9ad3585c20b`，测试源 SHA `62d8531b88ad25c0e66ab687e6c397dcaea4f90c3cdacc7212b5d8db19f88dd1`。

测试实际创建CPU HTTP进程与同组子进程、发送完整原请求、走既有owned stop；SSE与admission内容为合成数据。真实fork→setsid子进程继承同一listener并实际处理GET，采集器在首个POST前拒绝；测试同时清理逃逸子进程与owner。主collection SHA `7f70adfe48353f2ff46288958f503f6c395300c8f46d8cbb36bf550679087649`，停止记录 SHA `4fd38bf9b66e0dc0d190153a1b784fe7225c772e55476b6dd79793cee797aee9`。独立源码及SSH实物复核通过，结论限于该协议/生命周期范围；未运行真实D16采样器、目标模型或GPU，不提升输出/数值/性能标志。

**宿主接入仍受阻。** 同一代码在普通宿主dell会话中遇当前UID的sshd、sd-pam FD访问限制，在发送POST前失败；没有跳过不可读进程。失败目录 `/data2/FreeToken/runs/dev_D12/ordinary_owner_v3_cpu_20261008_2312/` 保留，receipt SHA `f647fe98fb14002eeca0f4f0b5ad0edff000de7a897d7105e6fe7ddb05666ffc`，log SHA `97d4627c742e2ba3cfe313fd3c7a9bc5706a3e9d967c1e1469ac16e03402b3a6`。成功测试使用已有 `unshare --user --map-root-user --pid --fork --mount-proc` 能力，receipt仍明确 `host_proc_observer_ready=false`；它不代替宿主正式caller就绪。

接入方案需在正式启动前完成二选一的具体设计与FILEdry：为受控观察器提供必要的只读FD观察能力，或把完整owner/worker放入可观察的隔离PID范围并建立宿主↔namespace出生映射。不能直接把隔离测试中的PID当宿主PID，也不能复用已冻结R062批准包隐式改变启动架构。当前不新增GPU批准请求；先完成启动身份、正式多臂/功能判据和D04调用方的具体接线及独立复核。

本地回执 `../D12_ORDINARY_OWNER_CPU_20261008.json` 与 `../D12_ORDINARY_OWNER_HOST_BLOCK_20261008.json` 分别对应隔离通过和宿主拒绝。早先v1的13PASS、v2的18PASS保留在各自远端目录；它们是修复前证据，不作为最终归属检查通过依据。

## 23:26 四角色启动描述与参数层 FILEdry

新增 `arm_plan.py`，提供 `build_plan`、`validate_plan`、`file_dry` 和原生CPU参数probe。它只生成诊断proposal与参数层FILEdry，源码没有模型服务启动分支；这不是现有owned owner在Popen前边界的完整启动演练。正式多臂调用方、宿主FD观察接入、启动准入和D04仍须继续实现及复核。

| 角色 | layer-major | routed-only阈值 | 比较用途 |
|---|---:|---:|---|
| control | 开 | 0 | 主对照 |
| repeat | 开 | 0 | 独立服务重复性参考 |
| ordinary_reference | 关 | 0 | 合法重排差异参考，不能单独作为容差 |
| enabled | 开 | 256 | 与control比较D12功能 |

四臂均使用同一候选8f6a912、同一原始G_seed12k三请求、TP1/bfloat16/SSM float32、GPU offload/NVFP4、固定cache与容量参数，并显式 `--disable-moe-prefill-overlap`。`FREETOKEN_DISABLE_OVERLAP_SCHEDULING=0`保留原普通调度，区别于MoE prefill overlap关闭。原 `max_tokens=2048` 仅是每请求上限，不预设140/58/113或任何新运行生成长度。草案共4服务/12请求，`approved_new_services=0`，不会计入已批准或待批准GPU队列。

环境从明确的最小集合构造，不继承FT/FREETOKEN调试开关、Python注入路径或凭据；四臂唯一预先声明的算法差异为layer-major/threshold。每臂有独立输出路径和execution ID；API/TCPStore两端口成对互斥、限定12000..29999且排除当前kernel ephemeral范围。工具不bind、不监听、不预订端口，`port_availability_checked=false`，正式owner仍须在实际启动时复用现有端口检查。

采集上限显式固定为8192个物理采样/16GiB序列化采样工件、16384个诊断事件/256MiB事件文本、既有512MiB保留hidden预算。它们是超过即失败的诊断限制，不是预期输出数、磁盘预留或性能指标；正式启动前仍需容量与资源检查。自然结束policy与原始末64位置tail policy由现有函数生成，各臂完全一致。

父侧先以固定candidate/源/输入重新生成并核对完整plan，之后只启动CPU参数probe。probe在CUDA隐藏环境执行真实 `worker_capture.prepare_environment`、候选 `parse_args`、D16导入来源核验及原生meta目标几何检查，逐项核对所有关键选项；不进入 `launch_server`、Scheduler构造或HTTP。proposal的 `functional_rules_frozen`、`formal_launch_authorized`、`host_proc_observer_ready`、输出等价及性能资格均保持false。R062默认关闭接受、独立功能规则、owned准入/观察、独立终态复核/D04是单独前置，不能凭生成的argv跳过。

Linux **15PASS / 17.75s**，实际完成23:22:39；目录 `/data2/FreeToken/runs/dev_D12/arm_plan_v1_cpu_20261008_2330/`。receipt SHA `27a52001c4d6174f71379404349c0973176793bc59798a09d8fabfcd5d62525d`，log SHA `e04d1ca7fdcd51abd6477907acbc51927c2dbbf0455d423fb041779526e0e4a0`；53份源/依赖/配置与10份冻结输入在测试前后SHA不变。四份真实native probe均无CUDA初始化或模型服务/请求；错误端口/身份、计划篡改、环境污染和重复输出拒绝覆盖通过。

实际plan SHA `6f2dacad59f6f9e1683d3dee372471b19842f020d1776bc60dcc806d10cbe70d`，参数FILEdry SHA `513c8ab7aeb85c2952350ef35f9e567eed66a2d1dafc2c7e66a496ab06bfef6f`，位于该目录 `pytest-artifacts/test_four_arm_native_file_dry_0/file-dry/`。本地回执 `../D12_ARM_PLAN_CPU_20261008.json`，完整启动描述 `../D12_ARM_PLAN_FILE_DRY_20261008.json`。独立源码与SSH实物复核通过；复核要求补齐README的LOW项已按本节处理。该产物为CPU proposal证据，不是正式轮次、宿主observer ready或目标模型接受。

## 23:58 宿主与隔离 PID 身份映射、PID 域绑定

新增只读 `namespace_identity.py`，函数不启动服务、进程或命名空间。宿主通过当前 `/proc` 独立观察原外层进程的 PID/start_ticks/PGID/session、直接子关系、NSpid/NSpgid/NSsid、UID映射和pid/user/mnt/net namespace；要求唯一的直接子PID 1、新user/mount/PID范围、共享network，并在映射前后重读原owner和init。仅遍历该init的实际子树，拒绝出生变化、错误内层PID/组/session、未预期嵌套PID范围或namespace变化。映射结果把inner birth和独立outer process并列保留，不改写或混用数字PID；boot与observer范围也参与绑定。

CPU原型位于 `test_namespace_identity.py`，复用已有ordinary HTTP夹具与D07 owned stop。外层 `unshare --user --map-root-user --mount --pid --fork --mount-proc --propagation private --kill-child=KILL` 启动受控inner PID 1；它先bind独立任务目录为自己的 `/tmp`、报告 `PR_GET_PDEATHSIG==SIGKILL`，然后等待私有stdin pipe的START。宿主核验原外层出生与直接子init后才发送START；EOF或超时直接退出，不创建frontend/worker。安装在该机的util-linux为2.37.2；此双阶段流程用于约束fork到PDEATHSIG设置之间的窗口。配置值本身不证明父进程存活，START后的并发父退出也不承诺零条子进程指令执行。它不是D07更上层owner死亡协议的替代。

该原型实际验证独立 `/tmp` marker在宿主同名位置不存在、host loopback能访问inner HTTP。外层被既有owned stop终止时，inner PID 1、frontend、worker以及另一个setsid进程均停止；分别从宿主原出生和PGID核验。这里的kill覆盖依赖PID 1死亡触发整个PID namespace清理。network仍共享，私有tmp只隔离pathname路径；不证明全宿主FD独占，也没有验证目标模型CUDA/IPC在此布局下运行。

普通证据的listener/live-worker/collection/stopped收据升级为 **v2**，加入 `{boot_id,pid_namespace}`。先核对 `/proc/self/stat` 的PID等于实际getpid，要求frontend/worker同域，采集与停止前后保持域稳定；停止reader先核域再解释记录里的PID，拒绝旧版缺域及跨boot/namespace记录。真实inner collection已验证能在inner停止核验，却不能被host拿来直接查PID。listener的同UID独占标志范围明确为“观察者PID namespace内、请求边界采样”，不能扩张为整个宿主。原宿主同UID不可读FD仍不跳过。

v2目录 `/data2/FreeToken/runs/dev_D12/namespace_identity_v2_cpu_20261008_2358/`，实际完成23:57:56。两条独立命令：宿主映射 **4PASS / 16.98s**；隔离ordinary回归 **25PASS / 27.62s**，包含此前21项和4项PID域/proc视图拒绝。40份源/依赖与10份输入前后SHA不变，候选8f6a912 tracked clean。测试实际发送原三请求；SSE与admission为合成数据，未加载权重或启动模型。独立审查后还有下节v4的两项修复；v2不作为最终实现。

本地回执 `../D12_NAMESPACE_IDENTITY_CPU_20261008.json` SHA `7b6364b53aa56301e0ee4c6ec5b90e8f9d556c0fcdd1791378e7b1617bcec34f`，映射log SHA `d5ee3b687e0fb7a32feed7aba36d560264fdf731e18258a90a9ec99c38e89b2c`，ordinary log SHA `6404d93732de04b4175aa4a3002d195bc141588a0407eeec5ddc9116f71e6c01`。v1的4PASS及 `0d4458fc` 回执保留。当前只完成映射组件与CPU原型；正式namespace controller、owned准入/锁/终态生命周期、功能规则与D04接线仍需完成。`host_proc_observer_ready`、模型、正式启动与输出/性能接受均未提升；R062已冻结包不受修改。

契约依据：[PID namespaces](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)、[proc PID向量](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)、[进程出生字段](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html)、[PDEATHSIG设置](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)、[PDEATHSIG查询](https://man7.org/linux/man-pages/man2/PR_GET_PDEATHSIG.2const.html)及[util-linux 2.37.2源码](https://github.com/util-linux/util-linux/blob/v2.37.2/sys-utils/unshare.c)。这些内核契约不代替实际模型或正式caller的验证。

## 2026-10-09 00:08 复核修复与退出竞争

独立复核指出listener检查只约束frontend的PID域，实际socket持有者还缺相同约束。现已在发现匹配FD后及最后稳定复核时，分别检查holder的PID namespace；仍先扫描FD，不按namespace预过滤。两项受控readlink变化测试分别覆盖初查和重查；这些负例是mock，不声称实际创建了nested-PID socket持有者。

v3真实回归又触发原D07固定helper的 `/proc` 退出竞争：`owned_group_alive` 只处理ENOENT，但已消失进程返回ESRCH时抛出 `ProcessLookupError`，使stop路径中断。原始 **3PASS/1FAIL** 在 `/data2/FreeToken/runs/dev_D12/namespace_identity_v3_cpu_20261009_0005/` 保留，receipt `215c62fb79449df8491ead464e54fdf7251d12dc4e497c86894d3fd775088dbc`、log `eb045f0782498057ba027e51861889855a92e8e139fce204c29569b18fdac031`；finally完成清理，无测试进程遗留。

新增窄适配 `owned_lifecycle.load_owned_lifecycle(gate)`：首先使用原D07 SHA固定loader，再复算原helper SHA `7e1c05a7`；确认原stop函数使用该独立module的globals后，仅替换此实例的 `owned_group_alive`。原停止信号、deadline、出生读取不改；scanner唯一语义变化是同时处理ENOENT/ESRCH，权限错误仍传播，活进程/僵尸/foreign PGID/session规则保留。没有改写原helper、D07入口或R062包。8项确定性回归覆盖退出竞争和拒绝边界，并证明原stop实际调用适配后的scanner。

最终v4目录 `/data2/FreeToken/runs/dev_D12/namespace_identity_v4_cpu_20261009_0010/`，实际完成00:06:52。宿主 **12PASS / 16.92s**（4项实际namespace流程、8项scanner回归）；隔离ordinary **27PASS / 27.68s**。42份源/依赖、2份v3失败记录和10份冻结输入SHA前后不变；118份JSON工件纳入回执。00:08现场重读五个已映射frontend/worker/escapee宿主PID均不存在，GPU计算进程为空，锁及四待批正式目录不存在，候选8f6a912 tracked clean。

本地 `../D12_NAMESPACE_IDENTITY_CPU_20261009.json`，receipt SHA `dfb17616779177ee8027275c724baed5ab5985dee56bacf7461b92310fe322e3`；host log `106fe55389fc41ba0563711b640217df40040fc158424fb9ac40f18cdf6e9fd2`，ordinary log `a36ee5c89dbedd7451d09a8d9e18eb4b4055a6dcc02dd3b8833e10d0e3572ce1`。六份相关本地源码与回执一致。正式controller/owned准入、功能规则及D04仍未接通；CPU原型保持全部模型、GPU、host-ready和正式接受flags为false。

独立只读终审通过，两项问题在此CPU范围内关闭：重新计算before/after各44项、10份input、118份JSON工件及receipt/log SHA均一致，六份本地源码相同，v3失败绑定有效。记录见 `../D12_NAMESPACE_IDENTITY_REVIEW_20261009.json`；结论为PASS_LIMITED，不提供正式启动或上层owner死亡协议的授权。

## 2026-10-09 00:34 私有控制管道与主线程阻塞时的退出

新增 `namespace_channel.py`，只提供host/PID1专用控制传输，不授予模型启动权限。host创建两条FIFO，自己只保留command-write/event-read；`Popen(pass_fds=...)`只传child所需的相反两端，随后host关闭其child副本。child把收到的FD设为不可继承、非阻塞；控制数据不占stdin/stdout，stdin为DEVNULL，普通stdout/stderr进入独立日志。消息绑定调用方给出的SHA、严格递增序号和固定schema；单帧不超过4096字节，先验证实际PIPE_BUF，再做单次原子写入，不重发部分命令。

`InitChannel`仅允许PID1。后台线程持续读取command pipe，将合法命令交给四槽队列；EOF、绑定/序号/格式错误、超帧或队列满均以125退出PID1。主线程即使阻塞在HTTP/health等操作中，控制writer退出仍能触发该路径。正常关闭watchdog只能发生在所有服务已停止或从未启动之后；START前host独立重验原outer/init出生的步骤仍保留。FD持有与消息SHA仅防误接线，不是正式D07 caller authority。

测试实际创建一个host proxy、一个unshare outer、inner PID1、HTTP frontend、worker和setsid escapee。inner主线程进入120秒sleep后，proxy直接 `os._exit(37)`，没有执行自己的finally；唯一control writer消失后，watchdog结束PID1，测试在5秒界限内确认outer/init及三个子进程全退出。另一个用例在同样busy状态发送5个合法递增命令，第四槽之后触发QueueFull，确认init/frontend/worker/escapee全退出。错误SHA/序号/JSON/4097字节帧在START前终止，无frontend/worker创建。这些都是CPU流程，sleep模拟阻塞而非真实GPU kernel/HTTP停滞。

v1 `/data2/FreeToken/runs/dev_D12/namespace_channel_v1_cpu_20261009_0030/` 实际完成00:26:15：host **17PASS/22.02s**，ordinary **27PASS/27.68s**；receipt `b3950ede1b49fd2feb753d84e026602ff27655fe92792090c5a2b03fb3d4e898`。独立审查要求补queue-full实测，v2只新增该测试，生产transport与ordinary/lifecycle源未变。

最终v2 `/data2/FreeToken/runs/dev_D12/namespace_channel_v2_cpu_20261009_0040/` 实际完成00:31:47：host **18PASS/23.18s**。ordinary27没有在v2重跑；回执的 `retained_prior_ordinary` 单列v1命令/结果/log，并将v1 receipt和log作为稳定输入绑定。47项源/依赖/历史记录、10份输入及50份本轮JSON经独立重算全部匹配。两份本地更新源码SHA与回执一致。00:34现场重读v2 host-death五PID、queue-full四PID均不存在；GPU计算为空、锁及四待批正式目录不存在，8f6a912 tracked clean。

本地回执 `../D12_NAMESPACE_CHANNEL_CPU_V2_20261009.json` SHA `b20d1de3a8e65e3085763d067bdeca0633d2ba7ada23c46ecc0f26c2a8359f26`；host log `a1901da96a67ead738b62d77072c1071eecbe879bd3e6dbeff5582ebfc9d6d88`。独立终审记录 `../D12_NAMESPACE_CHANNEL_REVIEW_20261009.json` 为PASS_LIMITED，queue-full覆盖项已关闭。正式controller、D07批次准入/锁、模型/GPU及host observer仍未接入或验收。

下一步的既有owner接口已定位：`r040a_private_port_owner_v3` 的 `_ready_health` 仅GET `/health`，`_stop`提供出生校验和清理；但其 `_service`硬编码T17 exact-ID wrapper、receipt及参数，不能直接喂入D12 plan。D12需要自己的每臂适配来复用就绪/停服边界；不能调用会额外POST say-ok的 `_ready` 或T16 `Runner.ready`。外层D07锁和批准仍必须以宿主身份持有，inner PID不能写成宿主PID。

功能规则仍是独立待办：D12卡要求四层功能顺序且禁止用本次误差自校准；当前T04只提供分布。PLAN §4.1是T17恢复状态等于源状态的门，不可直接改写成D12 control/enabled最终状态必须逐位的授权，也不能据此声明D12全严格结果已自动获得正式接受。
