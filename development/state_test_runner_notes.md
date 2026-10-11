# State test runner review notes

`plan/01_测试与调研/batches/state_test_runner.py` is a dormant test harness for
the currently executable portions of T04 phase 1, T10 phase 1, and T11 phase 2.
It has not been uploaded or run on the GPU host.

Before any future `--run`, the root executor must review and explicitly supply
the assigned RID. The runner rejects pre-existing round directories and requires:

- `/data2/FreeToken/wt/e2base` to be exactly `E2-base@23f2e2c`;
- D00 `round.json` to carry `closed_at`, `proposed_verdict=kept`, and
  `verdict=pending_review` or a later D04-authorized `kept`; independent `review_batch26.json` must carry the
  exact rid, batch 26, and `verdict=PASS`; `status_batch26.json` must be
  complete and `gate_batch26.json` must bind `new_commit=23f2e2c` plus kept;
  the D00 directory must be read-only, every manifest entry must verify, and
  the latest `round_history/round.v*.json` must be byte-identical to `round.json`;
- T00 `baseline_acceptance.json` to carry `verdict=kept`,
  `code_version=E2-base@23f2e2c`, and a reviewer; T00 `round.json` base must
  close to that commit and tag; the accepted T00 directory must be read-only
  and its manifest entries must verify;
- the card worktree commit/import path, clean tree, trace schema and exactly 12
  trace rounds;
- no GPU lock, no 8095 listener, and GPU memory below 1000 MiB.

The runner rejects a pre-existing round before acquiring its O_EXCL lock, then
creates the round only inside the lock-owned try/finally scope. Every service is
a new session and writes its PID/PGID/session. The runner owns and stops only
that group, then requires both port release and low GPU memory. All arm writes
use exclusive creation: a failure leaves evidence in its new round and never
overwrites an existing arm.

The next assigned E2 phase-one RIDs are exact: T04 `E2-R002`, T10 `E2-R006`,
and T11 `E2-R007`; `--batch` is mandatory. The runner archives the actual
`batch<BATCH>_<RID>_python.sh` wrapper as `batch.sh`, and writes only
`status_batch<BATCH>.json` with that batch, its own PID, RID, card, and state.
Although the card table retains E1 historical trace and flag definitions, all
new service/import/commit checks run on `e2base@23f2e2c`.

The runner captures command/environment, runner SHA, trace SHA, health, parsed
arguments and replay validation. It never downloads state dumps: only paths,
hashes, and comparison summaries are written. For T04, `eq_B_vs_R4096.txt` is
the same-configuration determinism gate: any nonzero `state_eq.py` return code
stops the round. Only R4096-to-R8192 and R4096-to-RLM legal-reorder comparisons
retain rc 1 as a diagnostic difference; other nonzero codes stop the run.

T10 pairs replay rows by `messages_sha`, requires it equal `trace_messages_sha`,
and rejects non-bijective or non-12-round outputs; it does not pair by round
index. T04 allows only its specified `max_extend_tokens` / LM and generated-PID
differences. T10 and T11 allow generated PID only. T11 has the card's
`slots=32`, dump, and `FT_D3_TRACE=1` configuration, but classification of the
uid=8 trace lines remains a reviewer readout rather than an invented parser.
Replay metadata and every replay row must state `dry_run=false`; simulated
replay output is rejected.
