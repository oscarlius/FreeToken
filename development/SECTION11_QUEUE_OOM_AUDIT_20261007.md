# §11 剩余队列逐臂配置与 OOM 审查

审查快照：SSH9 `date -Iseconds` = `2026-10-07T09:56:46+08:00`。依据 `plan/CODEX_HANDOFF_20261006.md:173–192`（09:55 第十一节）及 PLAN §8 所有权。只新增本文；未修改任何泳道源码、冻结包、旧轮次或协调日志。开工/交付时间交根负责人追加协调日志。

结论：当前五批入口没有显式启用 **route trace + 0.88**，不能据此宣称它们不会 OOM。已知确定性组合是 R055a/R046a G3-on 的 route+pause、0.88、32064 输入、628 MiB 申请/625.69 MiB 可用；五批的 native/state/D0 观测并不等同于该 route 缓冲。当前必须更新的是 R049/R047 对失败 R046a 的活跃依赖。R040a 发布树停靠臂实际打开并调用 pause：根确认历史用户已明确批准走0aa，候选保持0aa，只登记该暂停路径尚未实际验证的缺口。

交付前根负责人最新证据：独立R以真实前端CPU构造确认T06 `seed_real`首请求 **87100 tokens > 49152**，且种子SHA匹配。本文未独立复算该输入，按根提供的新证据记录。它是启动前科学输入/窗口协议阻塞，不是可用降低ratio处理的OOM；根将暂停GPU并请求用户裁定，不trim种子、不扩大KV、不以字母后缀绕过。以下各批排序只描述裁定后应做的准备。

本次只读当前本地源、最小 handoff/identity/dry 元数据；服务器仅 date、D08 HEAD 和必要源码文本查询。没有 GPU 查询、取锁、端口分配、HTTP、8095 访问、模型/服务启动、新轮次、完整库存哈希或旧 raw 重读。没有执行实际 dry/self-test；本文是启动复核输入，不是启动签字。

## 1. 优先级与根负责人动作

| 优先级 | 事实与影响 | 最小后续动作 / 所有权建议 |
|---|---|---|
| P0 | R049 的训练、heldout、manifest 和 admission 都指向 `E2-R046a`，该轮 failed_harness 且 T06 未启动；不能产生合规 T21 画像。 | 分配 C2/T21 修改 R049 当前开发源及必要测试/交接；新冻结版本读 `E2-R046b measured`。保留 seed12k 唯一训练源及三 heldout 分区，不重读旧失败 raw。 |
| P0 | R047 的活跃前置要求 `E2-R046a measured`，会拒绝已批准的 R046b。 | 分配 R047/02 owner 更新该前置及必要测试/交接，独立冻结；不能给 failed R046a 改 verdict。 |
| P0 | 根提供R的真实前端证据：seed_real首87100超49152，种子SHA匹配。 | GPU启动前科学输入阻塞，由根向用户裁定；不得trim/扩KV或视作非性能ratio重试授权。 |
| P1 | R040a v3 固定发布树 `0aa23431`；parking control/restore 四臂设 `FT_DEV_PAUSE_ENDPOINT=1` 并实际 `_dev_pause`。包装器只接 exact-ID/capture/parking reply seam，没有发现替换 eff 调度消息修复的代码。 | 用户已明确授权0aa，保持候选；A/D16 owner在启动复核写明该暂停路径尚未实际validated。不能自行换eff/新candidate或关pause/state trace。 |
| P1 | 五批源码没有 route+.88；仍缺各实际模型进程在最长业务请求上的显存峰值。R055b 的 trace-off 最低1.066 GiB是特定单冷请求证据，不能覆盖 T21 的长 heldout、T05 双路、D16 native capture。 | 各批启动复核写“未发现已知 route OOM 组合，显存安全未获 GPU 证明”。保持科学 trace。性能 OOM 交根停问用户；非性能 OOM 可按 §11 同配置参照一起降至 >=.80、字母后缀和新版本。 |
| P2 | R040a 的可选插入前置枚举仍含 R046a；默认 `--after-round E2-R048` 不因此阻塞。旧 D06 helper 也含 E2-R046，但合并 R045 不执行该旧独立 admission。 | 精确区分活跃调用，见 §7；不要为清理历史字符串改冻结旧包。 |

队列保持 `R046b → R049 → R048 → R040a → R045 → R052 → R044 → R047`。当前先等87100科学输入阻塞的用户裁定；解除后完成 R046b source/CPU/真实路径 dry/R 签字，其 measured+D04 后才允许 R049 画像构造和同入口 dry。后批可并行准备源码与 CPU证据，实际启动仍严格串行，CPU/dry 不能替代前置封存。

## 2. 共用服务参数与已知 OOM 边界

`development/d07_g3g4_prepare.py:286–315`：清除继承的全部 `FT_*`，未传 `trace_dir` 则 route/pause 默认都未设置；传入 trace_dir 才设置 route 与 pause。服务默认 `memory-ratio=.88`、`moe-cache-auto`、`moe-prefill-hit-d2d`、pinned/offload、NVFP4 triton、max-running=2、graph-bs=2、KV reserve=49152、seq override=49152、max-prefill=4096、layer-major、host-slots=0、special-token checkpoint。以下逐批注明覆盖项。

