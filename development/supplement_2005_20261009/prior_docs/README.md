> **10-09晚间有效状态**：[新指令](plan/EVENING_DIRECTIVE_20261009.md)已归档，D09/D10与X-STRATA-R002-mini已批准；推送仍仅明早申请。独立481开发树已建；D09第7/10轮预测与D10条件区间已封存，机制接线及CUDA原型尚待完成。GPU按09:00观察→申请→R067d→R047/T03b→D09→D10排队。Strata v0.1.39无MTP服务被源码启动条件阻塞；不升级/构建/下载，未测。下方“Strata未批”等为历史状态。
>
> **论文v5.2**：[全文](paper/FreeToken_MultiGPU_CoExec_v5.2.html)仅更新§8的R045实测；C5等待mini。标题、多卡范围不变。[英文arXiv大纲](paper/ARXIV_ENGLISH_OUTLINE_20261009.md)已独审；尚未投稿。新CPU工装：[晚间文档/构建/渲染](development/evening_directive_20261009/)、[D10准备](development/d10_staggered_20261009/)、[D09预测证据](development/d09_prediction_20261009/)。开发与正式GPU门分别记录。

# FreeToken (FT)

> **论文当前版本 v5.1（仅文字修订）**：[打开全文](paper/FreeToken_MultiGPU_CoExec_v5.1.html)。用户本版[15项要求](paper/REVIEW_v5.1_20261009.md)均已处理并独立复核PASS，新增[长期终审清单](paper/REVIEW_CHECKLIST.md)。v5.0/FTD原字节保留，无模型或GPU重测；以下FTD及发布状态继续有效。


## 重新部署当前状态（2026-10-09）

**重新部署成功，481d3a7已常驻serving并登记内网放量。** 审批 `DEPLOY-E2-20261009-REDEPLOY-01`：OPSv8 local/Linux FT venv各65 passed、0 skipped，独审PASS；旧184正常停止，release独占SDK+pytest冒烟1 passed、0 skipped、exit0。long行结构[512,7745]、正文SHA9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c及8257/128/8385完全符合预期，现场冷基准已签。首次通过、无invalid/retry/回滚；supervisor3015442/service3015453，GPU锁/实际身份已复核。未把冒烟称为业务任务或长期观察验收。R067c/R045尚未执行，每次停服另批；push和Strata未批。完整结果见[重新部署结果](development/REDEPLOY_RESULT_20261009.md)。 新工装 `smoke_campaign.py` 和 `test_redeploy_cpu.py` 对一次invalid重试持久化限额，`development/redeploy_smoke_fix_20261009/approved_attempt.py` 绑定原服务/-retry1身份。

[发布方案](development/RELEASE_PROPOSAL_E2_20261009.md) · [H2回执](development/release_e2_ops_v2/h2_allowlist_evidence_v2/h2_receipt.json) · [二进制清单](development/release_e2_ops_v2/binary_manifest.json) · [R045新计划](development/r045_aiperf_481_cpu_v1/README.md)。

二进制现状：release与cold D20只使用gate对齐的 `_cpu_moe`、`_pinned_tensor`；重编译三件只归档，row_store已移除。默认disk依赖row_store，本次显式pinned配方不使用。见[清单](development/release_e2_ops_v2/binary_manifest.json)及[源码行号/证明](development/deploy_conditional_20261009/BINARY_PRECONDITIONS.md)。

## 当前交付（2026-10-09，最终复核完成）

候选481d3a7的发布门已闭合。R066c实际3服务/5调用均为字面文法异常，单独冷请求同样异常，按11:45逐提示分类归c；未观察到对方完整口令、U+FFFD或非法控制字符。[五行结果及SHA对照](plan/01_测试与调研/results/T20-E2-R066c_20261009.md)与D04已封存，旧not_met/failed_harness保持；R063a kept只归E3。

[FTD-20261009-1](plan/data_releases/FTD-20261009-1.json)已服务器只读发布（SHA256 `cff4e114ba6f661878a601f353756dc0367d478dda487787e32f8ec64cd95840`）。[论文v5全文](paper/FreeToken_MultiGPU_CoExec_v5.0.html)已完成（SHA256 `2e2b3c726b94107dde542f091ee0a31c694b5c3ccf6f73aa7d1504e71cadfa0d`），原v4及源码保留，11图18表，桌面与窄屏渲染通过。[独立数据/论文终审](development/FTD-20261009-1_AND_PAPER_V5_REVIEW_20261009_v1.json)均PASS（SHA256 `16bea91f531c1fc65805578f405aa1acb020b37c2826c5cc3f34a4e2ba380ba3`）。

T17的逐位等价证据覆盖现算尾段≥65 token；≤64（含1 token）走不写检查点的分支，正确性待证。论文§10拆为冷可复现/热与同结构冷参照一致/并发不保证，并新增已知限制。[发布方案](development/RELEASE_PROPOSAL_E2_20261009.md)含候选链、回滚、完整启动命令；release/e2与工作树已按13:00批准创建；首次条件部署失败证据保留；OPSv8重新部署已成功，推送未批准且未执行。Strata22服务/345调用未批准，[具体范围](../strata/r002_prepare/README.md)已重新报告。

交付文档同步脚本：[final_delivery_docsync_20261009.py](development/final_delivery_docsync_20261009.py)，仅用于本次终审后的状态归档，不启动服务、不修改封存证据或审批字段；已执行一次，不应重复运行。

## 以下为历史状态（均由上方最终状态更新）


> **11:52 当前状态**：R066c/b131已在独立启动签核与root实际admission后开跑，3服务/5调用冻结范围，服务X加载中；终审待定。R063a kept仅E3。发布门等待R066c分类c与D04，FTD/v5尚未生成，分支部署推送未执行。



> **11:45 当前口径**：用户已澄清逐字字符串判定与逐提示0/a/b/c分类；R066b四原始回复冻结前自检为异常/异常/干净/干净，与要求一致。R066c本地76、Linux101项CPU验证及实际FILEdry通过，候选481/3服务5调用，待独立启动复核后开跑。R063a kept只归E3，不绑定481门。C3按尾段≥65已证、≤64正确性待证。FTD/v5待R066c分类c终审；分支部署推送未执行。



> **11:34 当前状态**：R063a/b130 已独立终审+D04 kept，4服务/48调用与13/13完整尾段通过，78原件哈希不改，只归E3 D12；GPU释放。发布候选481门等待R066c共享前缀判别分类c，R066c CPU本地22/Linux47通过、原提示字节核对通过，尚未GPU开跑；分类“异常”含义待澄清。FTD/v5尚未生成，分支/部署/推送未执行。


> **当前状态（2026-10-09 11:20 用户修正）**：R063a/b130 继续完成终审封存，仅归 E3 D12（8f6a912），与发布候选481d3a7的门解除绑定。新增批准 R066c 共享前缀判别3服务/5调用，R063a释放GPU后执行；发布门等待R066c分类c与独立终审。D20缺口扩大为现算尾段≤64（含1）；T17仅覆盖尾段≥65。分支、部署、推送分别审批；Strata22/345未批准。以下早期状态按时间视为历史。


11:07当前状态：R063/b129已独立终审+D04 failed_harness，77原件不改；错误仅为合法PID后缀被新增断言误拒。第一次常设重试R063a/b130于11:06正式启动，原4服务/48调用；候选/配置/提示/判据不变，原cold_id显式冻结。v2 CPU本地/Linux34/34、实际FILEdry/独立startup和root四消费者通过。R066b c kept保持；发布门等待R063a独立终态/D04，FTD/论文v5尚未生成，未建分支、部署、推送。

10:57当前状态：R063/b129四臂结束后的比较报工装错误：新增默认关闭断言误拒合法PID后缀。独立actual参数与文本/full-tail复算确认failed_harness；原轮待D04封存，不记kept。新R063a仅复用原pinned strict_args修复断言，候选/配置/输入/判据不变，CPU本地与Linux33/33、实际FILEdry通过，待独立启动签核；按常设最多2次重试授权接续。R066b c kept保持，发布门仍未闭合；FTD/论文v5未生成，分支/部署/推送未执行。

10:29当前状态：R066b/b128已独立终审+D04 kept，实际1服务/4调用，无重试，两对均含own、无other/U+FFFD/非法control，热8256与独立冷0/0有实际缓存/并发证据。R063/b129已续启原授权4服务/48调用的D12默认关闭门（8f6a912 E3分支，不是合入481发布候选）。发布门待R063终态；D不补跑，D20只读同end查找问题已确认。未建分支、部署、推送；下述旧状态按时间保留为历史。

2026-10-09 09:00：R066 启动独立复核及实际准入通过，batch126正式运行（3新服务/6调用），B正在加载；全部通过立即接R063。D复用现有T17调度参数，旧R065/R040j not_met保留。发布门等待终态，未建分支、部署或推送。进展见 [09:00摘要](plan/MORNING_SUMMARY_20261009.md)。

2026-10-09 R066新授权：[用户更正](plan/R066_DISCRIMINATE_V2_AUTHORIZATION_20261009.md)说明R065 A2命中8256前缀，只现算1 token，旧冷/热比较判据不适用；R065原not_met保留。既有A1与R040j新进程single正文SHA相同已核为冷跑旁证。新R066上限3服务/6调用，B冷SHA、D同结构冷SHA、C并发串号；现有T17参数及对齐CPU验证可表达D，不另造调度工装。R066薄适配正在准备，独立准入后执行，全部满足接R063；Strata22/345仍未批准。

2026-10-09 08:08：[R065/b125结果](plan/01_测试与调研/results/T20-E2-R065_20261009.md)已独立终审并D04封存not_met，24原件不变只读、closed consumer通过。A1/A2同进程长请求全文从第83字符起不同，finish/usage一致，A2真实cache8256；实际1服务/2调用。B/C与R063未启动，GPU空、进程/组/端口/锁全清，不自主重试。发布门未闭合，等用户裁定；warm2正确性门移除与D19只读调研完成，FTD/论文尚未开始。

2026-10-09 08:05：R065/b125在服务A两次串行长请求的全文不等，触发not_met。实际1服务/2调用；两次finish/usage相同，第二次cached_tokens=8256。B/C未启动，R063不续行、不自主重试；进程、端口/锁和GPU清理已核，独立终审/D04封存处理中。发布门未闭合，等用户裁定单请求冷/热不一致；warm2和D19只读说明已完成。

2026-10-09 08:00：[R065 SDK薄适配](development/r065_d16_discriminate_v1/README.md)已22项Linux CPU通过、实际FILEdry与独立启动审查通过，根实际准入及前置closed consumer回读通过，正式batch125已启动3服务/7调用，首服务A加载中。warm2[只读说明](development/WARM2_READONLY_DISPOSITION_20261009.md)已完成并移出正确性门，稳定hit及收益转E3/D15。发布门仍待R065终态，R063待a/b通过后续行。

2026-10-09 08:30 补充指令已生效：[新授权](plan/SUPPLEMENT_20261009_0830.md)批准 R065 在发布候选481d3a7上运行3服务/7调用，先验单请求确定性、再验并发无串扰，满足后继续R063。R065 SDK工装正在做CPU/FILEdry和独立准入；warm2只读核查后按新指令移出正确性发布门或转入E3性能线。R040j原not_met保留，两对未测不再补跑。发布门尚未闭合；分支、部署、推送仍分别审批。

2026-10-09 07:34：[R040j/b124](plan/01_测试与调研/results/T20-E2-R040j_20261009.md)长请求pair_1的API全文不等，独立终审与D04封存not_met；5服务启动/6调用完成，短pair_0通过，两对未测。07:27已按用户规则中止，49原件保持，进程/端口/锁清理完成，GPU为空；R063及后续GPU全部等待裁定，不自主重试。R061f恢复通过结论保留，完整发布门未闭合。[一页夜间摘要](plan/NIGHT_SUMMARY_20261009.md)与[候选草稿](plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json)已更新。

2026-10-09 07:07：[R061f/b122](plan/01_测试与调研/results/OOM-E2-R061f_20261009.md)已独立终审通过并D04封存measured，完成新OOM候选的一次公开SDK排队恢复验收。D16 [R040i/b123](plan/01_测试与调研/results/T20-E2-R040i_20261009.md)因就绪轮询提前耗尽封存failed_harness；[R040j](development/r040j_api_d16_v1/README.md)只修未就绪等待，20 CPU通过/2跳过、实际FILEdry、独立签及准入回读齐全，07:04已启动6服务/8调用（第1/最多2次工装重试）。warm2缺真实命中证据继续跳过；R063排在其后。[夜间摘要](plan/NIGHT_SUMMARY_20261009.md)单列实际占用和03:33—06:54空闲间隔。

2026-10-09 03:22：R061f/b122 已启动，是本481候选范围第2/最多2次自主工装重试（含R061d首次测量共3次）。[R061f适配](development/r061f_oom_runtime_v1/README.md)只修五项强身份比较；该冻结README沿用了“first”字样，实际序号以本条和独立v2启动签为准。27项Linux CPU通过，含真实D07进程身份函数；实际FILEdry及v2启动签回读通过，API/子进程/锁绑定已核。R061e已[失败封存](plan/01_测试与调研/results/OOM-E2-R061e_20261009.md)，原始数据保持不变。

2026-10-09 03:12：R061e/b121 已退出，独立 R 确认为进程身份校验的 `failed_harness`：真实函数返回含 `state` 的六个字段，工装却要求恰好五个。公开 SDK 请求进入重启队列并在 epoch1 生成128 token，仍不能替代缺失的通过终态。R061f 正准备第二次、最后一次常设工装重试，只修五项强身份比较并补真实 Linux producer CPU 回归；D16/R063暂等恢复门通过。Strata离线输入草案已核为25服务/525调用，未获GPU批准。

2026-10-09 03:02：R061e/b121 于02:58启动，是 R061d 的第一次常设工装重试。仅修正 SSE 错误帧选择，20 CPU 通过、真实 FILEdry、独立启动签及实际准入回读齐全；候选481d3a7、输入、配置和判据不变。当前正在测量，尚无恢复验收结论。后续按夜间授权串行运行 D16 v3 的6服务/8调用与 R063默认门；warm2未验证状态单列。

2026-10-09 02:52：R061d/b120 已按独立 R 判词 D04 封存为 `failed_harness`（[结果](plan/01_测试与调研/results/OOM-E2-R061d_20261009.md)）：实际 SDK 排队请求已恢复生成，但工装误将错误帧后的 usage 当作错误帧，未完成冻结终态检查。同候选、配置、输入和判据的第一次常设重试 R061e 正在准备。D16 [v3 启动适配](development/r040i_api_d16_v3/README.md)已修正 controller cwd；18 CPU 通过/2 跳过、真实 FILEdry、独立启动签和 root 准入回读齐全，保持 6 服务/8 调用，排在 OOM 恢复之后；v2 原件保留。D12 启用线仍冻结，仅新增[一页复用提案](plan/D12_ENABLED_REUSE_PROPOSAL_20261009.md)。

