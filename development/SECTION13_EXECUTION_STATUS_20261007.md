# 第十三节执行状态

记录时间：2026-10-07 13:44（ssh9 date）。全部任务完成后才提交发布审批；部署、release/e2 和推送仍需用户明确确认。计划/card 由 M 维护，本记录只汇总执行事实。

R057 与 R058 已分配 02、A 实现正式入口。最初五项 CPU 准备测试未覆盖完整 launch；root 检查后要求补齐 owned controller、模型 worker spawn 观察器、逐臂原始数据保存和退出清理。R058 还补真实 token 门、失败 barrier 中断、有界等待与全程显存采样。两批 CPU/Linux/真实路径空跑/R 启动签未全部完成，GPU 尚未启动。谁先就绪谁先跑，诊断臂 OOM 可继续，R058 OOM 必须停问；比例下降预授权暂停。

队列：R057 → R058 → R040a → 修复与 T16（从 R059 登记）→ R046c → R049 → R048 → R045 → R052 → R044 → R047。R040a 新 v5/base v2/dry v4 把旧 R048 前置改为 R058 measured，原 v4 冻结源和签字保留，不沿用为新版本授权。科学输入、采集器 v4、锚点 v3、窗口 98304/.88 不改。

已保留的 Linux 准备证据：R040a 175 PASS（7fb0d4c7），R045 53 PASS + 两 selftest（a44738d1），R048 26 PASS（8f666e57），R044/R047 48 PASS（23b9529b），R052 35 PASS（0d07bdf1）。它们不代替真实空跑、启动签或 GPU 验收；改变执行版本须重新绑定。

T06 UID 与 ACK 的区别见 T06_UID_BINDING_AUDIT_20261007.md：普通 API id 和 D0 reqs 能关联 UID，但现有客户端还依赖暂停开关才输出的 ft_dev ACK，需新工装迁移。G3 必须 trace 单变量。旧 19–34 小时预算已失效，待诊断确定修复范围后重估。

协调日志只追加，真实 ssh9 date，每行不超过 150 字；root 已持续同步饕餮实际读取的 /data2/_shared/run_monitor/COORDINATION_LOG.md，保留原前缀。每批结束简报，最终放行仍待全部结果。

## 2026-10-07 13:49 R040a 新入口 Linux 交付

R040a v5/base v2/dry v4 与原 collector v4、owner v2、anchor v3：Linux完整179 PASS（2.14秒）。报告 `/data2/FreeToken/runs/dev_D16/r040a_section13_cpu_v5_complete_20261007_134927/report.json`，SHA `e412b437972438e05d3069e4c2423799f105ef5ad9a09910b7a436ac06cf6fa1`。两次CPU capsule遗漏probe/AST参照的失败回执均保留，新包加入实际旧依赖，未删测试或替换实际参照；未占GPU、未创建正式R040a目录、未执行正式空跑。前置现要求R058 measured，到队首时再跑真实FILEDRY与R启动签。

## 2026-10-07 14:03 两批实际启动复核中

R057：Linux report `/data2/FreeToken/runs/dev_R057/r057_linux_cpu_v1_20261007_140138/report.json` / `ef9b4ee00ee7fd1708d8cba3c4cac1d6e77004348d16a9f6eb976b50d5c2d0ed`；实际FILEDRY `/data2/_shared/runs/ft_rounds/.dryrun_R057_v1_E2-R057/dry_run_receipt.json` / `1d13c3cfa13d3ffe3263c4b0bb1514b5579b63be529caaa34b76da86f8d88e43`；execution SHA `fa37cf1deab71b0abea4071ddffec15d2a09a6ce10c173cf8b739cf289cd3bdc`。同UID1000/cwd/脚本、守卫CPU验证通过，均0服务/0锁/0正式目录。各自独立R已开始实际启动复核，尚未签字或获得GPU结果。

R058：Linux report `/data2/FreeToken/runs/dev_R058/r058_linux_cpu_v1_20261007_135919/report.json` / `6f5f38d096267d2737d0d93f81d15a90b21cc03ce186ff6bd3bf27bb850309d3`；实际FILEDRY `/data2/_shared/runs/ft_rounds/.dryrun_R058_E2-R058/dry_run_receipt.json` / `c33072658e6b9c0228d105bc8cbe76112dd65013ba4e8e3fcfb4aa84eb7fb485`；execution SHA `97728a23a0ec822e81170d763ff708893d358bb0b7a1928743494f81a02164d1`。同UID1000/cwd/脚本、守卫CPU验证通过，均0服务/0锁/0正式目录。各自独立R已开始实际启动复核，尚未签字或获得GPU结果。


