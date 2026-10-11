# R044 FILEDRY handoff — 2026-10-07

Current writable source adds `--file-dry-run <fresh-sibling>` to `t10_e2_r044_prepare.py`. It validates the normal packet, copies the runner/capture startup/port-pair helper to writable `0600` files, invokes the existing paired API/TCPStore bind probe for all six services, and writes immutable receipt/plans. It never reserves a batch, takes a lock, starts a process, contacts HTTP, or creates `E2-R044`.

Formal execution now copies the same runtime sources to `E2-R044/source` and records a paired port receipt per arm. Formal GPU/R evidence is still absent; Linux source freeze, Linux CPU test, actual FILEDRY and a new R review must bind this changed source.

Local proof: `python -m pytest development/tests/test_t10_e2_r044_prepare.py development/tests/test_t03b_e2_r047_prepare.py -q` => 49 passed, 1 skipped; no service/GPU/port endpoint was started.
