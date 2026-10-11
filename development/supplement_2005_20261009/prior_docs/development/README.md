# FreeToken 本地开发与验证工装

2026-10-08 12:31：R049b/b108、R040f/b109均已D04 failed_harness封存；R051a/b110正执行第四臂。`e2d15-budget-guard/`隔离工作树的快照保护Linux40项通过（未提交、未纳入正式GPU候选）；`r048_t09_v12/`已把R049b改为失败历史绑定，真实数据前置为R051a kept；`r052_runtime_v8/`保留R045 measured前置，这两项绑定Linux6项通过。`r040g_d16_v1/`与`r049_t21_ordinary_v14/`仍为新重试准备，不能视为获准GPU包。当前授权以11:18记录及真实前置为准，下方“未批准”等旧时间记录只描述当时状态。

2026-10-08 11:32：R049b/b108运行中，P1完成请求组后进入PA1。R048b v12 / R052a v8仅恢复R049b / R045正常measured前置，6项本地定向检查及独立差异复核通过；真实前置与Linux/FILEdry/启动签仍分别待完成。五组GPU授权有效。

尾部工装更新（2026-10-08 10:59）：`r044_runtime_v6/` 与 `r047_runtime_v11/` 已Linux82项（含真实spawn双SIGTERM8项）通过；实际前置拒绝路径已核，无正式FILEdry或GPU启动。见 `TAIL_SHUTDOWN_CPU_HANDOFF_20261008.md`。

当前新增准备（2026-10-08 10:36）：`r051a_d08_runtime_v1/` 为76af D08新T16门（Linux29/FILEdry/R技术签）；`r048_t09_v11/` 为条件T09完整新轮（Linux64，待实际gate）；`r052_runtime_v7/` 为T11 one-shot SIGTERM完整新轮（Linux74/FILEdry/R签）。GPU批准均未取得。`d08_capture_trace_cpu_validate_v1.py` 记录专树/native复用与当前17CPU来源；`r052_b107_failed_close_v1.py` 已完成b107原地D04封存。具体范围和固定SHA见 `R048B_R051A_R052A_READY_FOR_USER_APPROVAL_20261008.md`。

当前状态以[问题清单](PROGRESS_AND_BLOCKERS_20261008.md)、[第十四节调度](SECTION14_EXECUTION_SPLIT_20261007.md)及协调日志最新时间为准。R048/b105已failed_harness封存；R048a/b106保留6条V0性能观测，诊断capture内同步失败，09:44退出，D04 v2经R审后于09:53:49完成只读封存。新增`r048a_b106_failed_close_v2.py`只归档此次真实失败，默认只预检；旧`r048_b105_failed_close_v1.py`与v9/v10源保持。新T09 GPU补跑需用户裁定；T11 v6源已本地40PASS/R审，封存后已开始远端验证。下方十三节及旧预算均为历史。

最新任务已转交接书第十三节：A/02准备R057/R058，谁先完成CPU→真实FILEDRY→R启动复核谁先进入GPU；两轮后R040a、修复+T16、R046c及余队列。普通4096恢复提案为历史未采用，旧19–34小时预算过期，须诊断后重估。R040a第十二节四组件完整Linux175PASS、R04553PASS+两selftest、R04826PASS、R044/R04748PASS的准备证据保留；改变队列依赖仍须新版本和正式启动复核，不能沿用旧签字。R按§8.6不提前复核CPU工具包。

本目录保存独立源码检出、开发工装源、小型验证摘要及服务器工件指针。原始测量、日志和张量留在服务器；轮次规则见 `../plan/00_规则_测试存储与数据版本.md`。

最新执行状态见[第十三节记录](SECTION13_EXECUTION_STATUS_20261007.md)和[T06 UID/ACK审计](T06_UID_BINDING_AUDIT_20261007.md)。下列旧提案与预算均为历史记录。

