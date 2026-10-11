# D09 batch153 CPU/source diagnosis

Written: 2026-10-10T09:16:59.1438343+08:00. This is a read-only diagnosis of the sealed `E2-D09-T17-20261010_batch153` evidence. It does not retry the run, change product source, reinterpret the existing formal verdict, or make a GPU/HTTP/build action.

## Bound evidence

The sealed raw root is `/data2/FreeToken/development/d09_t17_morning_20261010/runs/E2-D09-T17-20261010_batch153/E2-D09-T17-20261010`. Its `MANIFEST.sha256` has SHA-256 `73cd1520dc7405bf4472d955c2e9a7c88f0e194026c7bd6c2075096e8936c999`. `terminal.json` is SHA-256 `5deb1f86af826562ae624f9811e441b4d5d712fdff7d2543bf14026150e93936`. The candidate is clean `c17b69a46cd512fbf3d127d3879bce92caae457b`.

The terminal records three cleaned services and four calls, then `BoundaryStateError('boundary state mismatch; discard output comparison')`. Cold A/B state hashes match. At P=20,282, hot differs in `conv_states`, `recurrent_states`, and `slot:ple_conv`; `slot:ple_ngram_ctx` matches. The terminal therefore discarded output comparison and recorded `failed_harness`; this diagnosis does not alter that result or call it a C3 mechanism conclusion.

## Cache ownership observation

`services/hot_c0_p20282_t1020/serve.log:222` reports `free_pages(450) + cache_pages(317) != num_pages(768)`: 767 accounted pages, one unaccounted page. `scheduler/cache.py:783-827` is the exact accounting guard. The error occurs after the hot target path, so it independently prevents treating any later output observation as a mechanism result.

The source bound below identifies the only D09-specific ownership transitions near this failure, but does **not** reproduce the missing page. In particular, it is an unreproduced source inference, not a causal finding: `snapshot_message_boundary` copies the current linear slot to ping-pong and stores the literal boundary (`scheduler/cache.py:298-320`); finish first donates/frees the frozen boundary path (`:517-575`), and the non-page-aligned branch transfers full-page ownership to the singleton D09 entry (`:626-680`). Each branch changes the free frontier. A minimal reproducer must trace the actual `page_indices`, `prefix_len`, `free_upto`, and D09 entry indices around both donor finish and target restore before assigning the one-page discrepancy to any one line.

## UID, anchor, and geometry

The hot donor is receipt `input_receipts/0.json`, UID `0`, length 21,302, SHA-256 `24068f95180ac5cca644024d56f749a341df16ceb35574e41c83bb396471142a`. Its boundary receipt is `state_dump/boundary_receipts.jsonl:1`: UID 0, length 20,282, prefix SHA-256 `05735e47c67fcd9c86a76e0d9648bd99bff9e41b2a79a29052c7ba199e9734bd`. The hot target is receipt `input_receipts/1.json`, UID `1`, length 21,302, SHA-256 `22ed510abb88eaaac15e6103fe292ba23d641e18ea01c14fa1f2dce6c4790fbc`. `observations.jsonl:40` admits that target with `cached_tokens=20282`, and `:42` processes its remaining 1,020 tokens. The hot serve log corroborates this at line 198 with `#new-token: 1020, #cached-token: 20282`. Thus the intended D09 anchor was actually cached for the target request.

For the donor-side P comparison, cold A, cold B, and hot donor have the same recorded subchunk schedule: 20,224 tokens in layer-major children `[4096,4096,4096,4096,3840]`, then 58 to boundary 20,282, then 1,020 continuation. See each service's `observations.jsonl:3-6`; hot donor is UID 0. This rules out a pre-P cold-versus-donor *subchunk geometry* difference as an explanation for the P state mismatch. The hot target is necessarily a different resumed path (one 1,020 token continuation from cached 20,282), and its cache-integrity failure leaves no output-based mechanism conclusion available.

## Source identity and smallest next CPU check

Bound source: `python/freetoken/scheduler/cache.py`, SHA-256 `c19968b21dd5991913ef8e40aeaf51b44a9bed9ecf333af81af143b7c1fcdd6b` at candidate `c17b69a46cd512fbf3d127d3879bce92caae457b`.

The next minimal validation should be a new, separately approved CPU-only unit reproducer, not a rerun of batch153: set `CUDA_VISIBLE_DEVICES=""` and `torch.set_num_threads(1)`; construct the candidate CacheManager with the recorded page capacity (768) and the exact donor UID 0 / target UID 1 order; instrument only the existing `CacheManager._free`, `prefix_cache.insert`, and D09 entry ownership; assert `len(free_slots)+cache_pages==768` after donor finish and after target restore. It must also assert the observed donor schedule and target cached length (20,282), and must stop before any model server or HTTP action. Only after that conservation test passes may a separate protocol decide whether another formal run is justified.