2026-10-09 01:52：[夜间预授权](plan/NIGHT_PREAUTH_20261009.md)优先于下述 01:00 冲突条款。R050a/b118 已独立复核并 D04 封存 kept；新四路由 OOM 候选481d3a7已通过真实公开SDK八项重启CPU回归，R064/b119 默认门4/48已独立复核并D04封存kept。随后 R061d恢复1/3（SDK公开路由）→ D16 SDK interleave6（6服务/8调用）→ R063默认门4/48。三项准入齐全即运行，任何新测量 not_met 停止。R040h追加复核不能排除产品原因，已改为待定（canonical pending_review）；warm2缺少真实命中证据，今晚跳过。R061c保留not_met。D16 [SDK薄适配](evaluation/d16_api/README.md)与[范围说明](plan/D16_API_SDK_REMAINING_SCOPE_20261009.md)采用6/8，旧8/12不执行。T21不建新工装、Strata只准备、D12启用线继续冻结。

2026-10-09 01:00：[执行指令](plan/ROOT_EXECUTION_DIRECTIVE_20261009.md)规定发布门仅 T17、R041、T20/D16 与 OOM 恢复，其他指定优化项进入 E3。新增测试工装复用 AIPerf、openai-python SDK、pytest；D12 namespace/PID/control/watchdog/宿主FD线已冻结，最后在途CPU回执25通过/2失败原样保留，不再修测。D08按已测量、无收益关闭，保持默认关闭。发布分支、部署、推送仍分别审批。

2026-10-09 00:34：[D12私有控制管道](development/d12_enabled_runtime_v1/README.md)已host18PASS和独立复核（`b20d1de3`）；ordinary27沿用字节绑定的v1结果，未合称同次运行。实际host突然退出、PID1主线程阻塞和队列满均触发整个CPU namespace退出；错误控制帧在服务创建前拒绝。正式每臂owner、D07准入/锁和D04仍待接入，无模型/GPU验收。下一步复用已有health-only/stop接口，完整T17 service函数的硬编码路径不能直接套给D12。

2026-10-09 00:08：[D12宿主/namespace身份映射](development/d12_enabled_runtime_v1/README.md)最终Linux宿主12PASS及隔离ordinary27PASS，receipt `dfb17616`。真实CPU流程覆盖两阶段START、私有tmp、跨PGID清理；普通证据绑定boot/PID域，跨域解释被拒绝。修复独立复核发现的holder PID域漏检，以及真实回归触发的旧helper退出竞争；原失败记录保留，D12窄适配未改冻结helper/R062。正式controller/owned准入、功能规则与D04仍待接线，`host_proc_observer_ready=false`；未运行目标模型或GPU。

2026-10-08 23:26：[D12四角色启动描述](development/d12_enabled_runtime_v1/README.md)已参数层FILEdry及Linux15PASS（27a52001），独立源码/SSH复核通过。原生解析核对control/repeat/ordinary-reference/enabled四角色，共计划4服务12请求；工具没有服务启动分支，`approved_new_services=0`，不预订端口。正式owner启动演练、宿主观察、功能规则及D04仍待完成；R062及既有GPU批准范围不变。

2026-10-08 23:05：[D12普通HTTP与进程证据](development/d12_enabled_runtime_v1/README.md)已隔离Linux21PASS、独立限定复核通过，receipt `4916a01b`。真实共享socket/setsid逃逸负例在POST前拒绝；完整三请求原body/SSE/event时钟、实际worker出生及停止collection SHA链已接通。宿主同UID sshd/sd-pam FD不可读仍会fail-closed，失败回执 `f647fe98` 保留；隔离通过不代表宿主或目标模型就绪。正式多臂/功能判据、D04和GPU验收仍待完成。

2026-10-08 22:26：[D12目标模型规格](development/d12_enabled_runtime_v1/README.md)已Linux15PASS，receipt `3725e157`。固定实际qwen4_exp overlay目标/SHA、248320词表、四角色状态布局及48层MoE分母；原生meta池核验不读取权重。规格可供完整比较器使用，实际服务身份/设置与正式多臂功能门、D04、GPU和性能仍待验证。

2026-10-08 22:10：[D12成对完整比较](development/d12_enabled_runtime_v1/README.md)已Linux236PASS，receipt `27db5a38`。完整生成token/SSE、native最终状态与固定tail logits分别比较，usage与实际admission/交付/首次cache核对；三token末位分叉被准确识别为位置2。数值指标不派生容差，T04现行分布交付不重开；正式功能门/D04、目标模型/API/CUDA和性能仍待完成。

2026-10-08 21:50：[D12原生D0调用分母与bank完整性](development/d12_enabled_runtime_v1/README.md)已Linux170PASS、独立源码和SSH实物复核通过，receipt `b287ceed`。普通/层优先的全部MoE调用与阈值命中事件逐项关联；修正全回退也称bank覆盖成功的flag。三UID联合CPU夹具取得2/6/2调用并绑定状态/tail；真实CUDA、目标模型输出、正式三臂数值/D04和性能仍未验收。

2026-10-08 21:11：[D12普通SSE语义比较](development/d12_enabled_runtime_v1/README.md)已Linux46PASS、独立SSH实物复核PASS_LIMITED，receipt `6ad1b5d0`。按固定API源码仅排除运行时钟和tool ID随机后缀，固定UID/正文/reasoning/arguments/finish/usage精确比较；三条历史业务响应的运行时元数据副本比较通过，语义变化负例判不等。逐token及数值门、bank覆盖和D04/GPU验收继续待完成。

2026-10-08 20:56：[D12状态/tail独立读取](development/d12_enabled_runtime_v1/README.md)已Linux117PASS，独立SSH产物复核PASS_LIMITED，receipt `822aff65`。同一D16 adapter/worker与候选model loop/D03的三UID CPU联合夹具完成外部policy、实际admission、四角色状态及末64位置绑定；19个篡改/缺失负例拒绝。bank调用覆盖、prefill调度分母、跨臂输出等价及GPU功能/性能仍未闭合。

2026-10-08 20:38：[D12固定prompt-tail采集](development/d12_enabled_runtime_v1/README.md)已接入普通worker的显式诊断模式，Linux97PASS，独立SSH产物复核PASS_LIMITED，receipt `1c30d2b8`。复用D03 collector/TP1投影/writer/reader，保持同一请求原分段，真实三请求末64坐标policy已冻结。CPU fixture不等于目标模型/GPU；正式四层比较与D04调用方继续待完成。

2026-10-08 20:10：[D12普通tools SSE读取](development/d12_enabled_runtime_v1/README.md)已Linux15PASS、独立PASS_LIMITED，三条真实封存响应的正文/reasoning/tool ID/name/arguments/usage完整结果回放通过；receipt `82c63e5e`。复用既有wire采集及SDK离线拼接，不调用模型端点或执行工具。CLI/spawn另2PASS；固定后续logits兼容性、正式D04调用方与GPU四层验收仍待完成。

2026-10-08 20:00：[D12入口检查](development/d12_enabled_runtime_v1/README.md)已2PASS，真实CLI解析及spawn目标到TP保护分支通过，receipt `a30ad70f`。关闭overlap的实际参数为 `--disable-moe-prefill-overlap`，规划文档已勘误；实际模型/API尚未启动。固定后续logits需要适配缺失的D03输入/采样钩子，不能直接用独立前缀探针替代原门。

2026-10-08 19:36：[D12自然终止采集](development/d12_enabled_runtime_v1/README.md)已Linux87PASS、独立PASS_LIMITED。显式冻结UID/输入/生成上限，复用D16物理采样与实际交付，独立报告/reader确认capture_complete但不声明输出等价；旧fixed reader拒绝自然报告。CPU正常/清理故障生命周期均保留证据，receipt `8e05cb3a`。真实CLI/API/spawn、正式D04接入及GPU四层数值/性能仍待完成，四个待批GPU范围未启动。

2026-10-08 19:20：[D12冻结输入绑定](development/d12_enabled_runtime_v1/README.md)已Linux67PASS；三条完整token输入通过实际D16 admission与worker CPU夹具，错误UID/输入/采样参数拒绝，固定expected_queries未变。receipt `d29d9d93`；真实HTTP/CLI/GPU尚未验证。新确认三条tools请求自然结束与D16固定生成数契约不兼容，需显式完成条件，不能使用历史140/58/113或2048伪造当前生成数。四个既有GPU范围仍待回复。

2026-10-08 19:00：[D12 worker接线](development/d12_enabled_runtime_v1/README.md)已复用既有D16构造/采集/退出流程，Linux51PASS、独立PASS_LIMITED；正常及清理故障两个CPU夹具分别封存complete/failed，原错误保留、shutdown各一次、CUDA未初始化。原生状态池和D16组件实际执行，模型forward仍是夹具；未证明CLI/spawn、GPU bank、四层数值或性能。候选8f6a912/R062未变，四个待批GPU范围仍未启动。

2026-10-08 18:35：[Quality60 SDK入口](evaluation/quality60/README.md)已接入原共享题循环和规范判卷器，并同步服务器；Linux23PASS，独立复核60条记录/60份chunk日志及47/11/2判分一致。修正了CLI输出model身份，传输/解析失败保留证据并记RUNTIME_ERROR；旧共享调用方默认路径继续兼容，冻结测试包未迁移。部署回执 `evaluation/quality60/deployment-20261008T1835.json` 绑定旧源备份及新源SHA。本次是CPU协议/回放集成，不是目标模型验收。D12已定位真实worker安装边界和layer-major child身份来源，主诊断必须关闭route trace；实际接线与GPU四层验收继续待完成。

2026-10-08 18:19：评估工具部署与无 GPU 验证已收尾。AIPerf 实际 CLI 对自有模拟端点完成2请求、0错误、TTFT/TTFO各2个样本；官方JSON/CSV/JSONL及日志保存在 `evaluation/toolchain/smoke-runs/20261008T101803Z-ca1f2f34dd16/`，root回读receipt `efdb127e`及profile `18050cd6`通过。SDK采集Linux16PASS与60题逐题回放已独立复核；D12原生状态落盘CPU回读10PASS。这些均不代替真实模型验收。18:17服务器无GPU计算进程，R040h/R050a/R062/R061c正式目录均未创建，仍待先前具体范围回复。

2026-10-08 18:05：[隔离工具链](evaluation/toolchain/README.md)已部署 AIPerf0.11.0、openai2.54.0、pytest9.1.1、lm-eval0.4.13，依赖检查及 SDK loopback JSON/SSE 通过；AIPerf 模拟端点运行验证正在补齐。[Quality60 SDK采集](evaluation/quality60/README.md)已 Linux16PASS，经真实SDK离线回放封存60题，逐题保留正文/thinking/结束原因及47/11/2判分，独立复核通过。它拒绝缺失finish_reason和损坏JSON，不将其默认判stop；现有共享benchmark入口尚未切换。以上均未使用GPU，不是目标模型验收。

2026-10-08 17:50：用户已确认工具部署与修正后的评估边界，见[交接书第十八节](plan/CODEX_HANDOFF_20261006.md)。独立 Agent 正在 `evaluation/toolchain/` 部署固定版本的 AIPerf、SDK + pytest、lm-eval 专属隔离环境；安装与无 GPU 接入验证进行中。root 继续产品写侧与协调，D15 输出分叉尚未证明解决。D12 transfer audit v2 已 Linux27PASS，segment capture 仅本地9PASS，均未作为目标 GPU 验收。17:50 最新协调记录已追加到本地与服务器监控副本，历史前缀保留。

2026-10-08 17:31：[D12专家bank诊断适配器](development/d12_enabled_runtime_v1/README.md)已Linux16PASS，CUDA未初始化；它核对实际slot映射、GEMM bank views和六个NVFP4 bank被选中行的全字节，尚未接入GPU采集。T06的51段属于tracing配置，正式启用验证还须核对trace-off layer-major的实际子段；不能从历史段数推算新运行分母。

2026-10-08 17:16：[D12启用输入与分段口径修正](development/D12_ENABLED_INPUTS_AND_SEGMENT_CORRECTION_20261008.md)已完成离线准备，工具 [d12_enabled_inputs_v1.py](development/d12_enabled_inputs_v1.py) Windows/Linux8PASS。实际阈值按单次MoE预填段判定：29个warm请求含51段，35段≤256，15段恰为64；原10/29只是请求后缀统计。已固定三条完整普通请求及真实worker token IDs，不是GPU正确性或性能证据。四个既有待批GPU范围仍未启动。

2026-10-08T16:59：R060c/b114 已 D04 kept；R061b/b115 已 D04 failed_harness 封存，R061c 工装时序修复已 Linux14PASS、实际FILEdry、独立复核且实际入口绑定通过。[D16/D15](development/R040H_R050A_READY_20261008.md)、[D12](development/R062_D12_DEFAULT_GATE_READY_20261008.md)与[OOM R061c](development/R061C_READY_20261008.md)具体GPU范围均已提交、待回复。D13 7e3db70 Linux50PASS/1skip及独立复核通过；[目标配置CPU/meta检查](development/d13_target_meta_preflight_v2.py)已在真实overlay配置上构建TP1/2/4全部7个rank声明，未加载权重或启动CUDA。现场仍仅一张4090，多卡正确生成未验证。

R050a D15 runtime gate package: [development/r050a_d15_runtime_v1/README.md](development/r050a_d15_runtime_v1/README.md).

R062 D12 default-off gate package: [development/d12_default_gate_runtime_v2/README.md](development/d12_default_gate_runtime_v2/README.md).

2026-10-08 15:21：D12短后缀候选8f6a912已Linux60PASS/3skip，源码独立复核PASS；默认关闭，实验0对256、两臂均关闭overlap，实际CUDA数值/性能待验证。D15槽提升修复8256553已Linux19PASS，最终同测试对原988c在临时槽清理后复现丢映射、修复通过；只证明驻留映射缺陷已修，R049c第8token分叉仍未证明解决。D13逐类G0 v3独立复核通过为条件设计预算，普通TP2稠密分片首版实现及CPU重建测试进行中。R040g/b113运行中，已生成5个场景采集manifest。

2026-10-08 14:55：R049c/b112已独立复核并D04 not_met，只读封存；PA1第二条冷请求的输入与L1/P1一致，第8个生成token分叉，32raw哈希不变，仅2请求、0完整服务，无完整T21/性能结论。R040g/b113已按既有批准启动，effb996、98,304/0.88，补14服务16调用，child2914235:153687054。D12候选eb7f54a的Linux CPU为26通过/3跳过/3个父版本同样失败，无新增失败；CUDA内核/性能尚未验收。

2026-10-08 14:25：T09/R048b b111 已独立复核并 D04 measured，8 服务48请求，C按115 GiB前置跳过；409原始文件哈希不变、目录只读。SC1未复现，S仅为A亲和性重复，诊断不证明CPU/PCIe实际时间重叠率。R049c/b112已按批准启动，保留L1/P1，余7服务168调用，child2828886:153492983；下一项R040g。D12候选97f6ee3已本地提交，Linux CPU验证待测量空档。

2026-10-08 13:52：用户批准R049c一次7服务/168调用补跑，并要求D05、D09、D10、D11、D12、D13尽快排期。T09/b111已完成V0/A/B两阶段与S性能共42份请求产物，S诊断运行中，尚待终态独立复核；当前批次收尾后按R049c→R040g接续。D12建卡与其他五卡真实前置核对并行，原有六项已编码功能的验收继续；新开发工作不包含在原9批计数内。

