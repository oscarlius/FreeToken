# R027 independent CPU evidence

This is a retained read-only recomputation record. It is diagnostic evidence only and does not state an acceptance verdict.

## Reproduction

- Run `python development/t17_r027_independent_cpu_review.py` only when the local JSON receipt is absent. The script uses SSH host `9`, sends its audit program through stdin, sets `CUDA_VISIBLE_DEVICES=` and `PYTHONDONTWRITEBYTECODE=1`, and performs no remote writes, GPU operations, lock changes, or lifecycle operations.
- The script creates its JSON receipt with Python exclusive mode `x` and refuses replacement.
- Script SHA-256: `4a682715d648b811c0157eb670e2a5e9b8b261124241f0f8dc40136d7b8e0685`.
- JSON stdout/report SHA-256: `59721f2a9695f322380e008461d50aea57eaf4d268ffd8fe911102d3f47a7852`.

## Bound inputs

- RID/batch: `E2-R027-diagnostic-T17` / `55`; diagnostic SHA-256: `ec433cdd4e6b5e5ddeedb15415960cd926f3740634d8f31576f20528a3b4af04`.
- CPU-stage SHA-256: `85cf811e1d0d91c8c6e6e0dbd826edfc80a9793f7061b3cb7e4f653a8148ec7c`; all `18` stage/frozen source bindings passed.
- Exact input SHA-256: `5f72fe7f4117dbdd1d28c1e4bf212817352db3caf43def3bd97bbf10ceeabb95` (equals the launch-receipt input binding).
- Batch and both service identities were terminal with matching stop receipts; CUDA remained uninitialized.

## Tensor comparison

- The audit verifies 26 tensors: six fields (`conv_in`, `q`, `k`, `v`, `g`, `beta`) across two segments for warm and cold, plus each target `h[56]`.
- Segments are `[512,4608)` and `[4608,8192)`. Warm donor device length is 8193; cold device length is 8257. Both receipts bind `h` to absolute 8192 / computed row 56. Cold records its independent actual tracker at 8256 / row 57.
- Exact aggregate encoding: UTF-8 of sorted `logical_name + NUL + SHA256 + LF`; pair aggregate is sorted `logical_name + NUL + warm_SHA256 + NUL + cold_SHA256 + LF`.
- Warm aggregate: `dd0a4ddbd67ce2f0e56f3b77eff1d4886aaa18acdcf4ae222302e75a1479442d`; cold aggregate: `8418375b570867b1565aa54adf17fcd5496d499c1dbc9add35327ce997c0f0d0`; pair aggregate: `72855d74353c9f28d287d46457e3916d4d2e8f15c5f5fe8d5de668987e5cc8b7`.

| Field / segment | Equal | First different absolute token | Different bytes | Max abs |
| --- | ---: | ---: | ---: | ---: |
| beta_4608 | False | 4825 | 6 | 0.00390625 |
| beta_512 | True | None | 0 | 0.0 |
| conv_in_4608 | False | 4608 | 30515 | 0.125 |
| conv_in_512 | True | None | 0 | 0.0 |
| g_4608 | False | 4815 | 78 | 0.6962432861328125 |
| g_512 | True | None | 0 | 0.0 |
| h_8192 | False | None | 68115 | 0.015625 |
| k_4608 | False | 4610 | 3658 | 0.00390625 |
| k_512 | True | None | 0 | 0.0 |
| q_4608 | False | 4611 | 3774 | 0.03125 |
| q_512 | True | None | 0 | 0.0 |
| v_4608 | False | 4608 | 13643 | 0.015625 |
| v_512 | True | None | 0 | 0.0 |

## Frozen raw validation

- `artifacts.validate_case` was run from the frozen runner and exactly matched `diagnostic_batch55.json`.
- 128 cold and 128 hit tokens were checked. Tokens equal: `False`; full text equal: `False`; first token fork: `36`.
- Restored-state roles are recorded in the JSON report; their evidence remains distinct from the first-GDN numerical comparison.

## Interpretation limits

- The runtime record does not explicitly persist first-decoder index/layer ID; observer selection is the first `_is_linear` layer.
- The record proves an actual returned `h` but does not retain the original `return_h=True` keyword.
- Snapshot publication used `exists()` followed by `torch.save`, so its write is not exclusive/atomic. The report validates retained file hashes but cannot turn that publication pattern into an atomic write proof.
