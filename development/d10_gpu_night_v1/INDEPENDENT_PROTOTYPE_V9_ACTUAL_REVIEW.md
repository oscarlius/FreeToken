# Independent D10 Prototype V9 Actual Review

**Verdict: FAIL.** CPU-only review; no GPU, HTTP endpoint, service, or compile ran.

The sealed V9 receipt has SHA-256
`82d4715ca1cbcc58d55af1a356c5f184c6fe4d5b54d3e34a41bc666d89119fe2`.
Its `formal_r067d_consumption` claim is boundedly true: the standalone V9 formal
helper successfully read a real R067d retry1 formal manifest, including its `./`
entry convention and exclusion of governance metadata.

V9 is not an executable V9 runtime. It has no `main()` or `require_admission()`;
running it with `--filedry` silently exits successfully with no output. It directly
exports the V8 controller, child, and filedry. Those retain V8 RID, V8 child argv,
and a V8-only source map. The V9 proof function is never invoked, so it cannot gate
the inherited runtime.

Two actual helper paths independently fail. `native()` rejects the real regular
extension files before checking their already verified reuse SHA/size evidence because
their mode is `0775`. `cleanup()` raises `KeyError('status')` on the sealed actual
rootwatcher record, whose producer uses `actual_status`, a `child_absent` identity,
and launch/status hashes rather than V9's assumed fields.

Its semantic reader also uses the wrong formal JSON layout: it reads top-level
`candidate_commit`/`parent_commit` instead of `experimental.candidate_commit` and
`base.commit`. It searches serialized JSON for `False`, although JSON emits `false`.
Future T16 and D09 retry1 proofs are pending; that is not a conclusion about their
future outcomes. V9 remains blocked now by its unintegrated wrapper and incompatible
actual proof consumers.