2026-10-08 13:17：R048b/b111完成V0性能6请求，V0诊断执行中；R051a/b110已kept。R040g的14服务/16调用effb补跑及按原提交汇总历史证据已获用户批准，Linux6/真实FILEdry/独立启动签齐，等待当前GPU批次结束。R049c的7服务新重试仍待回复。T05 v17/T10 v7/T03b v12前置绑定Linux143及独立源码复核通过，仍须真实R040g measured后才能继续。

2026-10-08 12:47：R051a/b110已D04 kept，四臂/48调用、78raw哈希未改；关闭D0的父/候选解码34.78/34.79 tok/s仅记录。R048b/b111已按原批准启动，76af、五变体×性能/诊断，共10服务60调用；FILEdry/R签已齐。R049c七服务补跑包已Linux34/真实FILEdry/R技术签，新GPU批准已发待回复；R040g仍在准备，未启动。

2026-10-08 12:12：R040f/b109已D04 failed_harness原地只读封存，0/14scope、20raw哈希不变；0aa开启暂停接口时无条件延迟普通消息，root保存现场后SIGINT结束。R051a/b110已启动，76af候选对effb四臂/48调用，child2472372:152718491。D15显存快照保护Linux40项通过，旧源故障对照如期失败；仅CPU证据。R040f/T21新GPU重试未获授权，其余已批准独立批次继续。

最新授权（2026-10-08 11:18）：用户已批准 R040f、R049b、R051a→条件R048b、R052a、R060c→条件R061b 五组；本段及上方运行态覆盖下述历史待批准记录。R049b授权已用于b108；其失败后的新GPU重试另行裁定。Harness优先复用成熟工具，可独立工作并行；发布/部署/推送未获授权。

当前权威为[交接书第十四节](plan/CODEX_HANDOFF_20261006.md)，**全部开发和测试完成后再提交发布裁定**。root负责调度，具体文件归属、依赖和证据见[执行拆解](development/SECTION14_EXECUTION_SPLIT_20261007.md)。正式GPU批次串行，CPU开发和R独立复核并行；每批先CPU自检、同入口/路径/用户的真实文件空跑、R启动签，再运行、逐组复算和D04原地只读封存。协调日志持续同步到监控读取的服务器副本。

R059四臂已按权威128-token口径纠正复核并D04 kept，旧v1不改。60题CPU逐题比較60/60判分、文本和计数一致（47PASS/11TRUNCATED/2ANSWER_FAIL）。发布性能数字取R056的98,304/0.88配置；R040实际73,728，约10.4%解码差异按跨窗口代价记录。R058三并发场景0 OOM，最低377.7MiB，只支持已测场景。

最新运行态（2026-10-08 03:27）：R046g/b99 四组34请求独立复算通过并 D04 `measured`；G3沿用R046e，G4/T06完成。seed_real 完成8轮，第9轮计划100,223 token触窗，未发送、未截短，不算失败。见[本轮报告](results/T06-E2-R046g_20261008.md)。R040d/b100 与 R049/b101 都已 D04 `failed_harness` 原地只读；D16的首批512记录仅部分保留，T21没有完整性能臂接受，原始与判词均未改。

当前状态（2026-10-08 11:03）：R052/b107已10:25:36 D04 failed_harness原地只读封存，27raw哈希不变，8重放+续问仅为局部证据、T11未接受。R052a v7a已Linux74/默认FILEdry/独立R技术启动签通过。D08新候选76af7584已同步专用服务器树，Linux17及实际模块导入通过；R051a新T16门Linux29/四臂FILEdry/R技术签齐，条件后继R048b T09 Linux64，等待新门实际kept后正式空跑/启动签。这两个新GPU范围尚未批准。T10/T03b同型收尾问题的新版本已完成Linux82项（含8项真实双SIGTERM对照）及独立R源码复核，正式空跑仍被实际T20/T11前置阻断。

最新T09状态（2026-10-08 09:54）：R048a/b106于09:44退出，V0性能6请求已独立复算；V0诊断在CUDA Graph capture内调用stream.synchronize触发Unsupported/Invalidated，非OOM。A/B/C/S未启动，T09没有完整测量结论。独立R已绑定67原文件和失败边界，专用D04 v2经R审及实际预检通过，09:53:49已原地failed_harness只读封存；服务、进程组与GPU锁均已退出。因已启动服务并测量，后续GPU重试需新用户裁定。D08诊断采集修复在隔离本地分支推进；T11随后于10:00首启b107并失败，当前状态见上段。此前R048/b105的测量前CLI失败已封存，旧证据不变。详见[问题清单](development/PROGRESS_AND_BLOCKERS_20261008.md)。

此前运行态（2026-10-08 05:54）：R040e/b104完成9个scope后，在停靠组导入multisession_probe时failed_harness；child已退出、自有GPU锁已释放，D04原地只读封存已完成。9scope均局部复算通过，slots4组合证明四输入的四次运行全文与128采样token一致，但整轮未接受，后续保留范围按卡面独立复核。A正在新版本修复冻结依赖，计划仅补parking/cache/interleave剩14scope；新重试未批准。R049b新v13 Linux56/同入口真实路径空跑/独立R启动签通过，8服务批准待回复，L1的24请求保留。OOM修复4c878f6 CPU69及协议7通过，R060c空跑/R启动签通过，门与条件R061b批准待回复；真实恢复尚未验收。

R040f准备（2026-10-08 07:21复验）：新v6/Linux45项、v7封存SOURCE生成端→真实消费者、正式目录下14项文件空跑及独立R启动复核全部通过。范围为parking4/cache4/interleave6，保留R040e已复核9项；0aa23431、98,304/0.88不变。SOURCE/FILEdry/启动签SHA与只读位已由root回读。GPU补跑尚未批准，未起服务、拿锁或建正式轮次。旧不合格回执及封存原件保留，见[重试审批包](development/R040F_READY_FOR_USER_APPROVAL_20261008.md)。

T05新v16已通过Linux86项，现有6个真实前置封存元数据链通过，目前入口仍要求R040f measured。T09旧v8已通过Linux50项，R049/R049a失败元数据链通过；09:05代码/R双审确认R049b仅为顺序前项、不是T09数据依赖，v9正按交接书§8.7做固定例外的CPU→空跑→R签，齐备后首次运行R048。fixed-token与native判据保持原v7口径，旧版本与判词保留。T05保持排在T09后；R确认其卡面要求T20完成，保留R040f measured验收前置。见[旧CPU交接](development/TAIL_CLOSED_PIN_CPU_HANDOFF_20261008.md)及[当前问题清单](development/PROGRESS_AND_BLOCKERS_20261008.md)。T11/T10/T03b后继CPU版本分别已38/29/38项检查（T03b已换v10，API缺缓存值显式unreported并绑定D0账目），真实路径空跑与R签在核实各自实际前置后进行。T04/S-007当前只读分析范围已交付，见[差异分布](plan/01_测试与调研/results/T04-S-007_20261008.md)和[范围审计](development/T04_S007_CURRENT_SCOPE_AUDIT_20261008.md)：普通冷四组296点、历史两比较1776点及四组128输出差异。历史UID映射/R002正式封存/logits保留为观察缺口，不授予容差或放行结论。

[发布说明](development/RELEASE_NOTES_E2_DRAFT_20261006.md)、[部署与回滚草稿](development/DEPLOY_ROLLBACK_E2_DRAFT_20261006.md)和[FTD草稿](plan/data_releases/E2_BASE1_RELEASE_DRAFT_20261006.json)同步以上证据。全部任务完成再申请发布；release/e2、部署、推送分别待批准。[剩余工作量与工期依据](development/SECTION14_REMAINING_ETA_V2_20261008.md)已按当前入口更新；旧24–47小时预算撤回，暂不承诺总完成时刻，GPU实际验收、复核和审批时间分别记录。协调日志持续同步服务器监控副本。

## 历史阶段记录

以下第十二/十三节时段记录保留。其“当前”“待裁定”和旧队列描述以当时为准；启动依据用上述第十四节状态及最新执行拆解。

当前执行依据是 [交接书第十二节](plan/CODEX_HANDOFF_20261006.md)。发布基线仍为 `E2-base.1@0aa23431`，仅将发布窗口改为98,304（KV与最大序列两个键），比例0.88、生产不开D0；T17 28/28、R041 kept证据沿用，不重跑。R050/R051各4/4 kept。R040/batch71仍为`failed_harness`，已测部分是否作为发布依据待用户裁定，完整T20尚未通过。

root已接管A/02/T统筹，协调日志同步到饕餮实际读取的服务器副本，见[接管约定](development/EXECUTION_LEAD_HANDOFF_20261007.md)。当前[R046b恢复提案](development/R046B_OOM_RECOVERY_PROPOSAL_20261007.md)待用户批准；R052缓存证据新v4的Windows/Linux定向回归各35 PASS，正式FILEDRY、R启动复核和GPU接受分别待完成。

最新队列：**R056 → R046b → R049 → R048 → R040a → R045 → R052 → R044 → R047**。R056/batch81已完成11/11请求，独立原始复算及D04封存复核通过，终态`measured`，GPU锁已释放。32K排首枪中位6.465秒/34.33 tok/s；完整87,100提示两次首token（any delta）18.771/18.132秒、解码30.30/30.32 tok/s。历史R040实际窗口73,728，新98,304下32K解码下降约10.4%，仅作跨窗口配置观察。87K请求后最低样本约0.357GiB，不是连续显存最低值，也不证明R046b现场余量。新入口与观察器见`development/r056_long_context_prepare.py`；此轮不授予发布批准。

R046b/batch82于12:38原地D04封存为`failed_harness`：G3-off已完成并独立复算保留，G3-on在98,304/0.80下发生CUDA OOM，申请752MiB时剩余45.69MiB。失败位置为FLA的`chunk_delta_h.py:324`；具体分配维度未记录，不能归因为GPU route trace缓冲。G4/T06未执行，暂停链尚未验证。所属进程已精确清理、本批次锁已释放；比例已到授权下限，依交接书第十二节停止队列并等待用户裁定，R049未启动。见[R046b结果](plan/01_测试与调研/results/T06-E2-R046b_20261007.md)。

R056测量和封存证据见[完整结果](plan/01_测试与调研/results/T20-E2-R056_20261007.md)。`seed_real`首条完整请求已在发布树真实前端CPU核实为**87,100 token**，原SHA保持，不截短。R046b全臂98,304/0.80，同配置重跑G3-off；T06在实际提示超过96,256时自然结束，记完成k轮/第k+1轮触窗，不算失败。R049发布配置98,304/0.88，训练仅seed12k；seed_45k实际约1.2万token，名称不改。超过98,304仍拒绝，Strata131,072是已知窗口差距。

route trace快照位于CPU pinned内存（32K约30MB），旧“628MiB GPU trace缓冲随提示增长”解释及对应发布后改写计划作废；分配来源留到发布后allocator snapshot调查。.80仍依真实OOM数据授权，运行显存余量必须实测。R055门已结束，六冷臂默认路径证据沿用；R055a/b与R046a/batch80失败原件保持只读。旧49,152窗口下的CPU拒绝报告仅描述历史工装，不代表第十二节的新源启动签字。

R049的工装画像专家数已由256修正为目标模型的512，并对齐实际R046b生产端的清单schema；原候选builder/reader合成高ID与实际生产端→消费端回归及 Linux 54 项通过。R047依赖迁移的 Linux 25 项通过。性能比例保持0.88，未读取正式route、构造正式画像或启动模型；新版source/CPU SHA及前置边界见 [第十一节执行交接](development/SECTION11_EXECUTION_STATUS_20261007.md)。

R040a 当前补测入口为 `development/r040a_d16_supplement_prepare_v4.py`，私有动态端口、collector v4 包装沿用 collector v2/shutdown v3。旧 v3 的 Linux 集成176项及来源复核保留；新98304 v4局部CPU127项通过，尚待新版Linux/实际空跑/R启动复核。精确冻结源与后续命令见 [R040a 当前交接](development/R040A_PRIVATE_PORT_OWNER_HANDOFF_20261007.md)。所有后续批次仍需 CPU 自检、同入口/路径/用户的真实文件空跑、R 启动复核、GPU 实测与 D04；CPU 通过不能代替任何正式判定。

2026-10-07 轨迹绑定修正：T05/R045 按卡面使用正向 `trace.json`（FTD SHA `055ea005…`），T11/R052 按 R011 使用反向 `trace_rev.json`（SHA `097b7a03…`）；不能混用路径与 SHA。新 R045 v5 已通过 Linux 43 项回归及两项自检，实际空跑仍待前置；新 R052 v2 已通过 Linux 29 项回归和同入口/路径/用户的文件空跑，原客户端复算目标 index7 摘要为 `e3a67ebe075b0126`。旧冻结源、失败空跑与旧 CPU 回执保持不变，新版拒绝旧签字。详见 [R045 交接](development/R045_HANDOFF_20261006.md) 与 [R052 交接](development/R052_HANDOFF_20261006.md)；两轮均未取得 GPU 启动签字，R052 正式启动仍需 R045 measured。

上述轨迹修复已由独立 R 复核为 `PASS_CPU_AND_FILE_ONLY`，回执为 `/data2/FreeToken/runs/dev_R052/r052_r045_trace_mapping_cpu_file_review_v1/review.json`，SHA256 `c9256c2028d68c1baf2bcd2b66c8ac0dacca31f50870ce4e3586a5b8d1a14aa0`。R 已核源码、CPU 报告与 R052 实际输入副本/15 个文件探针；回执明确 `startup_approved=false`、`gpu_launch_approved=false`。R045 实际空跑与两轮正式测量仍未完成。

Qwen3.8-Flash-Next-NVFP4 / GLM-5.3-Flash-NVFP4 在 FreeToken 推理框架上的适配、评测与调优工作目录。远端环境：`172.16.108.9:/data2/FreeToken/`（venv：`/data2/FreeToken/venv`）。

## 本地开发与服务器验证

- T10/T03b当前CPU闭包为 `development/r044_runtime_v6/`、`development/r047_runtime_v11/`；Linux82项含8项真实双信号对照，详见[关闭链CPU交接](development/TAIL_SHUTDOWN_CPU_HANDOFF_20261008.md)。两正式轮次目录不存在，必须等真实前置后做FILEdry/R签。

- 新重试包：[D08新门及T09、T11收尾修复](development/R048B_R051A_R052A_READY_FOR_USER_APPROVAL_20261008.md)。运行闭包分别为 `development/r051a_d08_runtime_v1/`、`development/r048_t09_v11/`、`development/r052_runtime_v7/`；D08产品在 `development/e2d08-capture-trace/`，CPU来源验证脚本 `development/d08_capture_trace_cpu_validate_v1.py`。旧源与封存原件保留。
- 新失败报告：[T11 R052](plan/01_测试与调研/results/T11-E2-R052_20261008.md)；其专用D04脚本 `development/r052_b107_failed_close_v1.py` 固定原轮与R终审，仅用于已完成的该次封存。


