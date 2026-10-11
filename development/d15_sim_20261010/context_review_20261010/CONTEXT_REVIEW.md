# D15 Stage 0 context independent review

Reviewer timestamp: 2026-10-10 19:36–19:44 CST. This review is read-only for source evidence and existing results. It is not a GPU or token-equivalence acceptance.

## Evidence reproduced independently

The raw source is `/data2/_shared/runs/ft_rounds/E2-R046g`. A separate read-only recomputation checked every binding and route record consumed by `reconstruct_context.py`.

| group | bindings | route events | D0 min/max layer steps | calibration request tokens | full request tokens | median, prompt + prior routed decode |
|---|---:|---:|---:|---:|---:|---:|
| G_seed12k | 12 | 3241 | 3219/3219 | 3219 | 3219 | 22,192 |
| G_seed_45k | 12 | 3948 | 3929/3929 | 3929 | 3929 | 20,646 |
| G_seed_real | 8 | 1141 | 1125/1125 | 1125 | 1125 | 90,954 |
| G_two | 2 | 88 | 79/80 | 149 | 154 | prefix 673; full 674 |

For all 34 bindings, `worker_input.input_tokens == api.usage.prompt_tokens == d0.cached_tokens + d0.new_tokens`. Route `seq` is strictly increasing in every group. Every per-UID routed prefill/decode total equals that binding's `route.accounting` total. Therefore `reconstruct_context.py:18-54` and `context_proof.json` correctly bind complete prompts, preserve request identity, and weight medians by routed request token instead of scheduler step.

`G_two` has 85 route decode events. Its D0 snapshot contains 79 calls for layers 11–47 and 80 for layers 0–10. The calibration prefix is therefore the first 80 decode events: 149 request tokens. The five later one-request events make the full trace 154. This agrees with the calibration truncation in `sim_d15.py:33-36`; using 154 for the D0-calibration prefix would be wrong.

## Findings

### HIGH — published speed conversion uses an unbound context length

`sim_d15.py:74-99` initializes each UID at zero and accumulates only routed prefill `n_tokens`; it never loads the binding's complete prompt length or cached prefix. It then emits `L_ktok` from that partial value at lines 108-114. Consequently `ONE_PAGE_CONCLUSION.md:16` states `L=0.768/1.395/2.127/0.674`, whereas bound-prompt reconstruction proves `22.192/20.646/90.954/0.674` for full trace medians (G_two calibration prefix: `0.673`).

Impact: LRU/miss calibration remains independently valid, but all §4.7 speed numbers based on the first three old L values are not evidence-backed and must not guide a strategy decision.

Fix: consume the same binding file map in `prepare_group`, initialize each UID with `input_tokens`, assert full-prompt equality to cached+new, and rebuild speed-only outputs. Preserve existing simulation/calibration artifacts; publish corrected output as a new, hash-bound result.

### MEDIUM — first decode needs the runtime `+1` convention stated explicitly

`reconstruct_context.py:42` records the first routed decode at `prompt`. Runtime calls `Req.complete_one()` immediately after the prefill forward (`python/freetoken/engine/engine.py:1072-1079`), and it advances `device_len` by one (`python/freetoken/core.py:96-98`). The next decode forward runs one input token at position `prompt` (`python/freetoken/scheduler/scheduler.py:1201-1208`) with sequence length `prompt + 1`.

If §4.7's L means model input/context sequence length, each reconstruction value must be `+1` token. The effect is exactly `0.001 ktok`: G_two full `0.674 -> 0.675`, G_two calibration prefix `0.673 -> 0.674`, and likewise for the single-request groups. This meets a `<=0.001 ktok` numerical boundary but needs a declared convention. The result must label either prior-routed-decode context excluding the current decode input or model-input context including it; do not silently mix them.

### LOW — malformed route phases are accepted as decode

`reconstruct_context.py:38-47` treats every phase other than `prefill` as decode. Current raw data was valid, so no result changes. A future rerun should explicitly accept only `decode` and reject any other phase before it can silently alter counts.

## Gate for D15 result reuse

1. Keep calibrated miss-rate findings; their LRU replay does not use the speed context field.
2. Do not reuse the current speed table or strategy-throughput conclusion until a full-prompt L result is regenerated in a new result artifact and hash-bound to the bindings.
3. State the first-decode `+1` definition. Either form is within 0.001 ktok; the runtime sequence-length reading favors `+1`.
