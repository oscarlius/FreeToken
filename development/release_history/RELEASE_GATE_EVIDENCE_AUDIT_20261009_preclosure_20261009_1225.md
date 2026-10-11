# 发布门证据审计（2026-10-09，保留链校正）


> **11:52 当前状态**：R066c/b131已在独立启动签核与root实际admission后开跑，3服务/5调用冻结范围，服务X加载中；终审待定。R063a kept仅E3。发布门等待R066c分类c与D04，FTD/v5尚未生成，分支部署推送未执行。



> **11:45 当前口径**：用户已澄清逐字字符串判定与逐提示0/a/b/c分类；R066b四原始回复冻结前自检为异常/异常/干净/干净，与要求一致。R066c本地76、Linux101项CPU验证及实际FILEdry通过，候选481/3服务5调用，待独立启动复核后开跑。R063a kept只归E3，不绑定481门。C3按尾段≥65已证、≤64正确性待证。FTD/v5待R066c分类c终审；分支部署推送未执行。



> **11:34 当前状态**：R063a/b130 已独立终审+D04 kept，4服务/48调用与13/13完整尾段通过，78原件哈希不改，只归E3 D12；GPU释放。发布候选481门等待R066c共享前缀判别分类c，R066c CPU本地22/Linux47通过、原提示字节核对通过，尚未GPU开跑；分类“异常”含义待澄清。FTD/v5尚未生成，分支/部署/推送未执行。


> **当前状态（2026-10-09 11:20 用户修正）**：R063a/b130 继续完成终审封存，仅归 E3 D12（8f6a912），与发布候选481d3a7的门解除绑定。新增批准 R066c 共享前缀判别3服务/5调用，R063a释放GPU后执行；发布门等待R066c分类c与独立终审。D20缺口扩大为现算尾段≤64（含1）；T17仅覆盖尾段≥65。分支、部署、推送分别审批；Strata22/345未批准。以下早期状态按时间视为历史。


11:07当前状态：R063/b129已独立终审+D04 failed_harness，77原件不改；错误仅为合法PID后缀被新增断言误拒。第一次常设重试R063a/b130于11:06正式启动，原4服务/48调用；候选/配置/提示/判据不变，原cold_id显式冻结。v2 CPU本地/Linux34/34、实际FILEdry/独立startup和root四消费者通过。R066b c kept保持；发布门等待R063a独立终态/D04，FTD/论文v5尚未生成，未建分支、部署、推送。

10:57当前状态：R063/b129四臂结束后的比较报工装错误：新增默认关闭断言误拒合法PID后缀。独立actual参数与文本/full-tail复算确认failed_harness；原轮待D04封存，不记kept。新R063a仅复用原pinned strict_args修复断言，候选/配置/输入/判据不变，CPU本地与Linux33/33、实际FILEdry通过，待独立启动签核；按常设最多2次重试授权接续。R066b c kept保持，发布门仍未闭合；FTD/论文v5未生成，分支/部署/推送未执行。

10:29当前状态：R066b/b128已独立终审+D04 kept，实际1服务/4调用，无重试，两对均含own、无other/U+FFFD/非法control，热8256与独立冷0/0有实际缓存/并发证据。R063/b129已续启原授权4服务/48调用的D12默认关闭门（8f6a912 E3分支，不是合入481发布候选）。发布门待R063终态；D不补跑，D20只读同end查找问题已确认。未建分支、部署、推送；下述旧状态按时间保留为历史。

## R066b 后的当前 D16 证据（R063 在途，发布门未闭合）

[最新用户判据](../plan/R066B_CANARY_V2_AUTHORIZATION_20261009.md)替代先前冲突的全文比较条件。旧机器verdict保持；下表是新判据所引用的具体子范围，不能把旧轮整体改判为通过。

| 当前条款 | 已测范围和结果 | 边界 |
| --- | --- | --- |
| 普通单请求冷跑跨进程一致 | R040j interleave_3 single、R065 A1、R066a B1正文同SHA256 `9845c3860e326f437ad9fa6759c0c7e1bcca71a4ce3a37b702c5a76c9dd1cf4c`，同prompt UTF8SHA `9aa87d71a2bc70d4e3101dfa5be01bea8541af8cca0934915751c68efec5a0b6`；length、usage8257/128/8385 | 三个新进程的该请求；不是所有prompt或并发/热路径全文不变 |
| 热路径与同结构冷参照逐位一致 | T17 R036沿用14组+R038新测14组，28/28，用户保留；尾段≥65 | 1-token热路径未与同结构冷参照逐位比对；D不补跑 |
| 并发无串扰（共享+独立前缀） | [R066b/b128](../plan/01_测试与调研/results/T20-E2-R066b_20261009.md)1服务/4调用，c_met=true，独立/D04 kept；own均完整、无other/U+FFFD/非法control，API重叠且热8256/冷0-0有实际cache证据 | 指定两对canary；API重叠不证明物理同batch，普通ASCII拼写变体与截断重复已披露 |
| finish/usage有效 | 前述普通冷三次length128一致；R066a C长请求同8257/128/8385；R066b四次length32，usage与实际prompt/token预算相符 | R066b为不同max32/EOS协议；不能要求它与历史max128请求usage数值相同 |
| 发布门接续条件 | R063/b129既有四臂/48调用运行中，D12默认关闭，独立startup复核通过 | 该轮候选8f6a912、parent effb996是E3独立分支，未合入481发布候选；尚待terminal、独立R、D04 |

