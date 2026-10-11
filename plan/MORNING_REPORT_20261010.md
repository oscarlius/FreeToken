# 2026-10-10 当前证据早报

真实写入：2026-10-10T07:57:42.873861+08:00。按用户07:55修订立即出报，不等待09:00。早报等待程序已按精确PID/出生时间停止；原观察暂继续，首个CPU独审通过项目就绪后停481并如实截断。尚无最终观察终态。

| Round / scope | factual state | service / calls | boundary |
|---|---|---:|---|
| Old observer | TRUNCATED | 306 / 0 issues | 17:35:56–22:41:20; not an overnight pass |
| R067 original | user reclassified failed_harness | 3 / 7 | 6 hot valid |
| R047/T03b; R052a; R044 original | not_met; not_met; failed_harness | 6/24; 1/9; 1/0 | R052a cache13376 vs floor13504/full13554 |
| Strata S1; S2 original; S2 retry1 | valid subset; failed_harness; valid subset | 1/11; 1/0; 1/11 | S1 MTP OFF; S2retry1 MTP ON; parallel=1 queued |
| D09 original; R067 retry1; D09 retry1 | failed_harness; not_met; kept | 4/48; 4/8; 8/100 | R067 hot39/cold248046 A=B cold cache0; D09 default-off only |
| R047 diagnostic; Strata S3; D10 T16 | failed post-exec; valid subset; kept | 1/3; 1/11; 8/100 | R047 missing d0_decode/alignment3/mismatch60; S3 parallel=2, cap4 used |
| R044 retry1; retry2 | failed_harness; failed_harness | 1/24; 1/24 | retry1 missing19 intermediate captures; retry2 captureerror0+19 chunk receipts, strict args reader missing max_prefill_length; no third retry |
| D10 prototype formal | FAILED_HARNESS | 1/2 | completion TPS 5.855077/1.064367, outputs46/58; defective per-step cache reset; not evidence against D10; profiles1–3 not run |
| RESTORE481 smoke | passed | official SDK 2 prompts | 512/8257 each128, cache0; 17 fields match frozen first-cold baseline; no rollback184 |

## 新解释与下一轮

依照07:45主会话核查记录，R067d-retry1原formal not_met保持，但热种子512+7681与冷donor8193一段的切分不同，donate边界36层状态已不同；不能作为短尾机制/C3被否定的证据。retry2复刻真实种子切分，并先比较donor@P状态哈希，相异则failed_harness停止。

D10原formal FAILED_HARNESS保持；5.855077/1.064367来自每步清空lane缓存的缺陷原型，不能否定错相位重叠机制。持久化/ownership epoch修复后复测；论文/README/claim map同步更正。在R067retry2和D10复测出结果之前不出PDF、不投稿。

R047/T03b修复64页对齐快照；R052a差128记H-bug，D05排查。R044旧三轮failed_harness不改判，CPU别名表复审仅诊断，R044b为新轮。Strata S4验证parallel2+真实batch-MTP opt-in；S3没有此opt-in。

## 生产与观察

481于04:49:08完成唯一首次冷SDK冒烟，17字段逐项匹配df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97，无184回滚。新观察当前189样本，状态in_progress；实际统计={"active_owner_matches_failures": 0, "supervisor_alive_failures": 0, "service_alive_failures": 0, "monitor_alive_failures": 0, "watchdog_fresh_failures": 0, "unhealthy": 1, "unhealthy_after_first": 0, "alerts_max": 0, "epochs": [0], "restarts": [0], "first_watchdog_age_seconds": 51.00800538063049}。首条窗口前50.99秒loading快照保留，不改为clean PASS。原观察17:35:56→22:41:20为truncated，306样本0issues，不能称隔夜通过。

Strata同v0.1.41同构建：S1无MTP冷32K61.4–63.35/短60.44–66.31；S2开MTP冷/短均值77.17/79.06，原提示聚合64.6189（S1为48.4182，parallel1排队）；S3两路20.6089/40.5569、聚合35.4811，未达两路均>30。ignore_eos固定256不支持，52/60仅R001历史。D09/D10 T16 kept均只是默认关闭门，启用路径不提前认定通过。

