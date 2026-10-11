## D09 T17 batch164 independent closure review

**Decision:** `CLOSE_TERMINAL_AS_FAILED_HARNESS`. This is approval to formally archive the completed terminal result only. It is not product acceptance and it does not authorize another GPU attempt.

The original terminal is preserved byte-exactly in `terminal_original_snapshot.json` (`63a27ab3fbc95471cea02c270a437bb584027f0bd1892d99efb57ac7de570d2d`). Its 76-file `artifact_sha256` map exactly matched the live raw directory. The live terminal remains `failed_harness`, with three cleaned services and four calls; no result or count was changed.

Current cleanup revalidation found the controller and all three owned service groups absent; all six recorded API/TCPStore ports (31501–31506) bindable; `/data2/_shared/gpu.lock` absent; `nvidia-smi` reported no compute applications and 4 MiB used memory. The terminal records `post_cleanup_closed=true` and `gpu_lock_released=true`.

The immediate failure is the `evaluate()` usage assertion at `protocol_t17/runner.py:166`. The exact-ID binding matches, but the real hot target response reports `cached_tokens=20160` where the configured boundary is `20282` (prompt 21302, completion 32). This is an observed cache-contract mismatch from the actual product run, not a missing-tooling, source-pin, or cleanup failure. The runner’s generic `AssertionError` catch carries it as `failed_harness`; this closure preserves that terminal verdict rather than relabeling it.

The JSON closure input carries every original raw-file SHA, exact terminal binding, cleanup revalidation, and the pinned formal round tools. Root may create the append-only formal round archive with `pending_review -> failed_harness`; it must retain the original terminal result and exclude product acceptance.
