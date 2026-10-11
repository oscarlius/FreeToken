# 夜间补充指令（2026-10-10 00:35，主会话起草，用户睡前转发即生效）

## 现状（主会话 00:20–00:35 只读核对服务器）

| 项 | 终态 | 核对结论 |
|---|---|---|
| R067d | 独审 not_met | **应改判 failed_harness（参照工装配置缺陷）**，见一.1 |
| R047/T03b | 独审 not_met | 维持。候选 0aa2343 的锚点快照没有触发，属于候选缺陷 |
| Strata S1 | PARTIAL（有效子集） | 32K×4：TTFT 8.0–8.4 s、decode 61.4–63.4 tok/s；2K×3：60.4–66.3 tok/s。无 MTP，同一 v0.1.41 构建 |
| Strata S2 | failed_harness，0 调用 | 维持。工装读了外层 UI 日志，引擎 stderr 实际已加载 MTP |
| R052a | 进行中（batch140） | 12 轮，00:28 时完成 6 轮，预计 00:40 前后结束；之后 watcher 自动接 R044 |

预计 R044 和 D09-T16 跑完约 02:00，之后 GPU 会空 5 个多小时。下面补齐。

## 一、裁定

1. **R067d 改判 failed_harness**，原独审字节保留，另记改判依据：
   - 冷 A 臂 argv 带 `--cache-type naive`；热臂没有这个参数，默认值 radix 由 `engine.py:1465` 映射为 `hybrid_radix`。
   - `scheduler/cache.py:54`：只有 `hybrid_radix` 时 `is_hybrid` 为真，ping-pong 槽也只在 hybrid 下分配。
   - `attention/linear.py:_build_track_metadata`：所有请求的 `mamba_ping_pong is None` 时，返回空 track。
   - 因此 `engine.py:1271-1273` 必然抛出 "scheduled donor did not build exactly one rewind checkpoint"。这个失败是确定性的，与产品热路径无关。
   - 热臂 2 个服务、6 次调用全部 valid，cache 计数为 8192/8256，符合预期。
   - 本轮没有产品结论，可使用工装重试额度（第 1/2 次）。
2. **Strata S2 维持 failed_harness**。授权 S2 重试 1 次，Strata 总服务上限由 2 提到 3；可选 S3 再加 1，上限为 4。
3. **R047 维持 not_met**，不重跑验收，转为调试（见四）。

## 二、R067d-retry1（新 RID `E2-R067d-d20-short-tail-retry1`）

- **只改一处**：所有设置了 `FT_DEV_PREFILL_SCHEDULE` 的冷臂，去掉 `--cache-type naive`，改用默认缓存（解析结果为 hybrid_radix）。输入、判据、端口规则以及 10 服务/14 调用的预算都不变。
- **如何保证是冷启动**：每个冷臂都是全新服务的首个请求；`_forward_dev_prefill_schedule` 已有守卫，`cached_len != 0` 时直接抛错；另外增加判据：API 返回的 `cached_tokens` 必须为 0。
- **GPU 准入前的 CPU 工作**：
  - (a) 新增用例：对每个含回退段的冷臂配置，cache type 的解析结果必须是 `hybrid_radix`，`naive` 必须被拒绝；
  - (b) 用 v1 `cold_A_p8192_t1/serve.log` 的真实日志回放这个失败签名，期望被识别为工装失败；
  - (c) 完成 FILEdry 和独审。
- 通过后执行 D12 的 CPU 准备（与之前的安排相同）。

## 三、Strata S2-retry1

- 同一 v0.1.41 构建；负载和 11 次调用与 S1 完全相同。ignore256 组只为保持对称而保留，不用作验收。
- **MTP 加载判据**改为读取引擎 stderr 追加日志的切片（即 `ENGINE_STDERR_ACTUAL_SLICES` 的做法），切片里必须出现 `draft layer loaded`；外层 UI 日志不再作为判据。FILEdry 时用 S2 v5 的真实日志做正例和反例回放。
- **报告**：S1 与 S2 在同一版本下的 MTP 差值。v0.1.41 源码中没有 `ignore_eos`，固定长度组记为已知限制。
- **可选 S3**（S2 有效且时间允许时执行）：S2 配置加 `parallel: 2`（真正的两路），与 R045 的 22 tok/s/路做对照。S1 中 AIPerf 并发 2 实际只是排队，不能写成两路结果。

## 四、R047/T03b 调试（诊断用，不是验收轮）

- **现象**：3 轮回复都有 `reasoning_content`，说明解码中已经出现 `</think>`；radix 也已映射为 hybrid_radix。但 `D0 anchor_snapshots_taken=0`，第 2、3 轮的 cached 只有 64 和 192。
- **做法**：在独立的 dev 工作树里改，不动 481，也不动已封存的 0aa2343 树。给 `scheduler/cache.py:snapshot_toolcall_anchor` 的每个 continue 条件加计数器，同时给 `scheduler/scheduler.py:461-473` 的 anchor_hit 加计数器。计数至少要区分：anchor_len 为 None、ping_pong 为 None、`mamba_last_track_seqlen` 未清、`cached_len != anchor`、未对齐。
- **待证假设**：
  - overlap 调度下，`_process_last_data` 设置 anchor_len 时下一步已经入队，导致 `cached_len != a` 恒成立；
  - prefill track 写入的 `mamba_last_track_seqlen` 没有被 `cache_req` 清掉；
  - `</think>` 的 token id 与 `toolcall_anchor_id`/`d3_extra_anchor_ids` 不一致。
- 能在 CPU 上复现就先在 CPU 上定位。需要 GPU 时，限 1 个服务、最多 3 次调用（使用 A_cut_on_p1 的冻结输入），只读取计数器。

## 五、GPU 顺序

R052a（进行中）→ R044 → Strata S2-retry1 → R067d-retry1 → D09-T16 → R047 调试诊断 → Strata S3（可选）→ D10（若已就绪）

GPU 空闲时，按以上顺序取**第一个已通过独审**的项，不为等某一项的准备而让 GPU 空等。CPU 准备工作全部并行进行。停止规则不变：每个范围的工装重试最多 2 次；产品 not_met 只封存本轮，继续下一个独立项。

## 六、截止时间

- 06:45 之后，不再启动预计在 07:30 前跑不完的轮次。
- **最晚 07:30 开始恢复 481**：恢复冒烟逐项比对首次冷基准 `df77cb14…`；失败则回滚 184 并停止全部 GPU 工作。08:00 前必须处于 serving。之后开启新的观察，持续到 09:00。
- 09:00 早报：列出今晚每一项的终态，并附推送申请。推送仍未批准。
