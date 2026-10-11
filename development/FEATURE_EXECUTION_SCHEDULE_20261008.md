# 新增功能执行排期（2026-10-08 用户裁定后）

R049c 一次七服务、168 调用补跑已获批准。D05、D09、D10、D11、D12、D13 已纳入执行范围；此前“未立项”的描述不再构成阻塞。真实技术前置和独立验收仍保留。授权原话及 SHA 见 `USER_R049C_AND_FEATURE_SCOPE_APPROVAL_20261008.json`（`7b87b409a6673421129a356c0f400c9f3963612b710fc789478267b21db0b7b6`）。

## 立即执行的两条工作线

**既有功能验收线**：T09/R048b 已独立复核并 D04 measured，只读封存；8 服务、48 请求，C 按原 115 GiB 条件跳过。R049c/b112 已 D04 not_met，输出等价性失败后需定位并准备新验证范围。R040g/b113 已 failed_harness，D16 后续修复与补跑待新批准；R060c/b114 已 D04 kept；R061b/b115 已 D04 failed_harness，修复请求时序后再提补跑。D16 完整接受后 → R045/T05 → R052a/T11 → R044/T10 → R047/T03b。R060c 与条件 R061b 按既有独立就绪规则插入，不能抢占运行批次，也不能因排在前面就跳过真实数据依赖。

该线对应 D01、D02、D06、D08、D15、OOM 恢复六项已编码能力的未闭合验收。D15 memory-snapshot guard 另有 CPU 证据，尚未纳入正式候选；是否需要集成由 R049c 结果及具体影响面决定。

**新增实现线**：优先开发已满足画像前置的 D12；并行补全 D13 的 G0 分析、准备普通 TP2 接口设计。D05、D09、D10、D11 先核准已有前置，前置到位后直接进入对应实现，不再仅因旧卡写“后置”而停留。

## 六张卡的实施顺序

| 卡 | 现在的动作 | 正式实现或验收触发点 | 工程量依据与边界 |
|---|---|---|---|
| D12 短后缀按需搬运 | 已建完整卡；本地 `exp/e2d12-short-suffix` 工作树已创建，父提交 effb996。默认关闭的阈值分流、slot 生命周期已实现；最终8f6a912 Linux 60PASS/3skip、独立源码复核PASS；默认关闭T16四臂48调用v2入口已Linux33PASS、native绑定、实际FILEdry与独立启动复核通过；具体R062 GPU范围已申请 | T06/R046g measured 已满足画像前置；阈值依据从封存分桶提取。候选就绪后新 T16、D16 四层数值与性能验证 | 旧卡读码估计 2–4 人日；不是 GPU 完成时刻 |
| D05 完成捐赠问题 | 准备两条分支定位，保留旧失败观测 | R052a/T11 正式判定：H-hook 补默认关闭钩子；H-bug 修完成路径；若 D14 已解决则以证据关闭 | H-hook 0.5 人日，H-bug 1–2 人日；当前不能任选分支 |
| D10 错相位重叠解码原型 | 先准备独立原型的输入和统计设计 | R045/T05 时间线闭合后实施；先做独立原型，不接服务 | 原型 3–5 人日；若转完整产品，原卡另估 10–20 人日，不混入本原型 |
| D09 层优先多锚归档 | 核对既有 layer-major/archive 触发点和槽位约束 | R047/T03b 与 T04 阶段二的正式结论/数值口径到位后实现；T04 已有分布分析，不从零重做 | 旧卡 5–8 人日；新多锚目标尚未实现 |
| D11 遍内插解码 | T14 已完成，立即移除这一待办；准备层循环、CUDA Graph 和缓存隔离设计 | T05 时间线闭合后结合 D10 原型结论实施；处理不可嵌套 forward 的实际约束 | 旧卡 15–25 人日；与 D10 共用源码时串行集成，设计可并行 |
| D13 真正 TP | 复核已有 10 月 3 日 G0 报告、补三类负载和独立预算依据；T15 已完成 | 按普通 TP2 → TP4 顺序实施；真实多卡验收需要目标节点与卡数就绪。14:00 左右 `.9` 的 nvidia-smi 仅列一张 4090，不能把四卡规划当现场事实 | 旧卡 15–30 人日；基线 qwen4_exp loader 拒绝 TP>1；D13候选7e3db70已实现BF16 dense与Triton NVFP4专家bank切分，Linux50PASS/1skip及独立复核通过；dense实际iterator→dtype/materialize→model.loadstate覆盖TP1/2/4，NVFP4 production-bank重构覆盖TP2/4。G0 预测不等于 TP 实现或正确生成 |

