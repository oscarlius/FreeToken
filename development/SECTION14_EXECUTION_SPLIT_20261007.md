# 第十四节执行拆解与调度

2026-10-08 15:21：D12短后缀候选8f6a912已Linux60PASS/3skip，源码独立复核PASS；默认关闭，实验0对256、两臂均关闭overlap，实际CUDA数值/性能待验证。D15槽提升修复8256553已Linux19PASS，最终同测试对原988c在临时槽清理后复现丢映射、修复通过；只证明驻留映射缺陷已修，R049c第8token分叉仍未证明解决。D13逐类G0 v3独立复核通过为条件设计预算，普通TP2稠密分片首版实现及CPU重建测试进行中。R040g/b113运行中，已生成5个场景采集manifest。

2026-10-08 14:55：R049c/b112已独立复核并D04 not_met，只读封存；PA1第二条冷请求的输入与L1/P1一致，第8个生成token分叉，32raw哈希不变，仅2请求、0完整服务，无完整T21/性能结论。R040g/b113已按既有批准启动，effb996、98,304/0.88，补14服务16调用，child2914235:153687054。D12候选eb7f54a的Linux CPU为26通过/3跳过/3个父版本同样失败，无新增失败；CUDA内核/性能尚未验收。

2026-10-08 14:25：T09/R048b b111 已独立复核并 D04 measured，8 服务48请求，C按115 GiB前置跳过；409原始文件哈希不变、目录只读。SC1未复现，S仅为A亲和性重复，诊断不证明CPU/PCIe实际时间重叠率。R049c/b112已按批准启动，保留L1/P1，余7服务168调用，child2828886:153492983；下一项R040g。D12候选97f6ee3已本地提交，Linux CPU验证待测量空档。

2026-10-08 13:52：用户批准R049c一次7服务/168调用补跑，并要求D05、D09、D10、D11、D12、D13尽快排期。T09/b111已完成V0/A/B两阶段与S性能共42份请求产物，S诊断运行中，尚待终态独立复核；当前批次收尾后按R049c→R040g接续。D12建卡与其他五卡真实前置核对并行，原有六项已编码功能的验收继续；新开发工作不包含在原9批计数内。

2026-10-08 13:17：R048b/b111完成V0性能6请求，V0诊断执行中；R051a/b110已kept。R040g的14服务/16调用effb补跑及按原提交汇总历史证据已获用户批准，Linux6/真实FILEdry/独立启动签齐，等待当前GPU批次结束。R049c的7服务新重试仍待回复。T05 v17/T10 v7/T03b v12前置绑定Linux143及独立源码复核通过，仍须真实R040g measured后才能继续。

2026-10-08 12:47：R051a/b110已D04 kept，四臂/48调用、78raw哈希未改；关闭D0的父/候选解码34.78/34.79 tok/s仅记录。R048b/b111已按原批准启动，76af、五变体×性能/诊断，共10服务60调用；FILEdry/R签已齐。R049c七服务补跑包已Linux34/真实FILEdry/R技术签，新GPU批准已发待回复；R040g仍在准备，未启动。

2026-10-08 12:12：R040f/b109已D04 failed_harness原地只读封存，0/14scope、20raw哈希不变；0aa开启暂停接口时无条件延迟普通消息，root保存现场后SIGINT结束。R051a/b110已启动，76af候选对effb四臂/48调用，child2472372:152718491。D15显存快照保护Linux40项通过，旧源故障对照如期失败；仅CPU证据。R040f/T21新GPU重试未获授权，其余已批准独立批次继续。

2026-10-08 11:51：R049b/b108已D04 failed_harness只读封存：P1完成24请求/6334输出token，PA1在线性状态池分配时OOM，T21未通过。R040f/b109已启动，child2414470:152585541，按已批准范围补parking/cache/interleave剩14项。D08新门和OOM新门授权仍有效；R049b进一步GPU重试尚未授权。并行核查引擎预算，不扩建Harness。

