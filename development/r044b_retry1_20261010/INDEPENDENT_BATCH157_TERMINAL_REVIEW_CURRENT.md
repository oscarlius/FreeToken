# Batch157 independent terminal review

- Reviewed at: 2026-10-10T10:48:29.897284+08:00
- Verdict: **FAILED_HARNESS_PRESERVED**. B1 has 24 raw request receipts; B2 never started, so no B1/B2 strict identity or product comparison exists. Those B1 bytes are retained evidence, not a valid measurement result.

The reproducing stack is `batch157.log`: `run_r044b_actual.py:241` calls `serve_identity`, which fails at line 171. The raw `B1_serve.log:2` ServerArgs has `max_extend_tokens=4096` but no `max_prefill_length`. The frozen code requires the latter as raw at line 170, even though its file-dry receipt declares the alias at line 154. Retry1 therefore keeps the raw record and derives `max_prefill_length` only in the normalized strict-comparison map; a contradictory explicit alias is rejected.

The telemetry terminal receipt is absent. The manifest remains `started`; `owned_cleanup.json` is also absent; the root recovery receipt records that vmstat PID 1798589 survived until recovery. The frozen `OwnedTelemetry.stop` can raise before processing sidecars at lines 72–73, and its lines 75–83 stop traversal on an earlier sidecar exception. The outer finally catches and discards that specific exception at lines 261–264, leaving only the generic cleanup error in `batch157.log`. The original individual exception cannot be recovered from existing artifacts. Retry1's mixin attempts every sidecar, records aggregate failures, and only writes a terminal receipt after all cleanup succeeds.

Root recovery is bound by `raw_evidence/ROOT_CLEANUP_RECOVERY.json` SHA-256 `6edae6cbbd195d676a104faaa7ec4d84f8dd32e55d4b0142745f256626801bfc`. It records batch157 lock release, absent sidecars after recovery, and incomplete telemetry. This package is CPU-prepared only and requires independent root review plus a new source-bound admission before any launch.

Retry1 executable wrapper and immutable-predecessor source binding were CPU-validated after this terminal diagnosis: source manifest `5dd3d0c7f8c7ca6c163a1f96614680db9a55b1ef958fc9c7cd17cd874cd8b82b`, file-dry receipt `b909974a07b405687c6c8857f16e9f530d569b8cc1d9381c34ead6dffe453f41`. The retry still requires a new root admission and independent review.