KV/seq 表列的是 argv 参数，不是实测物理页数。自动预算源 `development/e2r046_pausefix/python/freetoken/engine/cache_budget.py:64–96` 先留 KV reserve，再分专家槽，且最小缓存计划过大时在CPU算术门拒绝；比例下降需要保持原 KV/seq、策略与输入不变，不能擅自降窗口/改 kernel。

§11 的 628 MiB/625.69 MiB/32064 及 R055b 1.066 GiB 来自用户已裁定的封存证据。本审查未复算旧 raw，未独立证明该628MiB申请的具体张量表达式或所有 native/state 观测峰值。`max-prefill-length=4096` 也不能单独证明长提示的全部临时内存只按4096分配。

## 3. R049 / T21 — 9个独立服务臂

当前源：`development/r049_t21_prepare.py`、`r049_d0_startup.py`；既有冻结 `r049_real_path_source_v1` 及 `R049_SECTION10_READONLY_PRELAUNCH_20261007.md`。候选 `988c9e18` / parent `effb996`，工作树 `/data2/FreeToken/wt/e2d15`。

| 每一臂（正式顺序） | 策略 / 是否性能 | route / native事件与state观测 / pause | ratio；KV/seq；mode |
|---|---|---|---|
| L1 | lru；性能 | route OFF；D0 OFF；无 state/memory observer；pause endpoint ON，仅SSE ACK绑定 | .88；49152/49152；offload layer-major，chunk4096 |
| P1 | profile；性能 | 同 L1；配置 seed12k STRP | 同上 |
| PA1 | profile+adapt；性能 | 同 L1；adapt_every=1/swaps=1 | 同上 |
| L2 | lru；性能，第二重复 | 同 L1 | 同上 |
| P2 | profile；性能，第二重复 | 同 P1 | 同上 |
| PA2 | profile+adapt；性能，第二重复 | 同 PA1 | 同上 |
| L_D0 | lru；非性能诊断 | route OFF；D0 ON，worker出生、decode active/missing/fetched、H2D/swap journal；pause endpoint ON；无模型 memory observer | .88；49152/49152；offload layer-major，chunk4096 |
| P_D0 | profile；非性能诊断 | 同 L_D0；STRP | 同上 |
| PA_D0 | profile+adapt；非性能诊断 | 同 L_D0；adapt journal | 同上 |

来源：arm定义 `r049_t21_prepare.py:18,48–55`；服务 `:28–35` 调 D07 argv；env `:472–480`；D0 counters `r049_d0_startup.py:51–74`。`env_for` **明确拒绝** `FT_DEV_ROUTE_TRACE`。pause flag用于现有 DevStreamAck，不是正在请求暂停；本批 workload 未调用 pause API。

九臂相同输入：两个冷请求 built32052/输出128；two-decode `ctx32000`、两个不同提示、每路输出512（`:262`）；seed_45k/seed_real 使用封存 T06轨迹热重放（`:308–309`），输入参数与前端 IDs逐次绑定。T06生成配置为12轮、每轮max_tokens2048，但**不能把该上限当成 R049每次最大prompt**。R046b还未产生有效heldout元数据时，最长prompt精确token数不可由seed文件名推断；应由T21 owner在未来R046b封存后用所绑定前端/必要小元数据确认，禁止现在读取active/failed raw。

判定：没有已知 route+.88 组合；pause+.88的trace-off历史余量不够证明本批最长提示安全。六个性能臂保持.88。三诊断臂当前也保持.88；若诊断OOM，字母后缀下按用户授权同配置L/P/PA参照调整>=.80，保留D0并说明槽数变化对miss/bytes统计的口径，不能把不同ratio的诊断量直接解释为.88性能缓存统计。

## 4. R048 / T09 — V0/A/B/C/S

当前源 `development/r048_t09_prepare.py`；handoff 当前07:21块优先于早期 `BODY_READY=False` 记述。源码 BODY_READY=True、候选 `8bf0ad39` / parent effb996；本审查仅以SSH `git rev-parse HEAD`核到远端 e2d08 HEAD确为该值，没有重做门或编译。

| 每一臂 | NUMA / affinity | route / native/state / pause | ratio；KV/seq；mode；性能 |
|---|---|---|---|
| V0 | cpunodebind0,1；interleave all | route OFF；D0 ON；HYB_TRACE=1；native task start/end/barrier与PCIe CUDA event完成；无state dump/memory observer；pause OFF | .88；49152/49152；hybrid，普通prefill，chunk4096；性能 |
| A | interleave all；taskset 1,3-23,25,27-47 | 同V0 | 同上 |
| B | interleave all；taskset NODE1=1,3,…,47 | 同V0 | 同上 |
| C | membind1；taskset NODE1 | 同V0；node1内存不足由既有规则skip | 同上 |
| S | 与A相同，nativepool无独立开关 | 同V0 | 同上 |

来源：`:15–21,38–48,86–91`。去除D07 layer-major，保留host-slots0；不设置D0 timeline。native字段见 `:203–214`；候选 `development/e2d08/python/freetoken/layers/moe.py:33,40,421–442` 在显式HYB_TRACE分支同步并写 `trace_mode_perturbs_timing=true`，CPU executor/native扩展提供 task_timing。不能关闭该科学trace以规避OOM，也不能把诊断扰动隐去。