最新授权（2026-10-08 11:18）：用户已批准 R040f、R049b、R051a→条件R048b、R052a、R060c→条件R061b 五组；下述历史“待批准”状态由此替代。依既定前置推进，下一就绪项 R049b。Harness 优先复用成熟工具，可独立工作并行；发布/部署/推送未获授权。

当前执行覆盖（2026-10-08 10:36）：下方00:14及以前执行表仅为历史，实际调度以本段、README、FTD和协调日志为准。

- R046g/b99已measured。R049a/b102、R061a/b103、R040e/b104、R048/b105、R048a/b106、R052/b107均已D04 failed_harness只读封存；已执行批准不覆盖新的测量后重跑。
- R049b仅余8服务192新请求；R040f仅余parking4/cache4/interleave6；R060c与条件R061b均已提交各自审批，尚待回复。已复核的L1/9个D16 scope保留。
- D08新候选76af7584已专树同步、Linux17/真实import/R源码通过。R051a四臂T16门Linux29/默认FILEdry/独立R技术签通过；实际kept后才允许R048b做正式默认FILEdry和新R启动签。T09 v11 Linux64通过，完整五变体×性能/诊断；不拼接b106局部V0，GPU新门与重跑尚未批准。
- R052a v7a吸收cleanup与receipt fsync前的重复SIGTERM，Linux74/默认FILEdry/独立R技术签通过。真实T11新轮仍需批准、完整重跑9请求。R052/b107旧H-bug raw观察不是正式T11判词。
- T05/T10/T03b卡面T20前置保留。T10新r044_runtime_v6、T03b新r047_runtime_v11已修复同型shutdown风险，Linux82含真实spawn8项通过；R044要求R052 failed元数据/R052a measured/R040f measured，R047显式要求R040f measured并保留R045/R044。实际入口拒绝尚未完成的前置。
- GPU严格串行；T09与T11各保留经R核卡的固定§8.7顺序例外。已有新审批的问题不重复发送；新D08/T11具体范围见 `R048B_R051A_R052A_READY_FOR_USER_APPROVAL_20261008.md`。
- Agent已重核当前剩10批、最多59服务642生成调用，总完成小时数未知；同类T16约27–46分钟只作条件参考。release/e2、部署、推送仍分别未批准。

当前状态核验：2026-10-08 00:14，服务器 `date '+%Y-%m-%d %H:%M'`。权威为 `plan/CODEX_HANDOFF_20261006.md` 第十四节及用户在本会话追加的调度授权；此前无冲突约束继续有效。下方18:11起的表格与追加记录为历史，执行以本段和协调日志最新记录为准。

- R046g/b99四组34请求已独立复算，00:07 D04 measured只读封存。G3复用R046e；G4/T06完成；seed_real完成8轮后第9轮触窗，未截短、不重跑。
- R040d/b100于00:09启动，child381519:148383321与本轮锁一致；只补D16余24项。新采集链保持fp32 logits与四类状态schema，Linux28PASS、24scope FILEdry、17角色来源审查和最终R启动签通过。旧R040a六锚点与R040c slots2六项保留。
- C2做R049 v4正式seed12k画像和完整入口FILEdry；C1提前查T09普通API规范化与SSE终态工装，维持原候选/性能配置。R独立边跑边复核D16；CPU工作不连接模型端口。
- R045 v7 Linux54PASS+两selftest，前置为R040d measured；R047 v9 Linux30PASS、生产者R046g。R061a v7已就绪，原GPU补跑申请仍待用户回复。
- R049正式材料未齐，按第八节独立就绪例外先运行已获用户续跑授权的R040d。其后R049→R048→R045→R052→R044→R047；R061a仅在获批后插入当时批次之后。release/e2、部署、推送均未批准。

执行负责人为 root。CPU 开发、轻量回归和只读复核并行；正式 GPU 批次串行，共用 `/data2/_shared/gpu.lock`。任何持锁期间的非批次进程均不得连接模型端口。

