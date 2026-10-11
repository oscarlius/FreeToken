# 20:05补充指令 CPU准备归档

真实写入：2026-10-09T20:31:28.158032+08:00；仅今晚CPU准备，不是GPU验收或09:00观察报告。

两份原始指令于20:06:52同步服务器，逐字节核对；[同步回执](../development/supplement_2005_20261009/DIRECTIVE_SYNC_RECEIPT.json)。后续操作手册§11、补充条款与明早报告清单也已同步，旧文档字节另存。

## R067d

第1–4项CPU准备完成，独立审查CPU_PASS。Linux FT venv全相关suite 12 passed、10 subtests。七组真实日志（retry2 seed/T1/T64，481与真正184各短/长）回放，21类样本反例外加usage/POST/独立超额分支与端口超时诊断测试。FILEdry执行真实child实际使用的启动/判定函数，fake probe/Popen共10服务14调用、20唯一端口，无真实HTTP/GPU。

- packet SHA `25151f618dde4dd661cbec26b2ef157e7479706b91736ffb446db53c0a46778b`
- config SHA `5768a39f446eba206d5bc31a584b37d12c109125e2643142bd2844362ce248e1`
- FILEdry SHA `08a884c6b2079fe38a3598046ba39fdae67e54fc7fb00226c70e442b822f774e`
- 独审 SHA `243cfe5b5bc73c51a91bc3e144fa6bfbf6db2c17ae2bb2e99698cb693f0757b5`

[当前绑定与历史排除](../development/r067d_short_tail_v1/CURRENT_CPU_READY.json)。真实GPUchild仍需明早报告实际提交后root预检与准入。独立新轮，工装重试≤2；产品not_met立即停止；按既定停服恢复481/冷基准比较/失败回滚184政策。

## Strata

新工作树`/data2/Strata/wt/r002-v0141`锁定`fb58e0dbc8399662c0e47c76578c6e878b14f6cf`、tree `b5a210b6301395b703e3ed6224e0251c3ae5cc35`；旧v0.1.39和r002-v0140保持原样。逐参数迁移表、静态资产格式、S1/S2及冻结负载已独审CPU_PREPARATION_APPROVED。

- Strata独审 SHA `f729bd1384101cc89c0b23ac402ec2ca3dfe9b2c0c2c23f65b049101cd4aac34`
- 当前manifest SHA `30eb37526c7edd8db18e7e6c801fc5ee8e3d9dc3d9aff02a677031a6814b36d3`
- 现有pack/mtp只读；资产加载兼容、正确生成、速度均未测。两臂同版本/同构建，S2只改MTP、spec4及spec-min-p0.5；suffix draft0与CPUshare环境相同。跨版本R001↔S1不是单一MTP差值。
- 未来构建以真实终态和另行提交凭据绑定报告SHA；fresh检查生产service/worker仍绑1,3-47，方用0,2、nice19、ionice idle、-j2构建。
- 负载绑定R001冷32K×4/短×3、R045两条冻结提示/同AIPerf配置及256token ignore_eos追加组；沿用52/60，不重测60题。
- GPU窗口：R047/T03b之后、D09 GPU就绪之前；D09就绪则让位至D10之后，不中断已开始轮次；≤2服务/≤2工装重试。

## 当前服务与后续

20:29:43只读快照：481 owner/进程出生身份未变，174样本、0告警、epoch0/restart0；observer终态未产生。R067d正式run与Strata构建目录均不存在。快照不等于隔夜完成。

明早09:00观察报告实际提交→推送申请（尚未批准）→R067d→R047/T03b→D09→D10→R052a/R044。Strata仅按空窗插入。今晚未构建、未prepare/下载资产、未运行GPU/服务/HTTP生成、未推送。
