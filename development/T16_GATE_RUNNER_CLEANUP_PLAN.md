# T16 shared runner cleanup plan

1. Reuse `t16_candidate_runner_full_tail.py` and its single protocol implementation
   `t16_full_tail_base_runner.py`; remove the proposed duplicate `t16_gate_runner.py`.
2. Lock behavior with the actual R019/R021 fixture and targeted lifecycle tests
   before changing future launch entrypoints.
3. Make obsolete executable entrypoints thin adapters to the shared implementation.
   Require a newly reviewed, frozen stage receipt; reject stale source bindings.
4. Preserve historical preparations, immutable round copies and the running R022
   execution copy. Their recorded hashes remain evidence, not future launch pins.
5. Derive telemetry coverage from observed parent events and the explicit terminal
   event coverage proof. Never derive expected counts from a gate/card number.
6. Verify event sequence, per-row transfer bytes, complete output and process
   ownership checks still reject malformed evidence. No GPU launch in cleanup.