- 当前后续工装见[CPU交接](development/TAIL_RUNTIME_CPU_HANDOFF_20261007.md)：T11 `r052_d0_shutdown_startup_v1.py`复用原scheduler启动/退出，Linux38PASS；T10 `t10_capture_startup_v2.py`＋`t10_ordinary_replay_v1.py`使用真实普通SSE及capture shutdown，Linux29PASS；T03b v6复用同shutdown、单私有端口对和同writer空跑，Linux29PASS。正式空跑/R签/GPU分别待前置。
- OOM产品在`development/e2oom-recovery/`，对应服务器`/data2/FreeToken/wt/e2oom-recovery`，父树0aa23431。只用本地提交/bundle同步专树；`development/tests/test_oom_supervisor_recovery_actual.py`针对真实supervisor验证旧worker退休、重启失败、二次OOM与非OOM边界，Linux6PASS；CPU证据不代替R060/R061。
- `development/t16_d14_schedule_stage.py` 冻结新卡D14默认路径 T16 工装、D18 客户端证据与已通过的引擎 CPU 回执，在专属 Linux venv 执行 CPU 回归；失败结果保留。`t16_d14_schedule_launch.py --stage <冻结目录>` 只预检，`--launch` 才通过原子批次入口执行。新声明 `t16_d14_schedule_runner.py` 比较 `e4f3202` 与直接子提交 `e45e2c2`，覆盖层优先及普通预填各四臂；D18 测试源码随工装冻结。此登记不代表 T16/T17 已接受。
  `t16_d14_schedule_start.py` 仅启动准确独立复核的 `a9eaf6c40ec8` 工装并保存权威进程回执；`t16_shared_monitor.py <回执>` 只读核对执行源、PID、生存状态和GPU锁。
  R032 原始复算为 `t16_r032_review.py`，复用固定历史读辅助函数；`t16_r032_review_stage.py` 冻结并在 Linux CPU 验证审核器，`--review <CPU回执>` 仅在本轮进程及八臂都终止后写独立原始审核，不授予 T17 接受。
- `development/d14_schedule_sync_cpu.py [--previous-receipt <精确旧回执>]` 将干净的本地已提交调度候选通过 Git bundle 同步专属服务器工作树，并冻结 CPU 实测结果；失败夹具和此前66 PASS均保留，当前门候选 `e45e2c2` Linux 70 PASS。详见 [卡D14/卡D16进度](development/D14_schedule_progress_20261005.md)。`development/tests/test_t17_schedule_readiness.py` 验证健康检查不发生成请求。
- 卡D14 新调度候选位于 `development/e2d14-schedule/`（父 `e4f3202`）；卡D16 CPU 工具在其 `scripts/equiv_suite/`。`PYTHONPATH=scripts python -m equiv_suite` 提供 `compile`、`check-structure`、`evaluate`、`replay`，命令见 [工具说明](development/e2d14-schedule/scripts/equiv_suite/README.md)。历史重放 [d16_historical_replay_20261005.json](development/d16_historical_replay_20261005.json) 已核对 R019/R021 各臂13事件及 R023 四角色恢复；R023 缺同结构参照，结果为 indeterminate，未放行。D14 Linux 执行验证、D16 实测工具与 T17 批次仍待完成。
  `development/e2d16-tools/` 的 `e9ee6aa` 已实现实际命中、自动调度、双进程参照和普通冷包络的续算编排；`development/d16_tools_sync_cpu.py` 将该已提交工具树同步至专属服务器工作树并取得 31 项 Linux CPU PASS。`development/d16_tools_deliver.py` 已将九个准确工具文件交付至本地及服务器 `scripts/equiv_suite/`；[实际交付回执](development/d16_tools_delivery_e9ee6aac1786.json) 不代表 GPU 接受。引擎候选仍为 `e45e2c2`。
  `development/t17_continuation_inputs.py`／`t17_continuation_inputs_stage.py` 用真实目标分词器生成四个边界、七种尾长的 28 组输入，并冻结 token SHA 和上下文；`t17_continuation_runner.py` 是复用原服务生命周期的新运行包装，首算子诊断与 T17 批次尚待交付。`development/t16_r032_close_stage.py` 冻结七项准确封卷源并完成七项 Linux CPU 测试；`--prepare` 只读复算，`--close` 需准确 CPU 回执及独立原始审核文件，R032 未终态时均不得封卷。
- `upstream-flashml/` 保持上游固定提交的只读参照用途。
- `development/e2d01/` 是从服务器 `E2-pre@3db7b50` 克隆的完整开发仓库；D01 分支为 `exp/e1r008-anchorcut`，交付提交 `f91054b`。本地编辑、审阅和提交，再用 Git bundle 同步到 `/data2/FreeToken/wt/e1r008/`；同步时核对源码、Git tree 和提交一致。
- Windows 当前 Python 未安装 torch；单元测试和 Linux/CUDA 推理自检在 FreeToken 专属 venv 执行。D01 单元测试结果：384 passed / 2 known failed / 1 skipped，新增 14 个测试通过。
- `development/remote.py <本地脚本.sh>` 将 UTF-8 脚本经标准输入送入 `ssh 9 bash -s`，避免 Windows/SSH 多层引号损坏。
- `development/e2d14/` 为 P0 快照及上下文修复候选 `fix/e2-ngram-track@e4f3202`，父树 `E2-base@23f2e2c`，已按准确 Git bundle 同步服务器。CPU 13 failed→13 passed；R021 failed_harness保留，R022默认四臂已独立封存kept，R023真实命中续算输出/计算态不等，独立封存not_met。E2-base.1及修复版T10未接受。见 [D14交付](plan/02_开发任务/D14_交付记录_20261004.md)、[T17结果](plan/01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md)。
- T16 当前共同实现为 `development/t16_full_tail_base_runner.py` + `t16_candidate_runner_full_tail.py`，D14 仅声明准确父/候选绑定。`development/tests/fixtures/t16_failed_full_tail.json` 收录实际 R019/R021 回归；历史 runner 只用于原始复算。废弃入口 `t16_candidate_launch_full_tail.py` 拒绝启动；R022使用的冻结历史bytes已归档。
- T17工具为 `development/t17_d14_runner.py`、`t17_d14_gpu.py`、`t17_d14_observe.py` / `t17_d14_artifacts.py`、`t17_d14_stage.py`、`t17_d14_launch.py` / `t17_d14_start.py`。`t17_owned_launch_protocol.py`只提供已复核进程函数，不执行历史main。R023已终止封存；`python development/t17_r023_read.py`只读复算counterexample，`t17_r023_close.py` / `t17_r023_close_stage.py`保留exact-scope封存源。见 [工具说明](development/t17_d14_README.md)、[分块诊断](development/t17_r023_computation_diagnosis.md)。
- T17 首层数值诊断：`development/t17_prefix_numeric_{observe,startup,runner,launch,stage,start,monitor}.py` 保留R023默认4096分块，记录第一GDN共享前缀实际入参与原返回h[56]。stage验证Linux CPU及正常spawn，start只启动准确独立审查的冻结源，monitor只读实际进程／源码／结果。见[诊断计划](development/T17_PREFIX_NUMERIC_DIAGNOSTIC_PLAN_20261005.md)及[观察器契约](development/t17_prefix_numeric_observe.md)；只作定位，不授予T17接受，时间不作性能数。
  `development/t17_prefix_numeric_read.py` 使用SHA固定的独立CPU程序读取准确R027启动回执，绑定全部42个原始张量的SHA、shape、dtype与用途；[原独立程序](development/t17_r027_independent_cpu_review.py)是其保留依赖。`development/t17_r027_d04_close.py` 在重算结果与预审记录一致后才允许封存诊断，kept不改变原T17接受判定。
  R027 的[独立预终态审查](development/t17_r027_independent_preterminal_review.md)记录坐标核验及层索引、return_h来源、非独占张量发布的证据限制。
- T17 同分块诊断：`t17_matched_stage.py` 冻结工装并执行 Linux CPU/normal-spawn 预检；`t17_matched_start.py` 只启动已独立复核的准确 stage。`python development/t17_matched_monitor.py E2-R025-diagnostic-T17` 只读本次真实 batch53、进程 birth identity、8192 prefix receipts 和服务停止记录。R025 使用 `FT_LM_CHUNK=7680`，仅定位 R023 分叉，不能改写原 T17 `not_met` 或授予 E2-base.1 接受。观察器见 [说明](development/t17_matched_observe.md)。
- R025已封存为诊断kept：`t17_matched_read.py E2-R025-diagnostic-T17`只读复算8192前缀、8256四角色、128个ID与全文；[结果](plan/01_测试与调研/results/T17-E2-R025-diagnostic-T17_20261004.md)保留原门not_met。`t17_r025_close.py`／`t17_r025_close_stage.py`和`t17_r025_panel_record.py`保留本轮已执行的封存／8098读回来源，不作为新轮启动入口。`t16_r024_provenance_correction.py`仅追加R024原始文件分类更正，保留原74项声明、73项测量工件和既有判定。
- 原分块首层诊断：`development/t17_projection_stage.py`冻结源并执行Linux CPU、正常spawn检查；`t17_projection_start.py`仅启动已经独立审查的准确stage，`t17_projection_monitor.py <准确RID>`只读核对。`t17_projection_startup.py`／`t17_projection_runner.py`保留4096分块及原始精确输入，观察器只复制六类65行CPU张量；[说明](development/t17_projection_observe.md)记录实际PLE方法、GDN投影和坐标绑定。这是归因诊断，原T17接受门仍未通过。
- 采用实际parser的投影R029／batch57已独立封存诊断kept，91原始文件不变；[结果](plan/01_测试与调研/results/T17-E2-R029-diagnostic-T17_20261005.md)记录embedding相同、其余五类suffix投影不等和token index36分叉。`t17_projection_close.py`／`t17_projection_close_stage.py`保留准确收尾源，`t17_r029_panel_record.py`登记并核验8098回读；原T17 not_met保留。R027的[独立CPU复算](development/t17_r027_independent_cpu_review.md)与[修复选项](development/t17_numeric_repair_options.md)区分已测差异和待验证原因。
- HC上游诊断工具：`t17_hc_observe.py`／`t17_hc_startup.py`／`t17_hc_runner.py`在原4096分块中保留9类共同64行，原运算M保持3585／3649。R030已独立封存诊断kept，八处上游边界字节一致、首个GDN投影输出789字节不等；[结果](plan/01_测试与调研/results/T17-E2-R030-diagnostic-T17_20261005.md)保留98原始文件、四类恢复一致和index36分叉。`t17_hc_read.py`只读重算准确终态来源；[观察器](development/t17_hc_observe.md)和[集成说明](development/t17_hc_integration.md)保留协议，不授予原门或性能接受。
- HC准确收尾源为`t17_hc_close.py`／`t17_hc_close_stage.py`，先在私有副本运行D04 prepare，再写入真实轮次；[收尾说明](development/t17_hc_close.md)绑定终态、launch／bindings／初始monitor及独立CPU审计。`t17_r030_panel_record.py`登记并核验8098封存源回读。
- GDN单操作重放为`t17_hc_gemm_replay.py`／`t17_hc_gemm_execute.py`，由`t17_gemm_runner.py`持有并验证唯一GPU锁后调用实际TorchLinearKernel。`t17_gemm_stage.py`冻结LinuxCPU与真实权重／输入，`t17_gemm_launch.py`／`t17_gemm_start.py`绑定准确阶段，`t17_gemm_monitor.py`／`t17_gemm_read.py`只读核验。R031已独立封存诊断kept：M3585复现暖输出，M3649／4096复现冷输出，三重复均一致；完整M的其余行显式补零。见[结果](plan/01_测试与调研/results/T17-E2-R031-diagnostic-T17_20261005.md)、[准备](development/t17_hc_gemm_replay.md)、[执行](development/t17_hc_gemm_execute.md)。`t17_gemm_close.py`／`t17_gemm_close_stage.py`以`serve:none`封存，`t17_r031_panel_record.py`验证看板登记；R023历史not_met保留，新T17依[总负责人任务书](plan/PLAN_20261005_重新规划.md)执行。
- R026 / batch54因观察器误认PLE层初始化失败，已封存`failed_harness`；[失败报告](plan/01_测试与调研/results/T17-E2-R026-diagnostic-T17_20261005.md)保留23份原始失败工件及派生元数据边界。准确收尾为`t17_r026_failed_close.py`／`t17_r026_failed_close_stage.py`；`t17_r026_panel_record.py`登记并核验API及持久化回读。成功测量收尾准备`t17_r026_close.py`不适用于该失败轮。
- R028也已封存`failed_harness`：[编号映射失败报告](plan/01_测试与调研/results/T17-E2-R028-diagnostic-T17_20261005.md)区分一基HF id2和零基decoder1。`t17_r028_failed_close.py`／`t17_r028_failed_close_stage.py`保留23原始文件、19运行来源和实际parser；`t17_r028_panel_record.py`核验看板登记。`t17_ple_index_correction.py`仅向R026追加编号解释更正，保留旧声明和失败判定。
- `development/quality_regrade_20261004/panel_record.py`已登记规范离线重判并核对8098持久化读回；[最终独立复核](development/quality_regrade_20261004/independent_final_review.md)记录180条CPU重现及最终追加驱动器未冻结的溯源缺口，原始回答和评分字段保留。
- `development/p1_snapshot_prepare.py`／[准备协议](development/p1_snapshot_prepare.md)只检查未来非零快照证据声明的结构和关联；11项CPU测试通过。它不读取或证明原始回执、基线接受或实际GPU执行。R008六个历史计数均为零，仍缺正对照；实际验证等待接受后的E2-base.1及准确来源绑定。
- P1 保留工件检查：`python development/p1_snapshot_evidence.py --packet <packet.json> --evidence-root <目录>`实际读取并核对声明文件的SHA、receipt内容和UID／槽关系；[文件契约](development/p1_snapshot_evidence.md)明确其不证明GPU或进程来源。冻结Linux CPU回执`p1_snapshot_evidence_cpu_receipt.json`记录19 PASS，含实际symlink负对照。
- D0 对账工具：依次运行 `development/d0_decode_inventory_20261004.py`、`d0_decode_inputs_20261004.py`、`d0_decode_source_20261004.py` 和 `d0_decode_reconcile_20261004.py`，只读历史工件、保存选择性 CPU 证据并核验两个 manifest。独立复核通过；[结果](plan/01_测试与调研/results/D0-decode-reconciliation_20261004.md)保留 −3.5% 与 −10% 的协议差异及因果边界，门解码值禁止性能引用。
- 规范质量判卷与离线重判：`development/quality_regrade_20261004/regrade.py`／`stage.py`绑定判卷器、语料、输入和逐题来源，CPU重判保留历史工件。`close_stage.py --receipt close_cpu_receipt_r2.json --close`使用冻结闭包；`close.py`／`publication.py`通过身份journal、flock及Linux `renameat2(RENAME_NOREPLACE)`同步标准并追加E0更正，中断后先读回实际状态。`test_regrade.py`、`test_benchmark_standard.py`、`test_publication.py`覆盖判分与并发恢复。共享 `_shared/benchmark_client.py` 直接调用校验后的规范判卷器，逐题和汇总写入判卷器／语料／客户端SHA；生成预算仍为768。历史内置 `grade_response` 不作为新轮次计分路径。 `finalize.py`只通过冻结D04工具追加独立审核与离线分析kept判定，初次pending快照和原manifest保留；[结果](plan/01_测试与调研/results/T08-E2-R009-regrade_20261004.md)。
- R024 D07收尾：`development/t16_r024_d04_close.sh`及 `{inspect,evidence,verify}.sh`保留准确本轮审核／D04封存入口；只证明父D06与候选D07默认四臂等价，不代替T17、G3/G4或T06。
- [判卷器独立复核](development/evaluator_canonical_review.md)：同一 E0 corpus/answers 下，当前可取的 `250e197f` 与 `39f10fa8` 均重判 47/60；历史 raw 38/60 的实际计分源码未完整 pin，不能把分数变化归因于这两个文件的 diff。规范化实现由现有 `development/quality_regrade_20261004/` 主线 lane 完成。
- `development/t10_d14_prepare.py` / `t10_d14_prepare.md`锁定R017三进程×12轮及实际双trace/runner/probe哈希；SSH9已刷新36/36冷冷、36/36热热、3/36冷热相同的历史口径。此工具只CPU准备，不分配RID或启动GPU。`refresh_r023_status.py`将已封存R023与新准备证据按行合并到计划/状态；历史`refresh_plan_status_20261004.py`不再用于当前状态。
- `development/t16_r022_review.py`、`t16_r022_close.py`、`t16_r022_close_stage.py` 用准确R022原始数据复算并D04收尾；[R022结果](plan/01_测试与调研/results/T16-E2-R022-gate-D14_20261004.md)记录kept及未完成的T17边界。`refresh_plan_status_20261004.py` 将本次已验证回执合并到本地计划看板，重跑前须核对状态是否仍适用。
- `development/ftd_release_20261004.py`、`p0_release_stage.py`、`p0_release_apply.py` 已发布 FTD-20261004-1；[发布结果](plan/01_测试与调研/results/T01-FTD-20261004-1_20261004.md)记录两端相同清单 SHA。D04 正式判定和输出子结论分开，受 D14 影响的输出保持 hypothesis。
- `development/p0_r013_refresh.py` 在服务器 CPU 只读重算已封存 R013 的分叉分类及 token-0 top-2 logits；只保留本地小型摘要，不启动 GPU 或上传原始张量。
- `development/d01_gpu_selfcheck.py` 是开发自检脚本，只写 `/data2/FreeToken/runs/dev_D01/`，检查工作树、端口、显存、单写者与 GPU 锁后启动自己的服务；通过 `/health.status=ok` 等待模型就绪。自检读数不作 01 正式验收数据。
- GPU 开发自检：冷 13 消息请求开/关切段为 2 / 1 段，12 轮 `cached_tokens` 逐轮相同；两臂成功解码快照计数都为 0，快照覆盖缺非零正对照，T16/T03 仍待执行。自检已停止并清除自有锁。
- D00 最终 `E2-base@23f2e2c` 已集成D01/D02，通过T16-D00和T00基线立项，已用于后续GPU业务测试。D01的T16及T03已复核封存；T03成功快照计数仍全零，保留非零覆盖缺口。交付详情见 [D00/D01 交付记录](plan/02_开发任务/D00-D01_交付记录_20261003.md)。
- D02 在 `development/e2d02/` 独立分支 `exp/e1-ms` 开发，服务器对应 `/data2/FreeToken/wt/e1ms/`；继承 D01 交付树及 `E2-pre`，同步使用 Git bundle。`development/d02_gpu_selfcheck.py` 只写 `runs/dev_D02/`，用于两请求并发、末段即时落盘、ABAB 开销和时间线开发自检。
- D02 已交付 `23f2e2c`，目标测试 33 passed，回归 414 passed / 2 known failed / 1 skipped；两开启臂的预填执行日志与记录均为 4/4，时间线 8 步 × 48 层通过分析，D0 ABAB 开销约 2.40%。正式T16-D02已独立复核并封存，T05依赖D06，尚未执行业务验收。详情见 [D02 交付记录](plan/02_开发任务/D02_交付记录_20261004.md)。