五臂每臂相同：first_shot prompt2000/output64；dec32k_s3A/B built32052/output128；short prompt2000/output512；two-decode ctx16000、不同提示、每路512（`:188–200`）。实际frontend token绑定保留，built不是完整wire prompt；冷32K完整输入以正式ACK为准。没有已知route OOM组合；native events是否峰值安全仍无本批实测。T09速度臂全部.88，任何性能OOM交根，不能降.80或关闭HYB/D0。

## 5. R040a / T20未完成附加项 — 36个服务scope

入口 `r040a_d16_supplement_prepare_v3.py`，private owner v1、process collector v4→冻结collector v2、shutdown v3、anchor v2。冻结交接 `/data2/FreeToken/runs/dev_D16/r040a_section10_cpu_v1/development`；候选0aa23431，当前176 CPU证明与source review不是GPU准入。

### 5.1 S-批槽 / S-交错 / S-停靠 / S-缓存（共30臂）

所有 native服务：route OFF、D0 OFF、D0 timeline OFF、HYB trace OFF；owner先清除所有FT环境，再由 configured/私有服务明确装观测。ratio=.88；KV/seq=49152/49152；offload layer-major；chunk4096；max-running/graph-bs=4。**T20第5项非性能等价/state采集臂**。

必需观测键：`FT_DEV_STATE_DUMP`、`FT_T17_INPUT_RECEIPTS`、`FT_T17_OBSERVATIONS`；`FT_D16_SERVICE_CAPTURE_DIR/EXECUTION_ID/EXPECTED_JSON/MAX_CAPTURES/MAX_BYTES`。每请求128 decode采样，MAX_CAPTURES=`128*request_count+1024`，MAX_BYTES=2147483648。这些是 native/state/sampler/delivery 原始采集，不能关掉。无R055B模型memory observer。

| 分组及每一臂（名称相对各组目录） | 输入 / output | pause与state特有项；host-slots |
|---|---|---|
| native_slots_2：`dev_D16_2_batch_0_None`,`dev_D16_2_batch_1_None`,`dev_D16_2_single_0_0`,`dev_D16_2_single_0_1`,`dev_D16_2_single_1_0`,`dev_D16_2_single_1_1` | 每路512 exact-ID；batch两路/single一路；输出每路128 | pause OFF；host0 |
| native_slots_4：`dev_D16_4_batch_0_None`,`dev_D16_4_batch_1_None`,`dev_D16_4_single_0_0`,`dev_D16_4_single_0_1`,`dev_D16_4_single_0_2`,`dev_D16_4_single_0_3`,`dev_D16_4_single_1_0`,`dev_D16_4_single_1_1`,`dev_D16_4_single_1_2`,`dev_D16_4_single_1_3` | 四个不同512切片；batch四路/single一路；每路128 | pause OFF；host0 |
| native_interleave：同native_slots_2的6个叶名称 | 短512；长 `4096<len(query)<=16384`；batch在真实decode后触发长prefill；每路128 | pause OFF；host0 |
| native_parking：`control_0`,`control_1`,`restore_0`,`restore_1` | 一个512切片；每路128；等待decode触发后pause1秒 | 四臂pause ON且实际调用；PARK_RESTORE分别0,0,1,1；host5；before/host/cleared/restored四状态 |
| native_cache：`cold_0`,`cold_1`,`warm_0`,`warm_1` | 一个512切片；输出128；warm不是warmup请求 | pause OFF；CACHE_INIT=cold/cold/warm/warm；host0；before_decode/after_decode127四状态 |

来源：私有owner `:137–155`；configured `d16_native_process_collection_v2.py:116–150`；各native scope `:295–332,440–470`；正式输入 `r040a_d16_supplement_prepare.py:49–67`。dry用5000长夹具仅证明文件路径，不是正式最长输入。

显存风险：每路512 / 最长16384与已知route32K组合不同；native四状态捕获、4槽与停靠host5仍有额外tensor/复制峰值。2GiB capture byte limit并非CUDA余量保障。未发现已知同数字OOM，不提前修改ratio；若发生非性能OOM，整组含两次batch/single参照或control/restore/cold/warm都按相同ratio>=.80新后缀重跑，保持全部状态/采样协议。

### 5.2 锚点四格（6个独立进程）

每臂依次 `OFF_p1,ON_p1,OFF_p2,ON_p2,OFF_p3,ON_p3`，OFF/ON只差special-token checkpoint。ratio=.88；KV/seq=73728/73728；offload layer-major；chunk4096；max-running/graph-bs2；host-slots未显式指定。清全部 FT_T17/FT_D16/FT_DEV/FT_D3/FT_D0，故route/native/state/D0/pause都OFF。

每进程10请求：single/multi交替5对（每shape一冷四热），max_tokens4。固定历史probe实际上取 seed_45k **前24000字符**构single；multi为12条交替消息各取前2000字符，再加末尾用户消息；不是45K token整文件。精确wire prompt token数需要绑定候选tokenizer，已有源码/小metadata未列该最大值，不能把字符数当token数。来源：`r040a_anchor_four_cell_v2.py:322–340,417–438` 与固定probe `t16_frozen_helpers_v1/ft_probe_ckpt_tax.py:38–48`。

