# Independent retry-1 GPU evidence and raw-completion review — 2026-10-14

## Code Review Summary

**Files Reviewed:** 7  
**Evidence Files Verified:** 47  
**Total Issues:** 0 unresolved

### By Severity

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

### Evidence finding

`gpu_evidence/DOWNLOAD_MANIFEST.json` was re-hashed locally: all 47 recorded
artifacts match their pinned SHA-256 values.

The retry terminal remains authoritative and **must remain** `failed_harness`:
only `candidate_off` is listed as kept. E3 restoration is independently
recorded as passed (`...-02`, official SDK smoke exit code 0).

The captured candidate-on event is meaningful but incomplete GPU mechanism
evidence:

- `oom_faults.jsonl` records one actual `OutOfMemoryError` for uid 1, epoch 0,
  from a real over-total allocation.
- The API health evidence records `maintenance: restarting`, `backend_epoch: 1`,
  then `maintenance: serving` with the same `instance_id`.
- The backend handle ledger records one API process identity and distinct epoch-0
  and epoch-1 worker sets. `queued512.sse` is a terminal 128-token generation.
- The candidate-on client stopped before its post-recovery `long8257`, final
  request-accounting check, and worker-liveness assertions. This evidence does
  not establish a full GPU acceptance result.

The failure came from the public raw-completion wire contract, not an overly
strict private assertion. `api_server.py` synthesized
`UserReply(error_code="insufficient_workspace")`, but the captured
`fault_uid1.sse` emitted OpenAI `error.code: null`. The client correctly rejected
that response rather than parsing an error message.

### Serializer repair reviewed

The current product diff is the minimal root-cause repair:

- `python/freetoken/server/openai_api.py:452` passes `ack.error_code` through
  non-stream `/v1/completions` errors.
- `python/freetoken/server/openai_api.py:479` passes the same code through the
  streaming SSE terminal while preserving partial text and exactly one `[DONE]`.
- `tests/server/test_openai_api.py:386` verifies the raw non-stream 400 response;
  `:404` verifies streamed partial output, one coded terminal, and one `[DONE]`.

This change does not alter OOM detection, restart scheduling, request replay,
worker retirement, or recovery admission. It preserves the existing
`UserReply.error_code` value at the final public serializer boundary.

### Verification

- `py_compile` for the two changed serializer/test files passed locally.
- Local `pytest tests/server/test_openai_api.py` could not collect because this
  Windows interpreter lacks `torch`; its fresh route-level validation must run in
  the stated Linux main-venv. This is a validation-environment gap, not a passing
  test claim.

### Reviewed SHA-256

| Artifact | SHA-256 |
| --- | --- |
| `gpu_evidence/DOWNLOAD_MANIFEST.json` | `2690569237e1ebc2013d47ea897e4a8731ad39ed442b770fb273fe13508b9522` |
| `gpu_evidence/GPU_WINDOW_TERMINAL.json` | `ef61d6571915225f79c8766690d4dc0cb6fe86cfd1d9808ca98e88beb156252a` |
| `gpu_evidence/gpu_results/candidate_on/fault_uid1.sse` | `c9b2ecc11f44866d5fe31a4e6eb0ecb05c1e043647b4723ce5a8611a95d42519` |
| `gpu_evidence/gpu_results/candidate_on/native/oom_faults.jsonl` | `fa95719a26a30a67d326bb81099b729ec74fba35efbcebe3f2c12e4206d84ff5` |
| `gpu_evidence/gpu_results/candidate_on/native/backend_handles.jsonl` | `1ec712628cf8f6d00f2eab32d70816c10a6ac1149d405e0e4c50756dd40aae0b` |
| `openai_api.py` serializer repair | `02a805be3cc41d2df17ae583dfd5898d6fc7d77598559b3426197777cd77aadb` |
| `test_openai_api.py` route regressions | `191abf4054e743cb25dbcb74167c4ce5d2d4d0d02d92b7c1473589bc90b483fb` |

### Publication assessment

The contribution can be published honestly only after fresh Linux CPU route-test
and broader CPU evidence for the serializer delta. Its description must state:

1. GPU evidence demonstrates a real injected CUDA OOM, API-process continuity,
   backend epoch replacement, queued generation, and successful E3 restoration.
2. Both authorized GPU windows ended `failed_harness`; there is no full GPU OOM
   recovery acceptance claim.
3. The post-window serializer repair is CPU-validated only; no GPU claim may be
   transferred to that changed source revision.

### Recommendation

**COMMENT — no unresolved source defect after the serializer repair; await fresh
Linux CPU validation before publication.**