并发时或命中前缀缓存时temperature0正文可能与单独普通冷请求不同，两条已知限制保持。warm2同路径/零hit的[只读处置](WARM2_READONLY_DISPOSITION_20261009.md)已完成，正确性门移除；R056性能数值不改。完整发布门仍等待R063，发布方案为草稿、FTD/论文v5尚未生成。

## R066最新授权与R065解释更正

[用户最新指令](../plan/R066_DISCRIMINATE_V2_AUTHORIZATION_20261009.md)更正R065判据：A2实际命中前缀8256，仅重算1 token，比较的是冷与热，并非两次冷请求。热路径正确性按T17同结构冷参照，不与普通冷请求直接等全文。R065原not_met及其独立/D04封存仍保持；先前“单请求确定性回退”的解释不再作为当前产品结论。

R065 A1与R040j interleave_3 single正文SHA相同，两个新进程、不同候选且无前缀命中，已核为冷跑跨进程一致旁证。新R066执行B冷1、D同结构冷1、C两对并发4调用，上限3服务/6调用。D复用既有FT_DEV_PREFILL_SCHEDULE：完整8257层优先预填保存8256内部检查点，再ordinary重算最后1 token；模型实际page64、FLA64、QSA4，LCM64及既有parse/admit已CPU核对可表达，不新建工装。

发布门仍待R066终态；满足后才采用“冷跑跨进程一致、热与同结构冷一致、并发无串扰、finish/usage一致”口径。R040j/R065原判保持；warm只读移出正确性门的处置保留。下述08:30及07:34结论是历史，不覆盖本次新授权。

## 08:30 补充指令：当前有效裁定

**最新实测：[R065/b125](../plan/01_测试与调研/results/T20-E2-R065_20261009.md)在服务A发生not_met，独立终审与D04封存均已完成。** 同一进程内长请求串行两次全文不同；两次finish均length，token usage均8257/128/8385，第二次实际cached_tokens=8256（第一次该字段缺失）。实际仅1服务/2调用，B/C未启动，单请求确定性条款a不满足，新的D16发布判据尚未生效；不继续R063、不自主重试。24原件不变、全目录只读、history/closed consumer通过，child/API/组/端口、锁及GPU已清理。warm说明的正确性门移除保留，但完整发布门仍未闭合。

[08:30用户指令](../plan/SUPPLEMENT_20261009_0830.md)优先于下述07:34历史状态。新R065使用发布候选481d3a7，最多3服务/7调用：A长请求同进程串行两次、B新进程一次、C原长短并发及两个长口令请求并发。单请求三次全文/finish/usage一致、并发无串扰且finish/usage一致时，采用新的D16发布判据；并发全文是否与单请求相同仅作为批不变性观察。任一确定性或串号检查失败仍判not_met并停报，不补跑R040j剩余两对。

warm2的[一页只读说明](WARM2_READONLY_DISPOSITION_20261009.md)已完成：现有warm初始化未建立稳定槽命中的前提，warm/cold统一走split预取入口；本次零hit不证明缓存损坏，也不验收正hit分支。按用户新口径将warm2移出正确性发布门，稳定命中、驻留策略与收益验证转E3/D15；R056原性能数字不改，R040h原待定状态不改。R065尚待完成，发布门当前未闭合。R040j原not_met及既有封存元数据均保持，下述07:34历史阻塞描述不再代表当前授权状态。

**当前结论：发布门未闭合（07:34更新）。** 本文读取既有结果、封存/保留元数据和候选父链，不改变既有 verdict。01:00 指令的门为 **T17 + R041 + T20（含 D16 补项）+ OOM 恢复**。T17、R041、R056、R064和R061f各有已封存范围；OOM恢复已通过本次批准的1服务/3调用验收。D16的R040j长请求API全文不等，已D04封存not_met；warm验收仍缺实际命中证据。

## 可追溯覆盖表