按§11性能枚举，T20第4项属于非性能后补，即使记录TTFT也不能拿其低ratio结果替换T20第1/2/3/7项.88性能。当前无route OOM组合；若非性能OOM，OFF/ON及三重复同ratio>=.80、新后缀，保留冷热四格和实际请求绑定。

## 6. R045 v5 / D06+T05 与 R052 v2 / T11

### R045

当前合并runner `development/r045_section10_draft_v5/source/r045_d06_t05_prepare.py` 及同包D06；handoff09:29 v5优先。实际候选effb996，runner `d06_module():56–57` 覆盖D06旧静态0aa常量。冻结 `/data2/FreeToken/runs/dev_R045/r045_section10_cpu_v5/source`；43CPU与self-test通过，尚无同最终入口实际dry和R启动签字。

| 每一臂/服务scope | route / native-state / pause | ratio；KV/seq；mode；性能 |
|---|---|---|
| g3g4/G3 | route OFF；D0+timeline20000；无FT_DEV_STATE_DUMP/native capture；R055B UserMsg模型memory observer与pause observations | .88；49152/49152；offload layer-major/chunk4096/host0；非性能D06 |
| g3g4/G4 | 同一服务同配置；idle ACK/D0/真实log窗口 | 同上；pause ON且h1真实使用；非性能D06 |
| g3g4/before, pause_completed, pause_cancel, after_cancel | 同一服务；真实before/after请求和模型加载/请求前后memory样本；504有效JSON处理 | 同上；pause ON；1秒accepted、30秒/0.05秒pending cancel、恢复；非性能链 |
| P1 | route OFF；D0+timeline20000；无模型memory/state observer；pause ON | .88；73728/73728；offload layer-major/chunk4096/host0；T05性能 |
| P2 | 同P1，独立服务重复 | 同P1；T05性能 |

D06来源：`d06_g3g4_prepare.py:294–304,334–345,437–444`；当前 `prepare_service_files:338–339` 仍硬拒非.88，runner `:91`结果也硬编码.88。这是未来非性能OOM重试所需最小变更点，**不能连带改T05 argv**。D06冷before/after built32052/input32064/output128；G3两同prompt ctx32000/每路512；G4 pref_target32000、H1/8/32（runner`:74–79`）。

P1/P2每臂首枪冷built32052/output128，随后六workload：two不同提示ctx32000/output512/reps3、two同提示reps1、stall冷pref_target32052/短decode ctx4000/output1500/reps3、stall agent正向T2 round6/reps3、pair-short T2 rounds3/4/reps3、h1 H1/8/32/pref_target32052/reps3（`:136–144`）。T05固定正向 `E1-R003-v2/trace.json`/055ea005；精确agent请求最长frontend token数未列在小元数据，不能由round号估出。当前全服务无已知route OOM；P1/P2必须.88且保留D0/pause；性能OOM交根。

### R052

当前 `r052_t11_followup_prepare.py` + `r052_t11_replay.py`；发布树0aa23431；冻结 `/data2/FreeToken/runs/dev_R052/r052_real_path_source_v2`。v2 Linux29及实际filedry已通过；startup review未签，R045 measured未完成。

只有一个服务，8个replay请求(index0–7)和1个followup，并非9个独立配置臂：route OFF、pause OFF、native/state dump OFF；`FT_D3_TRACE=1`、D0=1、D0_TIMELINE=1、steps20000；无模型memory observer；ratio=.88；KV/seq49152/49152；offload **普通prefill**，chunk4096，host32，max-running/graph-bs2。来源 `r052_t11_replay.py:135–147`，移除D07 layer-major并改host32。

输入固定反向 `E1-R003-v2/trace_rev.json`/097b7a03，不能与T05正向统一。replay输出上限200，followup64；followup精确增加实际assistant输出和“请继续”。完整prompt由保留messages/工具/thinking及实际assistant决定，小metadata只有目标index7/history_uid8/messages摘要，没有最长token数。seq49152为配置上限，不是所有业务输入都已CPU确认装得下。T11缓存/行为分类属非性能；目前无已知route OOM组合。若OOM，可用新后缀、同协议>=.80，保留D0/D3/host32/实际cache计数，不能改cached threshold。

## 7. R046b依赖迁移精确源位置

| 文件 / 行 | 活跃程度与需改内容 |
|---|---|
| `development/r049_t21_prepare.py:9` | 活跃 TRAIN_ROUTE：a→b |
| 同文件 `:10` | 活跃两个HELDOUT路径：a→b |
| 同文件 `:67` | 活跃T06 manifest路径：a→b |
| 同文件 `:76` | 活跃closed-round键与要求：b measured，R050 kept不变 |
| 同文件 `:419` | 实际profile_binding训练来源登记：a→b |
| 同文件 `:527` | prepare输出training/heldout/run_requires同步b |
| `development/R049_SECTION10_READONLY_PRELAUNCH_20261007.md:20,28–37` | 旧handoff对应路径/前置已过时；owner新增最新§11块，保留旧上下文与原freeze |
| `development/t03b_e2_r047_prepare.py:47` | 活跃FORMAL_PREDECESSORS：a measured→b measured |
| `development/r040a_d16_supplement_prepare_v3.py:74` | predecessor_checks可选插入枚举：a→b；默认R048保持 |
| `development/r040a_d16_supplement_prepare.py:117` | v3 execute实际调用的retained require_review允许枚举：a→b；需在新capsule里处理而非覆盖旧freeze |
| `development/d06_g3g4_prepare.py:36,121,134` 及R045 v5包同文件 | 旧独立D06 checker指E2-R046；合并R045 `run_d06_g3g4`直接调用clients/validators/pause_chain，不调用D06 execute/require_t06_measured。当前不把该历史字符串当本批活跃阻塞。 |

