# D03 state-envelope v2 readiness

`state_envelope_v2.py` was copied from the Linux authority `/data2/FreeToken/scripts/state_envelope.py` with origin SHA-256 `8b8719f2cee0d5105010aea4bad05cd2396dc9c656303977b08d7724f8d6a7e1`.

The only metric extension is a per-layer `max_abs` field in `paired_metrics` and CSV output. Existing identity, UID, prefix, layer provenance, shape, dtype, nonfinite, zero-reference, and relative-L2 envelope semantics remain unchanged. Integer max-absolute deltas use Python integer subtraction after tensor extraction, preserving adjacent int64 values beyond `2^24` and preventing signed-int64 overflow at the bounds.

Linux Torch CPU evidence: `/data2/FreeToken/runs/dev_D03/d03_state_envelope_v2_cpu_20261008_015606/report.json` (`b0e15e48796564d12b2c5a8201d4244708cfca9e0cfd25f95372168a282072ed`). The guarded run passed 9 tests for float, bf16, adjacent high-int64 values, int64 bounds, zero reference, shape/dtype/identity rejection, and real CSV values. Source is sealed `0555/0444`; no raw state groups, service, GPU, request, lock, or batch was used.