| 门项 / 结果 | 真实候选和当前封存/保留事实 | 当前可用覆盖 | 精确未覆盖或边界 |
| --- | --- | --- | --- |
| T17 | `a9dca443cd07e1f60d1533e0a678935a09d21636`；R036 沿用 14 组、R038 新测 14 组，合计 28/28，D04 `kept` | 28 组续算逐位门 | 不含后续 OOM 恢复或 T20/D16 补项 |
| R041 | `0aa23431e5b800797543bdecbf35a01045131d7d`；cold 与四组 warm 对照经独立原始复核，342 原始文件 D04 `kept` | D17 默认冷请求及四组续算兼容 | 不替代 T20/D16 或 OOM 恢复 |
| T20 主体已测部分 | `0aa23431…` E2-R040/b71 原件 D04 为 `failed_harness`，但用户已要求保留其已测部分、不重跑 | 7 性能臂、60 题、Agent 冷/暖/编辑三趟、4/4 续算抽样；60 题后来 CPU 复算为双方 47 PASS/11 TRUNCATED/2 ANSWER_FAIL，逐题字段 60/60 相同 | 原 round 不是 `kept`；本审计不改变既有用户对历史测量的沿用/汇总许可 |
| 发布性能 R056 | `0aa23431…`，98,304/.88，E2-R056 11/11，D04 `measured` | 已批准的发布性能口径：32K TTFT 6.465s、34.33 tok/s；64K 13.13s；87K TTFT 约18.5s、decode 约30.3 tok/s；跨 R040 73,728 窗口差异只作扩窗代价披露 | `measured` 不是 `kept` 或发布批准；87K 使用 any-delta 口径，不与 content-only 指标混称 |
| R040a anchors | `0aa23431…`，E2-R040a failed-harness 闭包保留 **6 个完成 anchor arms** | 6 anchors 已由后续 R040b/R040g 保留链沿用；不再作为 R040i/R040h 的新建范围或要求重跑 | 本审计未发现需要重新审批这些已允许沿用的 anchors |
| D16 保留完成项 | `effb9969706922ddad9e59b96377e46469ebe97f` 的 E2-R040g/b113 为 failed-harness，但其 retained binding 绑定 4 parking + 2 cache-cold，共 6 completed cases | six cases 的输入、128 采样 token、全文、logit/state 比较已独立复核；15 份元数据与 sealed manifest 绑定 | `accepted_full_D16=false`；不能自行扩展成完整 D16 verdict |
| D16 历史 slots 链 | `0aa23431…` 的 R040c slots2、R040d 首 slots4 batch0 保留；**R040e/b104 实际完成 9 个 terminal scopes** 后才 failed-harness | R040e scopes 是 `dev_D16_4_batch_1_None`、`dev_D16_4_single_0_0`、`dev_D16_4_single_0_1`、`dev_D16_4_single_0_2`、`dev_D16_4_single_0_3`、`dev_D16_4_single_1_0`、`dev_D16_4_single_1_1`、`dev_D16_4_single_1_2`、`dev_D16_4_single_1_3`；其独立 slots4 group review 保留 batch0 四输入各 128 token 的逐 token 一致比较 | R040e round verdict 仍为 `failed_harness`，group review 为 `PARTIAL_RAW_EVIDENCE_ONLY`，且还有 14 scopes；本次未读取到将该链与 R040g 六项合成为 terminal D16 verdict 的最新 closure，故只记“保留、未合并终态” |
| R040h / R040i / R040j 剩余 D16 | R040h无真实warm命中而待定；R040i就绪轮询failed_harness；R040j候选effb996，5服务启动/6调用，独立终审与D04 not_met | 短请求pair_0等价；长请求pair_1同输入、同finish/usage而全文不等，第83字符开始分叉；49原件保留 | 两对未测，warm2未运行；内部根因未定位，不能作为完整D16通过。全部GPU按用户规则停止 |
| OOM 默认门 R064 | **OOM 候选** `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` 对 `0aa23431…`，E2-R064/b119，4 services/48 calls，D04 `kept` | OOM 产品改动的默认路径 parent/new 结论：128 completion tokens、finish `length`、全文、D0 prefill/decode、business-prefill sequence | 这不是 D15 门，也不证明 OOM 后 API/worker 的恢复 |
| OOM恢复 R061f | 候选481d3a7，1服务/3调用，独立24项终审通过、D04 measured；30原件不变，closed consumer通过。d/e保留failed_harness | 同一API五项强身份、UID隔离、waiter1、新epoch、旧worker退出、完整128 token与SSE正文相等 | 本次公开chat路由单次GPU故障恢复；其他三协议有官方SDK真实路由CPU证据，不外推为各自GPU故障或压力验收 |

