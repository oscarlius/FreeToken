# 任务书独立审查与分配（2026-10-05）

用户要求先启动独立 Agent 检查，再分配。审查由 `plan_audit`（critic，fork_turns=none）只读完成。
结论：当前不具备直接分配 T17 GPU 执行的条件；可以分配 CPU 开发与工具复核。

## 已确认的问题

1. 权威计划仍写 R032 运行中。实际八臂已复算、D04 封存 kept，155 个原始文件哈希不变；回执 `r032_closure_receipt_20261005.json`。
2. 卡D16 交付的是 CPU 工具与读者，完整 T17 原样批次缺失，不能要求01自行编写。
3. `t17_continuation_runner.py` 遇到输出 not_met 而缺诊断时仍保留 not_met，未满足首层/算子证据要求。应保留测量差异，同时将工装完成度判为 failed_harness。
4. 算子启动草稿引用不存在的 `t17_original_startup.py`；比较草稿只检查交集，空交集可能误判相等。未上传或运行GPU。
5. T20 复用 D06 多会话源码，不代表 D06 G3/G4 已验收。不能把排在 T20 后的 G3/G4 倒置为 T17 前置；T20使用的具体功能须先有独立工具自检。S-批槽的四路范围须在D16明确，不能默默扩大原D06“两路”契约。

## 已下达的分配

| 负责人 | 文件所有权 / 工作 | 交付与边界 |
|---|---|---|
| `operator_wiring`，02 executor | `development/t17_operator_observe.py`、`t17_operator_startup.py`，及对应两个测试文件 | 修复实际生成 startup 接线、精确输入SHA绑定、双侧非空完整覆盖、真实拓扑首差异；先CPU功能测试。不提交、不远端GPU执行 |
| 主Agent，02开发职责 | `development/t17_continuation_runner.py`、stage/launch工装、`plan/01_测试与调研/batches/batchNN_T17.sh`、状态勘误 | 完整28组输入矩阵、warm单进程与双独立参照、D0结构核验、缺诊断失败关闭、只读历史重放、源码SHA冻结及Linux CPU自检 |
| `plan_audit`，独立复核职责（开发交付后再启动） | 上述交付物只读复核 | 不修改runner；核对启动链、源码SHA、真实失败夹具和CPU日志；不能把复核直接当GPU放行 |
| 01测试执行职责（尚未启动） | 原样上传批次并执行E2-R033 | 不改源码、参数或现有脚本；独立GPU门、锁、工件封存；R034只在有依据的重跑时使用 |

## 串行关卡与停止规则

R032已kept → D16/T17工具交付并独立复核 → E2-R033新版T17 → 必要时R034重跑 → 正式接受或按PLAN §4.1裁定 → 卡D17 → R041默认门 → T20。
此后才排D06/D07 G3/G4以及阶段B测量。阶段C与TP继续服从原依赖。Strata已测，不重复运行T19。

审查建议“两轮必须都通过”超出原任务书，未采纳；R034保持重跑用途，不另增接受条件。
任何工具缺失、门禁失败、结构不匹配、双参照不稳定、恢复状态不等或输出不等均停止当前批次，保留工件。
输出差异而诊断缺失同时记录 `measurement_verdict=not_met`、`verdict=failed_harness`；不得把工具缺证据作为模型放行理由。
旧R023原判据not_met保留；不直接否定新版同结构T17，也不能凭重新解释就放行。

## 首个开发切片验证

诊断工具四项P0修复及续算runner接线已在本地实现：缺诊断失败关闭；使用实际生成的startup；输入SHA绑定和供体排除；非空双侧算子/绝对行集合、dtype/行形状严格核对，并按实际执行顺序定位首差异。
本地三组测试合计18PASS。Linux冻结自检阶段 `/data2/FreeToken/runs/dev_D16/continuation_cpu_7f3989d13492` 为PASS：18项测试、原startup实际spawn、operator startup实际spawn（CUDA均未初始化）、R032封存绑定与28组真实输入矩阵CPU预检通过。
回执 `t17_continuation_cpu_7f3989d13492.json`。前一失败阶段 `continuation_cpu_9876c26bdb2b` 保留只读，发现独立解释器未显式导入importlib.util；已在本地修复后新阶段验证，未覆盖失败证据。

该切片由 `plan_audit` 独立只读复核，结论为 **OKAY，仅限CPU工装修复与预检**。原样T17批次和完整GPU运行前交付仍缺，不进入R033，不宣称卡D16整卡完成或GPU门通过。
下一项明确分配给02开发职责：交付原样批次与完整执行入口，完成CPU验证后再次独立复核SHA/启动链；01只在交付、复核与实际单写者门均通过后执行R033。