## 2026-10-07 14:12 R057正式启动

R057/batch83已按原队列启动，独立启动签 `7c665e7516b888a950a7940dfb443475d60d60e6617e3107887d56f371531eef`；owner PID2687970/start_ticks144791308。A只trace、B只暂停、C二者、D二者关闭且graph关闭；effb996/98304/.88，四臂各自独立服务进程，诊断不判kept。R只读边跑边复核，root/CPU不访问模型监听端口。

R058也已通过启动签 `6fd20a4757d8f64a19b880b43a121c81fbc1aaf1383c9931837284f02acee4b7` 与只读pin `6360af752e518da6db118178c455dcb754243ed38e946db71f05804c3fc23652`；尚未正式启动，等待R057释放锁。三种生产并发形状在0aa23431/98304/.88下验证，出现OOM即停问。两轮签仅表示source_execution_ready，不表示模型准入或完成。

## 2026-10-07 14:40 R057停止并封存；补跑待裁定

R057/b83在C启动遭TCPStore EADDRINUSE，D未跑。A OOM、B完成均保留，D04 failed_harness和独立闭合通过，GPU无锁。新R057a仅CD/R058端口版本Linux27PASS与同入口FILEDRY通过；已向用户提出§13补跑确认，未起GPU、不沿用旧启动签。完整事实见 results/E2-R057_OOM诊断_20261007.md 及 R057A_R058_PORT_SAFE_HANDOFF_20261007.md。02普通SSE/真实Detokenize侧车CPU7PASS，C2普通双流adapterCPU4PASS；都未取得正式GPU结论。


2026-10-07 14:42 用户最新答复已批准R057a只补C/D，随后使用端口新版本跑R058；先经独立R新启动签。A/B沿用，不重跑，配置不变。root已立即发起R057a启动复核。

## 2026-10-07 14:45–14:53 补跑恢复与最新用户方向

R057a/b84于14:45正式启动，PID2798972/start_ticks145003733；仅C/D，原冷输入SHA cd003af3d6f2713fbcf896fe756fb3baf79e38100f10ae5eb4bdcbc937710632不变，effb996/98304/.88。新启动签ce89fc51400ca2d3ba4fc24dbb5bfd66692a332ef1b63f9cbd6218b92481ac91。C同位置OOM，错误快照保存，14:53仅精确清理该臂私有服务组以解除HTTP等待；controller和锁不变，回执SHA b6841ed123742acc9e18da4df43e897659b51137fe5c8cccb3cc4b4379726c3a。D继续，不改冻源。

R058端口v2实际空跑与独立启动复核已通过，review SHA e93434315d3bb1a8a1b5b0ad570bcad29f97e39074c168441fe362071096997f、只读pin ca056d1a479eba2ebbee3e8f74f7b24f3883919adacc8d2d6f4cbd9a4fe268d2；等R057a封存释放锁立即启动。两批新端口版本Linux27PASS，旧源保留。

用户随后粘贴的新方向优先：不实现新的显存排队；先核实现有KV/会话/GDN状态准入。D07修复trace collector支持layer-major层×子块并保留层优先执行；tracer关闭的默认路径不改，解码trace关闭graph的差异如实记录。CPU、新提交及T16（从R059登记）后再跑R046c，trace与pause不混变量，比例恢复.88。用户队列为R057a→R058→D07修复与T16→R046c→其余按§13；R040a保留，未被取消。请求级OOM隔离只交设计与独立CPU原型，未经用户裁定不合入产品默认路径。发布仍等全部开发测试完成与用户确认。

2026-10-07 15:06 R057a/b84 D04 measured diagnostic_only，独立闭合1fb303ae PASS，62文件/9目录全只读。R058/b85于15:05按已签v2正式启动，controller2860782:145120319，生产0aa/98304/.88，R逐组复核，尚无并发结论。根结果见 plan/01_测试与调研/results/E2-R057a_OOM诊断_20261007.md 与 E2-R058_并发显存_20261007.md。

## 2026-10-07 15:40 R058封存与R059 v2空跑

R058/b85三场景完成0 OOM，D04 measured，独立闭合SHA7bb300f1362eac4285df833cdc21482de17f705eb975ea4f09faf787bcad9411；60文件/13目录只读。最低剩余显存377.7/1055.7/381.7 MiB，不代表任意负载安全；没有纯排队时长/ETA或每条actual body SHA。结果报告已更新。