## 当前 D16/T20 的正确读取方式

- 不应再以 R040c/R040d 的早期 failed-harness 作为最终 coverage 叙述。最新可消费的保留链是：R040a 的 6 anchors、R040g 的 parking4/cold2，以及按原候选身份保留的 historical slots；R040h runtime 显式消费 `R040G_RETAINED_PARTIAL_BINDING_20261008.json`，不复制 raw。
- R040g 原批次在第七服务 warm_0 的 **readiness/generation 前**因 collector int64/int32 问题终止；封存记录因此将剩余精确收敛为 warm2/interleave6。R040h 随后的实际 warm 不能证明 hit，已改为待定，不得改写为产品 `not_met` 或纯 harness 故障。
- R040e 不是只有准备：b104 已完成上述 9 个 terminal slots4 scopes，且有逐 scope retained review、slots4 group review 和 failed-harness D04 review。它们仍是 partial raw evidence，不能替代 final D16 verdict；在第 10 个 scope 的 `multisession_probe` 缺失后，round 按 9 complete / 14 remaining 封存。
- R055a 已逐位复核的六个默认关闭冷臂是已有用户决定允许的默认路径依据；R055/R040a 的保留和 R056 的发布性能采用均不因本审计要求再次审批。R056 跨窗口比较按既有批准只披露为长窗口代价，未套用 same-window 7% 判据。

## 候选关系与未闭合条件

候选父链为 `0aa23431 → 4c878f6 → d577e32 → 481d3a7`。所以 0aa 的 T20/R041/R056 是 481 的祖先基线，不能被描述为“481 上重新运行的 T20”；R064 和 R061f 才是直接面向 481 的通过门证据；R061d/e失败原件另存。T17 的 `a9dca443` 通过 R041 的 `a9 → 0aa` warm 对照进入该基线。

**warm跳过仍是独立需要用户裁定的D16验收缺口；R040j的长请求不等价也是当前阻塞项。** 当前 R040i admission 将其写为 `warm_skipped_no_hit_evidence=true`；这限定 SDK interleave 的执行范围，却不会生成 actual expert-hit，也不会把 cache-hit/warm 结论变为通过。当前interleave API测量已not_met，不能作为已通过的替代证据；后续若修复该差异，warm实际命中的验收边界仍须单独裁定。

R040j已独立复核并D04封存not_met：计划6/8，实际5服务启动/6调用，pair_0相同、pair_1全文不等、两对未测，见 [R040j结果](../plan/01_测试与调研/results/T20-E2-R040j_20261009.md)。全部后续GPU停止，等待用户裁定。R061f已通过并封存，见 [恢复结果](../plan/01_测试与调研/results/OOM-E2-R061f_20261009.md)。R040i于07:03按就绪轮询缺陷封存failed_harness，19份原件保留，见 [R040i结果](../plan/01_测试与调研/results/T20-E2-R040i_20261009.md)。发布分支、部署及推送仍须各自批准。

## 读取来源（未重验大 raw）

- [01:00 执行指令](../plan/ROOT_EXECUTION_DIRECTIVE_20261009.md)；[01:30夜间授权](../plan/NIGHT_PREAUTH_20261009.md)覆盖冲突条款；[OOM 候选父链](OOM_RELEASE_CANDIDATE_CHAIN_20261009.md)。
- [T17 R038](../plan/01_测试与调研/results/T17-E2-R038_20261006.md)；[R041](../plan/01_测试与调研/results/T16-E2-R041-gate-D17_20261006.md)；[T20 R040](../plan/01_测试与调研/results/T20-E2-R040_20261006.md)；[R056](../plan/01_测试与调研/results/T20-E2-R056_20261007.md)。
- [R040g result](R040G_RESULT_20261008.md)；[R040g retained partial binding](r040h_d16_v1/runtime/R040G_RETAINED_PARTIAL_BINDING_20261008.json)；[R040h runtime README](r040h_d16_v1/README.md)；[R040h reclassification](r040h_d04_close/reclassification_v2.json)；[R040i admission](r040i_api_d16_v3/R040I_V3_D04_STARTUP_ADMISSION_20261009_v1.json)。R040e 的只读远端元数据为 `/data2/_shared/runs/ft_rounds/E2-R040e/round.json`、`MANIFEST.sha256`，以及 `/data2/FreeToken/runs/dev_D16/reviews/E2-R040e_*` retained reviews。
- [R064 terminal review](R064_TERMINAL_REVIEW_20261009.json)；[R064 D04 closure](r064_d04_close/closure_v1.json)；[R061e runtime scope](r061e_oom_runtime_v1/README.md)。