### D02 开发埋点

`FT_DEV_D0=1` 开启预填及逐步解码记录；默认关闭。`FT_DEV_D0_PATH=<目录>/d0` 生成 `d0_prefill.jsonl`、`d0_decode_steps.jsonl` 和原有两秒聚合 `d0_decode.json`。预填在真实批次计算完成处同步落盘，包含调度时冻结的请求编号、段原因及墙钟 `t_start/t_end`。逐步解码的缺失数来自累计计数器差值，H2D 字节为实际取回专家行数乘完整权重 bank 行大小；CUDA Graph padding 产生的执行量包含在计数内，`bs/rids` 仅标识真实请求，必要时另给 `padded_bs`。

同时设置 `FT_DEV_D0_TIMELINE=1` 时关闭 CUDA Graph，日志打印 `D0 TIMELINE: cuda graph disabled`；前 `FT_DEV_D0_TIMELINE_STEPS` 个真实解码步落盘，默认 200。CUDA 时间戳为相对本步起点的毫秒，墙钟 `t` 用于客户端对齐。每层 `compute_scope=gpu_experts` 指 GPU 专家计算（hybrid CPU 服务时间由 D08 单独测量）；`cpu_stream_wait_and_result` 指 CPU 层的 CUDA 流提交、等待与结果搬运包络。时间线模式吞吐不能作为性能数。聚合增加 `sm_clock_mhz`，查询失败为 null。

## 结果归档

- `RESULTS_E1_20261003.md` — **第 1 代（epoch 1，基线换到 `origin/main d3512b4`）轮次记录**：`dev/d-series-clean`(`40fd5d4`) = d3512b4 + D 系列 21 提交 + 开关默认值修复；`exp/e1r001b-pr578`(`80943fd`) = 基线 + 上游 #578。E1-R001 `kept`：**层优先冷 32K 首 token 13.86 → 6.49 s（−52%），过了 D1 一直未过的 ≤9 s 门**，解码不变、跨树输出逐字符全等、不引入新失败测试；4096 分块路径只 −2%（搬运主导）。含 CRLF 回放坑、忠实性 211 行残差核对、首枪 penalty 方法学结论、以及 `tests/scheduler` 由 18 failed → 2 failed/99 passed 的默认值修复。**不同代数字不连线**，本代比较以 E1-R000b 为父轮。
- `RESULTS_FT_COLD32K_20261002.md` — 冷 32K 首 token 测量（20261002）：首 token 21.32/21.52s（明显短于 ExLlama 48.7s），解码 37.13/37.91 tok/s。按判据生产锁定 FreeToken。原始 JSON 与服务日志在远端 `/data2/FreeToken/runs/cold32k_20261002/`。
- `RESULTS_FT_PAPER_HEADROOM_20261003.md` — 论文余量参数任务（20261003）：唯一保留 `--max-prefill-length 8192`（首 token 13.01/12.90s，解码持平 37.29）；NUMA 重绑 / 16384 块（OOM）/ 专家槽扩容均不保留；88.33% 质量门因判卷器漂移失真（8192 与 4096 的 60 题响应逐字一致、同判 78.33%），未宣称替换生产。工件在远端 `/data2/FreeToken/runs/paper_headroom_20261003/`。
- `RESULTS_DEV_D0_20261003.md` — 开发 D0 埋点交付：分支 `dev/d0-instrumentation`（远端 `/data2/FreeToken/src/FreeToken`），开关 `FT_DEV_D0=1`（默认关）。实测每预填块 H2D ≈ 整个专家池 63.46 GiB（命中仅 7.7%）、copy 2.64s ≫ compute 1.21s——D1 层优先前提成立。
- `RESULTS_DEV_D1_20261003.md` — D1 层优先长预填交付：分支 `dev/d0-instrumentation`，开关 `--prefill-layer-major`（默认关）。冷 32K 首 token **12.66 / 12.98 s**（基线 21.52，−40~−41%；早期带 `FT_DEV_D0` 仪表的两轮为 13.91/13.14），解码 38.25 不降，64K 无 OOM，并发字间隔 16.7s 优于基线 20.4s；与基线重放输出逐位一致（127/127 token）。未达 ≤9s 点估计（计算流成新瓶颈），默认关闭。
- `RESULTS_DEV_D3_20261003.md` — D3 多锚检查点：第一步已实施（锚点集合匹配 + 预填锚封顶，commit `e92fdf5`/`cd450be`），**验收未达标（NOT MET）**。⚠ 这两个改动挂在 `config.special_token_ckpt` 上，而生产命令就带 `--enable-special-token-ckpt`（`runs/cold32k_20261002/SERVE_CMD.txt`），所以它们**不是默认关闭**；「生产未动」未经 A/B 证实。另有一处缺陷：`scheduler.py:150` 无条件读 `d3_extra_anchor_ids`（只在 ckpt 分支赋值），不带该 flag 启动会在 `Scheduler.__init__` 抛 `AttributeError`。回放：中途编辑轮 8.14s、零复用（不过 ≤4s 门）；整段重发 2.69s、命中 13120 只证明前缀匹配，不证明恢复状态正确。机制问题与顺序见 `DEV_NEXT_D3_20261003.md`（修订版：层优先下整段元数据先翻转真实 req 的 ping-pong 指针、子块代理冻结该指针致所有边界快照写同一槽）。

## scripts/

### 2026-10-05 任务书审查与开发分配

本轮先由独立Agent只读检查，再分配文件职责，见 [检查和分配记录](development/PLAN_AUDIT_ASSIGNMENT_20261005.md)。Strata已测试，不重复T19。
`development/resume_r032_close_20261005.py` 复用冻结的R032复核及D04收尾，已执行成功；再次执行会拒绝覆盖已封存轮次。
`development/t17_continuation_stage.py` 是新版T17工具链的Linux CPU冻结/自检入口，明确不启动GPU。冻结 stage `continuation_cpu_a914a2a85e0d` 已通过36项回归、实际CPU spawn、历史只读重放及28组输入预检，并获独立Agent复核；这些证据不授予T17接受。
`t17_continuation_launch.py` 校验冻结源码、模板、独立复核、R032封存绑定与实际资源，默认仅预检；`t17_continuation_dispatch.py` 以明确RID/stage/review启动，重复调用拒绝既有回执。R033/b61因标量字节观察缺陷已封存failed_harness，5968原始文件不变。修复stage `continuation_cpu_7037a8b76a91` 通过41项Linux检查及独立复核，R034/b62因重复调用比较缺陷已封存failed_harness（2039原文件不变），R034a/b63已通过47项Linux CPU检查及独立复核，按已分配编号字母补测规则实测中；`t17_continuation_monitor.py --rid E2-R034`只读跟踪准确进程身份。
`t17_continuation_review.py`从本轮归档工具与原始endpoint/D0/state/operator证据独立复算；`t17_continuation_close.py`经冻结Linux CPU及独立审查后执行D04收尾，保留原始工件与追加历史，默认仅audit-first。对应`*_review_stage.py`与`*_close_stage.py`只进行CPU冻结/测试；关闭器中的audit SHA需绑定该轮独立回执。T17测量及独立数据复核仍待完成，D17尚未获准集成。

