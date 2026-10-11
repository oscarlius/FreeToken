# R026 原分块投影诊断启动证据（2026-10-05）

目标：保持R023原4096分块和同一8257输入，比较冷请求与缓存8192后的65行首层投影；只作归因诊断。
前置：R023原not_met、R022默认门kept和R025同分块诊断kept均保留；新诊断不授予T17或E2-base.1接受。

独立verifier `d14_gate_review`完成只读预启动审查，修复后的准确阶段无正确性阻塞：

- 阶段：`/data2/FreeToken/runs/dev_D14/projection_cc7819fff546`，18个源码绑定均非链接、无写位、SHA一致。
- CPU报告SHA：`7e598d0264f52213aee4d661cda57bec68ae0f3cef81c064f3b620e9e299884d`。
- Linux观察器/服务12PASS，含真实Torch CPU序列化、signed-zero字节比较及竞争写者负对照；原门10PASS，语法及正常spawn通过，CUDA未初始化。
- 观察器包装实际PLE bound method `_short_conv`；decode在坐标检查前排除；只记录六类、各65行的CPU张量，要求UID、slot、实际cached/device/extend与源码哈希一致。
- 张量通过`open('xb')`后交给Torch保存，receipt/final也独占创建；先到的其他写者字节保持。
- 控制器绑定准确阶段和报告，在实际回执中复核全部来源、4096分块和diagnostic_only；锁、进程身份与停止协议复用已审查的T17单写者实现。

保留的前期阶段：`projection_7531b1f73fdd`因CPU环境变量名错误失败；`projection_a8952e0fb0f6`CPU通过但独立审查发现snapshot非独占保存。两者均未启动GPU，保留作失败/修正证据。

实际启动：`E2-R026-diagnostic-T17`，batch54，batch PID/PGID/SID547926，birth ticks122463873；冻结执行目录`/tmp/ft-t17-projection-l7qnivau/`。暖服务PID548647、birth ticks122464527。启动回执为`development/t17_projection_E2-R026-diagnostic-T17_launch_receipt.json`。

只读监视：`python development/t17_projection_monitor.py E2-R026-diagnostic-T17`；全部测量和所属进程终止后才执行CPU原始复算及独立封存审核。服务HTTP就绪或启动回执不作为诊断完成证据。

## 实际失败及修正阶段

R026 未完成诊断测量：实际配置 `ple_layer_ids=[2]`，旧观察器却假设 PLE 位于 decoder0，加载后安装时报 `NoneType.value_proj`。这暴露了旧假对象测试的覆盖缺口。R026 已封存 `failed_harness`，63 项清单、18 份运行来源和 23 份原始文件经独立只读复核，详情见[失败报告](../plan/01_测试与调研/results/T17-E2-R026-diagnostic-T17_20261005.md)。上面的预启动通过记录只代表当时检查，不构成实际 GPU 测量通过。

修正阶段 `/data2/FreeToken/runs/dev_D14/projection_caf94387505a` 有 19 份冻结来源，CPU proof SHA 为 `85310fd65f781b755cb374a3aa4c2c5716907c723a58f9371f5e326a67a9bf0d`。Linux 观察器／服务／真实配置 16 PASS、原门 10 PASS、编译及正常 spawn 通过，CUDA 未初始化。独立 verifier 检查实际 stage/log/source hashes 与只读权限，结论 GO。

修正内容：GDN decoder0 与 PLE decoder2 分别选择；启动在导入引擎及加载权重前验证实际配置 SHA 与层声明。模型别名 config.json 是合法链接，准确解析到 `config.json.qwen4_exp.orig` 后验证字节及结构，不能因链接本身拒绝已声明模型配置。此前 `projection_e9fa4ca91e7e` 的链接拒绝失败亦保留，没有 GPU 测量。

截至本次复核，修正投影阶段尚未 GPU 启动；单 GPU 由 R027 的 `prefix_numeric_65b32b3fc54a` 诊断占用，它与本投影阶段属于不同工装。

后续实际启动：R027 在00:33:42完成测量并释放所属锁，独立监视确认batch与两服务均不存在、GPU4MiB。随后caf943修正投影轮启动为 `E2-R028-diagnostic-T17`／batch56，batch PID/PGID/SID618600、birth122614666，warm服务619025、birth122615309；19份运行来源与CPU表一致。冻结执行目录 `/tmp/ft-t17-projection-0xk1x8a_/`。实际启动回执及早期monitor分别保留为 `t17_projection_E2-R028-diagnostic-T17_launch_receipt.json` 和 `..._initial_monitor.json`；这仍是启动证据，终态结果待原始CPU复算。

R028随后在初始化时失败：HF配置PLE id2为一基编号，候选 `parse_config` 明确减1，实际零基owner为decoder1；caf943误断言decoder2。R028已封存failed_harness并完成8098回读，上面的GO仅保留当时检查历史，不构成目标结构正确的证据。R026的旧编号解释通过独立审查的追加更正保留原声明，原始文件/判定/清单不变。

当前独立审查GO阶段为 `/data2/FreeToken/runs/dev_D14/projection_95638b538008`，CPU SHA `5336d493a67695f46e1ba634d34556678ab9af907ee503640491f3cda11428f4`。Linux观察器/服务/配置17 PASS、原门10 PASS、编译及正常spawn通过；实际candidate parser SHA72905266…14607被执行并验证HF[2]→parsed[1]，CUDA未初始化。19份来源及日志均只读并逐项核验。

该阶段实际启动为 R029/batch57，主进程PID/PGID/SID652970、birth122686573，warm653353、birth122687205，冻结目录 `/tmp/ft-t17-projection-vfbdvzmg/`。回执及早期monitor保留。R029只记录绝对8192..8256的六类suffix投影；共同前缀4608..8192的HC各阶段没有在本轮记录。
