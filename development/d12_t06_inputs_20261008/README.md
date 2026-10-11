# D12 T06 sealed-input analysis — 2026-10-08

2026-10-08 17:18 clarification: this file and `analysis.json` describe **whole-request suffixes**. The implemented D12 threshold applies to a single MoE prefill forward segment. The original request counts remain preserved; they are not branch coverage. A newly bound derivation finds 51 warm segments, 35 at or below256 and15 at exactly64. See `../D12_ENABLED_INPUTS_AND_SEGMENT_CORRECTION_20261008.md` for source bindings, frozen replay history and independent review. The absence of a whole-request suffix≤64 must not be read as absence of a64-token business segment.

This directory retains four read-only `route_summary.json` copies from E2-R046g. Root verified the enclosing round (`3f50a0...`), manifest (`282f1a...`), and their manifest bindings. This analysis independently rechecked each local SHA-256; the values are recorded in [analysis.json](analysis.json).

`suffix_tokens[].n` is the scheduler-worker suffix used here. It equals the same UID's `raw_suffix_tokens` value in all 34 copied rows, so the artifact records both facts without treating one as a new measurement. `round == 0` is the cold first request: it remains visible in the all-request denominator and is removed from the warm-continuation denominator. The bucket boundaries are `1`, `2–19`, `20–32`, `33–64`, and `>64`.

| Group | Eligible all / cold / warm | Warm min / p25 / p50 / p75 / max | `65–128 / 129–256 / 257–512 / 513–1024 / 1025–2048 / 2049–4096 / 4097–8192` |
|---|---:|---:|---:|
| G_seed12k | 12 / 1 / 11 | 123 / 248 / 317 / 1015.5 / 4922 | 1 / 3 / 3 / 1 / 2 / 0 / 1 |
| G_seed_45k | 12 / 1 / 11 | 157 / 195 / 330 / 1735 / 4918 | 0 / 4 / 2 / 1 / 2 / 1 / 1 |
| G_seed_real | 8 / 1 / 7 | 188 / 270 / 1417 / 1987.5 / 2389 | 0 / 2 / 1 / 0 / 2 / 2 / 0 |
| G_two | excluded | — | no ordinary-worker binding; no round/trace |
| Eligible total | 32 / 3 / 29 | 123 / 242 / 330 / 1834 / 4922 | 1 / 9 / 6 / 2 / 6 / 3 / 2 |

`G_two` is a decode-pair scope (`ordinary_worker_token_bound: false`), so its two suffixes (659 and 613) are not put into a prefill threshold denominator. The analyzer's decode expert fields (`f_*`, `R_B`, B2/two-decode counts) are also excluded: they cannot establish a prefill routed-only expert ratio.

No ordinary-worker suffix is at or below 64, so `n=1, 19, 32, 64` remain explicit coverage gaps. That does not erase the observed 123–4922 warm range or prohibit all A/B work. The smallest exploratory A/B pair is frozen as `--no-moe-prefill-overlap` in both arms, threshold `0` control versus threshold `256` enabled. `256` is a predeclared exploratory value near the aggregate warm p25 (242) and would cover 10/29 warm rows; it is neither an optimum nor a predicted benefit. If that functional arm passes, `512` is a separately declared sensitivity candidate (16/29 warm rows). GPU correctness, transfer diagnostics, and performance remain unmeasured.