这些是旧卡的工程量估计，不能简单相加当作本次自动执行的墙钟时间。原“9 批、54 服务、570 调用”仅是既有验收矩阵，未计入上述新增实现及其候选验证；T09 的 C 跳过和整轮独立接受后，再更新剩余计数。

## 执行责任与闭合条件

2026-10-09 01:00：按 `../plan/ROOT_EXECUTION_DIRECTIVE_20261009.md` 最新24条重排。GPU已批准且串行R040h(8/10，b116运行中)→R061c(1/3)→R050a(4/48)→R063-D12默认门(4/48)。R062为已封存D07门。发布门收敛T17+R041+T20/D16+OOM，D05/D08–D13/D15与T05/T11/T10/T03b转E3。冻结D12自研隔离层；新增工装优先AIPerf/SDK+pytest，D16此次采集器再失败转API方案报批、不再修。旧“待批”与发布依赖条目保留为历史，不能继续阻塞现已授权队列。

2026-10-09 00:34：D12私有pipe/watchdog完成host18PASS及独立复核（b20d1de3）；v1 ordinary27独立保留且绑定，没有在v2重跑。实际proxy突然退出或queue-full可在PID1主线程阻塞时清理namespace全部子进程。接续写D12每臂owner，复用既有_ready_health/_stop，不能套用硬编码T17的_service；正式D07 caller/锁、功能规则和D04未闭合，无新GPU运行，既有队列不变。

2026-10-09 00:08：D12宿主↔namespace映射与生命周期原型最终宿主12PASS、隔离ordinary27PASS（dfb17616）。两阶段START、私有tmp、跨PGID清理和真实跨域记录拒绝已验证；修复holder PID域漏检与旧helper /proc退出竞争，v3失败原样保留，窄适配不改冻结helper/R062。正式controller、owned准入/锁/终态、功能规则与D04仍需接入。宿主全UID FD限制未绕过，host_proc_observer_ready仍false；无模型/GPU新运行，既有队列不变。

2026-10-08 23:26：D12四角色启动描述和参数层FILEdry已15PASS（27a52001）、独立源码/SSH复核通过。固定原三请求和所有关键参数，control/repeat/ordinary-reference/enabled共计划4服务12请求；approved_new_services=0，不预订端口，不改变R062。已完成的是原生参数/环境/meta/policy接线，正式owned启动前边界演练、宿主观察接入、功能规则与D04仍需完成；草案数量不并入GPU队列。

2026-10-08 23:05：D12普通HTTP证据适配器已隔离Linux21PASS（4916a01b）、独立限定复核通过，补齐原body/SSE/events、每UID实际worker及collection→stop SHA链。真实setsid共享socket逃逸在POST前拒绝。宿主当前UID sshd/sd-pam FD不可读导致fail-closed，f647fe98原样保留；需完成只读观察能力或完整owner隔离与宿主PID映射的具体接入方案及FILEdry，不能把隔离测试当宿主就绪。正式多臂/功能判据和D04仍需接线；不改变R062已冻结默认关闭包或四个待批GPU范围。

2026-10-08 22:26：D12外部目标规格已冻结并通过Linux15PASS（3725e157）。实际overlay解析至qwen4_exp原始配置，非模型根目录qwen3_next兼容配置；词表248320、四角色shape/dtype/layer IDs与48层MoE分母均以native meta池验证。只消除正式调用方独立规格缺口，不证明实际worker设置、目标权重或GPU输出。现有启停/ordinary-client/D04接口已完成只读定位；正式多臂接线及功能判据仍待实施，GPU队列未变。

