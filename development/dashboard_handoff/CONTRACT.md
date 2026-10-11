# 开发与测试看板：约束与接口

本文件由主线负责人制定，是 OpenCode 接手页面、数据适配器和状态更新器时的约束。需求：在现有 8099 页面增加独立的“开发与测试”Tab，随时查看开发进展、实时测试进展、测试结果相对基线的数据。

## 1. 已核实的环境与本次交付边界

- 首选入口：`http://172.16.108.9:8099/`。现有服务是 Docker `run-monitor`，代码 `/data2/_shared/run_monitor/monitor.py`，页面 `/data2/_shared/run_monitor/web/monitor.html`，宿主机目录以只读方式挂载到容器 `/app`。
- 现有路由为 `/`、`/metrics`、`/web/{name}`。新入口建议 `/devtest`，只读聚合接口建议 `/api/devtest`。不另建监控端口，不替换现有运行监控页面。
- `8088` 当前只绑定 `127.0.0.1`，不能当作已经可从局域网访问的备用入口。
- `8098` 是另一套轮次看板。它的 `/api/rounds` 读取会合并并写回轮次库，`/api/devrun` 当前还存在 `_rounds_index` 未定义错误；不要把它作为新页面的只读实时依赖。
- `run-monitor` 当前未共享宿主机 PID namespace。容器内 `/proc/<宿主机PID>` 不足以证明进程是否存活；必须由宿主机只读采集器观察，或经明确配置的只读 host-proc 挂载观察，并返回观察来源。没有该能力时显示“进程状态未知”。
- 本次交付是本地阅读文档、简单 Web 页面和接口示例，供 OpenCode 继续开发。线上部署、后台持续采集和新路由是否可用必须分别报告，不以本地页面完成代替已经上线。

## 2. 数据来源和写入权

| 数据 | 权威来源 | 页面行为 |
|---|---|---|
| 开发卡状态 | 主线负责人维护的 `development_status.json`，附提交、测试和交付证据 | 只读；不得从日志关键词或历史 E0 项猜当前 D00–D13 状态 |
| 测试实时状态 | 本轮 `status_batch<N>.json`、启动记录、宿主机 PID 身份和存活观察 | 区分实际运行、观察未知、测量结束待复核、失败 |
| GPU 持锁 | `/data2/_shared/gpu.lock` + 同一次进程观察 | 锁存在不能单独证明任务在运行；遗留锁单独提示 |
| 已关闭测试结果 | `/data2/_shared/runs/ft_rounds/<RID>/round.json`、版本历史、清单和复核记录 | 显示原始判定、测量值、证据路径和可比性；不写回任何轮次 |
| 开发自检 | `/data2/FreeToken/runs/dev_<D卡>/` 的小型报告 | 单独标“开发自检”，不能当作正式验收轮次 |

页面和 API 不执行模型请求、压测、启停、重建、封存、追加判定或其他写接口；不新增引擎/nvidia-smi 轮询，不读取权重、tensor、凭据、大段日志。采集只允许白名单目录中的有界 JSON/摘要，拒绝符号链接和路径越界。

已关闭轮次的原始工件保持只读。更正状态、判定或结果使用 D04 追加历史方式，不覆盖旧快照；主线负责人是开发状态的写入者。状态清单采用临时文件加原子替换，携带 `schema`、单调递增 `revision`、更新时间和更新者。读取失败保留上一份可显示快照并标明错误，不能生成“全完成”。

## 3. 如何更新状态、何时更新状态

| 事件 | 更新者与触发时点 | 必须携带的证据 |
|---|---|---|
| 开工/分配轮次 | 主线负责人，在工作或启动批次前 | 卡号、依赖、RID、源提交、计划阶段 |
| 代码交付 | 主线负责人，在提交和针对性检查完成后 | 完整 commit、worktree、检查输出、交付文件；状态为“已交付待验证” |
| 测试启动/阶段切换 | 测试执行器，启动后及每个实际阶段切换时 | 批次号、PID、启动身份、当前臂/步骤、真实已完成计数 |
| 运行观察 | 宿主机只读采集器，每 3–5 秒 | `observed_at`、PID 身份与存活、原状态更新时间、采集错误 |
| 测量结束/失败 | 测试执行器，真实子进程退出后立即 | 退出码、结果/错误路径；成功只标“测量结束待复核” |
| 独立复核与封存 | 主线负责人，在独立复核、D04关闭和清单检查后 | 复核结论及 SHA、清单 SHA、关闭时间；正式判定仍单列 |
| 验收完成/退回 | 主线负责人，任务卡要求的全部门和业务验收均满足后 | 验收证据；局部通过、开发自检或代码完成不能代替它 |

