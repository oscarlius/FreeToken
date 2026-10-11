# 开发与测试看板交接（本地静态页）

这是给 OpenCode 接手的本地交接包。它提供一个不依赖构建工具的中文页面和一份只读快照；它**不是**已部署的 8099 页面，也不是实时采集器。

## 当前已核实的入口与边界

- 首选线上入口是 `http://172.16.108.9:8099/`，对应 Docker `run-monitor`。未来应在该服务中增加独立 `/devtest` 页面和只读 `GET /api/devtest`，保留原运行监控入口。
- `8088` 只绑定 `127.0.0.1`，不是已可从局域网访问的入口。
- `8098` 属于另一套轮次看板：其读路径会写回轮次库，且 `/api/devrun` 有 `_rounds_index` 错误；不得将它用作本页的实时只读数据源。
- 当前 `run-monitor` 没有宿主机 PID namespace。容器内 `/proc/<host-pid>` 不能证明任务存活；必须接入宿主机只读观察器，或明确的只读 host-proc 挂载，并返回观察来源。否则页面必须显示“进程状态未知”。
- 本交付没有部署、重启服务、采集线上实时状态或新增后端路由。`snapshot.json` 是 2026-10-04 的交接快照，页面会定时重读它，但不会因此变成实时数据。

完整的不可变更接口和判读约束在 [CONTRACT.md](CONTRACT.md)。接手前必须完整阅读它，尤其是只读边界、PID 身份、比较可比性和 D04 追加历史规则。

## 本地打开

浏览器需通过 HTTP 才能读取 `snapshot.json`；在本目录执行：

```powershell
python preview.py
```

然后打开 `http://127.0.0.1:8099/`。该预览器只绑定 loopback，只提供四个静态文件；`/` 只是 `/index.html` 的别名，且不包含写接口。若不希望运行 Python，可用任意本地静态文件服务器；不要把它当作线上 8099 服务。

## 文件与页面行为

- `index.html`：三个可切换 Tab（开发进度、测试进度、基线对比）。
- `app.js`：每 5 秒只读拉取数据；默认 `snapshot.json`。在 URL 加 `?source=api` 才调用预留的 `/api/devtest`，接口失败时显示错误并保留上次成功数据，绝不回退成伪造 live 数据。
- `styles.css`：无框架样式。
- `snapshot.json`：当前交接事实与有限的 E2-R008 同轮对照数值。其 `mode` 固定为 `snapshot`。
- `preview.py`：仅供本地 HTTP 预览，非生产服务器。

所有文本通过 DOM `textContent` 创建，未净化数据不会进入 `innerHTML`。证据路径仅作可复制的文本显示，不会被转成任意下载链接。

## 当前进展（2026-10-04；以快照 revision / observed_at 为准）

| 工作 | 已有证据 | 后续工作 |
|---|---|---|
| D00 | E2基线默认门已过 | 后续轮次沿用完整基线提交 |
| D01/D02 | 代码交付、默认门通过 | 非零快照正对照、T05等业务验收仍待 |
| D03修复候选 f506 | 实际 G4/G5 开发 GPU 工件及 R018 v002 元数据复核均独立 APPROVE（证据 `development/d03_f506_r018_independent_review.json`） | 正式判定仍 `pending_review`；T04实际12672恢复仍待 |
| D06候选 0369263 | R020/b48四臂于19:18:46 CST结束；原始13条预填充事件及准确归档CPU重算均独立 APPROVE | R019/b47因包装器把完整13条父预填充分段按12条校验而失败；G3/G4自检准确源`195aa332`为Linux 11PASS并已自检，实际GPU自检和T05尚未启动 |
| D04封存工具 | 封存工具及实际raw私有副本15项PASS复核已独立 APPROVE | 真实canonical封存仍待root执行；不得将私有副本复核写成正式封存 |
| D07候选 fefb19c | 准确服务器CPU28PASS、1项CUDA检查未执行；独立源码复核通过 | 使用已修正完整尾段口径的新工装/启动器（Linux45PASS），等待D06前提门和GPU队列 |
| T10/T11 | R017、R013、R011已独立复核并封存 | 正式判定与科学归因单列；已封存不代表这些问题已经解决 |
| T04旧轮次 | R014/R015失败工件保留 | 不生成未证明的恢复/重算对比，不放宽科学阈值 |

本地状态文件 `../development_status.json` 由主线负责人维护，包含schema、递增revision、维护者、状态与证据。`../dashboard_refresh_snapshot.py` 可通过宿主机一次只读观察刷新它和页面快照；它不是持续采集器。每轮有独立RID和来源绑定，旧候选的检查不能替代新候选证据。

当前E2基线为 `23f2e2caa3395837c9474735ffc83321f3b9b5a1`。页面保留E2-R008已关闭同轮对照；其pending_review不能被页面改写为正式通过。新增可比结果时，无需更改页面代码，按接口约束增加数据记录即可。

## OpenCode 接入步骤

1. 按 `CONTRACT.md` 在 `run-monitor` 的既有服务中添加 `/devtest` 和只读 `/api/devtest`；不要另开监控端口，也不要使用 8098 作为依赖。
2. 用主线负责人维护的 `development_status.json`、当前批次小型 `status_batch<N>.json` 和受限白名单工件组装 `ft_devtest/v1`。采用临时文件加原子替换，并带 `schema`、递增 `revision`、`observed_at`、更新者和证据。
3. 实现宿主机只读 PID 身份/存活采集。需要同时返回观察时间、身份校验和观察器来源；无法观察时显式返回 `pid_alive: null`，不要从容器内 `/proc` 猜测。
4. 只读取有界 JSON 或摘要，拒绝符号链接和路径越界；不读取 tensor、权重、凭据或大日志，不执行模型请求、GPU 操作或任何写接口。
5. 保留本页面的比较规则：仅在 `comparable=true` 且双方数值有限时计算差值；零基线显示“不可计算”，缺失不补零，first-shot 独列，工件路径只展示或走独立白名单下载接口。
6. 部署另行记录源 SHA、备份、验证与恢复方式。静态刷新、后端重载、业务引擎重启必须分开；本页面不要求重启 8095。

线上实时采集、host PID 身份观察、后端新路由和正式部署均尚未实现，属于下一位接手者的工作范围。

## 本地验证记录

主代理已运行 `python ../dashboard_browser_check.py`，浏览器检查通过：三个Tab能切换，快照提示正确，390px移动端无横向溢出，API失败不回退为假实时数据，demo显式标演示，零基线和缺失值不生成错误差值。预览截图保存在 `../dashboard_preview.png`。本地预览已启动于 `http://127.0.0.1:8099/`；若预览进程结束，按上面的命令重新启动。

## Formal-verdict status correction (2026-10-04)

This handoff bundle is a local static template. No `/devtest` page or port 8099 deployment is currently published. The planned API and route remain an integration target, not live telemetry.

D04 has legally archived 14 `kept` measurement-only verdicts and 7 `failed_harness` verdicts. `kept` preserves a measurement; it does not admit a GPU gate, prove a scientific conclusion, or complete product acceptance. FTD04 has not been published. Immutable original snapshots and manifests stay pinned while a status reader validates the latest append-only history.

D14 commit `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42` has CPU13 evidence of a baseline FAIL followed by a repair PASS; GPU T16/T17 and the T10 rerun remain pending. D06's original tokenizer selfcheck stalled before G3/G4 evidence, so G3/G4 are not passed and D06/T05 is P1. D08-D13 and TP are frozen; T04 is P2.
