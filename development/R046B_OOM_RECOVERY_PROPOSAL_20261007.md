# R046b OOM 原因与恢复方案（待用户裁定）

**历史提案，已被交接书第十三节覆盖。** 用户新裁定先执行R057四臂诊断及R058并发显存，按结果修复并过新T16；此处普通4096提案没有被采用，不能作为任何启动依据。下文保留当时源码诊断与条件估计，后续以snapshot实测及第十三节执行记录为准。

当前 R046b/batch82 已原地只读封存为 `failed_harness`，独立 D04 终核通过；GPU 队列停止。本文只交付诊断与具体方案，不授予新轮次、配置修改或启动许可。权威边界为交接书第十二节，T06 卡面仍要求 layer-major。

建议批准 **E2-R046c：G3/G4/T06 全部采用普通 prefill、每批最多 4,096 token**。保留候选 `effb9969706922ddad9e59b96377e46469ebe97f`、窗口 98,304、比例 0.80、完整 seed、route trace、暂停开关及原判据。此方案复用已有源码，不需要产品提交或因源码变化新增 T16；正式接受仍依赖新配置实测、独立复算和 D04。

## 原因与证据

调度器在 `scheduler/prefill.py:166–178` 的 layer-major 分支把完整剩余长提示准入一批；引擎在 `engine/engine.py:1051–1060` 只有 `tracer is None` 时才走 layer-major 内部分块。开启 route trace 后，完整批次转入 eager forward，扩大 FLA 的临时工作区。调小 `FT_LM_CHUNK` 不能解决 ON 臂，因为 ON 已跳过该内部 builder。单独打开暂停端点不会触发这个分支变化。

R046b 实际失败点是 `chunk_delta_h.py:324` 的 `h=k.new_empty(B,NT,H,V,K)`：申请 752 MiB 时剩余 45.69 MiB。route 快照仍在 CPU pinned 内存，不能归因为 GPU trace 缓冲。模型加载及请求前分别约剩 4.40/4.38 GiB，也不能证明请求峰值余量足够。

依据本轮绑定的模型 config 和源码，若失败 forward 确为完整单序列 32,064 token，则 B=1、NT=501、H=48、K=V=128、bf16 的逻辑 `h` 为 751.5 MiB，接近日志的 752 MiB。运行时维度没有被记录，差额的 allocator 机制也未证明，故这是条件推导。相同推导下普通 4,096 的 `h` 为 96 MiB，完整 87,100 的 `h` 为 2,041.5 MiB；这些只描述一个工作区，不能代替总峰值实测。

## 具体配置差异

| 项目 | 封存的 R046b | 建议的 R046c |
|---|---|---|
| `--prefill-layer-major` | 开启 | 全部 G3/G4/T06 去掉 |
| `--max-prefill-length` | 4096；LM 可整段准入 | 4096；普通调度预算约束 |
| KV / max sequence | 98304 / 98304 | 保持 |
| `--memory-ratio` | 0.80 | 保持，不低于授权下限 |
| seed / 窗口止轮 / 输出预算 | 完整输入；提示超过96256自然止轮 | 保持；不截断输入 |
| route / pause | 各臂规定的开关 | 保持；OFF/ON 用同一普通预填配置 |
| 开发调度环境 | 既有白名单不足以证明所有继承项 | 明确清除 `FT_DEV_PREFILL_SCHEDULE`、LM覆盖及其他开发调度覆盖项 |

R046b 的 G3-off 保留为历史记录；新 OFF 与 ON 必须在普通 4096 下重跑比较，不能跨调度结构复用。T06 不采性能放行数字；R049/T21、R048/T09、T05 等性能臂仍按发布配置 0.88，不能把此采集配置用于性能比较。

## 已完成的 CPU 支持证据

现有 `route_analyze` 按同 RID 累加多块 token 数并合并专家集合；D15 builder 按每个 token 累加频次，普通分块不会把文件数当作权重。

Linux 纯 CPU 复用既有测试取得 3 PASS；额外夹具将相同两层路由拆成 1+2 token 文件，拆分前后画像二进制逐字节相同。CUDA 可见设备为空，socket guard 生效，未加载 torch、未启服务。

- 小报告：`/data2/FreeToken/runs/dev_R046/r046_chunked_route_cpu_v1.json`
- SHA256：`9b9e545638fa041a63079205408bc241454de50e7b5ee71fe842727a8ffa3c02`
- guard SHA256：`887fe6dd9943f6359b09ee37d41089033f9d6e1e654c43f51e3a64158423637d`

这证明既有消费端支持拆块及频次权重，不证明完整 seed 的 GPU 峰值、ON/OFF 输出逐位一致、暂停链或两路负载已通过。仍按 CPU 自检 → 同脚本/路径/用户真实 FILEDRY → R 启动复核 → 实测中逐组 R 复算 → D04 执行。

## 批准后执行边界

只新增工装版本；旧 source、R046b 原始数据、封存清单及判定保持。队列位置保留为 R046 补跑 → R049 → R048 → R040a → R045 → R052 → R044 → R047。R049/R047 的生产端引用须在新工装中绑定本次成功补跑的清单，不能继续引用失败 R046b 的画像。

普通调度保留同 UID 的续块及 linear state；但 GPU 数值与科学有效性仍需实测。尤其普通预填训练出的路由画像是否改善生产 layer-major 性能，要由 R049 留出集验证，不能预先宣告。最长链仍须记录请求前后模型显存；0.80 下仍不足、暂停业务失败、not_met 或其他测量后失败，保留数据并按用户规则停问。

**需要用户裁定的是：批准字母补轮 E2-R046c，并允许 T06 的采集配置从 layer-major 改为普通 4096。** 这是测量结构变化；本文没有替用户改卡面或启动。

## 若必须保持 layer-major

需开发 tracer 与 layer-major 内部 chunk 的集成，定义 layer、offset、UID 与记录终态，再形成新提交、CPU 回归及 T16 门。不能只删除 `tracer is None`：现有 `route_trace.py:81–85` 要求一条记录覆盖当前 forward 的全部 token，并拒绝同一 MoE 层重复记录。此方案需要另行开发与门授权，预计显著增加工期。

既有第十二节的发布后 allocator snapshot 调查安排保持；本次源码分支诊断没有启动 GPU 诊断。剩余八批工期与两条路径的估计见 [独立评估](REMAINING_WORK_ETA_20261007.md)。