2026-10-08 22:10：D12成对token/SSE/状态/logits消费Linux236PASS（27db5a38），组合FT原生组件与SDK读取；各臂先独立read_state_tail/D0，再比较完整token及API语义，D03给严格/数值差异。三token末位差异和usage=3覆盖通过，所有正式接受flags仍false。T04当前仅分布、不能单独放行，现行S-007不作为缺容差的新阻塞；正式D12门需冻结适用规则及D04调用方。未启动GPU，候选/既有队列不变。

2026-10-08 21:50：D12 D0分母/阈值事件完整性及worker/reader接线完成Linux170PASS，独立源码和SSH产物复核通过（b287ceed）。分母来自完整外部MoE层布局与native D0实际children，不能从bank成功事件反推；调用事件齐全与bank字节全成功分开，回退/零命中不能声明bank覆盖。联合三UID CPU模型循环为2/6/2调用，目标CUDA bank、逐token/SSE/三臂状态logits及D04仍待验证。candidate/R062不变，无新GPU运行；17/109待批和18/275条件队列不变。

2026-10-08 21:11：D12源码绑定SSE比较已Linux46PASS，独立源码/SSH实物复核PASS_LIMITED（6ad1b5d0）。只排除API生成的created和tool ID UUID，固定UID及正文/reasoning/工具名称/完整arguments/finish/usage严格比较；真实封存三响应运行时副本语义相等，八类语义变化判不等。实际新生成token/三臂数值、bank调用分母和D04仍未闭合，GPU队列及候选不变。

2026-10-08 20:56：D12状态/tail独立reader已Linux117PASS，独立源码及SSH实物复核PASS_LIMITED（822aff65）。同一实际D16 adapter/worker+candidate model loop/D03 CPU联合夹具绑定三条冻结输入、各末64词表logits和native四角色状态；19个负例覆盖SHA/身份/几何及内部SHA同步修改。明确bank_coverage/prefill_schedule/output_equivalence均false，正式四层比较/D04和GPU仍待完成。候选8f6a912/R062与17/109待批、18/275条件队列不变。

2026-10-08 20:38：D12单一ordinary请求的tail-K observer及worker接线已Linux97PASS、独立SSH产物复核PASS_LIMITED（1c30d2b8）。实际candidate层循环/CPU HC/LM head与D03组件验证普通、layer-major及跨outer坐标；受控CPU权重/decoder夹具，不是目标模型推理。三条完整冻结input预声明尾64 policy b119ceb3，无新增raw-ID路由/请求，GPU四层比较和D04调用方未完成；候选/R062及队列计数不变。

2026-10-08 20:10：D12普通tools SSE薄读取Linux15PASS、独立PASS_LIMITED；真实封存三条tools响应140/58/113完整结果离线复原，receipt82c63e5e。只复用v8 metadata/wire与SDK，不新增通用runner/round系统；v1 nested usage默认null导致的假拒绝已修复并保留失败。下一步固定后续logits候选兼容性及正式调用方四层汇合，尚无新模型/GPU输出或性能证据；候选/R062与待批/条件队列不变。

2026-10-08 20:00：D12真实CLI/help和spawn主模块目标到TP保护分支2PASS，receipt a30ad70f；实际ServerArgs/Scheduler/API/model仍未验证。修正启动参数为 --disable-moe-prefill-overlap，旧冻结源码/分析证据保留。D03固定后续token门的服务钩子在候选缺失；逐个独立前缀行不能直接充作tail-K/状态恢复验收。继续完成兼容性接线，GPU队列和整体ETA不变。

2026-10-08 19:36：D12 natural-terminal-v1契约完成CPU实现与Linux87PASS、独立PASS_LIMITED，receipt8e05cb3a。复用D16 adapter/sampler/实际发送/退出，以独立policy+report+reader处理自然结束，旧fixed源与语义不变。正常自然夹具3UID实际交付1/2/3测试token，reader capture_complete但output_equivalence_verified=false；清理故障保留原始错误并写failed。下一步实际CLI/API/spawn、正式D04调用方绑定和四层数值比较；非目标模型或GPU验收，候选/R062及GPU排队数不变。