- `state_envelope.py --ref <dump> --test <dump> --out <csv> [--legal A:B]` — D03逐层相对L2/不等比例与合法重排包络；按角色匹配四类设备态，长度/角色/形状/类型不齐时报错。历史论文复现使用ref=B、test=A、显式 `--lengths 12416,14080,21568`；旧归档对新boundary用 `--kind-ref archive --kind-test boundary --lengths 12672` 并指定UID，未带层映射的历史态按张量索引对齐并标明。
- `logits_probe.py capture --base-url <url> --model <name> --prefix P.json --suffix X.json --dump <dir>` — D03固定原始token输入，先预热P，再测P+X；X为1–64个token，服务须启用 `FT_DEV_LOGITS_DUMP=<dir>`。`compare --recompute R --restore S --legal L --require-restore` 检查真实恢复证据、输入SHA/K/位置和完整状态，输出逐位置top1、top2间隔、KL和首个差异层；同臂双进程用 `compare --recompute A --peer B`。不定义容差门限。
- D03服务端只读边界：`FT_DEV_STATE_DUMP=<dir> FT_DEV_STATE_DUMP_AT=448,4544,8640,12672,14144,18240,21504`，从同一次GDN扫描及请求本身的PLE上下文取样。完整四角色收齐全部层才发布。D03诊断仅支持TP=1；未设置新环境变量时不创建诊断目录。候选代码与GPU验收进度见 `development/d03_design_notes.md`，尚不能宣称GPU门已通过。
- `round_json_append.py <dir> verdict|retract|add|check` — D04关闭后追加工具，验证当前文件与最新历史逐字节一致及完整SHA链；禁止改旧数值、删键、改列表中部和类型。`add --json` 的列表表示待追加尾部；判定/撤回需要角色、理由及证据。直接修改round.json的 `rev_*.py` 停用。追加及收尾工具已同步正式服务器并用于T10；比较标签版本待现有基线队列及D03门禁后发布。
- `round_close.sh <round-id> [--round-root <dir>]` — D04首次收尾：校验必需工件，生成v001历史和不含round/history的manifest，恢复全目录只读并打印manifest自身SHA；重复收尾拒绝。纯分析轮次声明 `serve="none"`。
- `d0_timeline_summary.py <jsonl> [--json]` — 只读分析 D02 解码 CUDA 时间线，输出每层拷贝/计算中位数、P90，以及逐步重叠比例和未覆盖时长。重叠按两类区间并集的交集除本步时长计算；“气泡”仅表示未被这些专家事件覆盖，可能包含 attention、routing、CPU 等待，不能等同 GPU 空闲。输入缺失、字段不全或 NaN/Infinity 会报错退出。服务器路径 `/data2/FreeToken/scripts/d0_timeline_summary.py`。
- `probe_ft_cold32k.py` — 冷 32K 首 token / 解码流式探针。构造口径与 `exllamav3/scripts/probe_32k_once.py` 的 `build_text` 一致（唯一 `Cold-prefix-<id>` 头），流式量 TTFT（首条正文 content 事件）与 `(n-1)/(t_last-t_first)` 解码速，校验 `cached_tokens=0`。用法：`python scripts/probe_ft_cold32k.py <cold_id> [target=32052] [max_tokens=128] [nothink]`；`nothink` 追加 `chat_template_kwargs.enable_thinking=false`（服务端模板默认思考模式会占满 128 token 预算导致无正文输出）。已同步至远端 `/data2/FreeToken/scripts/`。
- `_shared/probe_cold32k.py` — 上者的参数化通用版（llama.cpp 系 OpenAI 服务，cafe/ik 用）。
- `_shared/smoke_5.py` — 5 条短提示冒烟（中文/JSON/工具调用/代码/多轮）。
- `_shared/ft_paper_stats_sitecustomize.py` — 论文余量任务的进程内仪表注入（远端 `/data2/_shared/ft_hooks/sitecustomize.py`；仅 `FT_PAPER_STATS=1` 生效，已被分支内 D0 埋点取代，保留作后备）。
- `launch_qwen38_test.sh` — ⚠ 窗口参数写死 32768（`--max-seq-len-override` / `--kv-reserve-tokens`），长上下文任务不可原样使用，参见 `TEST_TASK_FT_COLD32K_TTFT_20261002.md`。
- `start_d3.sh` — D3 验收用启动脚本 = 生产参数（窗口三件套 49152）+ `--prefill-layer-major --enable-special-token-ckpt`，日志默认写到远端 `/data2/FreeToken/runs/dev_d3/serve_d3.log`。诊断开关（均默认关）：`FT_D3_ANCHOR_MODE=last|first`（锚封顶切块粒度）、`FT_D3_TREE_DUMP=1`（空闲时导出 radix 树各节点）、`FT_D3_TRACE=1`（每次 GDN 捐赠打印边界与捐赠后的树）。
- `d3_trace.py` — D3 多轮轨迹回放：R2_cold（冷）→ R1_warm（第 5 轮改长文本，与 R2 公共前缀 8756）→ R2_warm_anchors（换回 R2，测整段重发）。结果写 `/data2/FreeToken/runs/dev_d3/d3_trace.json`。⚠ 只有 3 轮且不含工具调用/思考，未达方案要求的 ≥10 轮真实 OpenCode 轨迹 —— 该缺口由 `agent_trace.py` 补，不要用本脚本过 ≤4 s 门。
- `agent_trace.py` — **真实 Agent 轨迹工装**（`generate` / `replay` / `compare`），补齐上面那个缺口。`generate` 让模型自己发 `tool_calls`、脚本在 `--root` 内**只读**真执行（`read_file` / `list_dir` / `search_code`，路径经 `realpath` 限制在 root 内、`grep` 走 `subprocess.run(argv, shell=False)` 不接受任意命令）并跑满 `--rounds`（默认 12），逐轮存"实际发出的那份 messages 快照" + `ttft_s` / `prompt_tokens` / `cached_tokens` / `recomputed_tokens` / 思考段长度。`replay` 逐轮重放前缀（temp 0、输出预算默认 `max_tokens=32`，可用 `FT_REPLAY_MAX_TOKENS` 覆盖 —— 32 片会被思考段吃满，`ttft_content_s` 取不到读数，判正文口径要给到 200），记 `ttft_any_s` 与 `ttft_content_s`，并按片存下输出用于前 32 token 比较。`compare` 是失败关闭的判定器：轮数 ≥10、含工具调用、含思考、两侧请求逐字节一致（`messages_sha`）、未编辑轮与 generate 一致、temp0 前 32 token 一致（整体与正文双口径）、编辑后首 token ≤4 s、可选 `--min-cached`；**含 `--dry-run` 数据一律强制 NOT MET**。注意：远端没有客户端可用的清缓存接口，"全量重算"只能靠**冷进程**另跑一次 replay（`--fresh-note` 区分），同进程内升序回放只有第一个请求才是真全量重算。
- `ft_probe_floor.py` / `ft_probe_floor2.py` — 首 token 地板探针。v4 发现「重算 1 个 token 也要 2.67 s」且三臂同值，与缓存量无关；`floor` 版按字符数（40/6000/20000）看长度相关性，但**它把首个 `data:` 事件（空的 role 增量）当成了 TTFT，读数不可用**，只留作对照；`floor2` 版分别记 `first_wire`（首个 SSE 事件）与 `first_real`（首个带正文/思考/工具增量的事件），并加「同提示连跑两趟（第二趟应全命中）」「带/不带 tools」「同样字符量拆成 12 条消息」三组对照。探针的 `total` 包含服务端 `[DONE]` 后连接未关的空等（≈3 s），不要当耗时读。
- `pass_queue_model.py` — 论文第 4.5 节的遍数排队与 PCIe 预算推算（纯本地，不连服务器）：泊松到达下「每请求一遍（M/D/1）」与「同一时刻合批」的首 token 均值/P95、预填占 PCIe 比例与解码余量，另输出 $L^*$、双路每路 30 tok/s 所需带宽、$f(n)$、盈亏点与冷启 ≤10 s 上限。常数取自轮次库（D=2.66 s、B_P=24.3 GB/s、每 token 未命中 0.292 GB）。用法：`python scripts/pass_queue_model.py`。
- `serve_args_diff.py` — 逐字段对比两份 serve.log 的 `Parsed arguments`（`ServerArgs` 解析行），打印差异键。**任何「只改一个参数」的 A/B 在出数前必须先跑它**：命令行没写的字段会从服务端默认值解析出来。实例：E1-R002 声称只改 `--moe-strategy`，实际两腿 `max_extend_tokens` 是 8192 vs 4096，导致 hybrid 白得了一个「首 token −48%」的假收益（该行已撤回）。已同步远端 `/data2/FreeToken/scripts/`。
- `state_eq.py` — 状态层比对器：读两个落盘目录（由 `exp/e1r003-statedump` 树上 `FT_DEV_STATE_DUMP` 守卫的钩子产出）的 `index.jsonl`，按**角色名**（`conv_states`/`recurrent_states`/`slot:ple_conv`/`slot:ple_ngram_ctx`）在同长度上逐元素比，先报「同长度多条 donate 的自差」当噪声基准，再逐长度报 max|Δ| 与是否逐位一致，并对 archive↔host 两侧 sha 做搬运保真检查。**两个必须记住的口径**：① 匹配不能按文件名 —— 文件名带每进程的 `seq` 计数器，跨臂按文件名比会「两侧没有同名张量」假失败；② bf16 张量到不了 numpy，全程 `torch.save`/`torch.load` 在 torch 里比。取不到 index、没有 donate 记录、形状不一致、两侧角色集不等，一律报错退出（失败关闭），不返回「看起来一致」。已同步远端同名路径。
- `stop_freetoken.sh` — 停止 FreeToken 服务。

## 生产启动命令（49152 窗口，20261002 实测用）

见远端 `/data2/FreeToken/runs/cold32k_20261002/SERVE_CMD.txt`（PLE `pinned`、`--max-seq-len-override 49152`、`--kv-reserve-tokens 49152`）。面板记录：`http://172.16.108.9:8098/api/benchmarks` 中 Qwen3.8-Flash-Next-NVFP4 / ft 行。

D16路径读取器增量 `b89ebf9` 已本地提交并同步专用 `/data2/FreeToken/wt/e2d16-readers`，Linux CPU36项及独立复核通过；两路/四路批槽、停靠、缓存、交错和D03分叉context诊断均保持不自动接受。实际捕获/全套服务路径仍待验证，详见 [D16交付记录](plan/02_开发任务/D16_交付记录_20261005.md)。


### 2026-10-05 D16 CPU工具与D17预集成

D16候选 `development/e2d16-readers@df8a742` 新增 `scripts/equiv_suite/sampler_capture.py`（显式实例观察器）、`retained_d03.py`/`retained_state.py`（固定原始工件与独立服务sidecar）。`development/d16_path_readers_stage.py` 使用显式模块范围冻结已有读取器；`development/d16_sampler_capture_stage.py` 明确增加观察器及状态读取器测试。62 Linux CPU检查与独立复核通过；所有结果admitted=false，真实服务接入/目标模型路径仍待测试。详细证据见 `plan/02_开发任务/D16_交付记录_20261005.md`。

按最新版PLAN §8，`development/e2base1`只做D17预集成，T17正式接受前不打标签；真实GPU batch63和冻结依赖不改。当前五目录diff非空，T20续算按28组准备。泳道C1/C2独立基于E2-base开发，D06/D07 G3/G4由02在GPU队列执行，T19已完成不重跑。


### D15 CPU验证封存

`python development/d15_cpu_stage.py --candidate <完整40位提交SHA>` 在服务器专属 `/data2/FreeToken/wt/e2d15` 中验证clean候选及实际导入，设置CUDA_VISIBLE_DEVICES为空，不启动服务/GPU任务。工具执行边界/专家profile CPU测试，完整保存argv、所有测试与conftest/代码源SHA、日志、候选和导入绑定，封存到独立 `/data2/FreeToken/runs/dev_D15/cpu_<commit>_verified_<sourceSHA>`（目录555/文件444）。输出 `cpu_validation.json` 的全报告SHA；测试日志SHA是另一字段，不能混称报告SHA。CPU通过不能替代T16/T21目标模型GPU验收。

`python development/d15_core_cpu_stage.py --candidate <完整40位提交SHA>` 冻结 D15 对共享 scheduler、kvcache、engine 与 Qwen4-exp 路径的 CPU-only 回归证据。它强制 `CUDA_VISIBLE_DEVICES=''`，验证 clean e2d15 worktree 的实际 `freetoken` 导入，并保存 `python/freetoken`、四个测试目录及 `tests/conftest.py` 的完整 Git blob/文件 SHA 清单。pytest 预期保留 rc=1 与两个已知 scheduler 失败；只有失败集、553 passed 与 110 skipped 都匹配不可变 23f2e2c 基线时，报告才给出 `PASS_NO_NEW_FAILURES`。stage 保存完整 JSON、报告 SHA 与源清单后递归封存为目录555/文件444；它不构成 GPU/T21 验收。


### D16 opt-in service capture and synchronization

D16 committed `bde6283c68c0ad153dcd727a14f631244819b535` adds the independent `scripts/equiv_suite/service_capture_startup.py` launcher and admission/delivery adapter. Its framework README documents opt-in variables and CPU budgets. `development/d16_service_capture_stage.py` freezes the complete 86-test CPU suite; `development/d16_service_sync_cpu.py` transfers reviewed Git commits to the dedicated D16/D17 server trees and freezes source, conftest, actual imports, argv and logs with CUDA disabled. Service launch and target-model GPU behavior remain unverified.


### Versioned continuation dry-plan CPU validation

`python development/t17_v2_cpu_stage.py` freezes the versioned T17/T20 selection and dry-plan surface together with the complete D16 CPU suite. Its separate readonly report binds actual e2base1 imports, candidate, tests/conftest, source bytes, argv and logs, with CUDA hidden. The current 99 checks do not validate the retained runtime lifecycle; `runtime_lifecycle_verified:false` prevents the new runner from admitting execution. Current T20 selection stays all28 until PLAN §8.3's R041 cold plus four-case bitwise continuation closure is implemented and verified. Five-directory Git diff is diagnostic. Existing batch63 sources remain immutable.

### R041 CPU evidence reader

development/d17_r041_bitwise.py is read-only and defaults to indeterminate until the accepted T17 closure, R041 cold gate, and all four raw cases bind 128 IDs, text, physical process identities, coordinates, and four restore-role byte hashes. It does not start GPU work.


R041 reader is diagnostic-only and never returns an admission verdict from summaries. It requires raw pinned receipts and role files, but accepted T17/R041 closures are absent; GPU integration remains unverified.

### D17 R041 T16 case preflight

`development/d17_gate_case.py` binds `E2-R041-gate-D17` to D17
`2396728f5f210b98bfde0b8ba3556e9cbc2b234f` and D14 control
`e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7`. It reuses the shared T16 default
environment and `cold_eq.py` argv, selects only the four PLAN §8.3 warm cases,
and requires a sealed accepted-T17 closure, matching independent review, and an
absent `/data2/_shared/gpu.lock`. Run
`plan/01_测试与调研/batches/batchNN_E2-R041_v2.sh E2-R041-gate-D17` with its
three required evidence environment variables. The script is preflight-only:
it cannot turn a cold probe into warm-restore evidence and needs a separately
frozen continuation executor before any GPU execution.

`development/d17_gpu_gate_runner.py` is the later execution adapter. Once its
separate frozen CPU-stage/review admission exists, it uses the retained common
T16 `Runner.run_arm` cold path plus `t17_d14_gpu.Run.service/request` for one
D14-control and one D17-candidate donor2/hit128 service for each of the four
cases. It retains raw endpoint/input/D0/dump/PID/compiled-extension/argv
evidence and only yields `measurements_pass_pending_independent_review` after
128 IDs, full text, and all four restored state roles match byte-for-byte.



### R041 raw restore diagnostics (not a gate)

`development/d17_r041_bitwise.py` uses externally SHA-pinned readonly manifests to read separate input/output/process/restore-state files. It validates source fields and compares CPU tensor byte views, preserving the distinction between +0 and -0. `python development/d17_r041_cpu_stage.py` freezes its focused positive and tamper tests in an independent no-CUDA stage. These diagnostics always return `indeterminate` and `admitted:false`; equal tensors and self-declared process files do not establish actual owned-service restore provenance, accepted T17, or R041 closure. This supersedes the earlier three-test draft; the formal R041 gate and T20 sample4 admission remain unimplemented.


### Isolated retained continuation lifecycle replay

`python development/t17_v2_retained_stage.py` copies the four completed R034a first-case arms to a separate immutable CPU fixture, verifies each original file before and after copying, and invokes `t17_v2_retained_replay.py` with CUDA hidden. It runs the retained continuation orchestration and raw/operator readers against the snapshots, with actual owned CPU subprocesses replacing model services. Success, request error and stop error scenarios validate cleanup and retention of the fixture lock while a child remains alive. The original model output belongs to R034a; CPU subprocess identity never proves a new model generation. Reports remain `fixture_only:true`, `admitted:false`, `runtime_lifecycle_verified:false`; they do not authorize GPU execution. The global GPU lock is checked unchanged.


### D17 CPU package and default cold gate correction

`python development/d17_gate_cpu_stage.py` now freezes the complete retained source package, generated exact-ID startup files and D17-focused tests on the Linux host, and checks every equiv_suite Python file against the actual D17 Git blob. Reports keep lifecycle admission false. The R041 adapter uses two default T16 cold arms under one process owner and calls the retained argument/output/business-sequence checks directly; it avoids the D0-only prefill comparison. T17 acceptance re-runs the canonical raw auditor and D04 history check. A complete adapter lifecycle replay and actual accepted T17 are still prerequisites for GPU execution. This supersedes the earlier four-arm/mock-only draft.


### D17 adapter synthetic CPU lifecycle

`development/d17_gate_cpu_replay.py` exercises the actual adapter with real owned CPU subprocesses and a fixture lock. The endpoint receipts and tiny state tensors are synthetic and are validated through the retained raw readers; all four planned case dimensions are used. Six scenarios cover success, cold/warm not_met, request failure, and cold/warm stop failure. Stop failures retain the fixture lock until the owned child is recovered. The wrapper also checks the actual imported native binaries across worktrees by SHA while preserving their distinct origins. Reports remain fixture-only and do not authorize GPU execution or count as target-model evidence.


### Owned cold-helper package

`development/d17_frozen_helpers.py` freezes and validates the four original T16 probe tools. The cold entrypoint preloads its probe dependency from the owned raw archive, so the legacy script's live-path insertion cannot select another helper. Both the retained protocol and Runner globals use that archive. The old probe version comes from D18's SHA-pinned pre-update artifact, preserving T16's original MD5 contract while leaving D18's current live client intact. The formal and CPU-fixture entrypoints share the four-case context normalizer. These source checks do not establish target-model/GPU acceptance.

The D17 case preflight now invokes the same sealed-helper validation as the retained executor. Missing or changed raw helpers reject before lock acquisition; direct regression tests cover both conditions. CPU source-package readiness and actual model/GPU acceptance remain separate claims.


### D17 source-startup review binding