R048仍要求R049 measured，R045要求R040a measured，R052要求R045 measured，这些是队列前置，未发现直接读R046a路径。测试数据/历史freeze不做机械全文替换；只更改负责人的当前入口、必要回归和新handoff，新source identity/CPU/filedry/独立review按最终来源重新绑定。

## 8. 每批如何排后续及剩余验证缺口

1. R049：先分配活跃b依赖变更和CPU回归；等待R046b measured+D04后确认seed/heldout最长prompt的小元数据。再做新最终入口profile build/filedry、R startup签字；九臂协议不改，性能保持.88。
2. R048：保留8bf0ad39/eff、五arm、native完成事件、hybrid trace和.88；R049封存后同用户/同最终路径dry与独立R签字。没有必要先关trace或降ratio。
3. R040a：按用户明确授权保持0aa；启动复核记录parking pause尚未实际validated及实际包装器来源。必要源码版本依独立冻结、CPU、source review、最终路径dry推进；R048 measured前置保持。不能以当前176CPU替代真实暂停行为验证，不能自行修树。
4. R045：v5正向T2修正保持；预先登记D06非性能与T05性能ratio边界。仅若授权OOM重试需要非性能降比，则把D06:338–339硬门、D06argv:439和runner:91结果字段改成单一实际值，T05:99保持.88；新的source/CPU/dry/R绑定独立。等待R040a封存后实际dry。
5. R052：v2反向input与29CPU/实际dry保留；没有确定性OOM配置要预修。R045封存后metadata-only gate与R startup复核；实际请求完成后独立复算cached threshold并D04。

精确token最大值缺口集中在 R049 heldout、T05 agent输入、R040a anchor字符slice及R052 followup。若责任owner已有绑定前端token计数的小summary，可直接提交它，不读取旧raw；没有时只能用既有源/最终绑定输入做受CPU guard保护的前端构造并新增小metadata。CPU不能给出CUDA峰值；未测余量不写成已证明≥1.5GiB。所有性能OOM由根按§11停问用户，非性能重试才使用>=.80与字母后缀授权。

## 审查日志（每行<=150字，真实SSH9时间）

2026-10-07T09:53:14+08:00 SSH9｜开工：§11逐臂只读OOM审查；仅新增本报告。

2026-10-07T10:00:22+08:00 SSH9｜阻塞登记：根/R证据seed_real首87100超49152；GPU停，科学输入等用户裁定。

2026-10-07T10:00:22+08:00 SSH9｜交付：五批无显式route+.88，memory未GPU证明；R049/R047迁移位置已列；0aa pause缺口保留。

## 9. T21 STRP专家几何追加审查（只读源码，2026-10-07）

本节为10:16只读发现的修前状态；根随后明确授权的修复与新CPU证据见§10，旧行号按修前快照保留。

**P0：当前R049两处256是相互自洽的错误硬编码，不能用于本轮512专家目标模型。** 这与R046b依赖迁移和性能`.88`无关；即便未来R046b measured+D04及输入窗口获准，T21仍需先修正该源缺陷。没有读取任何R046b route、运行builder或模型加载；结论来自现有源和实际overlay的小config。

真实SSH9 `2026-10-07T10:16:06+08:00`只读核验：`/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json:8,9,103–105`分别为`model_type=qwen4_exp`、`text_config`、`num_experts=512`、`num_experts_per_tok=10`、`num_hidden_layers=48`。既有本地small report `development/r046b_memory_budget_v1.json:223–225`也登记同一512/10/48；没有重读旧raw或权重。

| 精确源位置 | 事实与影响 |
|---|---|
| `development/r049_t21_prepare.py:469` | build argv固定`--num-experts 256`；没有从绑定模型config取得512。 |
| 同文件 `:473` | 子进程reader固定`read_profile(..., num_experts=256)`；只证明错误header符合错误预期。 |
| 同文件 `:423` | 正式与file-dry路径均调用上述build_profile；`file_dry_run=True`不改变几何或跳过真实builder。 |
| `development/e2d15/tools/build_expert_profile.py:27–29` | 建立`[route_layers,256]`频表；若任一真实expert ID>=256，立即抛`route geometry differs from the first trace`。 |
| 同文件 `:33–34` 与 `development/e2d15/python/freetoken/moe/expert_profile.py:57` | 把频表专家维度写入STRP header；即使所有已观察ID<256，header也仍是256。 |
| 同reader `:35,74–75` | 格式允许512（维度上限65535）；读入时专家数必须精确相等，不裁剪、不重映射256→512。 |
| `development/e2d15/python/freetoken/models/qwen4_exp/config.py:116,202,242` | loader取真实`text_config.num_experts`并传入ModelConfig，目标值512。 |
| `development/e2d15/python/freetoken/engine/engine.py:725–729` | OffloadMoeCache的`num_experts`来自`config.model_config.num_experts`，不是cache容量或训练路由覆盖数。 |
| `development/e2d15/python/freetoken/moe/offload_cache.py:823,833` | profile/profile+adapt初始化按实际cache层数和专家数校验，256 header将抛`STRP geometry ... does not match cache geometry`。 |
| `development/tests/test_r049_t21_prepare.py:448–461` | 现有test mock builder写256 fixture并断言argv256；第二mock分支只检查含read_profile字样，没有实际执行reader或绑定真实512模型。 |

