# D15 window A/B independent read-only review

Reviewed local source and the server copies (server SHA-256 at review time:
`window_runner.py` `e1318cae7e7990ac90b657b1f6f1a1998718601738be4258fa278e3397705bbe`,
`window_startup.py` `df2a7624bf104876f87d66ed60ce1fc416f001ff5f1481b7a354afd961050be4`,
`window_observer.py` `04e5d384b0bc8351583d39001e5c46a861e2bdad634727f0637db83e76c25f04`).
No process, GPU, lock, or source file was changed by this review.

## Blocking runtime findings

1. **Adapter/client binding schemas do not match.** The runner calls
   `client.bind(...)`, then passes its return to
   `r049_t21_ordinary_adapter_v2.ordinary_binding(raw)`. The specified actual
   adapter accepts only `schema == 'ft_r049_t21_ordinary_binding/v2'`, while
   the inspected `r049_t21_ordinary_client_v8.py` returns v9. The first request
   raises `ordinary T21 binding differs`. Pin a v2-producing client with this
   adapter, or replace both with one reviewed matching adapter/client pair.

2. **The global 1,800 s limit is swallowed during health polling.** In
   `start`, `remaining(deadline)` is evaluated inside `try`, then its
   `TimeoutError` is caught by `except Exception: pass`; the loop sleeps and
   repeats indefinitely. Compute `timeout = remaining(deadline)` before the
   `try`, and catch only `urllib.error.URLError`, `OSError`, and JSON parse
   failures. Let `TimeoutError` propagate.

3. **A start failure can leak the just-created process.** `start()` calls
   `Popen` and then may fail its PGID/session check before it returns `p` to
   `run_two`; caller `p` remains `None`, so its `finally` cannot clean it.
   Wrap all post-Popen checks in `try/except BaseException`; call
   `lifecycle.stop_owned_process(process)`, wait up to 120 s, then re-raise.

4. **Native token times are wall-clock, not monotonic token times.** The R046c
   observer records `DetokenizeMsg` as `time_ns=time.time_ns()`. Thus
   `metric()`'s `(last-first)` can be affected by clock changes. The v2 adapter
   supplies `monotonic_ns` only for received SSE events and explicitly calls
   those chunk clocks, not backend token clocks. Either add a reviewed observer
   `monotonic_ns` field for every DetokenizeMsg or label decode TPS as the SSE
   timing metric; do not label current `time_ns` arithmetic native timing.

5. **Actual auto-slot validation is unproven.** `slot_check()` searches only
   `/ (?:auto.?slots|cache.?slots)[^0-9]{0,20}(\\d+)/i` in `serve.log`. No
   reviewed source/log contract was located proving that production writes this
   spelling or that its final match is the effective auto-slot count. Parse a
   documented structured cache-report record, or add a startup assertion that
   writes a structured `actual_slots` receipt from the engine after allocation.

6. **Required telemetry is absent.** There is no 1 Hz `nvidia-smi` sampler,
   no R-thread snapshot per request, no actual prefill compute timing, and no
   request-scoped min-free GPU record. `metric()` correctly calls TTFT only an
   upper bound, but the output must explicitly omit actual prefill rather than
   leave a field that downstream readers could treat as measurement.

7. **B continuation does not preserve the original round index.**
   `next_b_payload()` chooses `FOLLOW_UPS[(len(msgs)) % len(FOLLOW_UPS)]`.
   The reviewed R046c generator chooses `FOLLOW_UPS[index % len(FOLLOW_UPS)]`.
   Pass an explicit continuation round index (first continuation after request
   9) and use it for both the file names (`B09.api.json`, etc.) and FOLLOW_UPS
   lookup. The existing `prior.stem.replace('payload','api')+'.json'` happens
   to form `B9.api.json`, but mixed zero-padding makes manifest ordering
   ambiguous; use `B09`, `B10`, `B11`, `B12` consistently.

8. **Cold prefix is not fully bound.** The proposed `build_text(...,129012)`
   result is not rendered with the production `candidate_frontend` before send,
   and the expected prompt-token count is not asserted against Worker UserMsg
   and API usage. The cold request must record source/probe SHA, rendered input
   IDs SHA and count, and require Worker/API equality plus `cached_tokens == 0`.

## Confirmed API facts

`r049_t21_ordinary_adapter_v2.ordinary_stream_request(base_url, input_path,
out, timeout=1800)` writes `<out>.sse`, `<out>.events.jsonl`, and `<out>` JSON,
then returns the same JSON object. It records `dispatch_monotonic_ns`, first and
terminal SSE event `monotonic_ns`, and SSE usage. `ordinary_binding(binding)`
returns `uid`, `input_ids_sha256`, `input_tokens`, `prompt_tokens`,
`completion_tokens`, `finish_reason`, `token_ids_sha256`, and `token_events`.
It validates token list length and `completion_tokens_delta == 1` but does not
create backend-monotonic timestamps. It is therefore suitable for ordinary SSE
transport and worker-token identity only with a matching v2 client.

## Minimum repair sequence

1. Pin one matching adapter/client pair and add a CPU test that exercises their
   real `ordinary_binding` schema with a genuine shaped binding fixture.
2. Make `start()` exception-safe and deadline-safe before adding request work.
3. Add a structured actual-slot receipt and a 1 Hz sampler whose lifecycle is
   joined before cleanup; retain every sample and min-free value.
4. Add explicit B round index/filename handling and cold frontend-token binding.
5. Test the real effects seam: Popen success followed by PGID failure, health
   timeout, binding mismatch, first A token mismatch, and cleanup failure must
   each leave no owned process or retain the lock for recovery as specified.
