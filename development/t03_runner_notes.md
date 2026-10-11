# T03 runner admission and limits

`t03_runner.py` is local test tooling.  It has no default execution path:
only Linux `--run --rid E2-R... --batch N` reaches a server launch, and only
after all of these fail-closed admissions succeed:

- the worktree is exactly `E2-base@23f2e2c`;
- the matching closed D00 gate and independent PASS review exist;
- the read-only T00 baseline has `baseline_acceptance.json` with
  `verdict=kept` and `code_version=E2-base@23f2e2c`, plus a manifest-bound
  `round.json`; and
- the original `agent_trace.py`, tax probe and helper hashes match their
  recorded originals.

Admission is delegated to the shared `e2_runtime.admission()`/manifest
verification contract. It requires closed, history-bound, read-only D00 and
T00 rounds; D00 review RID/batch binding; and T00 reviewer, base commit, and
exact base tag. The runner archives the exact `e2_runtime.py` and
`t16_runner.py` it used beside its own source.

The six arms are started independently in `A,B,A,B,A,B` order.  They use the
49152 window, NUMA prefix, layer-major prefill 4096, slots 0, checkpoint and
D0.  The B arms add only `--no-prefill-anchor-cut`.  Parsed-argument checks
run before each arm's replay/tax probe and accept only PID plus the cut switch
across A/B; same-arm comparisons accept PID alone.  The runner takes its owned
GPU lock before creating a round directory, so a collision leaves an existing
round untouched.

The runner invokes the original remote-authoritative `agent_trace.py` twice
per arm with `--fresh-note`.  It validates its observed replay JSON schema
before reading it and requires exactly twelve live, non-error replay records
with positive TTFT.  It joins comparison rows by `messages_sha`, requiring it
to equal `trace_messages_sha` and the matching `round`'s digest recorded in
the immutable source trace. It rejects missing/duplicate rounds and any trace
other than the twelve source rounds; notes and replay index never establish
input identity.  It records P0/P1/P2.  Tax pair zero is the cold observation and
pairs one through four are hot; schedule-time D0 request metadata is grouped
by actual `rid`.  Coldness applies only to that request's first segment
(`cached_tokens <= 64`); each later segment must carry the preceding segment's
`cached_tokens + new_tokens`, so an A split such as `(6400,0),(624,6400)` is
valid rather than treated as a cache hit.

The final D0 JSONL row must align with every prefill event while the owned
service is alive.  Snapshot coverage comes only from the final successful
`D0 anchor_snapshots_taken=N` log line.  A zero is recorded as zero and is not
treated as positive coverage.  Any missing field, unexpected parsed argument,
server death, nonzero helper exit, cache breach, or telemetry mismatch stops
the run without retrying under altered parameters.