D07候选151ee718b88882b57dba75317bb53c697d5f235f（父effb996）已新建干净服务器worktree，同源native proofSHA93b56f403ad08062c222cbe60e8f3acc703c174e7c4387c7d41e15c74fb483e1；候选Linux33PASS/1CUDA skip。R059 v1 FILEDRY因guard误写/runs绝对路径在服务前停止；原冻结源不改，无formal/batch/GPU，v2修真实/data2/FreeToken/runs路径。v2源/data2/FreeToken/runs/dev_T16/r059_d07_source_v2_20261007_153844，MANIFEST0d3b7578a7a9d8f758df792b73f0a70ffc5d659c0e16f7f0ff60feda58ac1b92；Linux9PASS报告673aa1758a8350110b64bd2a1c54d8b352390bd029cada8f7ecb59be88143a8c。15:39真实空跑PASS，4臂文件操作、UID1000、动态端口13181，0服务/0锁/0batch/0正式RID，独立R正在实际启动复核。

最新用户方向：暂不新增排队；D07保持layer-major分块、trace解码graph差异如实声明。OOM隔离只交独立设计与CPU原型4PASS，未合入产品默认路径，不能称已实现worker存活/恢复。R046c普通会话实测工装由02完成，候选151ee/.88/98304；新C2 R049 ordinary完整runner同步准备，旧pause-ACK stub不授权GPU。R040a仍在余下队列，未取消。全部任务完成后才申请发布。


## 2026-10-07 16:15 R059标准交接纠正待裁定

四臂完成，无OOM或工装失败。root给R的交接误写256，权威T16卡实际要求128，冻结脚本及四臂一致按128执行；输入/token/全文/预填/D0一致。独立v1已经只读记NOT_MET，因此保留记录并按§13停問用户；新独立纠正依据SHA411d54ecbf871393c1557241deae6b04f38ef811c236535e9cebb605db8ab69f，不改判或封存kept。GPU无锁，后续正式GPU等待裁定。R046c和R040a/R049仍继续CPU准备，尚不算GPU就绪或验收。


## 2026-10-07 16:24 锁定版CPU与源码冻结

Linux guard 25PASS，真实candidate packet（clean151ee）及两.so实际import完成；CUDA未初始化。修正D0前缀/实际prefill路径、G3输出路径差异完整记录与标准化、G3同一API/TCPStore对、memory父/worker birth绑定；packet读取真实checked_worktree.commit。当前源码包 `/data2/FreeToken/runs/dev_R046/r046c_section13_source_v1_20261007_162252`，源MANIFEST SHA `8b7d1f368abbf0fc8aabaf858b0843a7c5e7eae3de39ca67da611a5b6bb40236`，LinuxCPU冻结回执SHA `784cb72958f68d7de7790296b6f1cb66a2facf8016b33a50339c5ae4ad053358`。全部14个源码/测试文件逐字节等于实际Linux25PASS来源；小报告原样保存，未复制失败轮次。

本包仅源码/CPU准备，不是R启动签。R059用户纠正裁定尚待，故未执行正式FILEDRY、未拿锁或启服务；获裁定且R059 kept D04闭合后才用本入口同路径同用户空跑，再由R正式启动复核。

## 2026-10-07 17:22 CPU准备更新

- R059：权威T16要求128；四臂均128且逐位证据齐。root交接误写256导致v1 NOT_MET，保留v1及独立纠正依据，待用户批准新复核。无后续GPU启动。
- R046c：冻结v2 `/runs/dev_R046/r046c_section13_source_v2_20261007_164507`，MANIFEST `c02939113b5625af1d096ec27977abcaf524057d5746e6ba2084477ac2a0dd2e`；Linux25PASS。修复只读源复制继承权限；旧v1不动。仍缺R059 kept、正式FILEDRY和R启动签。
- R049：root接管C2工装；新实际Linux22PASS、目标tokenizer与画像CPU检查、九臂CPU文件演练完成，独立R预审无P0；实际源/证据见 [handoff](R049_T21_ORDINARY_V2_HANDOFF_20261007.md)。尚无R046c前置、正式FILEDRY/R签。
- R040a：新v6源41文件MANIFEST239765e…b1ce；CPU89PASS、17项collector inventory报告d71619d…34a0，独立R collector review648eacf4…c714可消费。真实同入口FILEDRY `/data2/_shared/runs/ft_rounds/.dryrun_R040a_v6_20261007_171611/dry_run_receipt.json` SHA `4a2731ef6ba29ad5eb8a84c30fcf44917b475d944e168bea298a23d6a62adbb4`，36服务范围/685文件，模型、请求、锁、batch、正式RID均未创建。正式GPU startup review仍未签。
- 未实现新显存队列；R058三场景0 OOM只支持这些已测场景。OOM隔离仍为设计/CPU决策原型，未合入产品。全部任务完成才进入发布审批。