接管与此前准备：见[执行负责人交接](EXECUTION_LEAD_HANDOFF_20261007.md)。[R046b恢复提案](R046B_OOM_RECOVERY_PROPOSAL_20261007.md)已具体化为普通4096/.80/98304、完整seed、同配置OFF/ON方案，待用户裁定T06采集结构；未启动补轮。[R052缓存证据v4](R052_CACHE_EVIDENCE_FIX_20261007.md)已Windows/Linux各35 PASS，实际FILEDRY/R启动签字仍待完成。[独立剩余工期](REMAINING_WORK_ETA_20261007.md)只覆盖当前八批闭环，推荐路径批准后约19–34墙钟小时。

12:38终态更新：R046b/batch82在98,304/0.80下G3-on OOM，已原地D04封存`failed_harness`，保留独立复算的G3-off。G4/T06未执行，所属进程和本批次锁已清理。比例达到第十二节授权下限，GPU队列停止，R049及后续批次须等待用户裁定。[失败结果](../plan/01_测试与调研/results/T06-E2-R046b_20261007.md)与[执行记录](SECTION12_EXECUTION_STATUS_20261007.md)绑定原始证据；R056仍为`measured`，生产发布未获批准。

当前更新以交接书第十二节为准：新批次默认窗口98,304。R056（发布树0aa23431、0.88、不开D0）首排，随后R046b→R049→R048→R040a→R045→R052→R044→R047。R046b全部臂0.80，同配置重跑OFF；seed_real原样，提示超过96,256自然止轮。R049训练仅seed12k，性能0.88。新入口与观察器为 `r056_long_context_prepare.py` / `r056_performance_memory_observer.py`，CPU通过、真实路径空跑、R启动签字、实际GPU测量与D04分别记录，旧源签字不沿用。

R056/batch81已完成11/11，独立原始复算与D04复核通过，原地只读封存`measured`。真实完整首提示87,100，两次any-delta首token18.771/18.132秒；32K排首枪解码中位34.33 tok/s，较R040的38.30下降约10.4%。R040实际窗口73,728，比较只作跨窗口配置观察。两个87K请求后样本均383,451,136 bytes（约0.357GiB），不称连续显存最低值或R046b余量证明。原始API未报告cached_tokens，原客户端fallback0与后端冷prefill证据分别登记。route trace是CPU pinned快照，628MiB GPU分配因果暂未证明，发布后再用allocator snapshot核实。历史27项CPU/49,152超窗拒绝与§11冻结原件保留；下述旧版本记录只描述当时状态，当前授权见§12。

2026-10-04 本地核对：下列八个源码检出的已跟踪文件均无未提交改动。提交和源码是否与服务器一致，以对应交付记录、Git blob 清单及运行时 import binding 为准。

| 子目录 | 分支 | 当前提交 | 用途 |
|---|---|---|---|
| e2base | e2/base | 23f2e2c | 统一 E2-base 基线 |
| e2d01 | exp/e1r008-anchorcut | f91054b | D01 切段开关交付 |
| e2d02 | exp/e1-ms | 23f2e2c | D02 时间线与末段落盘交付 |
| e2d03 | exp/e1r003-statetools | c30ae0d | D03 状态及 token/logits 诊断候选 |
| e2d03-continuation | exp/e2d03-continuation | f5067bb | D03 普通分段恢复诊断修复候选 |
| e2d06 | exp/e2d06 | 0369263 | D06 多会话工装候选 |
| e2d07 | exp/e2d07 | fefb19c | D07 路由轨迹候选，父树 D06 |
| e2d14 | fix/e2-ngram-track | e4f3202 | P0 层优先快照及上下文修复候选 |
| e2d14-schedule | fix/e2-prefill-schedule-gate | e45e2c2 | 卡D14调度／新T17候选；父树e4f3202，Linux CPU 70 PASS，实际T16/T17尚待执行 |
| e2d16-tools | dev/e2-d16-suite | e9ee6aa | 卡D16续算工具；父e45e2c2，独立Linux CPU 31 PASS；不改正在R032测量的引擎候选 |

流程：本地开发及提交 → Git bundle 同步准确服务器 worktree → CPU 源绑定检查 → 冻结工装及真实数据只读重放 → 单写者 GPU 门 → 独立验收复算 → D04 封存。源码交付、CPU 通过、GPU 门、业务验收及正式判定各有自己的证据。

