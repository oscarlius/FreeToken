# Writer facts: slots, R046g continuation, and prefill timing

## 1. Actual auto-slot source and log line

In the production 481 worktree,
`python/freetoken/engine/engine.py:698-714` resolves auto cache geometry and
emits exactly:

```text
--moe-cache-auto resolved moe_cache_size={size} num_pages={pages} (prefill_overlap={overlap})
```

The authoritative actual slot count is `{size}` (not a generic `cache slots`
regex). Parse this exact line once during startup, require exactly one match,
and bind `moe_cache_size` plus `num_pages` to the requested arm. Existing old
`ServerArgs(...)` logs only show `moe_cache_size=0, moe_cache_auto=True` before
resolution and cannot prove the allocated size.

## 2. R046g continuation behavior

The reviewed producer is `r046c_ordinary_seed_driver_v3.py:65-88`:

1. loop index `index` creates request number `index + 1`;
2. it snapshots `messages`, builds payload with `max_tokens=2048`, renders
   frontend IDs, then tests the window limit before sending;
3. after a normal response it appends `original.assistant_message(result)`,
   then one read-only `original.exec_tool_call(...)` message for each tool call;
4. only when there are no tool calls, it appends
   `original.FOLLOW_UPS[index % len(original.FOLLOW_UPS)]`.

Therefore continuation from `trace.meta.window_hit` request 9 must retain an
explicit original producer index, not derive the follow-up from `len(messages)`.
Use stable `B09`, `B10`, `B11`, `B12` request/API/binding filenames. The
window-hit payload itself is request 9; its recorded frontend binding is
100,223 prompt tokens. For every B request, render with the same production
`candidate_frontend`, require planned IDs/count == Worker UserMsg == API usage,
then stop before dispatch if `prompt_tokens + max_tokens > 131072`.

## 3. Prefill compute timing: exact viable hook

The production engine path is `Engine.forward_batch` at
`engine.py:1034-1088`. It asserts `torch.cuda.current_stream() == self.stream`.
For prefill it calls either `_forward_layer_major(batch)` under
`ctx.forward_batch` / `model.forward_host_ctx`, or `graph_runner.replay(batch)`
or `model.forward()` (lines 1054-1060). After sampling it already records
`copy_done_event.record(self.stream)` (lines 1079-1082).

A minimally intrusive timing hook is:

- if `batch.is_prefill`, record a timing-enabled `start_event` on `self.stream`
  immediately before line 1047's forward work;
- record `end_event` on `self.stream` immediately after logits return at line
  1060, **before sampler/copy**;
- attach `(event pair, batch request UID list and input/cached lengths)` to a
  bounded observer queue;
- at the existing later completion/egress path, query `end_event.query()` and
  only then call `start.elapsed_time(end)`; never synchronize inside
  `forward_batch`.

This measures GPU stream interval for forward work, including queued work on
that stream; it is not host scheduling, tokenization, admission, or SSE TTFT.
If several UIDs share one prefill batch, publish one batch interval and list all
UIDs/lengths; do not divide or claim a per-UID compute duration without an
allocation rule. If the event pair is not ready before a request completes,
retain it until ready or mark the record missing; do not substitute TTFT.

Without this hook, only recover a **scheduling interval**, not compute time:
the ordinary adapter has dispatch / first SSE / terminal SSE monotonic times,
and the worker observer has wall-clock `time_ns`. Dispatch-to-first-output is
TTFT upper bound spanning queue/admission/prefill/decode/transport. It must be
reported separately as an interval, never `prefill_compute_ms`.

## 4. 131,072 capacity proof

Do not use character length or a static “about 126K” claim. Use the candidate
frontend used by production, with the exact cold payload, to obtain canonical
input IDs. Require `len(input_ids) + 256 <= 131072` before dispatch, save the
ID-array SHA/count, then require the Worker `UserMsg.input_tokens` and API
`usage.prompt_tokens` to equal that count. `cached_tokens == 0` is a separate
cold-path assertion. This proves request admissibility and actual rendered
context capacity; it does not prove allocator headroom or absence of OOM.