| 工作 | 负责人 / 文件范围 | 当前证据 | 下一步与依赖 |
|---|---|---|---|
| R059 纠正复核 | 独立 R；root D04 | kept；四臂均 128 token；v1 保留；闭合回执 `R059_D04_CLOSURE_20261007.json` | 已完成，不重跑 GPU |
| R040 / R009 60题逐题比较 | root，T20 结果文件 | 同一冻结判卷器；60/60逐题文本、判分、计数一致；47 PASS / 11 TRUNCATED / 2 ANSWER_FAIL | 已写入 T20；原 R040 failed_harness 不改判 |
| D07 G3/G4 + T06 | 02：新 R046d 入口及观察器 v4；R 独立复核 | R046d/b89已D04 failed_harness；G3-on预填成功后queueFull/8decode，G3-off保留 | 新背压版4fc2320 Linux17PASS/1GPUskip；修复新门与R046e补跑分开，测量后重试待裁定 |
| OOM 恢复产品 | 开发 Agent：`development/e2oom-recovery/` 独立树，parent 0aa23431 | 冻结608251，Linux67PASS/23源绑定；R060真实空跑v3已完成，R061工装v2收紧中 | 独立R签→R060 T16→R061 GPU故障注入；本版默认恢复不得只凭CPU发布 |
| T21 / R049 | root 接管 C2 工装，`r049*` | Linux 22 PASS；实际 tokenizer 与九臂 CPU 文件演练；R 预审 | 等合格 T06 的 seed12k route；只以 seed12k 训练，另三组留出 |
| T09 / R048 | 02 接管 C1 工装，`r048*` | Linux 29 PASS；五臂性能/诊断分离；正在并入观察器 v4 | 最新源 CPU → 空跑 → R；R051 kept 已满足 |
| R040a 缺失补项 | root；冻结 v6 只读，R 边跑边复核 | b88六锚点臂完成复核；首个双批槽因Batch.input_ids观察工装失败，锁已释放 | 19:00 D04 failed_harness原地只读；六锚点保留；新观察器实际_forward CPU回归后请求仅缺项R040b |
| T05 + D06 G3/G4 / R045 | 02 工装已交付，root 调度 | v6 Linux 53 PASS + 两项自检 | 等前置补项；性能 .88，暂停链实际验证，独立空跑与 R 签 |
| T11 第二阶段 / R052 | root：`r052*` | v5 Linux 38 PASS；真实 spawn/SIGTERM/原 scheduler shutdown 路径回归 | 等 R045；目标请求后续问、cached_tokens 和真实 D0 shutdown；空跑与 R |
| T10 / R044 | root 接管 `t10_e2_r044_prepare.py` 及对应测试 | v5 Linux29 PASS；普通SSE、同writer空跑、稳定worker shutdown及真实源闭包 | 等R052；真实路径空跑→R启动复核→六服务GPU原始测量 |
| T03b 第二步 / R047 | root 接管 `t03b_e2_r047_prepare.py` 及对应测试 | v6 Linux29 PASS c32d4ad3；实际11源绑定；复用R052 shutdown/common端口对 | 等合格T06/R045/R044；真实路径空跑→R→GPU |
| 发布说明、部署/回滚、FTD 草稿 | root 接管泳道 A 文档 | 性能使用 R056；rollback 184c965，普通8192；全部只写未执行 | 绑定最终通过门的提交与完整结果，再提交用户裁定 |

## 新轮次登记与验收

服务器与本地任务登记均未发现 R060、R061 占用。依据第十四节第 3 条登记：

- `E2-R060-gate-OOM`：OOM 恢复新候选与父树 0aa23431 的 T16 默认路径门；98,304 / 0.88，注入开关关闭，默认恢复开启。按权威 T16 卡比较输入、实际 token/全文、适用状态与采集证据；每个比较仅一项候选提交差异。门通过前不授予候选发布资格。
- `E2-R061-OOM`：同一候选的实际 GPU 故障注入；证明 API PID/出生与可用性保留、受影响请求得到明确错误、旧 worker 全部退出、新 worker ready 后排队请求完成、重启前后实际 token 与全文逐位相同。记录请求/worker epoch，禁止旧回复混入新请求；重启失败、超时、队满有明确可重试错误。

