# D0 解码开销对账：T07 与 R022（只读 CPU 分析）

同类历史比较：T07 的六样本均值为 −3.35%～−3.58%，R022 的单样本门诊断为 −10.07%～−10.21%；协议、工作负载与记录时钟不同，尚不能给出唯一因果归因。

本分析响应 `CODEX_HANDOFF_20261004c.md` 第 2 节，不启动新 GPU，不改写历史轮次、不把门诊断升格为性能结果。两轮原始 manifest 已重新全量核验：T07 共 240 项、R022 共 116 项，全部通过。

## 从原始样本重算

| 长度 / 比较 | D0 开启 tok/s | D0 关闭 tok/s | 相对解码差值 | TTFT 差值 | 每组正式样本 |
|---|---:|---:|---:|---:|---:|
| T07 8000 | 36.5433 | 37.8083 | −3.3458% | +52.833 ms | 6 |
| T07 16000 | 37.5100 | 38.9017 | −3.5774% | +58.667 ms | 6 |
| T07 32052 | 37.3917 | 38.7450 | −3.4929% | +64.500 ms | 6 |
| T07 48000 | 37.0600 | 38.3933 | −3.4728% | +59.500 ms | 6 |
| R022 parent 门诊断 | 32.4100 | 36.0400 | −10.0721% | +30.000 ms | 1 |
| R022 D14 门诊断 | 32.3500 | 36.0300 | −10.2137% | +39.000 ms | 1 |

相对差值为 `(mean(D0) − mean(PROD)) / mean(PROD)`。T07 每个长度的原始 `c_*_r*.json` 按三进程、每进程两次正式 cold 读取；每份均检查 `cached_tokens=0`、`completion_tokens=128` 与实际 `built_tokens`。R022 直接读取四臂 `det.json`，不把 parent/candidate 两个不同代码臂合并成重复测量。

T07 已封存摘要的 32K 解码差值区间为 `[-2.87685, +0.17018] tok/s`，跨过零。因此表中的负均值也不应被改写为所有长度均有同等显著性的定论。

## 已确认的差异

1. **正式样本与首枪处理不同。** T07 是 ABABAB 六次独立服务；每次先有 ready 请求，再做一份被排除的 `first_shot` 128-token cold，之后才测 8000/16000/32052/48000，每个长度两次。R022 每臂 ready 后直接测一份 32052 的 `det` 128-token cold，没有额外的 128-token 首枪排除。T07 的 32K 正式样本已在同进程内经过首枪和 8K、16K 请求；R022 的 det 是该服务首个长生成请求。
2. **同一长度没有绑定到同一实际输入。** T07 32K 正式样本的 cold ID 为 `E2-R003-t32052-r1/r2`，R022 为 `E2-R022-gate-D14-det`。长度同为 built 32052 / prompt 32064，但正式输出 SHA 不同：T07 r1 为 `fd5f53e1…`，R022 为 `2a3bb2df…`。历史工件没有把这两轮绑定为同一完整实际 input-ID 序列，不能按相同工作负载配对。
3. **服务累计状态与记录时钟不同。** T07 D0 每进程有 1144 条 decode-step 记录，R022 每个 D0 臂有 148 条；后者还包括 det 后的 tax 请求，不能拿整个累计 profile 当 det 独占计时。T07 三份累计 profile 记录 `sm_clock_mhz=2745`，R022 两份为 2520；其累计 miss rate 分别约 0.216～0.220 与 0.322～0.323。时钟和累计 miss rate 是已记录的差异，不能据此量化它们各自造成了多少吞吐差值。

## D02 timeline 环境与实现核对

两轮归档的 `SERVE_CMD.txt` 在 D0 臂只显式增加 `FT_DEV_D0=1` 与臂专用 `FT_DEV_D0_PATH`；均未显式设置 `FT_DEV_D0_TIMELINE` 或 `FT_DEV_D0_TIMELINE_STEPS`。`ENV.txt` 是主机/版本/资源快照，并非完整的服务环境变量快照，不能用它宣称所有继承变量都被排除。

从版本指定的 Git blob 核对：E2-base `23f2e2c…` 与 D14 `e4f3202…` 的两个 D0 实现文件字节完全相同：

- `python/freetoken/moe/d0_decode.py`：`9230fc1cbee72ebc31c40369f2d45b6a19140eba92319e08c9673247095c8bfd`。
- `python/freetoken/moe/offload_cache.py`：`37e4f48e7c3322daae7fe389498a26fd9262b77b200b4befd7bfcb1a690ac079`。

其中 timeline 由 `FT_DEV_D0_TIMELINE=1` 单独启用；`FT_DEV_D0_TIMELINE_STEPS` 仅在 timeline 启用时读取，默认上限为 200。两轮均无 timeline 输出文件，decode-step 行也均只有 `step,t,bs,rids,missing_per_layer,missing_total,h2d_bytes` 这些计数列。当前工件没有支持“R022 启用了额外 D02 timeline”这一解释，也没有显示 parent 与 D14 使用了不同的 D0 实现。历史完整环境未保存的边界仍保留。

## 使用结论

确认两个差值均可从原始记录复算；确认它们不是同一采样协议和同一工作负载下的重复估计。仅靠现有工件不能把 −3.5% 与 −10% 的间隔分解成 instrumentation、首枪、工作负载、时钟和主机负载各自的贡献。

R022 的 D0 解码值继续作为等价门诊断，禁止用作生产性能数。T07 的 TTFT 均值 +53～65 ms 可按既有发布来源引用；跨协议解码对账仍标“−3.5% 至 −10%，待受控同输入实验”，不修改论文、不新增 GPU 任务。后续若正式重测，必须先固定完整 input IDs、相同首枪/重复协议、完整实际服务环境、时钟/负载记录，并只在性能卡获准后执行。

## 复现与输入证据

本地工具位于 `development/`：`d0_decode_inventory_20261004.py`、`d0_decode_inputs_20261004.py`、`d0_decode_source_20261004.py`、`d0_decode_reconcile_20261004.py`。均只读 SSH9 历史工件；最后一项从已读取的正式样本重算，并重新执行两个历史 manifest 的 `sha256sum -c`。

机器结果：`development/d0_decode_reconciliation_20261004.json`。原始选择性证据：`d0_decode_inputs_20261004.json`（SHA `34a95f23dcfd459b1fa79fe719bea5833df5851b54940b528e3b955d7570f8c2`）及 `d0_decode_source_20261004.json`。

| 历史轮次 | round.json SHA | MANIFEST.sha256 SHA | 本次验证 |
|---|---|---|---|
| E2-R003 | `1e0bca7f75389447d29519df2b6eadbeeb4e15130de2509c734eb80e1b962709` | `b13a19c8e7cb535fb442b0302ee2f14f8ce9674c87dc798467dcb477109722fb` | 240/240 |
| E2-R022-gate-D14 | `976ac037e235dbb230dd9dcdee4a0ef3ea7dbe77c8e98e117ec339f0104f9d1f` | `91778cbcdc41ff9ad491758c39c382826cd0587706a87a62eaf23e9af59f81f0` | 116/116 |