因此两条失败路径明确：实际seed12k若出现ID>=256，未来file-dry的builder即拒绝；若恰好所有ID<256，builder及错误的256验证可过，但实际512 cache加载必拒绝。当前不读raw，故不声称已经知道该seed12k包含哪些ID。现有Windows75项（及之后根的新Linuxtargeted验证）只能证明各自覆盖的行为，不能据此签署本模型STRP几何通过。

最小后续修正归R049源码owner：让builder和reader使用同一个绑定目标专家数512，替换`:469/:473`两处256；优先从最终绑定的实际模型config取得并登记该值，若保留此单模型常量也必须CPU断言它与config一致。调整同test的fixture/argv/reader预期为512，并增加实际纯CPU reader回归：正确512 STRP接受、256 STRP对512 cache拒绝；如授权builder fixture测试，用合成ID256/511证明512接受、256拒绝。测试不得读取正式route。builder/reader格式和候选产品树本身无需修改，不改`.88`、训练partition、科学输入或测量协议。修后新source freeze/CPU/review重新绑定，保留旧封存包。

2026-10-07T10:14:19+08:00 SSH9｜开工：限查T21 STRP的256/512链，仅源码及实际config小元数据。

2026-10-07T10:16:31+08:00 SSH9｜交付：256不是有效目标几何；两处硬编码及mock缺口已定位，只追加audit，未build/test/GPU。

2026-10-07T10:16:31+08:00 SSH9｜阻塞：T21需512一致修正；seed_real超窗仍等用户，不能实际route build或file-dry。

## 10. 根授权的R049 512几何修复与CPU契约交付

根在§9事实确认后明确授权本owner修复当前开发源及必要test/HANDOFF。`r049_t21_prepare.py`新增 `MODEL_NUM_EXPERTS=512`，build argv和reader expected geometry共用该值；没有未来模型读取器或新抽象。实际overlay的512证据仍是§9所述小config及loader/cache链，候选988/父eff、性能.88、唯一seed12k训练与三个heldout保持。没有修改候选产品/工具/旧冻结源。

`test_r049_t21_prepare.py`现用真正的现有纯CPU builder/reader契约，而非只mock成功：合成临时 `[1,1,10] int16` route含ID511/256/510，按runner实际512 argv构建fixture，执行runner的reader `-c`脚本，确认512 header及ID511首排名。另两项回归要求builder以256拒绝高ID，真实reader把256-header对512 cache拒绝。正式R046b route/raw及科学输入均未读取，fixture STRP不作为科学画像或正式dry证据。

新Windows验证：R04952 + R04725 = **77 PASS in 0.84s**；既有sitecustomize network guard身份已断言、CUDA_VISIBLE_DEVICES空、第三方pytest插件关闭、torch未导入；修改runner/test的AST2 PASS。既有Windows75和根通报的修前Linux50/25=75（report f070…）保留为修前来源，不能替代本次新Linux验证或启动review。

本次开发源身份（两个小文件，不是全量hash；LF列用于根的Linux规范化同步）：

| 文件 | 当前本地raw SHA256 | LF规范化 SHA256 |
|---|---|---|
| `development/r049_t21_prepare.py` | `8ee96cd25d30b6c95b659b05c2947f767d3c305732454b11d093d5411c775392` | `ddb42745e01074ecfb1f8828926d338473eda658ce24f0b29af296b873180a3c` |
| `development/tests/test_r049_t21_prepare.py` | `bb852855dbc6da365b9f09a93901d64434e1cef7fc23b7345bf8f8273a3fb5fd` | `ff24bca86882e78b768aa14abbd73ef93ba0e1595651bf32501f5cebfaf8183c` |

根的最小CPU同步闭包增加两份只读988源：`development/e2d15/tools/build_expert_profile.py` 与 `development/e2d15/python/freetoken/moe/expert_profile.py`，维持test相对目录；依赖numpy已在本机可用。测试直接加载纯CPU模块，不需package init或模型加载。此次没有服务器同步；根应对当前runner/test及实际提供的依赖重新冻结/绑定/执行LinuxCPU，旧签字不用。seed_real超窗与R046b未measured阻塞延续；本修复不授予实际route build/filedry/GPU准入。

2026-10-07T10:17:28+08:00 SSH9｜ownership/开工：根授权修R049两个256与test/HANDOFF；不改产品树/性能.88。

2026-10-07T10:19:17+08:00 SSH9｜交付：同一512常量；合成高ID真实CPU契约及256拒绝，Windows77PASS/AST2PASS。

