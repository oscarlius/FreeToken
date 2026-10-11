# D06 T16 R019：完整尾段的工装口径修复

主线负责人记录。R019/b47 于2026-10-04 17:58:53 CST失败，原始工件保留在 `/data2/_shared/runs/ft_rounds/E2-R019-gate-D06/`；本轮不能标为通过。

## 实际证据与原因

父树为E2-base `23f2e2caa3395837c9474735ffc83321f3b9b5a1`，候选为D06 `03692633df48456fb0baa78de7b64e5628a12ab1`。两侧均有13条完整scheduler prefill事件和13条D0记录；业务prefill序列排除1条readiness事件后均为12条且逐字节一致。`anchor_cap`分段事件完整，未出现日志限流或缺行。

冻结旧base的实际 `run_arm` 调用将 `parent_tail_fix` 仅用于D03。对D06错误地要求父侧 `13-1=12` 条，候选要求13条，因此在后续最终比较前失败：`old=13/12, new=13/13`。这是包装器口径错误；不修改冻结父树，不删事件，不放宽计数约束。

## 修复与验证

新版本仅把上述条件扩展至D03/D06/D07；D01/D02保持旧行为。新adapter固定新base的实际字节SHA，轮次绑定与源码归档也声明新base。冻结旧runner、旧launcher及原R019不变。

| 文件/证据 | SHA256 |
|---|---|
| `t16_full_tail_base_runner.py` | `66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125` |
| `t16_candidate_runner_full_tail.py` | `d29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1` |
| `t16_candidate_launch_full_tail.py` | `7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf` |
| 完整Linux检查日志 | `6d70cd37dcaedef1cfdfac0ffe72fa484353c889da62578bc67bd0be7a237e1f` |

精确新源码Linux45PASS，base与adapter自检通过；报告见 `t16_full_tail_launcher_7e1c05a_289327f_cpu.json`。回归驱动真实 `run_arm` 控制路径，复现原13/12错误，验证D06/D07的13/13口径。缺事件、缺D02尾段、H2D/D2D不一致、参数、全文及业务序列差异仍会被拒绝。CPU测试使用模拟服务，不是新GPU门证明。

后续使用新RID重跑四臂默认门，执行前重新核对源、CPU证明、8095和GPU锁。D03 G4/G5正在串行队列执行，当前不并发启动新GPU任务。D06的G3/G4及T05仍待完成。