开发状态与测试状态分开，不用一个“完成”字段概括两者。开发状态沿用任务卡：待办、进行中、已交付待验证、完成、退回、阻塞、后置；依赖未就绪和待审批后置项分别显示原因。

测试阶段建议：排队、预检、加载、测试中、测量结束待复核、已复核待封存、已封存待判定、通过、未通过、异常、进程状态未知。任务执行状态、独立复核结果、科学条件、正式 verdict 分别保留，不能互相推导。

页面默认每 5 秒拉取，切出页面可暂停；接口有短缓存，不能每位用户重复扫描大型工件。快照超过 15 秒没有新观察时显示“数据过期/连接异常”，不据此判定进程停止。长时间没有状态事件但 PID 仍活可显示“运行中，尚无新阶段事件”。进程退出也不能自动升级为“测试通过”。

不估算无依据的总体百分比。卡声明了总臂数或总请求数时，才显示实际完成数/总数；加载、复核、封存独立显示。首轮加载很慢时显示阶段和耗时，不伪造 ETA。

## 4. 基线和结果比较

当前 E2 基线为 `23f2e2caa3395837c9474735ffc83321f3b9b5a1`，标识 `E2-base@23f2e2c`。D03 原候选为 `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`，T10 R013仍使用它。诊断传播修复候选为 `f5067bbe05da51d5f78185213435a8be095a684a`：其实际 G4/G5 开发 GPU 工件及 R018 v002 元数据复核均获独立 APPROVE（证据 `development/d03_f506_r018_independent_review.json`）；正式 verdict 仍为 `pending_review`，T04 实际 12672 恢复仍待。旧候选门不能替代新门。开发候选和测试所用基线必须同时可见，禁止把 E1/E0 数字混进 E2 曲线。

每次比较必须明确基线 RID/臂、实验 RID/臂、完整 source commit、指标字段路径、单位、工件路径和校验信息。以下条件需要核对：模型和 tokenizer/checkpoint、量化后端、数据/实际 token 输入哈希、上下文窗口、prefill chunk、层优先、cache 冷热、host slots、生成长度/停止条件、并发、精度、工具与判卷器版本。卡片有意改变的变量须写 `allowed_differences`，其余不一致或缺失则标“不可直接比较”，说明缺项。

- 同一轮次中已有明确对照设计的成对指标优先展示。跨轮次不能仅凭字段名称相同就相减。
- 秒、字节、tok/s 等单位保持一致。支持绝对差 `实验−基线`、相对差 `(实验−基线)/基线×100%`。基线为零时相对差为 `null`，显示“不可计算”，不除零、不补零。
- 方向明确：延迟低通常较好、吞吐和质量高通常较好；状态误差、H2D/缓存等诊断指标不自动转化为性能提升。
- first-shot 单列；只在协议允许时统计稳态。不能把首次请求和复测中位数比较，不能把冷与热、32K 与64K、不同判卷器的质量分数直接比较。
- 未产生结果显示“待测”，缺失值显示“缺失”，非有限值带显式原因；禁止把缺失/失败/NaN转成0或绿色通过。
- 默认同时保留绝对值和差值，不只显示改善百分比。科学阈值未满足也保留测量结果，页面不得放宽阈值或自动给正式 kept verdict。

## 5. 只读接口契约（建议 v1）

`GET /api/devtest` 返回 JSON，顶层：

```json
{
  "schema": "ft_devtest/v1",
  "mode": "live",
  "observed_at": "2026-10-04T03:05:00Z",
  "revision": 1,
  "baseline": {"code_version": "E2-base@23f2e2c", "commit": "23f2e2caa3395837c9474735ffc83321f3b9b5a1"},
  "development": [],
  "tests": [],
  "comparisons": [],
  "errors": []
}
```

