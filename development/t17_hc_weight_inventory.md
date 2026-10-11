# Decoder-0 HC checkpoint inventory for a future operator replay

This is a bounded metadata-only inventory. It read the served overlay JSON,
its checkpoint index, and only the safetensors headers for the single selected
shard. The recorded shard SHA is a full-file integrity read, not a tensor
decode; no tensor or scale values were copied, no GPU context was made, and no
model scan was performed. It does not identify a numerical culprit or authorize a repair.

## Served binding

The served overlay is
`/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay`:

- `config.json` SHA-256:
  `deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80`.
- `model.safetensors.index.json` SHA-256:
  `660414e8300728ba80062e6a3c81cb76a65e2ab136ac9e9ceb450ba0c51c3c0d`.
- The overlay `config.json` and index are declared symlinks.  The replay
  validator binds their declared paths and permits only their exact regular
  targets: respectively
  `/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json.qwen4_exp.orig` and
  `/data2/model/Qwen3.8-Flash-Next-NVFP4/model.safetensors.index.json`.
  It records both declared and resolved paths; another symlink target fails.
- Its selected shard is the overlay symlink
  `model-00001-of-00010.safetensors`, resolving to
  `/data2/model/Qwen3.8-Flash-Next-NVFP4/model-00001-of-00010.safetensors`;
  file SHA-256 `63fde954be6f08b49b876f4f70a0ad0bcfee71aff7b1faa33779b6b32feca2a2`.
- The raw safetensors-header byte SHA-256 is
  `067c21570b51a074d1b15f12fa7e296effcefcec7ca59ff82a8ca150ef11f928`.
  The earlier `517139...` value was a canonical parsed-JSON hash and is not a
  raw-header binding.

The protected text configuration declares `hc_count=4`, `hidden_size=2560`,
and `hc_lowrank=320`; therefore HC width is `4 * 2560 = 10240` and the merged
down output has `320 + 4 + 12 = 336` rows.

## Exact raw checkpoint keys

All listed source tensors are BF16 in `model-00001-of-00010.safetensors`.

| Raw key suffix below `model.language_model.layers.0.attn_hyper_connection` | Shape | Loader target / role |
| --- | ---: | --- |
| `hc_norm.weight` | `[10240]` | `hc_norm.weight`, raw zero-centered norm parameter |
| `input_mix_weight_down.weight` | `[320, 10240]` | merged down rows `0..319` |
| `block_inject_weight.weight` | `[4, 10240]` | merged down rows `320..323` |
| `input_mix_weight_up.weight` | `[10240, 320]` | `input_mix_weight_up.weight` |

The similarly named `mtp.layers.0...` tensors reside in shard 9 and are not
decoder-0 language-model HC inputs: `_rename()` rejects raw names beginning
with `mtp.`.

## Loader mapping and quantization boundary

The actual candidate loader source on host 9 is
`/data2/FreeToken/wt/e2d14/python/freetoken/models/qwen4_exp/weight.py`, SHA-256
`5aae8cba53326464b3fab7f10a36b1fd6022c6080d0c1f72bfc6d8b73d1671cd`.
Its relevant logic is `_PAD_TO`/`_HC_WITH_INJECT` at lines 78-82,
`_DenseFuser._target()` at 126-141, and `fuse()` at 166-188. It concatenates
the two raw BF16 down parts in checkpoint order and appends twelve newly created
zero rows so `input_mix_weight_down_block_inject.weight` is `[336,10240]`.
Those pad rows have no raw checkpoint key or safetensors header range. The up
weight is not fused.

The matching served HC implementation source is
`python/freetoken/models/qwen4_exp/hc.py`, SHA-256
`89294d30f73843cf8c0c7c62ac90ea5a37682ed6abfe4e4402b4e442b21bcac6`;
the linear wrapper source is `layers/linear.py`, SHA-256
`3cb7be1103842ff4cdba165d63c198f69e30400346a1ea871aabc3019eb6fee8`.

`hc.py` constructs the corresponding `LinearReplicated` modules with
`quant_config=config.quant`: lines 95-112 create norm/down/up; lines 114-126
use the merged down, SiLU, and up projection. The overlay quantization JSON
lists `model.language_model.layers.0.attn_hyper_connection*` in `ignore` and
does not list an HC quantized-layer entry. This is configuration metadata, not
runtime proof of `quant_method`. A future replay must bind the actual HC observer
leaf metadata and loaded runtime class before assuming plain BF16 or any kernel.

The local checkout has CRLF physical bytes (`hc.py`
`d48ee7441b09c29451960d7be1f8bc253b53ff7d011a68b6338fb7f696e6a7c7`,
`weight.py` `59872eb2ab5502f53060013a62225b8f84bb0121856a0e83e6d5bf7cb356dd3e`).
Replacing local CRLF with LF gives exactly the host hashes above. This establishes
newline-only byte differences for these two files, not an implementation
divergence; runtime binding still uses the host raw hashes.

## Replay prerequisite

Only after R030 locates the first mismatch may a small operator replay use these
real parameters. It must bind the served config/index/shard/header hashes, the
merged-padding rule, actual leaf operator metadata, and the observed input rows;
it must not substitute decoded/re-encoded or synthetic weights. This inventory
does not select a replay boundary or change the canonical T17 comparison gate.
