# T17 HC GEMM execution callable

`execute(plan, ownership, output_dir)` is for a root-owned replay driver only.
It does not acquire/release a lock, create a round, or manage service lifecycle.
Before importing or using CUDA it requires a diagnostic plan, current terminal
warm/cold role files and hashes, equal selected 64-row inputs, current checkpoint
config/index/raw-header and full-shard integrity bindings, and a live ownership
proof.

The ownership proof must bind the current caller PID and `/proc` birth ticks,
the exact RID, `/data2/_shared/gpu.lock`, current lock JSON owner/token/PID, and
the lock file inode. Caller-supplied fields alone are rejected. The root driver
must hold that proven token before calling this function and remains responsible
for all status/cleanup.

The callable reads selected BF16 checkpoint payloads only after those CPU checks:
down fuses `[320,10240] + [4,10240] + 12` generated zero rows; up remains plain
`[10240,320]`; GDN fuses qkv `[10240,2560]`, z `[6144,2560]`, b `[48,2560]`, and
a `[48,2560]` into `[16480,2560]`. It imports the candidate `TorchLinearKernel`, verifies its source
hash/body, and invokes `TorchLinearKernel.apply` on a simple layer object rather
than substituting an independent formula.

It retains the actual M=3585/3649 with the shared real 64 rows followed by
artificial zeros, repeats each run three times, and saves every first-64 repeat
with exclusive creation and its SHA. Repeat differences are retained as pair
metrics instead of discarded; a numeric repeat failure remains evidence for the
root driver to classify. It also records warm/cold and optional M=4096/M=1 pair
metrics against the same live outputs. M=1 is 64 independent one-row kernel
calls concatenated in row order. The report records CUDA, PyTorch, device,
current checkpoint source data, output hashes, and precision flags
(TF32/BF16/FP16 reduction controls), plus the
absence of a cuBLAS algorithm identity or past-runtime-weight checksum.
