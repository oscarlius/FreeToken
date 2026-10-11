# 2026-10-10 夜间执行工作报告（未终结）

真实写入：2026-10-10T02:49:27.961512+08:00。当前依据：`NIGHT_SUPPLEMENT_20261010_0035.md`。本文件不能代替 09:00 终态汇总。

| 项目 | 当前结论 | 实际服务 / 生成调用 | 证据及边界 |
|---|---|---:|---|
| 原观察窗口 | 截断 | 306 次只读样本 | 22:41 停服截断；不称隔夜通过 |
| R067d 原轮 | 用户改判 failed_harness | 3 / 7 | 热臂六调用 valid；naive 冷缓存无检查点槽；保留原判定字节 |
| R047/T03b 原轮 | not_met，已只读封存 | 6 / 24 | snapshots 全零，coverage 未达 |
| R052a | not_met，已只读封存 | 1 / 9 | full=13554，floor64=13504，cache=13376，低于 floor 128 |
| R044 | failed_harness，已只读封存 | 1 / 0 | DEV_D16 capture 路径约束导致启动失败 |
| Strata S1 | 有效测量子集 | 1 / 11 | 无MTP；parallel=1；ignore_eos 256 未受支持 |
| Strata 原 S2 | failed_harness | 1 / 0 | 工装读取外层日志；不构成 MTP 产品负结果 |
| Strata S2 retry1 | 有效测量子集，已独审封存 | 1 / 11 | 引擎 stderr 真切片证明 draft loaded；parallel=1；两路请求排队 |
| D09 原 T16 | failed_harness，已只读封存 | 4 / 48 | PID 适配器参数拒绝；无产品负结论 |
| R067d retry1 | not_met，已独审 D04 封存 | 4 / 8 | 默认 hybrid_radix；首冷 A=B 但 hot≠cold token0；按规则停止余格；D12 不触发 |
| D09 T16 retry1 | kept，已独审 D04 只读封存 | 8 / 100 | 仅默认关闭门；完整 T16 实际4×12+4×13=100；不等于 D09 启用机制验收 |
| R047 计数器诊断 | 正在运行 | 限 1 / ≤3 | 独立 dev b609；原 not_met 不改判；真实 native 复用经独审 |
| Strata S3 | 已独审，等待 R047 实际清理 | 限第四服务 / 11 | 仅 parallel=2 配方差异；不增加 batch-MTP flag；实际状态待测 |
| D10 默认关闭 T16 | CPU 预检/叶子独审通过，GPU 待跑 | 8 / 100 计划 | v7 启动器、canonical dry v3；不是 GPU 结论 |
| D10 启用原型 | CPU_READY，GPU 待跑 | 限 1 / ≤8 | 仅实际 D10 T16 kept 后准入；逐组 >30、分支真实执行及256输出门 |
| 最终恢复 481 | 待执行 | 首冷冒烟一次 | 最晚07:30开始；逐项比对df77cb…；失败先停481再回滚184，并停后续GPU |
| 新观察窗口 | 尚未开启 | 只读至09:00 | 必须与已截断原窗口分开报告 |

D09 retry1 D04 manifest：`0bf2dfd9a4b677875f8a9c9a2c876a07fee3c33555f618635d10e9c746b97de0`。R067d retry1 D04 manifest：`928bfbbd7fc30f2134c4e5ece5cc5e3d2ac05f2fa6c779a3f604e9090494f12e`。

Strata 同一 v0.1.41 构建：commit `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`，binary SHA `a1f4bc961395b8d347e3e73d48a35c372000006a42ca9c3ea8abd09fb46aa7a0`。构建在计时测量前已完成，无权重下载或 prepare。S2 retry1冷32K均值约77.17 token/s、短上下文约79.06 token/s；原两路AIPerf聚合64.6189 token/s（S1为48.4182），这是聚合值，不是每路并行吞吐；MTP/spec组合变化不作为纯MTP因果结论。

恢复包审批与首次冷基准均已准备，尚未提前填恢复 PASS。未推送。09:00报告需读取最终恢复/观察终态后再给出具体推送申请；release/e2当前HEAD481、tracked clean，远端 origin 指向 FlashML-org/FreeToken，lukas 指向 lukascechovic/FreeToken。D09/D10/R047诊断开发树均不得混入 release 推送申请。

英文 arXiv 来源稿已独审 SOURCE_READY_PDF_UNBUILT；当前环境无 LaTeX 编译器，未生成并审查 PDF，未提交 arXiv。中文 v5.2 范围仍限 §8 / C5，多卡部分保持推导/方案标注。


## 追加进展（真实写入 2026-10-10T03:06:58.883704+08:00）