2026-10-07T10:19:17+08:00 SSH9｜阻塞延续：seed_real超窗待科学裁定；需新Linux/source/review，不读正式route/build/dry/GPU。

## 11. 最终R046b producer/consumer schema补修

独立R发现P0后，根授权本owner仅补修当前R049开发consumer/targeted tests/HANDOFF。实际未改producer `development/r046b_d07_t06_prepare.py::manifest():310–329` 输出 **`ft_r046b_route_manifest/v1`**，先前consumer及手造fixture使用旧 `ft_r046_route_manifest/v1`，故实际未来b measured也会被拒。本次 `r049_t21_prepare.py:72` 改为唯一真实新schema；没有兼容旧schema或接受旧a/其他RID。

接口核对事实：真实producer与consumer其余已消费字段一致——RID=E2-R046b、candidate=effb996、四role seed12k/seed_45k/seed_real/two、目录各为G_role、typed d15_training_input仅seed12k真、d15_training_route=G_seed12k/route、heldout恰为G_seed_45k/G_seed_real/G_two的route。producer另有service/files/g3g4/timing和上游memory_ratio=0.80；它们不替代真实measured+D04闭环，也不改变T21性能.88。本次未扩展成通用manifest validator，未改producer、种子、候选树或旧冻结源。

tests `r046b_producer():23` 直接加载上述真实producer；`t06_manifest():31` 创建标记fixture_only/not_measurement的临时输出文件后调用真实 `manifest()`，整份document由producer生成，所有T06身份/partition测试共用此契约。`test_current_r046b_producer_manifest_is_consumed_without_translation():57` 核实际b/eff/.80/四role/typed bool并原样送consumer；`:69`新增旧schema拒绝。既有其他schema、a/c RID、wrong-tree、重复/污染臂与heldout拒绝保留，512高ID及256拒绝契约不变。只有合成临时文件，不读取真实route/旧raw、不运行producer正式入口或GPU工装。

新Windows证据：**R04954 PASS in 1.33s**；sitecustomize network guard身份/CUDA_VISIBLE_DEVICES空/插件关闭、torch未导入；runner/test AST2 PASS。未重复unchanged R04725。旧Linux52保留为修前几何版来源；新Linux54及source identity由根新freeze验证，本机结果不是新Linux或启动签字。

| 文件 | 当前本地raw SHA256 | LF规范化 SHA256 |
|---|---|---|
| `development/r049_t21_prepare.py` | `b87b5785e7f80b430afd65650053be260b11acd2b02ef73d9c4a5c70ae04654a` | `8ad23d0d5fef878528035a56b3ba9fc2a6e0ee07722b5cb14329821056e217ff` |
| `development/tests/test_r049_t21_prepare.py` | `b3d990eab773fde2205473e4d31f78f272090722d8e9ff2e989584c8d73914b1` | `7ad64b5f78c06ddc580055ca89cc54ae421b347b051d7132838788a6634c8213` |
| 未改producer `development/r046b_d07_t06_prepare.py` | `4c4f5a8dda5574aa2da7faa0782c11688096749b7ac1e3183ade46f1006db1ab` | `4c4f5a8dda5574aa2da7faa0782c11688096749b7ac1e3183ade46f1006db1ab` |

根上一几何版10文件CPU闭包仅需增加未改producer这一小文件，同test相对目录；此manifest契约加载仅用stdlib，不需其D07/种子/observer/launch运行依赖。没有服务器同步。根重新冻结并获得必要LinuxCPU/source/review后，仍须等待科学输入裁定和真实R046b measured+D04，才能排最终dry与GPU；不续用旧review。

2026-10-07T10:24:08+08:00 SSH9｜ownership/开工：根授权schema有限补修，核真实producer→consumer，不改producer/冻结源。

2026-10-07T10:26:11+08:00 SSH9｜交付：仅接受真实b schema；实际producer临时契约与旧schema拒绝，Windows54PASS/AST2PASS。

2026-10-07T10:26:11+08:00 SSH9｜阻塞延续：科学输入待裁定；旧Linux52保留，新源需根freeze/CPU，无正式route/build/dry/GPU。

## 12. 用户§12批准后的98,304实际客户端链交付

此节优先于本报告前文所有49K输入待裁定/旧静态route增长预算。用户明确保原seed、扩窗口98304；原seed_real SHA8fe6b36…保持，首87100仍为既有R的真实前端证据。seed_45k原名保持，实际首提示12434、seed本身约1.2万token。本owner按根授权改当前producer/R049/new v2 client及对应tests/handoff；未改旧client、候选产品、R056工具或任何冻结源。

R046b全部D07/T06服务argv同98304/.80，T21九臂同98304/.88。producer manifest保持 `ft_r046b_route_manifest/v1`，增加精确window（98304/98304/2048/96256）和各seed实际completed_k/window_hit；consumer严格对应该window，仍b/eff、唯一seed12k训练+三个heldout，512专家不变。T21实际filedry在任何目录/build之前要求真实R046b measured、R050 kept及新window manifest。

