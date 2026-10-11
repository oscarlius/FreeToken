# E2-R013 fork classification (read-only CPU analysis)

Source: sealed `/data2/_shared/runs/ft_rounds/E2-R013`; all 431 manifest entries and the preserved `round.v001.json` were verified before reading logits. CPU tensor loads used `map_location=cpu` with CUDA hidden.

Protocol: each pair used two fresh service processes, warmed its own prefix, then captured `P+X` at `K=1`. These are pairwise reproducibility observations, not direct cold-versus-warm requests or causal proof.

Parent token binding: R013 `phase1_manifest.json` is byte-identical to E2-R017 phase1 (`31f1a9c190f2b529b8e4b2d2bc964af0b5cd5e084d4a16b05db797143c4df98e`). All 11 stage2 forkpoints matched exactly one parent forkpoint on messages SHA, prompt IDs, K, first-difference index, common generated IDs, and observed next IDs. Each parent `int32le` prompt-token SHA-256 was recomputed. R013 stage order maps to parent ordinals `10, 4, 8, 1, 6, 2, 0, 5, 3, 9, 7`.

The T10 card supplied no early/late threshold. This report uses a descriptive partition only: token 0 (`idx=0`), early (`1..10`), late (`>=48`). It creates no PASS gate.

| fork | idx | class | top1 token / logit | top2 token / logit | margin | max A/B gap |
|---|---:|---|---|---|---:|---:|
| fork00 | 107 | late_idx_48_plus | 112244 / 23.625 | 101908 / 22.875 | 0.750 | 0.000 |
| fork01 | 154 | late_idx_48_plus | 1042 / 22.875 | 11 / 22.750 | 0.125 | 0.000 |
| fork02 | 4 | early_idx_1_to_10 | 5144 / 26.875 | 328 / 25.500 | 1.375 | 0.000 |
| fork03 | 10 | early_idx_1_to_10 | 799 / 25.750 | 506 / 25.750 | 0.000 | 0.000 |
| fork04 | 1 | early_idx_1_to_10 | 31315 / 22.000 | 73916 / 21.000 | 1.000 | 0.000 |
| fork05 | 0 | token_0 | 6820 / 20.125 | 5666 / 19.750 | 0.375 | 0.000 |
| fork06 | 2 | early_idx_1_to_10 | 16561 / 28.750 | 6587 / 28.125 | 0.625 | 0.000 |
| fork07 | 48 | late_idx_48_plus | 96846 / 23.500 | 109226 / 23.375 | 0.125 | 0.000 |
| fork08 | 0 | token_0 | 6820 / 25.250 | 96846 / 25.000 | 0.250 | 0.000 |
| fork09 | 0 | token_0 | 109185 / 23.500 | 6994 / 21.625 | 1.875 | 0.000 |
| fork10 | 9 | early_idx_1_to_10 | 314 / 24.125 | 13 / 23.750 | 0.375 | 0.000 |

## Three token-0 examples

- `fork05`: top1 `6820` = 20.125; top2 `5666` = 19.750; margin 0.375; A/B max logit gap 0.000; top1/top2 equal: True/True.
- `fork08`: top1 `6820` = 25.250; top2 `96846` = 25.000; margin 0.250; A/B max logit gap 0.000; top1/top2 equal: True/True.
- `fork09`: top1 `109185` = 23.500; top2 `6994` = 21.625; margin 1.875; A/B max logit gap 0.000; top1/top2 equal: True/True.

Counts: token-0 3; early 5; late 3; unclassified 0.

Provenance: `round.json` SHA-256 `580a24ff8d4009c07fd203eec2660d896922574fae92eadd976ca01c27acbf1c`, `phase1_manifest.json` SHA-256 `31f1a9c190f2b529b8e4b2d2bc964af0b5cd5e084d4a16b05db797143c4df98e`, `MANIFEST.sha256` SHA-256 `804d84e9fe0692d2989ba5786cc987599181ff59ecfe687e68b153d49b39cab8`.

Limitation: the equality and zero A/B logits gaps show reproducibility under the recorded protocol only. They do not identify an underlying cold/warm causal path.