`development/d17_source_admission.py --report <owned/source_tools/cpu_validation.json>` rechecks the sealed CPU source/output inventory, exact test and import logs, six owned CPU lifecycle scenarios, both Git worktrees and the retained helper archive. It leaves source startup and model admission false. After the actual independent R workflow reviews the package, `--review <external/review.json> --review-sha256 <R-delivered SHA>` also requires a sealed external review directory and exact report/commit/scope bindings. The caller-supplied digest pins the reviewed bytes; the reviewer label describes provenance and does not authenticate independence. The GPU adapter requires the same pin via `--source-review-sha256`. Successful review permits only owned test startup: accepted T17, the queue/lock, and real GPU results plus independent D04 closure remain separate prerequisites. Existing frozen CPU versions and running batch63 are preserved.


### Terminal R034a evidence preservation

`python development/t17_r034a_failure_snapshot.py` copies the complete terminal R034a tree into a new isolated artifact directory, verifies all source file identities and SHA before/after copying and again in a complete second source pass, archives batch63.log, and seals only the copied tree. It requires the exact batch/service processes and GPU lock to be absent. Snapshot PASS preserves evidence; it is neither a D04 closure nor a T17 acceptance or root-cause conclusion. Existing batch63 and its frozen dependencies are retained.


### Operator hash CPU optimization

`python development/t17_operator_hash_cpu_stage.py` freezes the observer and tests on host9 with CUDA hidden, runs real Torch parity tests, and benchmarks the complete legacy per-row hashes against one bulk uint8 wire-buffer export. Every selected row SHA and physical snapshot remains in the evidence contract. CPU benchmark speedups describe hashing only; they do not prove end-to-end GPU speed or resolution of the R034a timeout. Repaired code must enter a newly frozen, independently reviewed runner for a new allocated round.


### Reviewed T17 source-startup package

`python development/t17_startup_cpu_stage.py` creates a new package with the owned source archive, all equivalence readers, the original cold helpers, real Torch observer and source-admission tests, and three retained CPU lifecycle replays. The fixture bytes come from the separately sealed R034a first-case snapshot and do not represent new model generation. Its descriptor is `startup_cpu_report.json` beside `source_tools`; `development/t17_source_admission.py` revalidates the whole source/output inventory, raw fixture and actual CPU child receipts. A separately sealed, caller-SHA-pinned independent review may establish source readiness for one owned test startup. Runtime/model admission stays false. The v2 formal preflight rechecks this same review at execution; a `runtime_lifecycle_verified:true` boolean alone cannot authorize execution. Actual queue/RID/batch allocation and model acceptance still require their own evidence.


`python development/t17_r034a_close_clone.py` prepares a fresh mutable D04 closure copy from the independently rehashed full failure snapshot. It verifies every copied raw file against the pinned snapshot inventory and uses separate inodes. The original R034a directory and sealed snapshot remain intact. PREPARED means copied evidence only; an independently recomputed failed-harness audit, CPU-tested closer and canonical D04 checks must still close the new copy.

The next startup package also freezes the R035–R039 v3 launcher, batch template and launcher tests. The controller requires the pinned independent source review plus an independent launcher/template CPU review, checks live round/batch ledgers and preserves owned-process identity during receipt failure cleanup. It starts all 28 continuation cases with four ordinary cold envelopes; CPU source readiness remains separate from GPU/model acceptance.

The future R041 adapter archives each live warm server birth identity in an exclusive owned_process.json before donor/hit requests and rechecks it afterward. Its next frozen package and independent review are required before GPU use. The T20 sample4 reader is being bound to canonical D04 and raw responses/restore tensors; no summary passed flag or CPU package grants the exception.

D16's opt-in `development/d16_exact_service_startup.py` retains exact-ID requests and installs native scheduler capture in spawned workers. `python development/d16_exact_startup_cpu_stage.py` freezes a no-CUDA startup/HTTP regression package with a socket guard: only live fixture listeners are reachable, and port 8095 is always denied. The current package has 26 passing tests, including an actual CPU child installer probe and failure cleanup. `development/d16_native_process_collection.py` requires pinned independent execution-source review for queued model collection; its CPU-fixture branch requires the actual guard and explicit fixture client. Configure an independent `dev_D16` destination, explicit UID/generation list and capture budgets. See `development/D16_SERVICE_WIRING_20261005.md` and `development/R035_CPU_FIXTURE_INCIDENT_20261005.md` for evidence, incident scope, and remaining workloads. These CPU results do not authorize a model launch or grant a gate.

python development/t20_r041_cpu_stage.py freezes future R041/T20 readers and tests with real CPU Torch and CUDA hidden, preserving failed packages and the live GPU-lock identity. This fixture-only reader check grants neither sample4 permission nor runtime/model admission. Current R035 remains isolated in its earlier frozen source package.

The D16 workload collector calls a partially bound retained exact_id_request client, requires explicit native observations_path, archives terminal UID/input SHA receipts exclusively and retains failures. Concurrent dispatch remains diagnostic: the serial UID observation reader does not prove physical batch slots, parking or interleave. Future R041 --run additionally requires --candidate-tag pointing exactly to the accepted integration candidate; no tag is created before T17 acceptance.

Future R041/T20 raw-reader CPU freeze `t20_r041_reader_cpu_f9887b2f0459` completed 30 tests on Linux with Torch and CUDA hidden (report SHA `f9db0af6dd6632817bbbf49b3ca219b222051433bc6261252396cff1629a5cbb`). The byte readers now handle singleton views with nonunit stride via a fresh flat allocation, retaining exact dtype/shape/NaN payload/signed-zero semantics. This is fixture-only source evidence pending independent review; it grants neither R041 closure nor T20 sample4 permission. R035 frozen sources remain unchanged.

D17 preintegration now uses `b9c9248` with the opt-in D16 scheduler-batch observer, verified by 93 dedicated-tree CPU checks plus 52 gate-tool checks and six real CPU-child lifecycle fixtures. `python development/d17_batch_observer_sync_cpu.py` preserves the local-commit→bundle→dedicated-tree flow and archives its invoker/source/program. The source package is pending independent review; T17 acceptance/tag/R041/T20 remain separate. Details: [D17 observer preintegration](development/D17_OBSERVER_PREINTEGRATION_20261005.md).

PLAN §8.6 intervention supersedes earlier future-reader/package instructions above: before formal T17 acceptance, do not create new future readers, verifier packages, fixtures, or failure snapshots/clones. Existing artifacts remain preserved.

The actual T20 component `plan/01_测试与调研/batches/t20_measurements.py` reuses the existing cold/performance/checkpoint probes and quality/replay parsers. It provides an owned candidate production-service scope and items 1–4/6–7 orchestration, with the enclosing batch responsible for formal admission and lock acquisition. CPU socket-guard import checks passed; no model/client execution has been performed. D16 item 5, full batch launcher, Linux lifecycle validation, and formal acceptance remain pending. See `development/D17_BATCH_HANDOFF_20261005.md`.

D16 existing test startup supports explicit FT_D16_PARK_RESTORE=1 and FT_D16_CACHE_INIT=cold|warm; both are disabled by default. Native host restore retains four-state raw tensors; expert priming uses native cache transfers with zero warmup requests. Existing d16_native_process_collection.py now provides four-process parking and cache comparisons under the owned lifecycle. Windows guard checks: 29 PASS/9 platform or Torch skips; server CPU checks cover state transport/initialization only. Actual GPU parity, interleave, full T20 integration and round-end independent review remain required. Current R038 sealed sources are unchanged; see development/D16_SERVICE_WIRING_20261005.md.

D16 collection also accepts interleave=True for one short decode input and one >4096-token prefill input. It starts the long request after native short-query decode evidence and requires mixed scheduler geometry to match between repeated processes. The opt-in D16 startup retains both admitted prompt SHA and growing live-input SHA in scheduler captures. Current CPU guard regression: 34 PASS/9 platform or Torch skips; actual interleave/envelope acceptance remains pending GPU and independent raw review.

T20 full measurement composition is now present in t20_measurements.run_full_measurements, including native D16 batch, parking, cache and interleave components. The retained continuation lifecycle provides a T20-only after_cases hook inside its original lock/cleanup scope. Guard regressions: 59 PASS/14 platform or Torch skips. CLI/source-review wiring and actual Linux/GPU lifecycle remain pending; no full R040 startup or acceptance is claimed. Existing R038 sealed sources stay unchanged.

Full T20 entry is plan/01_测试与调研/batches/batchNN_E2-R040.sh (ASSIGNED_BATCH check|run). It requires the existing D16 startup review/SHA and binds full measurement sources into the actual source inventory. CPU guard checks: 65 PASS/14 platform or Torch skips; Bash syntax passed on host9. The actual candidate-bound T20 source package, formal T17/R041 acceptance, independent prelaunch review and Linux/GPU execution remain pending. The a9 T17 source package must not substitute for the 0aa T20 candidate package.

R041 来源准备：development/d17_gate_cpu_stage.py 已绑定 0aa23431/a9dca443 专属工作树并归档实际批次模板；CPU guard 单独放在 cpu_guard 下，仅 CPU 检查启用。尚待 T17 接受、候选标签与实际启动复核；见 development/D17_BATCH_HANDOFF_20261005.md。

R041 入口 --source-cpu-stage 接受来源包目录，实际校验报告为该目录下 source_tools/cpu_validation.json；外部复核回执及 SHA 仍必须提供。相关准备记录见 development/D17_BATCH_HANDOFF_20261005.md。


T20 现有测量函数现保存与 E2-R009 规范重判47/60的逐题变化及长多轮题清单；历史重判文件纳入来源SHA核对。CPU检查不代表新候选质量接受，正式GPU及余下历史对比仍待队列。详见 development/D17_BATCH_HANDOFF_20261005.md。

T20 现有测量函数同时记录与E2-R009三趟Agent回放的逐轮输出分叉；先核对同参数及同请求摘要，位置采用字符/工具列表索引。历史性能偏差报告仍待接通，正式接受仍由轮末复核与总负责人判定。

T20现有生产测量函数已增加T00五项及E2-R009冷32K历史性能比较：首枪不混入中位数，输出偏差及7%观察；token负载不一致则不给达标判定，窗口差异单列。与逐题/回放比较合计18项CPU检查通过，仍未启动正式T20或取得GPU接受。

R038 实际 D04 封存编排为 development/r038_actual_d04_close_20261006.py，仅适用于候选 a9dca443 的本轮 14＋14 结果。它核对独立汇总、R036 沿用许可、R037 封存与服务退出，调用现有 canonical round_close.py / round_json_append.py，封存后复验原始 SHA、manifest、历史链及只读状态；不启动模型、不连接服务，不修改冻结脚本或原始输入。执行与结论见 plan/01_测试与调研/results/T17-E2-R038_20261006.md。

2026-10-06：T17 续算机制门已通过（R036沿用14＋R038新测14），R038 D04 kept且146681份原始文件SHA、manifest、历史链、只读复验通过。最终证据见 plan/01_测试与调研/results/T17-E2-R038_20261006.md；R041/T20仍待实际执行与独立接受。


R041实际准入现支持PLAN§8.7的受外部接受SHA约束的14＋14汇总，并保留D04/history及逐组绑定核验；不重复T17状态复算。实际来源包 d17_gate_cpu_0e33a49343a0 的Linux61CPU检查与6生命周期场景通过；候选标签 E2-base.1@0aa23431 已同步。独立启动前复核和GPU实测仍待完成；详见 development/D17_BATCH_HANDOFF_20261005.md。


R041已用现有原子分配器从 development/d17_r041_actual_launch_20261006.py 启动为batch68，真实准入通过后取得GPU锁；来源/回执/输入原字节归档62份。正式测量、轮末独立复核与D04接受仍待完成，详见 plan/01_测试与调研/results/T16-E2-R041-gate-D17_20261006.md。T20抽样遵循PLAN§8.3用户13:35新裁定，五目录diff为诊断项。

T20 sample4读取器已适配R041实际warm参照a9，原始输入origin=e45保持不变并核对封存来源绑定；Linux CPU专项19 PASS，详细记录见 development/D17_BATCH_HANDOFF_20261005.md。R041/T20 GPU接受仍待。

T20启动准备复用 development/t17_startup_cpu_stage.py --run-kind t20 和独立来源准入profile；本地51项检查通过，实际Linux来源包bf8db29bad11仍在验证，尚不授权GPU启动。进度见development/D17_BATCH_HANDOFF_20261005.md。

T20来源包bf8db29bad11 Linux253PASS及3生命周期通过；D16同字节启动包5de0e05bc692 CPU spawn＋60PASS，14执行依赖SHA匹配。来源准入仍待实际一次R复核及R041正式kept；详见development/D17_BATCH_HANDOFF_20261005.md。

T20实际queued启动入口 development/t20_actual_launch_20261006.py 已冻结，绑定source5d485bd933e4的254项Linux检查及3场景；missing R041 kept负测拒绝--run。独立R启动前来源复核进行中，正式R041结果/参数仍待，不提前启动R040。

R041实际D04入口 development/r041_actual_d04_close_20261006.py 要求真实controller结束、GPU锁释放、独立cold/4warm原始复核；live-controller负测拒绝封存。T20两份R来源回执已通过，正式R041封存及T20测量仍待。

R041实际封存使用development/r041_actual_d04_close_20261006_v2.py（冷臂实际文件契约修正）；D07预检与所属进程清理CPU11 PASS，D06同路径调整。T20 E2-R040/batch69已启动，实际状态见plan/01_测试与调研/results/T20-E2-R040_20261006.md，尚未接受。

队列后续工装：development/t05_e2_r045_prepare.py、t06_prepare.py与t06_seed_agent_trace.py；D06/D07开发自检工具已对齐raw结果与owned清理。Linux独立CPU包queued_tools_cpu_76d5d46399b5 23 PASS，报告SHA7a01770213138d6b5bf55eda65ddb71a1fbc83b479d1a7bc5a1f736f0cdd458b。GPU仍按PLAN串行；这些CPU结果不代替实际G3/G4/T05/T06验收。

### 2026-10-06 19:24:28 CST：队列工装纠正

T06按优先卡面使用四独立服务臂，D15训练仅G_seed12k/route；旧23项LinuxCPU包不证明新四臂协议。T05入口执行候选树检查；所属服务组清理失败保留GPU锁，前置消费真实D06自检与cleanup。当前T05/D06/D07/seed wrapper本地guard CPU21项通过，GPU门仍按PLAN队列。详见development/T05_HANDOFF_20261006.md与T06_HANDOFF_20261006.md。

2026-10-06 19:26:41 CST：Linux实际修正版 /data2/FreeToken/runs/dev_D07/queued_t05_t06_cpu_20261006_192603，T05/T06+网络guard共13 PASS，CUDA未初始化，OS exit0；cpu_validation.json SHA256 db3569d23d6c9ae36528b33deb98c57d0e7cb38728923fff159ede1bd04234d5，含实际源码逐文件SHA，源码与报告只读。仅CPU工装证明，非GPU/R准入/D04。旧Linux23包原字节保留。

2026-10-06 19:34:38 CST：后续启动前遵循19:30干预，D07 require_closed_round仅登记round/manifest SHA、只读stat、D04history；实际R041门0.112秒，Linux30 PASS。pin只在实际D04后登记于runs/plan_batches/closed_round_pins；T20当前无pin不可提前放行。详见development/D07_G3G4_HANDOFF_20261006.md。