## 准备时间线

A R067d-retry2 CPU独审预计08:40；B S4 08:20/R044b09:00；C D10 lane缓存11:00；D T03b首版12:00；E D09-T17启动修复09:00/D05排查10:00。偏差>30分钟更新。GPU取首个已独审项串行接入，无可跑项时恢复481。13:00为状态与下午时间线汇报点，不是截止。

并发>2、持续负载>30分钟或打满CPU/内存/PCIe/磁盘均属于压力测试，必须预先报告范围、并发、时长、影响，用户知悉之后执行。当前各项预期<=2并发，仍逐项核对时长和影响。

## 推送与证据

状态PENDING_USER_APPROVAL_OBSERVATION_IN_PROGRESS。未获批准，未推送；目标仅origin release/e2精确481，不含D09/D10/R047调试代码、夜间工装或论文。实时Git={"head": "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9", "branch": "release/e2", "tracked_dirty": false, "shortstat": "91 files changed, 11964 insertions(+), 129 deletions(-)", "commits": "40", "origin": "https://github.com/FlashML-org/FreeToken.git", "remote_head": "", "remote_read_success": true, "scope_matches": true}。

证据快照：development/night_execution_20261009/MORNING_REPORT_CURRENT_EVIDENCE.json。旧轮原始字节、manifest、独审、终态保留，修正追加，不重复出同结论V2/V3文件。英文全文历史V9来源独审通过，当前解释更正后需要重新核对来源；无PDF、无arXiv提交，多卡仍DERIVED/PROPOSED。GitHub MTP查询见_shared/research/GITHUB_MTP_SCHEMES_20261010.md。

## 当前执行追加

真实写入：2026-10-10T08:40:32.994055+08:00。481 观察实际窗口 2026-10-10T04:49:08.147915+08:00 → 2026-10-10T08:31:15.579881+08:00，222 个样本，终态 truncated；末样本健康，backend_epoch/restart_attempts 为 0。停服完成 08:31:36.664012；没有隔夜通过或推送批准。

D09-T17 首次 batch150 在 GPU 前收据格式失败（0 服务、0 调用）；保留 failed_harness。修复出生身份规范化后，14 个 CPU 用例及独审通过，08:38:22 启动 retry1/batch151，候选仍 c17b69a。正常预计 08:55 完成；GPU 串行，其余准备继续。

D05 已把缺口绑定到 UID6/7/8：目标 UID7 的 13432+122=13554，解码不保存页边界状态，未对齐结束捐赠被跳过；UID8 先命中13376，随后自身 prefill 才产生13504。这是当前源与日志的诊断，未改变 R052a 正式 NOT_MET，也未进行新 GPU 验收。

真实写入：2026-10-10T08:49:54.476663+08:00。R067d-retry2 batch152 在实际 Effects 构造时因 input_binding 缺失而 pre-GPU failed_harness（0 服务、0 调用），未进行计时或产品比较。正在补实际 Effects 构造与锁生命周期 CPU 验证。D09 retry1 1 服务/1 冷调用有效，但清理遇驱动卸载延迟，保持 failed_harness；08:45:16 已证明进程出生退出、端口重绑、GPU空闲并按原锁收据释放，补120秒有界等待后做最后工装重试。

更新时间线：B S4 当前预计09:25，R044b独审包预计10:20；均已超过原估时30分钟。C D10持久化代码及真实D07收据验证已通过，补整体25分钟上限与清理卸载等待后可启动；D T03b工装预计10:30（产品代码与24CPU用例已通过，GPU未验收）；E D05诊断已交付，完成长度与真实 cached_len 关系保持源约束的条件说明，未开始修复/GPU。13:00汇报点和推送未批准不变。