恢复期间采用有界等待队列：上限128；root根据模型实测加载需几分钟，将等待预算由30秒改为900秒，与工装ready预算一致。超时、队满或重启失败返回可重试错误，重启失败立即唤醒等待者。CPU与实际注入验证后再写入最终产品行为；排队仅用于worker重启期间。最终限制和错误协议以通过的源码/结果为准。

两批各需 CPU 自检、相同路径空跑、R 启动复核、逐组复核和 D04。只在准备完成后插入当时运行批次之后；不抢占。故障注入测试需在 CPU 证据中逐项写出预期，不以设计原型替代真实 API/worker。

## 当前队列与停止边界

第十四节主队列为 R046c 后补 → R049 → R048 → R040a → R045 → R052 → R044 → R047，OOM 两批按授权插队。

R046d获批后已启动b89，但出现新trace队列满失败，19:27 D04 failed_harness；新R046e须测量后重试裁定。R049仍缺合格T06画像。R040a/b88六锚点之后工装失败，19:00已D04；六锚点沿用，仅缺项R040b待裁定。已有授权的OOM R060在CPU、真实空跑和R签后可先接上，不抢占、不需重复审批。

not_met、需改发布配置或越过已有验收判据、规定内的测量后失败仍报告用户。纯交接口径错误由 root 直接安排纠正复核，保留原版。生产部署、创建 release/e2、任何远端推送均逐项审批。全部任务完成后才请求发布，当前没有执行上述三项动作。

## 关键证据索引

- R059 D04：`development/R059_D04_CLOSURE_20261007.json`，回执 SHA `f1845b699e383637aedd326f05719d3e5372901a4a701af7d8a8cc69588240e3`。
- R046c D04：`development/R046C_D04_FAILED_CLOSURE_20261007.json`，回执 SHA `54da8045c0016792b09244f45f3cf828464bec50f76d144a91945dfa84eb4afc`；38 文件、16 目录只读。
- 60题：`development/T20_QUALITY60_CPU_COMPARISON_20261007.json`，报告 SHA `21c98fccd4d53c3079bdd1d2a332dba20f3287895955aaceee1ce58b7a2baabb`。
- R040a 启动：`development/R040A_ACTUAL_LAUNCH_20261007.json`；b88 child `3429069:146229523`，R 签 SHA `704688d6c84fd35cf3321bb6d1928adec1ea99390fa17dbb8a357a8b616c2c5f`。
- R052 v5 CPU：`development/R052_RUNTIME_CPU_V5_20261007.json`，38 PASS，报告 SHA `b386bb997c65d0d290e133031e99207eda1fe45efa470a7f7bdf1036ef97a25a`。
- R046d真实空跑：`development/R046D_REAL_FILEDRY_20261007.json`，回执SHA `73dc91dfab38edf3b8e2a87ec3112fd6d1b9af695dccba8a661147f23d31afa9`，已只读。
- R044 v5 CPU：`development/R044_RUNTIME_CPU_V5_20261007.json`，Linux29 PASS，报告SHA `750bc196e9ed4af96a7acc62ebb85e7e1108d3e806f6ca5b664d46b9b2dad236`。
- R047 v6 CPU：`development/R047_RUNTIME_CPU_V6_20261007.json`，Linux29 PASS，报告SHA `c32d4ad3a7ce29d2dbae8ce51ed64f279b0b24509caf9602fb0923ee13b9afa8`。

10-10 至 10-12 是规划目标，包含新纳入 OOM 恢复约一天工作，不是已验证的交付承诺。下一次估时依据剩余实际臂数、已就绪源码和新故障注入进度更新；不把 CPU PASS 算成 GPU 完成。

