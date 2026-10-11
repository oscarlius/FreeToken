# 卡D14 调度候选与卡D16 CPU 工具进度

> 2026-10-05接手更新：下文保留历史过程。R032/b60八臂已复算并D04封存kept，155个原始文件未变，见 `r032_closure_receipt_20261005.json`。独立任务书检查与分配见 `PLAN_AUDIT_ASSIGNMENT_20261005.md`；新版T17工装切片Linux18PASS、两个真实startup spawn CUDAfalse、封存绑定和28组输入CPU预检PASS，回执 `t17_continuation_cpu_7f3989d13492.json`。完整原样批次和GPU验收仍待，卡D17未放行。

当前门候选为 `fix/e2-prefill-schedule-gate@e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7`，
父基础是 `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`。本地工作树
`development/e2d14-schedule/`；专属服务器工作树
`/data2/FreeToken/wt/e2d14-schedule`。Git tree 为
`09068014ec70359cb20919669be43e2dc56c9cba`。

开发历史 `fix/e2-prefill-schedule@ac43f78` 保留四个局部提交：`c3e44f2`（卡D14）、
`9894d04`（卡D16 CPU 工具）、`57442a2`（完整夹具）、`ac43f78`（通用网格及证据绑定修复）。
门候选采用同一最终 tree，直接父为 `e4f3202`，满足共用 T16 的准确直接父约束；
没有重写这些开发提交。旧 `e4f3202` 及旧轮次保持原状。

## 已实现

- `FT_DEV_PREFILL_SCHEDULE` 读取 UTF-8 JSON 文件；默认不设置。首次真实冷请求
  一次分配完整 KV，绕过外层 FLA / 注意力元数据，按实际段清单执行。
- Engine 采用私有 Req 逐段构建 FLA / 注意力元数据；保留供体 8193 的计算形状，
  恢复 8192 快照后续算。最后只完成、采样真实请求一次。以实际相邻段推导回退点，
  没有把 8192 写死为唯一边界。
- D0 增加 `start,end,mode,subchunks`，保留旧字段；层优先子块网格取实际 child，
  不猜测配置值。旧 `cached_tokens` 是缓存命中统计，不能代替新增绝对坐标。
- 卡D16 `scripts/equiv_suite/` 有实际 D0 调度生成器、参照结构核验、三层判定、
  批内对单独包络读者、停靠/缓存恢复输出读者和覆盖矩阵。暂不具备完整实测执行入口。
- T17 共用服务入口新增健康检查模式；调度臂在首个正式请求前不发送 SayOK。
  观察工具记录实际首段和子块的初始状态 / fresh-state 标志。

## 验证

当前门候选 Linux CPU 实测：调度 23 PASS、Engine 15 PASS、D0 11 PASS、卡D16 工具 21 PASS，
合计 70 PASS。CUDA_VISIBLE_DEVICES 为空；导入校验未初始化 CUDA。
详见 [实际回执](d14_schedule_cpu_6454d1109e8d.json)，服务器冻结目录
`/data2/FreeToken/runs/dev_D14/schedule_cpu_6454d1109e8d`。

此前 `57442a2` 的 66 PASS 回执已由独立审阅实际复算文件与 Git blob SHA、冻结日志、
两项扩展链接及导入绑定，范围仅限 CPU。该成功阶段也保留，不能代替当前候选的门。

首个 CPU 阶段 `schedule_cpu_bb164dfb4193` 的 Engine 夹具缺少 Batch 字段：
22 调度 PASS、14 Engine PASS、1 FAIL。原始失败日志与回执保留只读；修复在本地
新提交后同步，未直接改服务器源码。

历史重放 [d16_historical_replay_20261005.json](d16_historical_replay_20261005.json)：
R019 / R021 两臂均为 13 事件、13 段，无不等价声明；R023 四状态恢复 PASS，
同结构参照缺失，当前新判据为 indeterminate。旧 not_met 保留。

本地 T17 健康检查入口与原请求验证合计 13 CPU PASS。

## 仍需完成

当前 70 项引擎 CPU 回执已由独立架构及验证 Agent 核对，范围为 CPU。
新默认路径 T16 工装另外完成 Linux 75 PASS、D18 实际绑定和独立预检复核；
冻结目录 `t16_schedule_a9eaf6c40ec8`，报告 SHA
`458553a9db361c00ff4f1056604fc6c8807c086f27b66a1b363122c1b542736c`。
R032/b60 已原子启动，PID907150、生存标识123278676，准确父树e4f3202与候选e45e2c2。
层优先及普通预填各四臂仍在测量，未接受或封存。

1. 完成 R032 八臂实测、独立原始数据复算及 D04 封存。
2. 卡D14 参数未设置的默认路径等价需要新轮实际证据，旧R022不能替代。
3. 卡D16 实测执行器：命中供体/续算同进程、自动编译调度、两个独立参照进程，
   参照 D0 核验、普通全冷包络记录、状态字节复算及首层/算子差异。
4. 交付卡D16 T17 批次，再执行新 T17。未放行卡D17 / E2-base.1。

CPU 测试证明工装和调度代码契约，不证明模型等价、GPU 正确性或性能。

卡D16续算工具已在独立树 `e9ee6aa` 提交，服务器 `/data2/FreeToken/wt/e2d16-tools`
完成 31 项 CPU 测试，并独立读取冻结日志及 Git blob 核对。九个工具文件已交付至
`/data2/FreeToken/scripts/equiv_suite/`；引擎候选 `e45e2c2` 没有因此改变。
实际目标分词器还完成四个边界 × 七种尾长的 28 组输入构造，均保留 token SHA。
这两项为源码与 CPU 证据；T17 完整包装、首算子诊断、批次和实际 GPU 硬门仍待完成。