真实写入：2026-10-10T09:13:01.355763+08:00。D09-T17 最后工装尝试 batch153 为 failed_harness：3 服务、4 调用，冷 A/B 相同但冷/热在 P 的状态哈希不同，输出比较作废；热臂另有 free_pages(450)+cache_pages(317)!=num_pages(768) 完整性报错。清理、双端口与锁释放已证明，停止本项，不追加重试。R067d-retry2 batch154 已启动（PID1591271，start_ticks168916803），候选 b86190d，10 服务/14 调用上限；按实测启动耗时预计正常全轮约09:55，前置边界门失败则提前终止。

D10 持久 lane 修复候选 54955f7：9 个真实 child-path CPU 用例及独审通过，完整冻结 argv 已在候选 ServerArgs 上解析并封存；旧 T16 仅历史证据。Strata S4：本轮1服务11调用/累计第5服务，绝对1350秒负载+150秒清理预算，7CPU用例独审通过；排在当前就绪项后。T03b：24产品CPU用例+9启动CPU用例，真实SSE与清理绝对预算已补齐，最后差异独审待完成。R044b真实6服务144replay副作用 seam已补齐、6CPU通过，独审中；不继承旧failed_harness为验收通过。D05诊断已root独审，R052a原not_met不变，无新GPU。

英文论文五文件已同步混杂/实现缺陷说明，独立源审通过；PDF与投稿继续等待R067和D10本次重测结果，推送仍未批准。13:00仍为报告点。

真实写入：2026-10-10T09:38:49.234182+08:00。R067d-retry2 最后工装尝试 batch154 终态 failed_harness：1 服务就绪，1 次私有接口调用返回 POST /internal/t17/exact-ids HTTP404，0 次有效生成；原始证据与独审已封存，不做第三次工装重试，无 C3 产品结论，D12 的通过前提未满足。CPU 路由诊断显示现启动钩子未注册该接口，保留为工装问题。

D10 持久 lane 缓存原型 batch155 已进入真实错相位分支，首组 2 次请求生成 46/58 token；逐请求 decode 速度为 0.872512/6.967070 token/s，均低于每路 >30 的门槛，终态 NOT_MET 并立即停止。不能用聚合吞吐或均值替代逐路速度；profiles1–3 和 ignore_eos 256 未执行，当前候选的新默认关闭 T16 未验收，正式开发条件不成立。先验 33.1–40.0 是有条件参数预测，不是置信区间；此实现是可行性负结果，不推导为理想机制不可能。原始证据、实际分支和正确逐请求指标均已独审封存。

T03b batch156 于09:26启动（PID1638426/start_ticks169010306），候选dc951c6，6服务24调用、串行加载，2700秒绝对总上限，单服务生成阶段1500秒上限。首组A/B均3个真实快照，UID2后续命中192缓存token，负控及双端口清理通过；其余两组进行中，预计10:05终结。Strata S4当前8CPU用例及差异独审通过（本轮1服务11调用、累计第5服务，25分钟绝对上限），作为后续首个就绪项接入。

R044b 的冻结负载是6服务串行、144调用、并发1，历史同协议生成与加载证据估计全轮64–72分钟、累计生成38–45分钟，各服务连续生成约6–7.5分钟；资源饱和程度没有遥测。已按07:55压力知悉规则向用户报备，等待用户知悉回复，尚未启动。CPU侧先补每服务1500秒生成阶段、全轮5400秒绝对上限和超时安全清理，预计09:45完成独审前包。若没有其他可跑GPU项而该项仍待知悉，立即恢复481并按df77cb做SDK冒烟。

论文当前源已通过09:08独审；正在以真实时间追加154/155实测结果，预计09:55，不出PDF、不提交arXiv，不推送。D09-T17最后failed_harness与D05源诊断保持不变。13:00仍是汇报点。

真实写入：2026-10-10T10:29:36.646871+08:00。按用户09:50裁定：T03b/batch156已封存KEPT（6服务24调用），UID2的192命中来源在原日志中不可辨，CPU补例用192与256不同状态区分，原判不改。StrataS4已结束497.319秒并清理，ignoreEOS256实际45/60输出不达标，逐请求/协议独审中。R044b/batch157于10:21:48正式启动，用户已知悉压力；6服务串行144调用并发1、5400秒绝对上限，现场1Hz dmon和标准vmstat/proc磁盘原计数采集齐全。