- `development[]`：`card, title, status, candidate_commit, updated_at, next_step, blockers[], evidence[]`。
- `tests[]`：`card, rid, batch, stage, execution_status, batch_pid, pid_alive`（允许null）、`identity_verified, process_observer, status_updated_at, elapsed_s, progress`（允许null；声明时为`{done,total,label}`，计数含义与实际工件一致）、`review_status, sealed, formal_verdict, evidence[]`。
- `comparisons[]`：`metric, unit, direction, baseline`和`experiment`（均含RID/臂/数值/字段路径/源commit/证据）、`comparable, reason, allowed_differences[], delta_abs, delta_pct, scientific_status`。只有 `comparable=true` 且两值有限时才显示计算差值。
- `evidence[]`：路径、摘要、可用 SHA；外部链接仅允许可信 http(s)，工件路径只显示或经独立白名单下载接口访问，禁止将任意绝对路径当下载URL。
- 小型响应，建议上限2MiB；日志摘要仅必要且有界，HTML安全转义。原始 prompt/生成全文、大数据下载、认证和历史筛选可由 OpenCode 后续扩展。

本地示例必须 `mode="snapshot"`，标明采集时间和“本地快照，非实时”。模拟的数据使用 `mode="demo"` 并明确展示，不允许假装 live；接口不可用时保持错误提示，不能自动切到假实时数据。

## 6. OpenCode 接手验收清单

1. 在8099增加独立Tab/路由，运行监控原入口继续可用；新页能单独收藏打开。
2. 开发状态可由主线负责人更新；状态变更有版本、更新时间、证据和依赖说明。
3. 真正的实时观察已接入，运行/退出/未知/遗留锁/断网状态均能区分，不能依赖容器内错误的PID观察。
4. 显示成对基线/实验绝对值和差值；零基线、缺失字段、不可比配置、科学条件失败、首轮数据都有正确提示。
5. 一轮测量结束后无需改页面代码就能显示；复核、封存、判定的后续更新也能被读取。
6. 只读页面/API不改变原始轮次、模型进程和GPU任务；不存在XSS、任意文件读取或状态写接口。
7. 正式部署记录源SHA、备份、验证证据和可恢复方式。静态刷新、后端重载和业务引擎重启分开；新页不要求重启8095。

## 7. 当前进展提示

2026-10-04：D00基线已过门；D01/D02代码及默认门通过，非零快照/T05等验收缺口保留。D03修复候选f506的实际 G4/G5 开发 GPU 工件及 R018 v002 已独立 APPROVE，正式仍 `pending_review`，T04 实际12672恢复尚待。D06 R019/b47因包装器父尾段口径错误失败，原始两侧各13条事件均完整；R020/b48 四臂已于19:18:46 CST结束，原始13条预填充事件及准确归档 CPU 重算均独立 APPROVE。D04封存工具及实际 raw 私有副本的15项 PASS复核已 APPROVE，但真实 canonical 封存仍待 root 执行。D06 G3/G4 自检准确源 `195aa332` 已完成 Linux 11 PASS 与自检，尚未启动 GPU。D07源码交付待GPU验收。T10/T11封存与科学归因、正式判定分别维护。具体数量、阶段与后续状态以snapshot.json和负责人状态文件的revision/observed_at为准，本文件不承担实时采集。

## Formal verdict display correction (2026-10-04)

This document describes an integration target only: neither `/devtest` nor an 8099 deployment is published. A future updater must render the latest D04 append-only history only after validating it with the reviewed public writer. It must retain and verify the immutable original snapshot/manifest pins.

There are 14 formal `kept` verdicts (measurement-only) and 7 formal `failed_harness` verdicts. `kept` must never be rendered as GPU gate admission, scientific acceptance, or release completion. FTD04 is not published. `pending_review` is read from the latest validated document, so a historical v001 snapshot must not freeze a future status.

Current development display: D14 `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42` has CPU13 FAIL-before/PASS-after evidence while GPU T16/T17/T10 remain pending; D06 G3/G4 are not passed because the original tokenizer selfcheck stalled before evidence; D08-D13 and TP are frozen; T04 is P2.
