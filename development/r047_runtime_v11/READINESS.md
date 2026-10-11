# R047 v10 CPU readiness

This isolated v10 replaces only the R047 post-trigger cache evidence record.
It preserves candidate `0aa23431e5b800797543bdecbf35a01045131d7d`, six ABABAB arms,
`E2-R046g` producer and `E2-R045`/`E2-R044` predecessors, 98K / 0.88
serve settings, and the D0 snapshot criterion.

For the final positive turn, v10 serializes the exact ordinary request once,
hashes those exact bytes, retains raw SSE bytes and SHA, derives the
`chatcmpl-{uid}` from raw SSE, and joins it to that UID's D0 prefill rows.  A
cache-hit record requires an integer first-admission cache value, zero cache
on all continuations, and `cached + sum(new) == API prompt_tokens`.  API
absence is recorded as `{state: "unreported", value: null}` and is never
coerced to zero.  This is an ordinary wire input SHA; the current R047 D0
writer has no worker UserMsg/input-ID observer, so v10 does not invent one.

CPU readiness does not satisfy FILEdry, independent review, formal
predecessors, or GPU admission.  The future queue gate remains closed until
its actual closures exist.