- R047 诊断已完成唯一服务的三次调用；完整 worker shutdown 收据存在，准确缺项是 `d0/d0_decode.json`，不是 worker shutdown。工装终态为 diagnostic_harness_failed_post_execution。最终日志 snapshots=0、anchor_none=150、cached_len_mismatch=60、unaligned=3、extra_anchor_token=6、anchor_set=3；只作为有源绑定的诊断观察。独审 `5dd6832557af6779a16eca0d9590233a56895b3494a7fd24200783c89fa600a5`，raw只读manifest `15adc0e74c0f3c4d7061fd6aa8d62fa4f69891ab84058b379afc85e472484f90`。不启动第二诊断服务，原R047 not_met保持。
- Strata S3第四服务11调用完成，有效测量子集独审V2 `050357014e41bb176f3fcd2b6d85767f4f9340733f8e73165bc361df434df3bb`；raw只读manifest `25c25830234a2a7c1a28fc5a4f99deae985c4e4bb27664f601534eac3e9940bd`。原128实际两路20.6089/40.5569 token/s、聚合35.4811，不能把每用户均值30.5829当两路都超过30。S3 batch-MTP未optin；ignore256实际46/60输出，仍不支持。清理代理missingload_v2原终态保留，根已验证同轮inode/device/token并释放残余锁，无新服务/调用；恢复收据83f7cc8d…。Strata实际服务总数4，已达上限。
- D10默认关闭T16已02:58:38准入batch146，完整8/100协议，当前运行中，不提前写kept；启用prototype仍待T16正式封存kept。
- R044原capture路径问题正在CPU侧准备第1次允许工装重试，未改变原failed_harness，不承诺未审包GPU就绪。


## 追加进展（真实写入 2026-10-10T03:33:50.256988+08:00）

R044 retry1 v3 的44个CPU用例、20项源绑定/完整FILEdry封存及实际消费者独审已通过；GPU尚未启动。D10 T16当前进入第六臂CHUNK_NEW，仍未终结；完整八臂清理后由已独审v2协调器接入R044重试，失败路径单独处理。D10启用原型准入构造器独审PASS_BUILD_ONLY，仍未准入GPU。

09:00推送申请的只读范围快照：release/e2@481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9，tracked clean，相对184基线40提交/91文件（11964增加、129删除）。推送候选为origin的release/e2，D09/D10/R047诊断开发树与夜间实验工装不混入；本快照不等于批准或推送。


## 追加进展（真实写入 2026-10-10T04:01:48.430794+08:00）

- D10默认关闭T16：03:53:26八臂测量终结，独审kept SHA `d72a78037e05c46a1eeaeca81bfacadf0b87417472a8c2d3d63cd33cdcf79a4b`；03:58:50正式D04只读封存kept，8服务/100实际调用，manifest `2499985050a757fdc7af12edcf6525b7f34d0269278181357954f1a6f8162696`。V10原型真实formal消费者CPU回读通过；该门不等于启用原型测量或产品验收。
- R044 retry1：03:53:52由已独审v2衔接器在D10实际8-owner清理后启动，batch147，子进程755381:167012231；源包v3、候选0aa，预算6服务/144调用不变。当前ordinary/B1正在加载，未写终态判定。原R044 failed_harness保持。
- 英文来源V6：独审SOURCE_READY_PDF_UNBUILT，review SHA `d24ae36ee8609b2a0abdea4563db67110b04dd4529fee987f573b0f03aecec78`。历史原R067d failed_harness与retry1 not_met、D09默认关闭T16 kept/启用机制待验收均分别表述；V5的PARTIAL及原件封存，中文未改，仍没有PDF/arXiv提交。


## 追加进展（真实写入 2026-10-10T04:25:23.074642+08:00）

- R044 retry1 已在 04:23:24 以 D04 sealed closure 终结为 `failed_harness`：RID `E2-R044-night-20261010-retry1`，实际 1 服务 / 24 生成调用，`accepted_measurement=false`；只读 round SHA `0dac948c30e4e2af5d6328e90f02459680b3975a7d46341111287ef8ec22004e`，manifest SHA `5a316836583ca787d988f33d361af8256792d8136b4270813b4712417ab6e366`。这不是产品负结论，原 R044 failed_harness 与 retry1 原始字节均保留。
- D10 启用 prototype 的 actual root controller 已于 04:23:51 启动：RID `E2-D10-PROTOTYPE-night-20261010-v10`，PID `836956:167192038`，限 1 服务 / 至多 8 调用；启动前 GPU empty，启动收据绑定 runner SHA `de48f9afc5727334a2e7c3e552092e2c6d606b60513edc630e95ae6191eb58cb`、admission SHA `b5aba3f20db5d521dbb2bbaa2e8ae499e822c1e301e62c64fb4900b99c9a040b` 与独立启动审查 SHA `9b193ae58f08cc6da3c163ff3434d0983f158cf9bcf7a03d5d74d8feb1a5c939`。该行仅记录实际启动，不提前写测量或产品结论。
- R044 retry2 CPU 工装已 root source-freeze，RID `E2-R044-night-20261010-retry2`，候选 `0aa23431e5b800797543bdecbf35a01045131d7d`；24 项来源和 FILEdry v3 已只读绑定，dry receipt SHA `355cb7f1e6ac3cf9fae3f8881b38e36fe2b53956ca3752c0b36b7149ea793170`，冻结收据时间 04:24:41。仍待独立 CPU 审查，不启动 retry2 GPU。若后续获准，其运行时仅按 retry1 的实际 24 调用约每臂 10 分钟作工作估算，6 臂约 60 分钟；这不是时限承诺，仍受启动、清理与失败停止规则约束。