2026-10-06：D07 G3/G4 `--run` 由原子 batch controller 启动；receipt 将 RID/batch/candidate/argv SHA 与 child PID/start_ticks 绑定后，child 才取得其自身 GPU 锁。默认 CPU 预检不分配 batch；详见 `development/D07_G3G4_HANDOFF_20261006.md`。

2026-10-06：D07 原子启动链 Linux CPU 17 PASS，报告 `runs/dev_D07/d07_atomic_cpu_20261006_2010/report.json` SHA256 `03f45024a64ec2ddf642643cdc783cd8648803a9b01fbc369882be1d68ff5650`。这不是 GPU 自检或 D04 接受。

2026-10-06：T10 原子 controller/child receipt 链 Linux CPU 10 PASS，报告 `runs/dev_D07/t10_cpu_capture_20261006_1946/report.json` SHA256 `b1577cfcc2f719677ea9f11cb27f155c31783155382008bc8a2c56131774da5c`；仍未开始 GPU 测量。

2026-10-06：新版本 E2-R046 合并 D07 G3/G4 与 T06 runner Linux CPU 7 PASS，报告 `runs/dev_D07/r046_cpu_20261006_211310/report.json` SHA256 `c360ea192125a65134dbd378600befe1fd4dcb153bc116e9bc82b6625edffab3`；待 R 启动前复核。

2026-10-06：新版本 E2-R045 合并 D06 G3/G4 与 T05 runner Linux CPU 12 PASS，报告 `runs/dev_D07/r045_cpu_20261006_211852/report.json` SHA256 `f63f6f017d4a96e32c515765c4ded749e7a2eb5b2252edf3c9976d78bde23d62`；待 R 启动前复核。
2026-10-06 19:59:05 CST：T20新启动来源44fbfb4f499d补齐e2_runtime独立导入，Linux254PASS/零跳过+三生命周期PASS；已封存前置轻门实测2.4秒。新v3启动器待一次R复核，详见development/D17_BATCH_HANDOFF_20261005.md。
2026-10-06 20:24:22 CST：T05原子批次预留与child回执绑定已接线；Linux联合38PASS含T05 12项与guard，实际T20锁未改变。详见development/T05_HANDOFF_20261006.md。
2026-10-06 20:27:50 CST：D07/T06/D06/T05原子预留与child回执补正Linux联合41PASS，报告f1cf4943，T20锁未改；详见development/T06_HANDOFF_20261006.md。

2026-10-06：T06 队列启动器在预留 batch 前拒绝外来 GPU 锁，锁检查覆盖符号链接；Linux CPU 6 项通过，详见 development/T06_HANDOFF_20261006.md。已封存前置继续仅核对登记 SHA、只读权限和 D04 history。

2026-10-06：T03b R047 工装已补全Linux controller/child预留回执、源码/输入审核绑定、六臂参数对照和失败清理保锁；Linux CPU20项通过，尚待队列前置和真实R启动复核。详见 development/T03B_TRIGGER_READ_20261006.md。

发布准备：development/RELEASE_NOTES_E2_DRAFT_20261006.md、DEPLOY_ROLLBACK_E2_DRAFT_20261006.md与plan/data_releases/E2_BASE1_RELEASE_DRAFT_20261006.json均为待T20封存及用户确认的草稿。跨框架_shared/ssh_exec.py仅读取FT_SSH_PASSWORD，缺失时连接前拒绝。

R052 T11第2阶段：development/r052_t11_followup_prepare.py与r052_t11_replay.py真实八轮重放后续问，原服务参数host32/ordinary4096，缓存字段不补零；Linux23PASS待R，见development/R052_HANDOFF_20261006.md。

R044新版叶子 development/t10_e2_r044_prepare.py 在任何batch/lock前要求R040 kept、R052 measured与固定封存review/pin（runs/dev_T10/reviews/E2-R044-v2），仅canonical ft_rounds输出；R017输入启动只查元数据，锁后绑定RO输入。Linux小CPU21PASS；未开展GPU验收。

R040a 的锚点补测使用 development/r040a_anchor_four_cell_v1.py：复用已固定 SHA 的历史计时探针，在计时外保存实际请求 bytes，并绑定只读输入 SHA。六个 OFF/ON 独立进程各保留一冷四暖测量，结论待独立原始复算；组件本身不分配 GPU 批次，须由已复核的 R040a owner 执行。CPU 自检不等于 GPU 放行。

R040a 后补入口现在使用新 d16_native_capture_shutdown_v3.py 与 d16_native_process_collection_v2.py，停车原始捕获经 d16_exact_service_startup_v4.py 保留四角色 raw index v2 和实际每角色 clear fill_value；独立 reader 逐位核验并交叉校验 PID/出生、UID/槽位、SHA/shape/dtype。旧冻结包保持原样；完整 Linux CPU 源包 55 PASS 与实际 owner 构造仅为启动前证据，不授权 GPU 或发布。

2026-10-07：R055 D06 暂停修复门使用 `development/r055_owned_launch.py` 的原子 controller/child；默认惰性且仅要求 R041 kept。其 GPU 阶段会绑定 eff 原生回执、T16 两种预填比较与动态端口 pause/cancel/recovery smoke。Linux CPU 13 PASS：`runs/dev_D07/r055_gate_cpu_20261007_025601/report.json` SHA256 `445ac2ec4715cc7a693f59667756caca10a1ff1e768cc7cedbbcf19dce394fba`；仍待独立 R 启动复核，不构成 GPU 验收。

2026-10-07 第七节更新：生产与 T17/R041/R040 已测证据继续绑定 0aa。eff 是暂停测量树；D08/D15 已 rebase，R046a 仅补 ON/G4/T06、保留原 OFF，T21 画像改取 R046a。新 `development/t16_private_port_base_runner.py` 给 R050/R051 使用动态私有端口并核所属进程出生/PGID；冻结原 runner 不修改。队列工装 Linux 93 PASS 证据见 `development/MEASUREMENT_QUEUE_CPU_20261007.md`，原因矩阵见 `development/BATCH71_CAUSE_CPU_20261007.md`。上面的早期 R055 13 项 CPU 包没有证明冷四态采集和真实取消链，不能用于当前启动；R055 工装修复后的独立 R 启动复核仍待完成。R044 现接受已裁定的 R040 failed_harness，R047 前置画像轮次为 R046a measured。

2026-10-07 第八节更新：R050 冷请求门不依赖暂停门，先执行；R040a 使用发布树 0aa。每批在拿锁前必须以最终封存脚本、实际服务器路径和用户完成全部文件操作空跑，回执与源 SHA 经独立 R 绑定。R050/R051 新 `development/t16_private_port_dryrun_base_v2.py` 在实际四臂文件准备后、创建服务前返回；`r050_r051_owned_launch.py --dry-run --card D15` 不分配 batch、取锁或创建正式轮次目录。R050 的 v5 封存包已通过 Linux 49 项 CPU 回归、真实路径空跑和独立 R 启动复核，以 batch76 启动；这些启动证据不代替 T16 实测及 D04 判定。旧冻结源和失败轮次保持只读。

R055a（HANDOFF §8）使用只读 `runs/dev_R055/r055a_real_path_source_v1/r055a_owned_launch.py`；从 `/data2/FreeToken` 执行 `--dry-run` 与 `--run`，不覆盖旧 R055 工具。Linux CPU 19 PASS、旧实现用例 1 deselected；真实路径空跑六冷臂和 PAUSE_ON 已通过（04:57），回执只读、绑定脚本 SHA／uid／cwd，冻结源复制后显式可写再注入观察器。正式启动仍需 R 启动复核与前置 D04 封存，详见 `development/R055A_D06_DRY_RUN_HANDOFF_20261007.md`。

R051 新候选为 e2d08@8bf0ad3（父 effb996）；最终工装 `runs/dev_T16/r051_real_path_source_v1/r050_r051_owned_launch.py --card D08` 已绑定实际重编译 native SHA／大小及只读 provenance，Linux CPU50 PASS。新 native 全部静态／小几何 CPU11 PASS，trace 默认为关，不能替代 T16/T09 GPU门。正式启动还需真实路径 `--dry-run --card D08` 与独立 R；不会调用已封存 R050 的源包。卡D08 事件 trace 会扰动时间，T09 记录中须保留该标记。

2026-10-07 05:54：R050/batch76 已由独立 R 原始复算并 D04 kept。R055a/batch77 六冷臂逐位复算 PASS，但 PAUSE_ON CUDA OOM，整门 failed_harness；development/r055a_failed_actual_d04_close_20261007.py 已完成本轮实际只读封存与 D04 history 校验，补充原始复算只以追加历史绑定。失败报告见 plan/01_测试与调研/results/T16-E2-R055a-gate-D06_20261007.md。依据 HANDOFF §8.4 停止后续 GPU，待用户裁定仅补暂停链的建议；生产基线仍 0aa，未部署或推送。R049 最终 source_v1 Linux CPU33 PASS，仅为工装准备，实际空跑和 R 启动签字未完成。

2026-10-07 06:59：HANDOFF §9 生效。R051 新 source_v3 已验证真实入口仅依赖 R041 kept，Linux50 PASS、四臂真实空跑和独立 R 通过，batch78 于06:57取锁；结果状态见 plan/01_测试与调研/results/T16-E2-R051-gate-D08_20261007.md。R055b 仅补暂停链并在模型GPU进程内记显存；T06保留trace/pause，按实际余量选择仅T06的memory-ratio。尚无R051整轮/D04判定。

2026-10-07 07:14：R055b正式新源 r055b_gate_d06_prepare.py / r055b_owned_launch.py 已冻结为 runs/dev_R055/r055b_real_path_source_v1，实际Linux generated observer/file writer/失败拒绝10 PASS（报告9bca71af）。只补暂停链，GPU worker直接记录显存和峰值，保留R055a六冷臂的v2 D04绑定；真实空跑/R签字/GPU结果仍待。详见 development/R055B_PAUSE_RECOVERY_HANDOFF_20261007.md 顶部实际交付修订。旧callback模块不作正式启动证据。

2026-10-07 R055b：`development/r055b_owned_launch.py` 与 `r055b_gate_d06_prepare.py` 是只补暂停链的入口；冻结执行源为 `/data2/FreeToken/runs/dev_R055/r055b_real_path_source_v1`。CPU10/实际空跑/独立R签字后启动batch79；模型进程CUDA显存原始记录位于正式轮次PAUSE_ON，`r055b_actual_d04_close_20261007.py` 仅在该批终局与独立R复算PASS后原地D04封存。当前启动不代表kept，详见results/T16-E2-R055b-gate-D06_20261007.md。

R055b终局更新：batch79为failed_harness并原地D04只读封存；新局部草稿 `development/r055b_pause_harness_v2.py`（8项Linux CPU回归）修复HTTP504 timeout解析与真实UserMsg显存边界，未授权/未执行GPU重试。完整证据见 `plan/01_测试与调研/results/T16-E2-R055b-gate-D06_20261007.md`。


2026-10-07 14:40 §13执行更新：R057/b83已封存failed_harness，A/B保留，C端口工装失败、D未跑。R057a/R058新端口入口与CPU/FILEDRY证据见 development/R057A_R058_PORT_SAFE_HANDOFF_20261007.md；ft_batch_port_pair_v1.py仅为这两批预检API/TCPStore端口，非永久预留，补跑待确认及独立R签。普通T06客户端/真实Detokenize侧车见T06_ORDINARY_V2_HANDOFF_20261007.md；尚非GPU验收。

2026-10-07 14:59 新用户方向：route trace须保留layer-major分块，R057a四臂证据已齐、待独立R最终复核及D04；R058端口v2启动签已通过。现有容量准入源码结论见 [显存准入核查](development/GDN_96K_MEMORY_ADMISSION_DESIGN_20261007.md)，请求OOM隔离设计及未合入的CPU决策原型见 [OOM隔离设计](development/OOM_REQUEST_ISOLATION_DESIGN_20261007.md)。新显存排队暂不实现；实际生产恢复能力尚未验证。

2026-10-07 15:42 执行更新：R057a诊断已封存measured；[R058并发显存结果](plan/01_测试与调研/results/E2-R058_并发显存_20261007.md)三场景全部完成、0 OOM并独立D04闭合。D07 trace分块候选151ee已新提交，当前[T16 R059门](plan/01_测试与调研/results/T16-E2-R059-gate-D07_20261007.md)在跑；工装见development/R059_D07_T16_HANDOFF_20261007.md及冻结source_v2入口，不沿用v1失败空跑。普通会话证据由r046c_t06_ordinary_startup_v3.py、r046c_t06_ordinary_client_v3.py、r046c_ordinary_seed_driver.py与r046c_route_analyze_ordinary_v1.py组成，完整R046c工装尚在准备，CPU准备不等于GPU验收。OOM隔离原型仅决策层CPU验证，未实现产品worker恢复。全部任务完成后才提交发布审批。

2026-10-07 17:22 执行更新：D07 trace候选151ee的R059四臂均已完成128输出；root交接误写256致原v1 NOT_MET，现待用户裁定纠正复核，后续GPU未启动。R046c权限新v2冻结/Linux25PASS；[R049工装](development/R049_T21_ORDINARY_V2_HANDOFF_20261007.md)实际Linux22PASS、目标tokenizer与画像CPU检查、独立R预审已完成；R040a v6同入口36范围真实文件空跑完成、未起模型。新显存排队不实现；[OOM隔离设计及CPU原型](development/OOM_REQUEST_ISOLATION_DESIGN_20261007.md)未合入产品，实际服务恢复尚待批准后的验证。全部任务完成才申请发布。


### 2026-10-09 批准的生产测量与恢复工具

`development/r045_production_aiperf_20261009/` 保存现有481服务的四请求 AIPerf 测量、独审与原始证据；结果见 `development/R045_RESULT_20261009.md`。`development/r067c_short_tail_v1/` 保存独立10服务/14调用的CPU/FILEdry包，启动须root准入。`development/r067c_production_control_20261009/` 保存生产停止后恢复481和首次冷基准比较的工具，工装重试最多2次，not_met不重试；恢复冒烟失败回滚184。推送与Strata仍未批准。

### R067c 工装重试（2026-10-09）

- `development/r067c_retry1_short_tail_v1/` 与 `development/r067c_retry2_short_tail_v1/` 分别保留独立 CPU 包和准入证据，旧轮不改写。retry1 修正分段 prefill 几何；retry2 重算新 RID 的 argv 摘要，并在 GPU lock 前核验 10 臂目录、argv 与环境路径。
- 对应 `development/r067c_retry{1,2}_production_control_20261009/` 为 root 专属控制；共用原始 `ROOT_ATTEMPT_LEDGER.jsonl` 限制原轮加最多两次工装重试。恢复入口仍调用冻结 v8，逐次比较首次冷基准。`prepare_root_proof.py` 只做 CPU 校验；`launch_approved_r067c.py` 需要独审和 root 准入。
- `observe_overnight.py` 只读取既有健康监测、告警和进程归属，写观察证据；不生成请求或执行推送。
