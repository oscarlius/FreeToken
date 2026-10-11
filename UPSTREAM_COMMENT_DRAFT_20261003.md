# 上游 PR 回帖草稿（4090 第二机复现数据）— 待用户批准后再发

状态：**草稿，暂不发送**（用户 2026-10-03 18:50 裁决）。发送触发条件：**D3 的状态层无损判据建好并跑通之后** —— 20:12 更新：工装已建好并出数，但**跑通的结果是「不等」不是「等价」**（11 个可比长度里 10 个状态层不等，同配置跨进程基准 12/12 逐位一致、地板为 0），所以这条前置条件**没有满足**，仍然不发；而且现在发出去等于把已定位的成因（第四刀：恢复后续算，已排除搬运/槽位选择/token 账面三项）通报给上游 —— 而且结论性质变了：**「逐位等价」这条门在恢复路径上根本不可达**（A 侧从 12672 恢复、只续算 704 个 token 得到的 13376 边界态，就与 B 侧全量重算的 13376 不等；`ple_ngram_ctx` 逐位相等，所以不是少算/多算 token），不能把它当发帖前置条件一直等下去。能发的正确形态是「报告一个实测现象 + 建议把验收判据改成边界容差 + logits 等价，并给出实测偏离量级」，不是「复现并背书正确性」。发不发、以哪种形态发，仍等你点头。。#578 那段证据完整（吞吐 + temp0 逐字 + D0 字节序列），等成因二分那刀切完再一起决定发不发。任务书 `TASK_UPSTREAM_PRS_HYBRID_20261003.md` 最后一段要求「E1-R001、E1-R003 若在 4090 上通过，把实测数据回帖到对应 PR」；E1-R001 判定为 `kept`、E1-R003/R004 判定为采用存储层+自挪触发点，数据在下面。发之前需要用户点头（外部可见动作）。

机器与模型：RTX 4090 24 GB ×1，CUDA 13.0，Linux，模型 `Qwen3.8-Flash-Next-NVFP4`（NVFP4 量化，与 #578 作者同款模型、不同卡）。
我们的树：上游 `d3512b4` + 自研 D 系列（含 `--prefill-layer-major` 层优先预填）+ cherry-pick 该 PR 的 head。

---

## 给 #578（NVFP4 预填按位放置解量化）

```
Second-machine reproduction on RTX 4090 (same Qwen3.8-Flash-Next-NVFP4 checkpoint, CUDA 13.0, Linux).

Base tree: upstream d3512b4 + our layer-major prefill, then cherry-picked this PR's head.

cold 32K prompt, temp 0, thinking off, window 49152:
  --prefill-layer-major: TTFT 13.864 / 13.782 s  ->  6.604 / 6.486 s   (-52%)
  chunked 4096:          TTFT 25.044 / 21.610 s  ->  ~-2.2% (small)
  decode: unchanged (39.58 / 37.83 tok/s before and after)
  64K prompt at window 73728: TTFT 14.08 / 12.426 s, decode 36.4 / 37.08 tok/s, no OOM

Bit-exactness: with temperature 0 the outputs are character-identical to the same tree without this
patch, and the per-chunk H2D byte sequences recorded by our counters match exactly. So on this
model/geometry the placement change does behave as a bit-exact reordering.

Two notes that may matter for review:
1. Most of the win we see is on top of layer-major prefill. On plain 4096-chunk prefill the delta is
   only ~2%, so the PR's value looks coupled to how prefill is blocked out. Our layer-major path is
   not upstream yet.
2. There is a fixed ~2.7-2.9 s per-request cost before the first token on this server that is
   independent of prompt length and of prefix-cache hits (400 chars cold 2.95 s / warm 2.88 s;
   20k chars 3.10 / 2.80 s; the same 20k chars split into 12 messages 5.43 s). At 32K prefill our
   TTFT is ~6.5 s, so roughly 45% of what is left is that floor, not expert dequant. Worth knowing
   when reading end-to-end numbers.
```

## 给 #577 / #505（预填中间块 GDN 检查点放进 pinned host bank）