R067e新RID/额度已批准，真实spawn服务工厂路由与Effects14ID/10服务materialize通过CPU独审；root独立复跑2用例20.14秒通过。按旧同候选实测加载275.53秒+清理66.34秒，完整轮预计55–70分钟，已按07:55补报压力时长，等待用户知悉后才能接GPU；未启动。

D09不上GPU：768页UID0→UID1回收少页/非对齐页地址及迟捕获推进后状态均在CPU复现并修复，当前bd57cfd，含conv/recurrent/PLEconv/ngram在P的CPU参照全张量比较与恢复检查，48用例通过；原GPU状态等价未重新验证。D10不上GPU：补真实步数/UID时间戳/延迟CUDAevent计时/实际lookup命中和H2D字节；CPU10通过、预注册独审通过，预热16步、同步两请求、每路实际≥256、只统计共同解码区间，严格每路>30且T16通过才GO。论文已删“实现缺陷造成”归因，写两版均未达标、不能区分机制与冷启动。推送仍未批准，13:00仍为汇报点。


2026-10-10T10:46:00.394984+08:00 更新：S4已独审限定测量子集；native AIPerf两路21.978/48.034 tok/s，输出45/60，256请求仍105/512不足，不能认定两路通过。R044b batch157因真实日志字段别名校验错误failed_harness（1服务24调用），B2未启动；1Hz原件保留，清理未正常闭合，root于10:44:41精确回收遗留vmstat及本轮锁。retry1正在CPU修复/独审。无可准入GPU项，10:45:06已启动481恢复，SDK逐项基准比对待结果。R067e CPU新计数规则14项及donor guard4项通过，完整55–70分钟轮次仍待压力知悉；D09/D10不上GPU。推送未批准；13:00仍为汇报点。


2026-10-10T11:01:15.407977+08:00 更新：481 restore01官方SDK2请求各128token，17项结果字段及argv与df77cb14基准一致(rootcomparison05b6fd...)；新观察10个样本已在10:59:14停服前如实截断。R044b retry1 batch158于11:00:16执行（PID1911541:169570571），独审14CPU通过/canonical631465.../rootadmission990b88...，保留6服务144调用上限和5400秒绝对上限，预计提前B1/B2门12:00附近，若继续则最晚12:30收工(含清理预算)。首轮157仍failed_harness。D09完整新协议独审PASS_CPU_NOT_GPU_AUTHORIZED，新GPU申请待批准；D10继续不上GPU。S4 native补充及论文§8/C5已root独审，PDF未构建，推送未批准。


## 追加 2026-10-10T11:24:32.380152+08:00

R044b retry1 batch158 已独审封存 failed_harness，2服务48调用；动态PID占位符解析异常，尚无产品结论，原遥测dmon清理超时如实保留。11:22:45 root核实进程退出/GPU空闲并释放所属锁。11:23:25启动restore02，SDK首次冷基准比对尚未完成，预计11:30；最后retry2隔离CPU修复预计11:45，未GPU准入。D09/D10仍不上GPU，R067e压力知悉及D09新GPU申请待用户回复。推送未批准。


## 追加 2026-10-10T11:29:15.078569+08:00

restore02 SDK在11:27:34通过，root逐项比对17字段、API缓存字段及启动argv全部一致，比对SHA0dbc5616dae326cb2c341e2df12f5c3ab676612b48315d32a68bc053e977bad3。481当前serving，新观察在进行，不能写为隔夜通过。R044b最后retry2仍在CPU证据封装，尚未GPU准入。


## 追加 2026-10-10T11:35:39.174553+08:00

R044b最后retry2已独审PASS，14CPU tests、实际B1/B2 strict及两层filedry均通过，独审SHAaa9dc7f7…。restore02 SDK全部通过后7样本观察截断并停服，11:34:59启动batch159（child2008171:169778903），6服务/144调用/并发1，预计早停12:00、完整12:40–12:50，绝对上限13:05。无下一可跑项时用root独审fresh03恢复481。13:00仍为实际汇报点，不是GPU截止。
