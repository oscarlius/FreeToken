# Q1–Q5 补充：严格 CPU 观察、差异化修复提案（默认关闭）

本补充仅追加分析和测试/修复提案；不修改 bd57/e483 产品源码，不启动 GPU、服务或 API。CPU 复放使用真实 `Scheduler`/`CacheManager`/`Req`；唯一替代是模型输出处调用真实 `Req.complete_one()`。`strict_scheduler_d09_observed_v1.py` 对两个原生实例方法做透明委托：先调用原函数、原样返回结果，仅写 receipt，未替换判断或返回值。

## Q1 / Q2：已观察的原生调用链

封存 UID0 token 输入 SHA 为 `24068…142a`，UID1 为 `22ed…0fbc`。UID0 按 `0→20224→20282→21302` 前填；UID1 的真实 `match_req` 结果为 20160。

透明 receipt：

| 原生调用 | 实参/载体 | 原函数返回 | 结果 |
|---|---|---:|---|
| `snapshot_message_boundary` | cached=20224，carrier.snapshot=None | false | 尚未到 20282 |
| `snapshot_message_boundary` | cached=20282，carrier.snapshot=None | true | carrier.snapshot=20282 已保存 |
| `snapshot_message_boundary` | cached=21302，carrier.snapshot=20282 | false | 保存的 carrier 保持 20282 |
| `_commit_d09_exact` | boundary=20282, idx=1, ping-pong=true, old_cached=20160, old_is_D09=false | false | 实际执行了 guard，未创建 exact entry |

因此 Q1 为“是”：carrier 在 Scheduler 的前填后被原生保存，最终 `cache_req(...finished=True)` 进入 `_cache_req_hybrid` 并调用 exact-commit。Q2 为“进入但返回 false”；实际失败条件是 `old_handle.cached_len != 0 and not isinstance(old_handle, _D09BoundaryHandle)`，即 pinned bd57 `scheduler/cache.py:648-656` 的 655 行。这个结论来自透明调用 receipt，而非由 `_d09_entry is None` 反推。

## Q3 / Q4：边界来源和同源判据

20160 由原生 `attention/linear.py:127-139` 的 mid-chunk 算式产生：`0 + ((20224 - 1) // 64) * 64 = 20160`。原始 state dump 也记录 UID0 `donate@20160`，随后 UID1 `resume-device@20160`。20224 是第一段前填结束点；它虽页对齐，却不是该 forward 的可捐赠“严格位于 extend 内”的 track 状态。

D05 的 13376 与 D09 的 20160 都进入同一 bd57 `_cache_req_hybrid` 函数，但**不满足 preregistration 的 same-source 定义**：要求“相同代码字节且相同拒绝 predicate/condition”。

| 案例 | 相关代码/条件 | 结论 |
|---|---|---|
| D05 decode tail | `cache.py:568-577`：current finish `cached_len=13554`，`insert_len=align_down(13554,64)=13504`，`insert_len == cached_len` 为 false；没有在 13504 取得可晋升 state，只保留既有 13376 node | exact/current-finish promotion 不发生 |
| D09 literal boundary | `cache.py:648-656`：old hybrid handle 为 20160，非 D09 handle；655 行 guard 返回 false | exact 20282 entry 不发生 |

所以 Q4 为“否”：函数相同，但决定结果的 predicate 与状态不同；不能把 D05 的 13376 归因成 D09 655 guard，也不能把 D09 的 20160 归因成 D05 的 13504 对齐规则。

## Q5：两项独立、默认关闭的 DIFFSOURCE 修复提案

### A. D05 decode-tail 对齐快照/晋升（预计 2 人日）

**范围：** 只处理 D05 类 decode tail；不碰 D09 literal-boundary entry。默认 `off`，需明确试验 flag。

在即将跨越/到达页边界 `P=13504` 时，捕获**恰为 P 的状态**并将该 P 快照晋升为可复用节点；不能把已经前进到 13554 的 live state 标注为 P 的 state。`13554` 仍是未对齐 current finish，应维持现行不晋升语义。页容量上，P 对应 `[0,13504)`（211 个 64-token 页）；13554 额外 50 tokens 必须仍为请求私有 tail，不能转交给 P node。

CPU default-off 测试必须同时断言三状态一致性：

1. **卷积状态**：P 的卷积历史来自 P 前 token，而非 13554 tail；
2. **递归状态**：P checkpoint 与恢复后继续计算的状态所有权/slot 计数守恒；
3. **PLE 状态**：PLE conv/ngram/context 对应同一 P，且不把 13554 的状态误装入 P。

另加前后 prefix/page/ref-count 守恒、13554 finish 仍不成为 P、以及 sealed D05 输入复放。工作量：0.5 人日设计/状态边界，1 人日 CPU fixture（conv/recurrent/PLE），0.5 人日独立复核。

### B. D09 非零 hybrid-handle exact-pointer 方案（预计 3 人日）

**范围：** 只处理 D09 carrier 20282 且已有 20160 hybrid prefix 的情形；不改变 D05 decode-tail 策略。默认 `off`，需单独试验 flag。

将现有 20160 prefix 的 KV pages/state 继续由原 hybrid node 持有；为 literal 20282 建立受控 exact pointer，final partial page 以 COW/私有页语义保存。不能以“替换旧 handle”方式夺取 `[0,20160)` 的 prefix pages 或 slot。实现前必须明确：

- old prefix 的 unlock/lock 顺序与 full/mamba/host refs 均守恒；
- exact pointer 仅拥有其 full-page 边界和必要的私有 partial page；
- 20160 node 在 exact pointer 创建、命中、淘汰、并发 reader 期间保持可恢复；
- 失败时回落到现有 guard，绝不释放仍被旧 handle/reader 引用的 pages 或 state。

CPU default-off 测试同样覆盖卷积、递归、PLE 三状态，并增加 e483/bd57 风格 page/slot/ref-count conservation、双 reader、exact 替换、回退 guard 与 UID1 20160 继续命中。工作量：0.5 人日不变量/所有权设计，1.5 人日 CPU fixture 与回收路径，0.5 人日并发/守恒测试，0.5 人日独立复核。

## T16 默认 gate（两提案共用）

任何实现默认关闭；先完成 sealed source/input/round SHA 绑定、CPU 三状态测试通过、完整 page/slot/ref conservation 记录、拒绝/回退 receipt、独立审查。随后才可申请一次单独批准的 T16 GPU 验证；CPU replay、HTTP 成功或启动日志都不构成 T16 通过。continuation 的成本上界应按剩余需重算 token/状态路径计算，不能用 decode TPS 外推或声称吞吐收益。
