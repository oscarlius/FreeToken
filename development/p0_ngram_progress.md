# P0：层优先 PLE n-gram 上下文核查与修复

结论：已用 E2-base 实际分词器和完整回放输入确认，4096 分块路径 12/12 正确，层优先路径 10/12 正确，两处 token 身份错误已独立复现。
数字：12416 应为 `[1469,17]`，层优先为 `[109990,9616]`；18944 应为 `[11,4093]`，层优先为 `[16,20]`；12736 两侧均为 `[198,248068]`。
限制：R022 T16已独立封存kept；R023 T17首个真实冷热输出/计算态不等，独立封存not_met。四角色恢复拷贝通过，后续诊断分块数值路径；修复版T10和基线接受仍待。

## D14 交付及当前真实验证

- 本地与服务器候选均为 `fix/e2-ngram-track@e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`，直接父提交 `E2-base@23f2e2caa3395837c9474735ffc83321f3b9b5a1`。服务器树 `/data2/FreeToken/wt/e2d14`；Git blob 与本地提交逐项一致，编译扩展与父树 SHA 相同。
- 准确服务器源码的 CPU 对照为修复前 13 failed、修复后 13 passed；两端实际 import binding、源码 SHA 和日志 SHA 均存于 `/data2/FreeToken/runs/dev_D14/t16_59fc2eb3bfca/cpu_validation.json`，SHA256 `2f35996f0ec2f675c13ae56ef8ee508c051eff38f0f9846980dbf71fda409894`。独立 verifier 已只读复核。
- 新工装首次用 GPU 前，对已封存 R020 原始四臂只读重放，证明全文和预填事件一致，以及完整 13/13 D0 行的 H2D/D2D 一致。
- 较大范围 CPU 回归已执行：父树、修复树均为 387 passed / 2 known failed / 14 skipped，失败集合与规则中的两个已知失败完全相同。服务器报告 `/data2/FreeToken/runs/dev_D14/regression_e4f3202_20261004_215009/report.json`，SHA256 `5d4c61da40963c512e3dcf47ba547f6c36e6e91e52db3d5703cad1056cf13cb3`。
- `E2-R021-gate-D14` / batch49 因父树尾段误按12条校验而失败，43个原始文件未变，已D04封存并追加 `failed_harness`，见[失败结果](../plan/01_测试与调研/results/T16-E2-R021-gate-D14_20261004.md)。
- 新共同工装使用R019/R021真实夹具，Windows/Linux39PASS。准确CPU stage `/data2/FreeToken/runs/dev_D14/t16_7e8f8f9569eb/cpu_validation.json`，SHA `d257c7d0e2d18094474cbb715b58d1be389344589b75984af71b91a674576b7f`；保留此前stage。R022/b50于22:10启动，PID/PGID192852、start_ticks121753831；用 `python development/t16_d14_monitor.py` 只读核对。
- R022四臂已完成并独立复算PASS，D04正式kept；74个既有原始文件未变。结果见 [T16-R022](../plan/01_测试与调研/results/T16-E2-R022-gate-D14_20261004.md)。
- T17准确Linux14+10+3PASS、signed-zero负对照和正常spawn通过。R023/b51于22:45启动，22:55首个真实冷热对照不等后停止；独立D04封存not_met，76原始文件未变。四角色恢复逐位通过，输出index36分叉，8256的GDN conv/recurrent及PLEconv不等。见 [T17-R023](../plan/01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md) 和 [新轮诊断设计](t17_r023_computation_diagnosis.md)。

交付细节见 [D14 交付记录](../plan/02_开发任务/D14_交付记录_20261004.md)。

## 已完成的只读验证

- 原始服务器工件：`/data2/_shared/runs/ft_rounds/E2-R002/{R4096,RLM}/dump/`，源提交 `23f2e2caa3395837c9474735ffc83321f3b9b5a1`。
- 真实轨迹：`E1-R003-v2/trace_rev.json`，SHA256 `097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24`。
- 按真实工具参数及 thinking 开关，经 `ChatCompletionRequest -> GenSpec -> TokenizeManager` 重建12条输入，并逐条核对两臂 replay 的 messages SHA、位置、前端 token 数和非 dry-run 状态。
- 三处争议长度在所有可覆盖的实际请求前缀中分别只有一个上下文答案；结论不依赖历史 B 与本轮采用相同数值 UID。
- 24条 tensor 在服务器 CPU 读取，无 tensor 下载、GPU请求或原始目录修改。
- 错误的 RLM-12416 tensor SHA 与正确的 RLM-21952 tensor SHA 相同：`40072b58f2fdbbd195ddf11b39ecc321d8630614335455681f84b21e4c93e8fb`。
- 独立复核：`/root/d06_server_review` 已重建输入及复算张量，确认两个层优先上下文错误。

本地复核摘要：[p0_ngram_semantic_proof.json](p0_ngram_semantic_proof.json)。受控复现入口为 `python development/remote.py development/p0_ngram_read_inputs.sh`；它规范化 shell 换行并传递 SSH/Bash 退出码，调用者必须检查返回码。证据脚本另已保存为 LF，禁止用末端 JSON parser 的退出码代替远端成功。

## 已定位的写入链

调度器先为原请求建立 FLA metadata，记录最终追踪边界并翻转 ping-pong 指针。层优先 Engine 再把已翻转指针复制给每个子请求，重新建立 metadata，子块写入另一槽；最终 `cache_req` 按原请求的指针捐赠原槽。这条链能留下旧槽内容。

修复必须统一原请求与实际子块写入的目标长度和槽位。不能只让子块自行交替槽位。回归还须覆盖最终目标落在子块起点/前块末端、短尾块、原请求已有缓存和关闭层优先的路径。

相对位置还会让实际GDN conv/recurrent和PLE初始化走fresh路径；它会改变计算。触发条件、短后缀区别和数据受影响范围见 [d14_impact_scope.md](d14_impact_scope.md)。T17四边界 exact-ID 工装已在实际Linux证明spawn/worker安装，尚待GPU。

## 当前执行顺序

1. D14 在 `development/e2d14/`、`fix/e2-ngram-track` 上修复，父提交为 E2-base 23f2。
2. CPU 回归、独立源码复核、准确服务器源验证；新 GPU 工装先对最近真实原始数据只读重放。
3. T16 及真实“层优先预填 -> 命中 -> 续算”门通过后，重跑 T10 三进程12轮，报告原33/36分歧变化。
4. FTD-20261004-1已发布：13 kept/8 failed_harness；清单SHA `836217380206fef106aa71dd6713cab0f18222932b9f884ba36d5ac4130ef014`。命中输出、T04包络和T11归因仍为hypothesis。[发布结果](../plan/01_测试与调研/results/T01-FTD-20261004-1_20261004.md)。
5. R013分类完成：token0/early/late为3/5/3，11对FP32 logits逐位一致；其预热前缀协议及归因限制见 [分类结果](p0_r013_classification.md)。

P1为D06/T05、D07/T06、同判卷器质量对齐和非零快照覆盖；P2为T04恢复协议、T09；D08-D13与TP冻结。R021失败已封存，旧T04失败工件保留。E2-base.1尚未合入。