2026-10-08 19:20：D12冻结普通请求到实际admission的guard完成，Linux67PASS，receipt d29d9d93；三条冻结token输入经过真实D16组件、fakeScheduler/model的CPU生命周期，固定expected_queries未变。新增自然结束契约缺口已确认：历史140/58/113与上限2048均不能直接作为当前精确生成数；在显式自然终止policy和reader就绪前，不申请D12 enabled GPU准入。实际HTTP/CLI/spawn、四层数值/性能仍待完成；候选、R062包、待批及条件GPU计数不变。

2026-10-08 19:00：D12窄worker接线已Linux51PASS、独立PASS_LIMITED，receipt52e09a16；复用现有D16 worker/service/sampler/SIGTERM生命周期及原生LinearStatePool。验证正常与清理故障两个CPU夹具：终态complete/failed，shutdown各一次，原错误未遮蔽，均无CUDA。未安装R040 exact-ID/parking/cache初始化；普通SSE模式下这些额外控制显式拒绝。实际CLI/spawn、完整四层数值和GPU门仍待完成。只增加开发诊断适配器，8f6a912候选及R062固定包不变。

2026-10-08 18:35：SDK采集已接入既有quality60题循环、规范grader和逐题输出；Linux23PASS，独立复核60行与60日志/全部SHA/47-11-2判分一致，实际CLI model身份已回归。已部署到服务器工具目录并以CAS更新共享回调入口，旧源码保留；部署receipt `c3acb728`，CPU验证receipt `711442cf`。不触发GPU或修改冻结轮次。D12只读源码定位已证明可在worker的Scheduler构造后安装现有两个适配器；child身份来自模型实际切换的ctx.batch，route trace会禁用layer-major，不能用于主诊断。后续完成该窄接线和四层证据汇合，不新增通用runner。

2026-10-08 18:19：工具部署泳道完成本次范围：固定发行版本、双环境依赖检查、SDK JSON/SSE、AIPerf两请求真实CLI模拟、官方原始产物保留；最新运行receipt `efdb127ea77317575dc94ac9014267ca837af03cc8c3c740ef436e4191de7239`，root已回读。`--locked` 遇实际freeze漂移即失败且不覆盖原锁。后续按现有产品依赖继续，工具部署没有改变模型验收、GPU补跑或发布状态。

2026-10-08 18:13 增量：工具链已安装；SDK 薄采集 Linux16PASS，封存60题逐题语义回放通过且独立复核。D12 已有状态采集器补齐真实 `LinearStatePool.dump_state` 的 CPU 回读，Linux10PASS，四角色内容/dtype/SHA一致；未接入目标模型运行，不改变 R062 固定候选或四个待批 GPU 范围。AIPerf 两请求流式模拟已成功，正在补齐官方原始产物持久保留，完成后不继续扩大工具自检。

2026-10-08 17:50：增加用户已批准的工具部署泳道，独立 Agent 仅维护 `evaluation/toolchain/` 与远端同名目录的隔离环境；root 继续引擎实现、数值问题定位与日志同步。采用 AIPerf、SDK + pytest、lm-eval，安装/协议验证/目标模型验收分开；按交接书第十八节冻结新增通用 runner，不重做已通过冻结批次。四个已准备的 GPU 范围仍待各自回复。

root 负责排队、候选/原始输入绑定、正式轮次启动和证据整合。引擎实现使用本地隔离分支，完成本地提交后同步专用服务器工作树。独立复核与作者分开；CPU/source PASS、真实 GPU 测量、业务数值接受和发布分别登记。

共享 GPU 的性能测量串行。已有路由、状态比对和 D04 工具继续复用；不因新增功能扩建平行 Harness。新候选的默认路径门、开关打开后的数值门与真实目标模型验证按卡完成；测量失败或需要改变判据、发布配置时，保留证据并按既有裁定边界处理。

R040g 的一次批准已用于 b113 并已 failed_harness 封存，R040h准备8服务/10调用具体补跑范围；R049c 的一次批准已用于 b112，失败后的新 GPU 轮次尚未申请，先完成具体诊断/修复方案。生产发布、创建 release/e2 和推送仍保留原批准边界。本文件只记录执行排期，不宣称新增六卡已实现。

