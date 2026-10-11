# D15 / T21 token-8 read-only findings

**Status: unresolved; D15 enable path remains stopped.** The only source-bound observation is PA1 UID 1, output token 8: retained L1/P1 `103988`, PA1 `103781`; the first seven tokens match. This is an *output step*, not an identified model layer. The PA1 token timestamp is an observer timestamp, not an adaptation timestamp. [T21 localization lines 9-13; SHA `5efbf6…987e1`]

| Required localization | Finding | Evidence boundary |
|---|---|---|
| Layer / expert / slot at token 8 | **Unknown.** | The retained files lack a per-step expert route, slot map, bank row, logits, or adaptation receipt. Therefore no actual layer, expert, or slot can be named. [localization 21; SHA `5efbf6…987e1`] |
| Did a replacement occur? | **Unknown.** PA1 requested `profile+adapt`, `adapt_every=1`, `swaps=1`; this is not a receipt that a plan published at token 8 or at all. | Existing source-bound summary says the 1,676 profile experts were preloaded into `[1024,2700)` and that per-step replacement is not recorded. [localization 9-11] |
| Did prefill overwrite a slot below `2E`? | **Unknown.** Actual resolved `moe_cache_size`, `num_experts`, slot map, and prefill-buffer trace are absent. | Static, unbound-current code reserves `[0,2E)` for double buffers and classifies only slots `>=2E` as stable hits; it cannot establish R049c state. [offload cache 1321-1358; kernels 66-85] |
| Same-kernel numerical explanation | **Conditional hypothesis only.** If runtime routes, weights, and maps were equal, a different token would require a differing activation/logit path; no evidence establishes that premise. A slot-address-only decode-reduction mechanism was previously excluded statically, but that does not prove numerical equality for PA1. [coordination 1742] |

The historical candidate source describes a transactional replacement plan/publish path (`offload_cache.py:952, 997, 1040`), but the source-bound candidate SHA is `5d7a9b…65df0`; the available current tree has a different SHA and is not substituted as R049c evidence. The formal `not_met` remains unchanged. [localization 15-21; terminal 3-19]

No new capture, GPU work, source change, or enable-path action was performed. Evidence index: `EVIDENCE_INDEX.json`.
