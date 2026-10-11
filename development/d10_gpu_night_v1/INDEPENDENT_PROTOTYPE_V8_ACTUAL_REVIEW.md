# Independent D10 Prototype V8 Actual Review

**Verdict: FAIL.** CPU-only review; no GPU, HTTP endpoint, service, or compile ran.

The target-host V8 CPU receipt is a regular `0444` file with SHA-256
`8501343fa3710485a054e395ba26d1e63ed78e89ae3066a72024d088373839ba` and
reports five CPU tests passing. Its complete runtime source/runner/input map was
read back as sealed `0444` files. V8 fixes real V7 behavior: it binds frozen inputs,
stops after a failed group, validates branch producer identity, records preflight
before gates, checks post-cleanup GPU idle, and retains the lock on cleanup failure.
Independent same-body CPU mocks confirmed these paths.

V8 cannot consume the real formal governance schema. Calling its actual `manifest()`
on the sealed formal R067 retry1 round raised `manifest does not cover all entries`.
Formal manifests use `./` names and intentionally exclude `round.json`,
`round_history`, and the manifest itself. V8 includes those governance files in its
actual file enumeration. Formal artifacts must stay unchanged; V8 needs to reuse the
formal verifier's artifact-set rules.

The D09 retry1 cleanup path required by V8 does not yet exist while D09 is running.
More importantly, V8 expects a `birthbinding` object that the real rootwatcher schema
does not emit; actual cleanup readbacks use `child_absent`, launch/status hashes, and
owners. V8 would reject that producer shape.

Its round binding also checks only round ID and verdict. It does not verify T16's
candidate/base/default-off gate or D09 retry1's candidate/parent binding. Native
artifact evidence itself is strong: the reuse receipt, extension SHA/size pairs,
kernel-path empty diff, and clean tracked candidate worktree were independently
observed. V8 does not parse that evidence at admission time, relying instead on a
self-declared ABI field and reuse file hash.

No real T16 kept proof exists and D09 retry1 remains active, so a real admission must
not be filled now. After those proofs exist, V8 still needs the stated formal-schema
and binding repairs before another independent review.
