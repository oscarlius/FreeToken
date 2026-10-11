# D12 readiness and implementation plan — 2026-10-08

## Decision

D12（机制 D13：短后缀按需搬运）现在具备**立项和本地引擎开发准备**条件，尚不具备“实现完成”“GPU 已验收”或“有性能收益”的结论。

唯一已满足的业务前置是可审计的路由/后缀输入：`E2-R046g / batch99` 于 2026-10-08 00:07 由独立复核和 D04 封存为 `measured`。它完成四个 scope（12/12/8/2 请求，共 34），并有终态 review、round、manifest 与 closed pin SHA。T06 曾有 R046、R046e、R046f 的 failed_harness 历史；这些失败保留，不能被 g 轮的 measured 结论回写。

该事实足以让 D12 从“等待 T06 再立项”转为“可开发”；它不提供阈值、吞吐或 TTFT 通过证据。T06 采集模式本身不构成性能测量。

2026-10-08 本地复核已将四份只读 summary 的 SHA-256 与 manifest 绑定值逐一核对，并写入 `development/d12_t06_inputs_20261008/analysis.json`。三个 ordinary-worker 组共 32 条（冷首 3、warm 29）在 `1 / 2–19 / 20–32 / 33–64 / >64` 分桶中全部落在 `>64`，但 warm 实际范围是 123–4922、p25=242、p50=330、p75=1834；`G_two` 没有 ordinary-worker 绑定且无 round/trace，排除在 prefill 分母外。`suffix_tokens[].n` 与相同 UID 的 `raw_suffix_tokens` 在全部复制行相等，但 decode 专家字段没有被当作 prefill 专家比。`n=1,19,32,64` 是覆盖缺口，不自动阻止探索性 A/B：两臂预先固定 `--disable-moe-prefill-overlap`，control `threshold=0`，首个 enabled exploratory arm 为 `threshold=256`（10/29 warm，靠近 p25，非最优/收益声明），功能通过后才考虑 `512` 敏感性臂（16/29）。

## Bounded dependency review

| 依赖 | 已有证据 | 对 D12 的含义 |
|---|---|---|
| D07 route trace/analyzer | 审计记录为完成；`E2-R046g` 的 measured 闭合包含其真实采集结果 | 可作为只读适用面和阈值候选输入；D12 不修改 route schema 或分析器。 |
| E2-R046g / T06 | 结果摘要绑定终态 review `7863bd…`、D04 receipt `2b83de…`、round `3f50a0…`、manifest `282f1a…` | 开发开始时读取封存 summary，并校验这些绑定；摘要未列出阈值所需的分桶统计，故不在文档中虚构 `n<=64` 占比或最佳阈值。 |
| D16 | 工具/入口已写，R040g 的实际剩余项仍是已授权 GPU 工作 | 用作默认关闭等价 Harness；不把 R040g 的 14 服务/16 调用授权挪作 D12 验收。 |
| D15 | 核心候选存在，T21/R049c 尚未接受，独立 memory guard 未合入正式候选 | D12 保持独立：使用现有 cache 基础能力，但不依赖 D15 策略或带入其补丁。 |
| T09/R048b | 当前 GPU 性能独占 | 只做本地源码与文档/CPU准备；不启动远端服务、CPU/GPU测试或大规模 raw 扫描。 |

## Implementation shape

现有实现的关键边界已经足够明确：`layers/moe.py` 的 prefill 路径整体 materialize layer 或走双缓冲 prefill；decode 路径则用 `OffloadMoeCache.ensure_experts()` 将 raw expert ids 改写为 slot ids。D12 必须将“短 prefill 的 raw ids”接到这一成熟的 slot 管理能力上，而不能继续把它传给依赖 `position == expert id` 的整层 GEMM 布局。

候选 `97f6ee3ff04dec680a8adea92838c0e8db6a8b71` 已实现默认关闭、可见 ServerArgs 阈值。仅 `0 < n <= threshold` 命中；零或长后缀保持旧路径。命中时使用唯一专家集合、`ensure_experts`、`copy_missing`、full `bank_views`、slot alphas 和 `n=None` GEMM dispatch。overlap 默认开启，因此 threshold 单独开启会记录 fallback；正式单变量 A/B 两臂均须 `--disable-moe-prefill-overlap`。静态资格失败回退整层；ids 被 `ensure_experts` 改写后的 copy/映射异常 fail closed，绝不回退拿 slot ids 当 raw ids。Linux pytest 待空档，未宣称 CPU/GPU 通过。