## 追加进展（真实写入 2026-10-10T04:34:20.204649+08:00）

D10 启用原型 batch148 已完成首组原提示两次调用（输出46/58）；两路实测5.855077/1.064367 token/s，均低于>30，后续profile1–3及fixed256未跑。直接方法回调证明两个请求完成了错相位方法；probe v4误读不存在的Batch属性，false字段不作为资格证据。原终态因显存释放延迟为failed_harness，保留原SHA e654be…；04:31:00根逐项核对同轮进程、双栈端口、GPU空闲4MiB及精确锁token/inode后完成清理，无新服务/调用。独审恢复补充SHA541e84c0…仅允许写作“首组观察性可行性负结果”，不改判正式not_met。raw只读manifest42336fd99cbee63a3d7bc6afc9d2a7797cf84cfd78e3b56deccbd5ab2f81c641。

R044 retry2已于04:31:01启动batch149，是最后一次允许的GPU工装重试。实际ROOT工作目录FILEdry v4及53个CPU测试已独审，24源绑定全部只读；旧误复制封存/目录不匹配审批均保留并由新凭据替代。当前第一服务加载中，尚无正式测量结论。独审startup SHA b0cce62e…，源冻结V3 SHA36898fad…，FILEdry SHAfc5443bd…。

恢复审批独审V2再次通过；GPU轮结束即恢复481，无须等待07:30。首次冷冒烟及至09:00新观察仍待实际执行，未推送。


## GPU队列终结与实际恢复（写入 2026-10-10T04:54:40.299704+08:00）

R044 retry2 batch149最终failed_harness，只启动ordinary/B1一个服务并完成冷12+热12=24调用。实际24UID的3581交付token、3594普通sampler行、19非交付ChunkedReq行及13终止后的额外sampler行已独审，delivery errors为空；阻塞点是冻结strict参数读取器未解析出max_prefill_length。两次GPU工装重试已用尽，无第三次。原始外置capture7252文件/4,490,523,098字节已只读，manifest210294b3…285ece；04:51:29正式D04 failed_harness、history check及整树只读完成，formal manifest6a63e112…deafd。完整六服务T10测量未成立，不能据此给产品负结论。

481已04:44:16进入批准的恢复流程，04:49:08完成唯一SDK首次冷冒烟并通过1/1门：512与8257提示各128输出，text SHA/usage/finish reason/API cache及backend cache行均与df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97逐项一致，未触发184回滚。首冷证据现只读，根回读SHA b6f2e4dd…d21e。至09:00的新观察已开始；首条样本引用观察开始前50.99秒的loading watchdog旧记录，故原样保留requires_review问题，后续已读样本健康。不能改写为clean_observation，09:00仍需以实际终态及独审为准；没有新生成或服务变更。

英文稿最新V9来源独审PASS/SOURCE_READY_PDF_UNBUILT，review SHA9a09461e…5a05；V8措辞歧义PARTIAL与全部原件保留。R045有效四请求测量与四路速度门失败、D10两请求观察性负结果分开表述；正文/TeX/中文在V8–V9未变。09:00之前不填观察终结结论或推送批准；未推送、未提交arXiv。


实际写入 2026-10-10T05:20:00.222390+08:00：晨报工具 development/night_execution_20261009/morning_report_readonly_v3.py 与 morning_report_waiter_v1.py 已完成7项CPU用例和独立启动审查；旧V1/V2保留，V2因读取不存在的terminal.until_epoch标记无效，V3使用start.until_epoch。冻结根等待器986245:167526625以nice19/核1,3启动，仅等待实际09:00和原观察terminal；不生成请求、不控制生产、不推送。届时写入新的09:00汇总及具体推送申请，并保留requires_review/自动资格false和首条旧loading样本，需用户裁决例外和批准推送。当前尚无最终晨报，不提前写观察通过。
