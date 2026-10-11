# R048 T09 v7 readiness

The v7 harness preserves the V0/A/B/C/S performance arms and separate D0 trace
diagnostics at 98,304 tokens and memory ratio 0.88. Native event tracing stays
default-off and ordinary SSE preserves the candidate wire, worker-token, and
terminal-stop bindings.

`native_all_zero_timing_semantics()` binds the actual e2d08 hybrid callsite,
CPU executor, and C++ pool. The current candidate exports only
`start_ns`, `end_ns`, and `barrier_wait_ns_total`; it has no serialized
task-not-submitted, zero-miss, or equivalent record. Therefore an all-zero
triple remains rejected as ambiguous. This is an evidence gap, not permission
to invent a product field or change a measurement criterion.

A fully resident hybrid route still enters `decode_submit` with all CPU route
ids set to `-1`; native workers skip those routes but submit, synchronize, and
record task completion. It is not a legal all-zero timing row.

The owned v7 exact-token wire wrapper sets `ignore_eos: true` and `stop: null`
for every T09 ordinary request. Before a completion count is accepted, the
candidate `ChatCompletionRequest -> GenSpec -> SamplingParams` path must retain
that flag, the exact `max_tokens`, and an empty `stop_strs` list.

Readiness remains blocked until E2-R049a is sealed `measured`. E2-R049 failed
metadata must still be read as `failed_harness`; E2-R050-gate-D15 and
E2-R051-gate-D08 must be rechecked as `kept` against the actual candidate
commit. Consequently this v7 package has no FILEdry receipt, R startup review,
or GPU authorization.
