# 第十一节执行交接

执行依据：`plan/CODEX_HANDOFF_20261006.md` 第十一节（用户10-07 09:55裁定）。本记录交接当前开发源和CPU证据，不授予GPU启动或改变正式判定。

## 当前阻塞

R046b 原 `seed_real` 的首条完整请求经候选真实 `TokenizeManager.render_prompt/tokenize` 复算为 **87,100 token**；固定KV与序列窗口 **49,152**，服务在 `input_len >= max_seq_len` 时拒绝。原种子SHA匹配。降低 memory-ratio不能解决输入超窗。已向用户请求是否授权提取真实会话的窗内片段、另建版本并绑定范围和SHA；尚未得到答复，没有截断、替换或扩窗。

独立预算的后续生成提示上界与完整显存峰值仍未证明，预测余量为null、`memory_margin_verified=false`。R046b没有真实文件空跑、启动签字、正式目录、批号、锁或模型服务。服务器真实10:19:12核验时GPU锁不存在。

## 已完成的CPU分支

| 项目 | 本次结果 | 边界 |
|---|---|---|
| R046b 新工装 | Linux 27 PASS、0 skip；AST 8；独立R `CPU_ONLY_PASS_EXPECTED_REFUSAL` | 全部D07/T06服务0.80，新OFF与ON同配置比较；实际默认入口在进程、端口操作前准确拒绝87100。预算/空跑/启动均未批准。 |
| R049 T21 | 最终接口版 Linux 54 PASS、0 skip；AST 11 | 改为实际R046b measured+D04；512同值用于builder/reader；消费实际producer清单schema，保持性能0.88与seed12k唯一训练、三个heldout。 |
| R047 T03b | Linux 25 PASS、0 skip | 只将活跃前置改为R046b measured+D04；其余前置、0.88性能参数和正式输出范围不变。 |

R049新回归实际调用候选的纯CPU画像构建器/读取器，用临时合成route验证专家ID511可接受、错误256几何和256-header被拒绝。没有读取正式route或构造正式训练画像。R047没有在R049后续修正时重复测试；它的源码SHA仍与上述25项Linux回执一致。

R046b验证包装器前两次在测试执行前分别因guard异常类型、pytest hook参数错误终止，原CPU预检失败记录保留；v3才是27項实际Linux结果。R049几何包首次冻结预检因包装器候选标识断言错误在写目录前拒绝，后按入口的完整CANDIDATE与真实git HEAD重新核验。上述均未执行GPU门、启动服务或创建正式轮次。

## 精确证据

R046b最终源码：`/data2/FreeToken/runs/dev_R046/r046b_real_path_source_v1`，MANIFEST SHA256 `c77be2c18f0f31400a9be4c439fe6be60e74c3dba55fb42b6285831fc7f04ada`。Linux [回执](r046b_linux_cpu_v3/report.json) 远端路径 `/data2/FreeToken/runs/dev_R046/r046b_real_path_cpu_v3/report.json`，SHA `a1f6349844d147ee35d2433af6ce4ef7a7ec5fa9551466b6c97b1021d0d069a8`；实际入口拒绝回执SHA `b357da8d74cba091d41601b4a56530123d3fb863e50d7d6df4d1703b977cbdf5`。[独立R复核](E2-R046b_independent_cpu_only_review_v1.json) SHA `4c6a64853391f118d9e8362bc8ccb2e8d92e6bc29a50a76eca37577e2692e998`。

R049最终接口源码：`/data2/FreeToken/runs/dev_T21/r049_section11_geometry_source_v2`，MANIFEST SHA `2fa6f6047ebdd725fdf0b23c81f2333a4795b295d66344184a47243f7280ad5d`。服务器入口绑定实际raw SHA `b87b5785e7f80b430afd65650053be260b11acd2b02ef73d9c4a5c70ae04654a`，不可替换成LF规范化SHA `8ad23d0d5fef878528035a56b3ba9fc2a6e0ee07722b5cb14329821056e217ff`。Linux [54项回执](r049_section11_geometry_linux_cpu_v2/report.json) 远端路径 `/data2/FreeToken/runs/dev_T21/r049_section11_geometry_cpu_v2/report.json`，SHA `4a3887c7bcdd45bb8d064bbe6edbed1b29a4e9a730ee899ed0d7a27f0256d5bd`。其中实际调用未改的R046b `manifest()` 生成所有T06 fixture，消费端仅接受 `ft_r046b_route_manifest/v1`，拒绝旧schema；上游采集0.80与T21性能0.88分别记录。

修前几何v1源码及 [52项回执](r049_section11_geometry_linux_cpu_v1/report.json) 保留，回执SHA `62ac29d68bcdccb92ffb5b0c078daaf21de45eaecd166788cecae533df77933b`；后续启动不得使用该旧源或旧签字。

R047依赖迁移源码：`/data2/FreeToken/runs/dev_T21/section11_dependency_cpu_v1/development/t03b_e2_r047_prepare.py`，SHA `96a0d0b617db4799e30350f4bbd65b62e07dc50fa50d65f152e213a62553ba60`；[原分组回执](section11_dependency_linux_cpu_v1/report.json) SHA `f070a394f71819bcfe4c35e3d81945f63ba0509f498637032f095dfe90ee799d`，其中R047为25项。此回执中的R04950项属于专家几何修正前的源；后续使用上面的52项新版，不沿用旧启动签字。

所有新服务器源码目录0555、文件0444，Linux报告与拒绝回执0444；本地只保留小型摘要和测试输出。已封存失败轮次及冻结旧版不改。

## 后续动作

等待用户科学输入裁定；批准后才另建绑定提取范围的新seed版本，重新确认全部实际提示预算与0.80显存余量、CPU自检、最终路径文件空跑、独立R启动复核。GPU顺序保持 **R046b → R049 → R048 → R040a → R045 → R052 → R044 → R047**。启动时间未定，不以CPU通过替代实测、D04或启动许可。

R049需等待实际R046b measured+D04才构造正式画像和执行同入口文件空跑；R047也须等齐正式前置。独立R对几何版已交 `CPU_ONLY_PASS_GEOMETRY`，记录见 [独立几何复核](E2-R049_geometry_independent_cpu_only_review_v1.json)，SHA `6445699c0674e2a461a39f159d890de3fb301a7ca41059a22ba8c4f9a9226326`；其指出的旧清单schema接口由同owner在v2修复。

最终 [接口增量独立复核](E2-R049_manifest_independent_cpu_only_review_v2.json) 已核源码精确schema替换、未改的几何用例、实际生产端→消费端契约、54项Linux与11份source身份；SHA `2960172e70124806b57062ce904444c03a86edd8bcd0d168a45f3a3240fc468e`。旧接口问题仅在源码与合成CPU契约中解决，正式R046b清单消费尚未实测。该记录明确 `source_execution_ready=false`、startup/GPU/input/budget未批准。旧冻结包、52项旧回执和旧独立复核原件不改。