`remote.py <本地脚本.sh>` 规范化 UTF-8 和 LF，经 `ssh 9 bash -s` 执行并返回远端退出码。新增命令须登记到框架根 `README.md`。

D14 的 R022 默认 T16 已封存 kept；R023 T17 已封存 not_met。R025 同分块诊断已封存 kept，8192 前缀、8256 四角色和 128 个输出 token 均逐位一致；它使用 `FT_LM_CHUNK=7680` 并增加观察，不能替代原 4096 分块接受门。`python development/t17_matched_read.py E2-R025-diagnostic-T17` 只读复算原始张量和输出；监视入口核对冻结源、进程身份、锁和终止回执，不能触发重新启动。后续原分块诊断观察器见 [首层投影说明](t17_projection_observe.md)。

R026、R028 已封存 `failed_harness`，均在观察器安装阶段失败，未完成诊断请求。真实配置的 HF PLE `[2]` 经候选解析器转换为零基 decoder1；R026 的旧 decoder2 解释已追加更正，原失败文件和判定保留，见[失败报告](../plan/01_测试与调研/results/T17-E2-R026-diagnostic-T17_20261005.md)。R029 已独立封存诊断kept：embedding 一致、其余五类 suffix 投影不等、四类缓存恢复一致、token 在 index36 分叉。R030 已进一步独立封存诊断kept：共同64行的八处上游边界一致，仅GDN投影输出不等；真实叶回执为BF16 TorchLinearKernel。两轮均已终止、锁已释放、准确封存源8098回读通过，原T17 not_met保留。后续单操作重放显式补零，完整模型门仍待修复复测。P1 的两类准备验证器分别检查声明关系和显式留存文件，均不授予真实 GPU 覆盖或 P1 接受。

`.bundle`、`.tar`、`.tar.gz` 为传输包，由 `.gitignore` 排除；相关清单与小型 receipt 保留。已封存失败数据、旧提交对应检出和仍被验证引用的工具不得删除。新增源码检出应同时更新本表。

R031真实GDN算子重放已独立封存并登记：M3585复现R030暖输出，M3649／4096复现冷输出，12份输出三重复稳定，18份原始文件不变。使用真实共同64行，其他行显式补零；它是诊断证据，不是新T17接受。当前执行总负责人的[20261005权威任务书](../plan/PLAN_20261005_重新规划.md)：卡D14先交付默认关闭调度参数与D0结构字段，卡D16自动生成同结构冷参照，随后进行双进程参照稳定性和状态／输出硬门；R023历史判定不改写。

新默认路径 T16 入口为 `t16_d14_schedule_stage.py` → 冻结目录内 `t16_d14_schedule_launch.py --stage <目录>` 预检 → `--launch` 原子启动。声明适配器 `t16_d14_schedule_runner.py` 复用固定共同门，准确绑定 D18 新客户端及实际 CPU 日志；`tests/test_t16_d14_schedule_{runner,stage,launch}.py` 验证绑定、冻结和启动边界。工装 CPU 验证及新八臂实测是独立证据，旧R022不替代新候选门。


### 10-07 第十节工装更新

R055 门结束，R055a六冷臂默认路径证据保留，R055a/b failed_harness 封存不改。`r046a_d07_t06_prepare.py` 新版并入 `r055b_pause_harness_v2.py` 的有效504回执和真实UserMsg显存观察；T06按已封存数据估算比例0.80（route+pause保留、加载时实际余量至少1.5GiB），G3/G4保持0.88。实际执行源 `/data2/FreeToken/runs/dev_R046/r046a_real_path_source_v6`（源MANIFEST `4ef7031e42ded1283bc147ea3bd4e7da8dc6baf4c3cc5e943045f29748b97c7f`），Linux89 PASS、同入口真实路径空跑回执 `4c4aa768fcb894aded9042c2bc7600c4b74a3a6e7b82a25a7a3b8ad2c3885780`；正式启动须由独立R签本版。v5遗漏CPU测试用的冻结dry依赖而失败，v5原件保留，只在v6补该依赖，未起模型或分配正式批号。