2026-10-08 14:25计数更新：T09已闭合，原既有验收矩阵剩8批、最多44服务、510调用（包含完整当前R049c；不按进行中的局部请求递减），仍排除新增六卡工程及新候选验证。D12候选97f6ee3已本地提交，Linux CPU测试待空档。

2026-10-08 14:55：R049c/b112已独立复核并D04 not_met，只读封存；PA1第二条冷请求的输入与L1/P1一致，第8个生成token分叉，32raw哈希不变，仅2请求、0完整服务，无完整T21/性能结论。R040g/b113已按既有批准启动，effb996、98,304/0.88，补14服务16调用，child2914235:153687054。D12候选eb7f54a的Linux CPU为26通过/3跳过/3个父版本同样失败，无新增失败；CUDA内核/性能尚未验收。

既有矩阵：已授权且尚未闭合的7个批次最多37服务342调用（包含当前R040g以及有条件R061b）；另有T21 not_met阻塞，后续修复/验证范围待定，不把失败矩阵扣除后称为全部工作。新增六卡与其验证继续单独计量。

2026-10-08T15:33:18.919256+08:00：R040g/b113启动第7服务warm_0时因采集工装int64编号触发int32断言，原始1729文件已绑定，六服务数值可保留范围待R；D04待完成，新补跑尚未批准。R060c/b114四臂默认门已实际启动，R061b须真实kept+fresh FD/R。已授权未闭合既有矩阵6批23服务326调用，另列D16与T21失败后的纠正范围，不将其视为已验收。

2026-10-08 16:00：R040g D04封存完成，R复核通过的parking4/cold2以SHA49125e61保留，完整D16尚未通过；R040h修复实际warm priming dtype为int32 contiguous，只补warm2/interleave6，正在实际入口CPU回归。R060c/b114于15:55结束，四臂默认路径比对一致，pending R/D04；R061b仍须真实kept后fresh FILEdry/R。D13 f84c495已完成Linux42PASS/1skip。

2026-10-08T16:21:47.626642+08:00：R060c/b114已D04 kept封存，4臂48请求。R061b v2实际前置绑定、Linux11PASS、fresh FILEdry通过，等待独立startup签后按既有批准运行。已授权未闭合既有矩阵5批19服务278调用；D16/T21纠正范围及新增六卡继续另列。D12/D15默认门Linux62PASS、同入口FILEdry通过；D13 e757e33 Linux42PASS1skip，继续实现NVFP4专家bank TP。

2026-10-08 16:45：R061b/b115 已D04 failed_harness（closure a09ae767），21raw不变；新epoch曾出现，但工装在观察restarting前发出所谓queued请求，队列恢复未验收。R061c仅修工装次序。R040h、R050a及R062已全部tools-ready、具体GPU批准待回复。D13 7e3db70 Linux50PASS/1skip，独立R f6d47b8b；TP多卡硬件及真实生成仍未验收。既有已授权未闭合矩阵4批18服务275调用，失败纠正与六项新增功能单列。

2026-10-08T16:59:58.609926+08:00：R061c完整新入口已Linux14PASS、实际FILEdry d9ae4ee2、独立启动v2 c68fa36a并被实际读取方接受；修复只改变等待restarting的工装次序，补跑1服务3调用申请已发。D13真实overlay配置SHA deef67a6已完成CPU/meta七rank声明，report5e75b847；不读取权重、不初始化CUDA。四个已就绪待批准范围合计17服务109调用，加原18/275条件队列共8批35服务384调用；未来D15启用策略T21和六卡功能的剩余实现/验收不含在内。

2026-10-08 17:16：D12离线输入校正完成，阈值实际作用于MoE预填段；原10/29为请求后缀分布，不是分支覆盖率。封存T06复算29warm请求/51段，其中35段≤256、15段=64；冻结G_seed12k前三条payload与worker IDs，历史段[512,12148]/[64,233]/[123]。Windows/Linux8PASS，输入binding282ec437、reportbe23dfed；候选和R062范围不变，启用功能四层工装仍待接线，未新增GPU批准或性能结论。
