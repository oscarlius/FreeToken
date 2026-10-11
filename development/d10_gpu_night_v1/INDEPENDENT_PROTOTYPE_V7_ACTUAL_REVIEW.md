# Independent D10 Prototype V7 Actual Review

**Verdict: FAIL.** This review was CPU-only: it did not start a GPU, HTTP endpoint,
service, or compile.

The V7 package manifest is sealed at SHA-256
`c70a1cc5c7f7e2a0572badd4829ba9a687bf67b8b628c5e8294e4f5d2c046c69`; the
CPU receipt is sealed at SHA-256
`fe29e56c3836ba4ed11f75b5cffce32ecaf14d360c4dad56055d84cdeae37d82`.
All reviewed runtime sources, inputs, native provenance, manifest, and receipt were
read back on the FT host as regular non-symlink `0444` files with matching hashes.
The receipt and fresh target-host run report eight CPU tests passing.

V7 corrects several V6 failures. Its self-contained runner binds both inputs, its
parser applies finite/positive per-request checks and the >30 decode gate to both
original and exact-256 fixed groups, and its actual dispatch command uses two
requests at concurrency two. The child uses D07 APIs, reserves and rechecks API plus
TCPStore ports, and the independent same-body CPU mock verified pending/not-met/
failed-harness terminal classification, group budget records, and cleanup lock
retention. The retained R045 fixture remains below threshold and is correctly not
treated as a qualifying measurement.

The admission is still not evidence-authentic. Its `_binding` accepts any sealed
file whose path/hash/verdict were supplied by the same admission. A fresh direct
reproduction used fabricated sealed native, T16, and D09 documents and passed
`require_admission`. No canonical path, schema, RID, manifest relation, append-only
history, safe-cleanup content, or binding of the admission's native object to
`NATIVE_PROVENANCE` is checked.

The actual child has three further defects. It accepts a branch event based solely
on two booleans/count fields and does not validate its schema, observed method,
candidate, engine birth, or PGID. It dispatches all four groups before parsing any,
so a low-speed first group still consumes the full eight-call budget. Finally,
wrong-birth and pre-launch idle failures happen before `output.mkdir()`, leaving no
terminal artifact; cleanup also releases its lock without a post-stop GPU-idle check.

No V7 admission or GPU queue authorization follows from this review.
