# R044b retry1 parser repair

This directory contains a CPU-side retry1 preparation adapter. It does not
modify E2-R044b-20261010, its batch157 raw bytes, failed_harness terminal, lock
state, or service/call count.

The adapter preserves raw ServerArgs fields and maps the frozen command
vocabulary alias max_prefill_length from actual server field max_extend_tokens
only in the normalized strict-comparison map. It rejects a missing extend field
or contradictory explicit pair.

The regression test binds the retained batch157 B1 raw serve.log SHA-256 when
run on the target. It proves the parser repair only; a new root admission and
independent review remain necessary before any retry.
