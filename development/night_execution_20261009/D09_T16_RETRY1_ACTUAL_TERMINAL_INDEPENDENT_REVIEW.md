# D09 T16 retry1 independent terminal review

## Verdict

**PASS — `kept` for D04 closure.** Batch 144 is an actual completed measurement set for `E2-D09-T16-night-20261010-retry1`; its own terminal state is `complete_measurements_pending_review` and its proposed verdict is `kept`. This is not broader product acceptance.

## Evidence

- `status_batch144.json` — SHA-256 `b011370ead1ad1dfecedb8793936837b011b282f977ee2ea5d4ed40a498b62ae`; batch 144, `kept`, updated `2026-10-10 02:31:10 CST`.
- `candidate_binding.json` — SHA-256 `f7d75d189e2e0199360bda6c7ae214bba7b2dc487cbe5ceb342c66c9a363c0b5`; parent `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, candidate `c17b69a46cd512fbf3d127d3879bce92caae457b`, candidate runner `ed628f69ae62bb84accb360c0ec306ab8514908853eb607b2df2f9ab9ad776e3`.
- All four candidate `serve_args.txt` files record `message_boundary_ckpt=False`; their paired `args_checked.json` files show that flag and only a PID suffix difference. The declared public default is also off.
- `gate_batch144.json` — SHA-256 `a5de3b46600d137da810291fc5d2b054a868e6306e04f2ffe6ceaf2a9f4843ab`; eight arms are present. Direct static inspection found every `ready_sayok`, all required serve documents, the expected cold-token values and `cached_tokens=0`, paired matching output hashes, and each tax record with five positive single and five positive multi results.
- Actual full protocol count is **100 HTTP generations**: `8 + 4×1 + 4×2 + 8×5×2`. The independently sealed count review JSON is SHA-256 `48adea9d0b998e1223dc13d963959d1daeb143cf602493200edd7a7289fd95bd`.
- `D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json` — SHA-256 `92dcb93d2e831b5f614df1992c2f85d28f6b743496fbd2379e475fa1de22f105`; it records clean retry1 ownership cleanup and all eight owned process groups absent.
- The observed raw round has 160 files and deterministic sorted path/hash inventory digest `c0442402f74503743e543722de781eb91835905b1143b6197ba6f5d27691a67c`.

## D04 closure

Root can create a retry1-specific pending `ft_round/v2` document that binds the batch-144 records, eight serve arms, cleanup readback, and this review; revalidate only the retry1 owned identities; then use canonical closer `d04_server_round_close_db7b2787.py` (SHA-256 `db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b`), append `kept`, run its check, generate `MANIFEST.sha256`, and set the closed artifacts readonly. Batch-142 `close_d09_failed_harness_v1.py`/`v2.py` must not be used.

## Gaps

The raw round has no `round.json` or `MANIFEST.sha256` yet, so it is not formally D04 sealed. This review did not replay GPU or HTTP work.

## Risks

The cleanup readback proves retry1 ownership at its recorded time; it does not prove current global GPU idleness. The cleanup record explicitly has `product_acceptance=false`; this measured `kept` result is not product acceptance.