`r040a_d16_supplement_prepare_v3.py`、`r040a_d16_dryrun_v2.py`、`r040a_d16_process_collection_v4.py`、`r040a_private_port_owner_v1.py`、`r040a_anchor_four_cell_v2.py` 为尚未冻结的R040a草稿。生产树引用统一为干净的 `/wt/e2base1-ordinary-rewind@0aa23431`，formal与file-only复用前Popen文件路径，所有请求绑定动态私有端口，原shutdown v3 / collector v2与生产参数保留。局部CPU回归与独立复核已通过，仍待最终Linux集成、真实路径空跑与启动签字，当前不占GPU、不优先于R046a。


R045第十节新版工装为本地v4草稿（`r045_d06_t05_prepare.py`、`d06_g3g4_prepare.py`）：D06 G3/G4实际接入严格504回执、真实UserMsg观察与完整暂停/取消/恢复；T05 P1/P2保留原入口及观测开销，所有比例0.88。`r045_section10_draft_v4/report.json` 为只读本地38 PASS与两self-test证据（SHA `f15d245b04930ea7e492ee57c03f2902cc933802d24f4aea578e7f9ced719c2c`）；尚待服务器CPU/真实路径空跑/独立R签字。目标dry `.dryrun_R045_section10_v4_E2-R045`，签字 `runs/dev_T05/reviews/E2-R045_section10_startup_review_v4.json`，旧冻结原件不覆盖。


10-07 第十节根集成：R040a 新私有端口入口的 Linux CPU 176/176 PASS，报告 `/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/report.json` SHA `a01c60ea2d0d89800ce42fe37c06ed34426472ab631ee3b173f4a1ef7af3c1be`；执行源码 `/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development` MANIFEST SHA `47ec23b87d12764083537591ecc556da0e25be1d99287314487c69cc47189b45`，只包含既有依赖代码和本次新工装、测试。真实路径空跑和独立 R 启动签字尚未执行。R048 Linux CPU 26 PASS 见 `t09_runner_notes.md`；R045 Linux CPU 38 PASS + 两项 self-test 见其 handoff。R046a/batch80 已起服务后 G3-on 0.88 OOM，当前 GPU 队列停止，不用以上 CPU 结果代替启动许可或模型验收。


2026-10-07 14:40 §13执行更新：R057/b83已封存failed_harness，A/B保留，C端口工装失败、D未跑。R057a/R058新端口入口与CPU/FILEDRY证据见 development/R057A_R058_PORT_SAFE_HANDOFF_20261007.md；ft_batch_port_pair_v1.py仅为这两批预检API/TCPStore端口，非永久预留，补跑待确认及独立R签。普通T06客户端/真实Detokenize侧车见T06_ORDINARY_V2_HANDOFF_20261007.md；尚非GPU验收。

2026-10-07 14:59 新用户方向：route trace须保留layer-major分块，R057a四臂证据已齐、待独立R最终复核及D04；R058端口v2启动签已通过。现有容量准入源码结论见 [显存准入核查](GDN_96K_MEMORY_ADMISSION_DESIGN_20261007.md)，请求OOM隔离设计及未合入的CPU决策原型见 [OOM隔离设计](OOM_REQUEST_ISOLATION_DESIGN_20261007.md)。新显存排队暂不实现；实际生产恢复能力尚未验证。

2026-10-07 17:22：R049 ordinary工装已由root接管，实际Linux22PASS（含spawn/SIGTERM）、目标tokenizer/画像CPU检查通过，独立R预审无P0；正式R046c前置、同路径FILEDRY与R启动签尚待。最新工具、依赖与证据见 [R049 handoff](R049_T21_ORDINARY_V2_HANDOFF_20261007.md)。R040a v6真实36范围文件空跑完成，无服务/锁/batch；见其私有owner handoff。R059因root误写256而v1 NOT_MET，权威128四臂逐位证据已齐，纠正待用户；旧封存不改，不发布/外推。
# R040h retry

The CPU-only [R040h D16 retry entry](r040h_d16_remaining_prepare_v1.py) prepares the retained-proof-gated warm2/interleave6 capsule; see [its README](R040H_D16_RETRY_README.md).