最新记录（2026-10-07 19:31）：R046d闭合回执33207315（69文件/19目录），R040a闭合b4692b6b（470文件/156目录）。独立待决策审计结论见 `PENDING_USER_DECISIONS_20261007.md`；开发和CPU工作持续。

2026-10-07 19:37：R060/b90实际预检通过，起服务前外层与runner重复取锁失败；0服务/0完成臂、无formalRID，锁已释放。按第八节测量前规则修新v3并准备R060a，先实际runner路径CPU回归/真实空跑/R新签。不得以controller launched标记视作测量已开始。

2026-10-07 20:10：R060a/b91仍在0服务/0臂时失败，原生gate在token/inode赋值前误将自身锁拒绝。新v4在原生gate前绑定实际owner身份，真实gate CPU2项和实际四臂FILEDRY通过，经独立R签后R060b/b92已实启，child3784590:146903265持自己的锁。R060/R060a现各9文件3目录经独立R失败复核、D04原地只读封存，外部原log/launch/wrapper仅引用SHA；不做快照/克隆。R060b是此门最后预授权测量前字母重试，若再次失败按第三次失败规则升级。

独立Agent再次审计：当前用户待决仍只有R046e测量后补跑、R040b仅补剩余D16；先完成必要具体修复/CPU/FILEDRY/R签再提交启动批准。R062新背压提交4fc2320门已登记准备，actual native两SO regular-copy、四臂FILEDRY通过，正式入口CPU及独立R签待齐；R061需完整实际协议CPU与准确时间FILEDRY，尚未启动。

2026-10-07 21:00：R060b/b92四臂独立复算与补充口径确认后D04 kept（90文件7目录）。R062新背压门v5补全原始R059递归来源、隔离Linux4PASS、四臂真实FILEDRY和R签，batch93实启。R040b v9的30项D16-only同入口FILEDRY已通过，独立启动R复核中；GPU重试尚未批准。R061实际完整协议CPU成功1PASS及真实sidecar binder1PASS，核心检查恢复与Linux证明继续。工期新独立估计71次启动/10轮，GPU8–20h、CPU7–17工程h，不含等待裁定或额外失败。

2026-10-07 21:48：R062/b93独立复算及D04 kept；用户批准后R046e/b96已实启持锁。R040b/b94与R061/b95分别0服务输入绑定失败、已起API观察器spawn失败，均D04原地只读封存。R040c Linux8/30FILEdry通过，R061a Linux11实际spawn与全故障协议通过；v7只修生成脚本SHA绑定，待完整新签后申请GPU补跑。原发布和T17/R041证据保留，产品最终恢复未验收。

2026-10-07 22:04：R046e/b96 D04 failed_harness（G3配对PASS保留；G4/T06未完成，无OOM）。R040c/b97已接续持锁仅补30D16。R061a v7 Linux11/FILEdry/独立R启动签齐备，用户批准待回复；R046f终态修复和仅补缺项准备中，准备齐后提交重试裁定。发布三动作未获授权。


更新 2026-10-07 22:58：R040c/b97已D04 failed_harness关闭，slots2六case保留、余24未接受。用户新增续跑指令用于新R040d剩余24项；修真实捕获/自动seal再CPU、FILEdry、R启动签，原件和判定不改。R061a GPU审批尚待回复；R046f Linux47+真实FILEdry+R启动签通过，提交仅G4/T06具体审批；R049 Linux28PASS，仍依赖完整R046f画像。GPU当前空闲。

2026-10-08 01:03：R046g/b99 measured闭合；R040d/b100 failed_harness闭合（首批512部分证据保留，拟R040e余23）；R049/b101 failed_harness闭合（两路EOS20/20，0完整性能臂）。GPU空闲，R049a固定512工装修复、R040e实际23项采集接线并行；具体就绪包CPU→FILEdry→R签后再提交补跑裁定，R061a原问题不重复。