```
4090 measurement, same Qwen3.8 checkpoint. We cherry-picked b1fd362 (which already contains the 5
lines from #505) onto upstream d3512b4. Single conflict, 20 lines, in kvcache/hybrid_radix_cache.py.
pytest tests/scheduler tests/kvcache -> 2 failed / 370 passed / 1 skipped, and the 2 failures are
identical on the parent tree (our own attribution: a hot-path attribute read against a
SimpleNamespace stub in tests/scheduler/test_abort_inflight_prefill.py), so not introduced here.
The bundled tests/kvcache/radix/test_hybrid_host_bank.py passes.

Effect, measured with a real 12-turn agent trace (10 turns with tool calls, 12 with reasoning, last
prompt 21,976 tokens), replayed at temp 0 against a freshly started server:

  shape A - requests arriving with a *shorter* prefix than what was already computed
  (rollback / branch / truncating edit), i.e. your "normal shape of an agent":
    --mamba-host-slots 32 : sum TTFT 66.6 s, prefix hit 82.9% (11/12 rounds), 34,998 tokens recomputed
    --mamba-host-slots 0  : sum TTFT 211.2 s, prefix hit 0%   (0/12 rounds), 204,406 tokens recomputed
  shape B - plain append-only agent loop: both 99.5% hit, 32.4 s vs 34.9 s. The bank adds nothing here.

Two findings you may want in the PR description:
1. It does engage under our layer-major prefill too. We expected not, because archive_chunk_track is
   only called on the ChunkedReq branch, but behaviourally: layer-major + slots=32 hits 5/12 rounds
   (39.4%), layer-major + slots=0 hits 0/12 while its append-only passes hit normally. So the
   checkpoint restore path is reachable from layer-major, just at about half the coverage of chunked
   prefill (39.4% vs 82.9%, 123,958 vs 34,998 tokens recomputed). We are planning to keep your host
   bank as the storage layer and extend the archival/match boundary ourselves.
2. It does not cost prefill speed: full-recompute round, same model, layer-major 12.109 s with the
   bank on vs 12.428 s with slots=0.

What we could not verify with an output-level gate: we tried "restored state == full recompute" via
temp 0 first-32-token equality. On 12-21k-token prompts the reference pair (same request, identical
per-round cached/recomputed counts, differing only in slots) itself disagrees in 9/12 rounds
reasoning-inclusive and 1/12 content-only, so the gate's false-positive rate is the same order as the
signal. If you have a state-level assertion (compare the restored GDN tensor against a from-scratch
recompute in-process) it would be the more usable check; we do not have one yet.
```

---

发送前还需要落实的两点（已按证据等级改过措辞）：
1. **#505 的前置红/绿已补**（父轮树只打测试 10 failed → 只打实现 23 passed），所以草稿里「bundled tests pass」的说法可以保留，但**不要**写成「我们复现了它修的问题并证明它修好了真实推理」—— 两个 PR 的测试都用合成标记值（`fill_(value)` / `-9`），证的是**检查点选择与搬运**正确，不是**数值等价**。
2. **数值等价（bank 恢复出的真实 GDN 状态 == 全量重算）我们已经做了状态层测量，结果是「不等」**（batch18/batch19，20:12）：同轨迹两个独立进程，`slots=32`（11 次恢复）vs `slots=0`（全量重算），11 个可比长度里 10 个在状态层不等（max|Δ| 1.906–12.08），archive↔host 的 sha 44 对全一致（搬运没改 bit），同配置跨进程基准 12/12 逐位一致（噪声地板 0）。**成因还没二分**：checkpoint 内容错，还是恢复后按不同子块边界续算导致的合法 bf16 舍入路径差（参照臂不产生中间边界落盘，要补一个边界落盘点才能切）。**这一段在二分出结果之前不要写进回帖**，无论哪种结论都对作者有用，但必须是确定的那一种。同时 batch16 那个约 2.87 s 每请求固定成本与 ckpt 的多消息税只做了一次读数（batch17 的 N=5 已撤回「ckpt 税」那半），回帖里那句「roughly 45% of what is left is that floor」需要在 N≥3 复测后确认或删除。