新 `r046_seed_agent_trace_v2.py` 逐请求调用实际候选TokenizeManager.tokenize（内部render_prompt、tools/thinking/effort sanitation和实际encode），发送前用完整实际input IDs判定：≤96256发送，>96256不发送，写完成k/第k+1触窗与完整未发payload。seed原bytes SHA先核，utf8解码直接拼TASK，不trim/更换/改CRLF。每个completed请求绑定actual IDs SHA/长度、messages/payload SHA、actual max_tokens、2048预留及renderer/model-tokenizer小metadata SHA；服务prompt_tokens必须相等。自然触窗输出not_failure/window_hit_count=1，保留真实完成数；route UID/完成数与observer期望都用actual completed_k。

wrapper仅在PIN332a187…封存原generate/replay两个函数的payload之后插入guard/break，旧工具、消息历史、结果字段、ACK companion与SSE计时仍执行；raw hash或dispatch seam不符拒绝，不是通用未来reader。自然触窗取消旧少于10轮警告，真实轮数/legacy summary事实不伪造。R049实际timed replay复用同wrapper，逐completed输入IDs与producer匹配，重新计算未发k+1仍>96256且IDs/长度完全相同，才记录同触窗停止。原frozen replay实际输出预算32保持，2048窗口预留独立登记，不能把两者写成同值。

旧最长49K预算JSON读取、float/628增长预测与由此导出的静态PASS已撤下；estimated_route_overhead_bytes/predicted_free_bytes=null，route_snapshot_location=CPU pinned。R055a历史628申请/625.69余量仅保留历史事实。新packet/memory_plan/actualdry首先要求R056 canonical measured+D04；根/R必须先确认完整11次有效测量（含真实87K两次）、无服务/输入/显存失败、独立raw复算，旧窗口历史对比只观察，不供partial放行。既有R055b已复核observer/hash不改：加载≥1.5GiB、每业务请求before/after与正常pause采样，现场87K峰值记录；.80不足或开测后失败保留failed证据、user_disposition_required=true交根停问。

新WindowsCPU **85 PASS/1 POSIX skip in 2.16s**（client5、R046b25+1skip、R04955），AST6 PASS，sitecustomize socket guard身份/CVD空/插件关闭、torch未导入。实际pinned client loops + 未改candidate frontend类方法，用合成tokenizer/CPU IDs/SSE测试87100→96256→96257：完成2、第三请求未发送、seed CRLF保留；实际R049 timed replay同k/blocked IDs及SSE计时、错误blocked IDs拒绝、动态route completed_k、真实producer→consumer新window、旧49K拒绝均通过。这不等于本机真实模型/seed前端重算，更不等于GPU余量证明；没有服务器同步/实际dry/正式route画像build/锁/batch/服务/GPU。旧Linux27/52/54不覆盖新版本。

| 文件 | 当前raw SHA256 | LF规范化 SHA256 |
|---|---|---|
| `r046b_d07_t06_prepare.py` | `435c48c5ebf62887ddf21efa6ba625f7585c56e282662f8548d020cb3e86f795` | 同raw |
| `r049_t21_prepare.py` | `ca8f6d5eede260c78acefa28d500b1d283ae316480727349093afd561e01d404` | `616ec17943d1485efb74e87611f7362641062512f8b2eb62ce15bb9fa07e0c53` |
| `r046_seed_agent_trace_v2.py` | `40b00702f998fe4a4eac753c53bc3aa9a4e50c412f6175a8cddf06975a267ce7` | 同raw |
| `tests/test_r046b_d07_t06_prepare.py` | `424f2560093907f6cbd4e8a954ffc64c1c10019a4695cec2c9a6b0b6b5ea1092` | 同raw |
| `tests/test_r049_t21_prepare.py` | `639c9178bad475320a30fb618fc1db0a4fc227e3f41b5d3743dd9ba3961d3f6f` | `7bc9482b0a8b4fa2e256fd4b0680f6ce9123647e89d22ac3e623435423b2beea` |
| `tests/test_r046_seed_agent_trace_v2.py` | `a5a1dbd21bda056d8d74daf135bf390ec1e84dd6b4f60d38f9553f69d1bd670d` | 同raw |

小闭包：上述6项；既有D07/D0/file_prepare、R055b_owned_launch/pause helper、test_r055b_owned_launch fixture及其原CPU闭包沿用；candidate agent_trace/raw、tokenizer/tokenize.py是v2新测试必需，T21 builder/expert_profile/ACK及numpy沿用。真实runtime frontend需候选完整tracked包+FT venv transformers/torch和模型tokenizer/config/template小文件，不加载权重；runtime_sources还绑定canonical writer、候选tokenize.py、model config（旧预算JSON移除）。根重新冻结/Linux/最终路径真实前端CPU/R；R056完整measured+D04→R046b实际dry/R/98304/.80闭环→R049实际dry/R/98304/.88。新client README登记及部署/回滚文档由根owner处理。本分支没有共享源码冲突。

2026-10-07 11:14 | SSH9 02 | ownership/开工：根授权§12 R046b/R049/new seed v2窗口链；读新裁定，不改旧client/产品/冻结源。

2026-10-07 11:30 | SSH9 02 | 交付：98304/.80与T21.88；实际client/前端方法合成CPU契约，85PASS1POSIX skip/AST6PASS。

2026-10-07 11:30 | SSH9 02 | 条件：先R056完整measured+D04，新freeze/Linux/真实前端/dry/R归根；运行采样保留，无GPU静态预算PASS。
