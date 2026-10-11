# Future T16 entrypoints

`t16_candidate_runner_full_tail.py` and `t16_full_tail_base_runner.py` are the
single future measurement implementation. Former runner/launcher names are
thin compatibility entrypoints. Historical frozen copies remain immutable.

`python development/t16_candidate_stage_shared.py` creates a new source-addressed
Linux CPU stage. It includes the real R019/R021 fixture, all active adapters,
the full-tail tests and the reviewed process lifecycle. A complete successful
test log and its SHA, exact source SHAs and suite list are frozen with the receipt.

Invoke the frozen stage's `t16_candidate_launch_shared.py --stage <same-stage>
--case D07` for preflight. Add `--launch` only when it is next in the serial GPU
queue. The launcher verifies the current frozen receipt, source, log, ledger,
candidate trees and resource gate, then starts the same runner with `--run`.
Old stages cannot supply the new proof. No historical round is rewritten.
