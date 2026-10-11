# T17 HC GEMM replay preparation

This tool prepares a future, operator-only HC diagnostic after an R030 raw
comparison identifies the first mismatch. It cannot select an operator itself,
start GPU work, acquire a lock, reserve a round, or change T17 acceptance.
`--run` deliberately raises: execution belongs to a root-owned launcher with an
external lock/RID context. A root driver can use the exported
`validate_external_ownership(proof, rid=...)` gate, which requires matching RID,
PID, process birth ticks, global-lock path, lock owner, and lock token. This
module neither acquires nor releases that token.

Select exactly one operator: `down` compares `hc_down_input` to
`hc_down_output`; `up` compares `hc_up_input` to `hc_up_output`; `gdn` compares
`gdn_qkv_input` to `gdn_qkv_output`. R030 has equal upstream HC roles and the
first recorded difference at the GDN output, so future selection is `gdn` unless
later evidence changes that boundary. Both arms must
have valid terminal HC receipts, matching UID/slot/source/file SHA metadata,
positions `4608..4671`, and actual logical M `3585` warm / `3649` cold. The
selected output must declare `UnquantizedLinearMethod`, `TorchLinearKernel`,
requested `auto`, and BF16 CUDA weight metadata.

The checkpoint reader consumes the target config/index and one safetensors
header, plus a streamed full-file SHA-256 integrity read of the selected shard;
it does not decode tensor payloads during metadata validation. It binds the decoder-0 raw HC keys from the weight inventory and records
that merged down consists of raw down `[320,10240]`, raw inject `[4,10240]`, and
twelve generated zero rows. It never reads a tensor payload in preparation.

When an external runner is authorized, it may place each selected real 64-row
input into its original full M (`3585` or `3649`) with artificial zero rows,
then compare common-row bytes against both original outputs. Optional matched
M=4096 and M=1 oracle diagnostics remain explicitly artificial. The plan records
this limitation and does not claim loaded runtime weights equal checkpoint bytes
unless an independent runtime checksum is supplied.

The kernel source guard accepts the plain `TorchLinearKernel.apply` path only
when the bound source hash contains the observed `F.linear(x, w, b)` body and
the two actual class declarations. Runtime leaf receipt metadata remains the
authority for method/kernel selection.