`eb7f54a` 的 Linux CPU 定向运行得到 26 passed / 3 skipped / 3 inherited `Global context is not set` failures；其父基线也有相同三项失败，故没有 D12 新失败，但这不替代 GPU 验证。后续 `num_indices` 的 H2D rows/bytes 主机读取仅在 `collect_stats` 或 D0 开启时发生；默认 enabled hot path 不读该 device scalar。当前 fail-closed invalid-id 的 `bool((ids < 0).any())` 与诊断用 `unique()` 仍可能引入逐层 CUDA 同步/额外工作，未用私有 device-assert API 掩盖该风险，留待 GPU 评价。

这比移植 Strata 的 `STAGE=8` ring 更小：Strata 的 `stream_all_min()`/环境变量只作为“阈值 A/B 需要验证”的成熟先例。本机 NVFP4 字节、缓存预算、同步语义与数值路径不同，不能继承 1024 或其性能结论。

## Execution sequence and acceptance boundary

1. 在新的 D12 worktree 上确认 `effb9969706922ddad9e59b96377e46469ebe97f` 父提交、D07/T06 封存输入和现有 cache API；提取且校验 route summary 的分桶数据。
2. 实现默认关闭的 config → engine → cache → GEMM 分流，并先完成合成单测、fallback/异常关闭和受影响回归。
3. 用 D16 证明关闭态逐位一致。若 D16 缺少表达 D12 关闭态所必需的 case，只提出最小 Harness 增补；不自行创建验收轮次。
4. 将候选、测试、输入绑定和阈值候选写入 D12 开发交付记录。
5. 仅在上述步骤通过后，提交新的 GPU proposal：先 T16 默认门，后由负责人分配一个 D12 业务卡/轮次。对照是 threshold=0；开启臂的阈值来自已封存分桶数据并在启动前冻结。

功能接受必须涵盖存储/传输、续算状态、固定后续 logits 和端到端输出；性能只在这些门通过后比较 TTFT、搬运字节、唯一专家数、fallback 和后续 decode 缓存影响。任何功能失败均关闭该配置并保留证据。

## Schedule and stop conditions

当前可承诺的是“D12 可进入本地开发队列”，不是一个 GPU ETA。2–4 人日仍是历史读码估计；待 D12 代码与 CPU 回归通过后，GPU 服务数和调用数取决于冻结后的短后缀样本与 D16/Harness 复用范围，由root按已授权范围及实际交接书边界具体冻结后排队。

停止并上报的条件：封存输入绑定缺失、实际父基线不被接受、slot 与 prefill overlap 的生命周期无法证明安全、关闭态不一致、功能门失败，或需要修改 D15/路由/调度等本卡非目标。R049c、R040g 和 T09 的既有授权不会授权这些 D12 动作。

2026-10-08 14:00 root：本地隔离分支 `exp/e2d12-short-suffix` 已创建于 `development/e2d12-short-suffix`，HEAD=effb996、tracked clean，0aa ancestor检查通过。当前仅完成开发树准备，尚无实现/CPU或GPU通过结论。


## 2026-10-08 15:21 最终CPU/源码就绪

候选8f6a912ea6066f192c37dc74435efc9da0c7591c。Linux实际offload、layer-major、默认开关、KV重建60通过/3跳过；日志SHA668ca3974054d9bd40d6dcfd1133253b90941176932797f589042a211da148a9。原父版本3个GlobalContext失败已通过补齐直接层测试夹具的默认context解决；未改产品判据。

D0成功和fallback均只有一段实际copy计时，miss/hit字节由CPU协议参考核对。关闭stats时不做unique或miss-row主机读取；保留一次非法ID检查bool(any)的CUDA同步风险。stats/D0开启仍有统计同步，其速度不计入性能比较。

真实CUDA slot kernel未运行；正式计划需默认路径T16门、flag开启后的D16数值比较和普通SSE 0对256 A/B（两臂均no-overlap）。业务阈值256只是T06 warm10/29覆盖的探索点，不代表最优。此前阶段CPU状态保留为历史，由本段覆盖。

2026-10-08 20:00 参数勘误：以上关闭 overlap 的命令已按候选 args.py 与真实 CLI help 改为 `--disable-moe-prefill-overlap`。旧分析 JSON、旧源包 README 和已固定轮次保持原始证据字节；其中 `--no-moe-prefill-overlap` 是历史误写，不能用于启动。此改动不改变两臂 no-overlap 的实验设计。
