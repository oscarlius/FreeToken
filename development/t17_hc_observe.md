# T17 first-GDN HC observer

`t17_hc_observe.py` is a runtime-only, fail-closed observer for the next
original-4096 T17 numerical diagnosis. It is not a runner, a launcher, or an
acceptance gate. The startup owner installs it after loading the real candidate
model and supplies the active batch getter; the runner calls `finalize(uid)`
only for the target terminal reply.

## Exact target

Only a singleton, non-decode second layer-major child is eligible:

- `cached_len == 4608`;
- `(device_len, extend_len) == (8193, 3585)` for warm donor or `(8257, 3649)`
  for cold query; and
- rows are the shared absolute interval `[4608,4672)`.

Decode callbacks, the first child, later warm cache-hit continuation, and any
other cached coordinate are ignored before coordinate validation. Target
multi-request batches, malformed coordinates, identity drift, a missing role,
or duplicate role make `finalize` reject the observation.

## Runtime source path and roles

The real candidate path is
`python/freetoken/models/qwen4_exp/model.py:95-105`: decoder 0 calls
`attn_hyper_connection.mix(hidden)` then `linear_attn.forward(block_input)`.
`hc.py:114-126` makes `mix` call `_down(rn)`, SiLU, and the up linear. `gdn.py`
`:143-150` calls the GDN input projection before it splits `conv_in`.

The installer asserts decoder 0 is linear with `_layer_id == 0`. Separately, it
asserts exactly one PLE owner at decoder 1, `_layer_id == layer_id == 1`, and
the passed parsed PLE IDs are `(1,)`. This binds the known HF one-based `[2]`
to the already parsed zero-based candidate configuration without assuming PLE
belongs to decoder 0.

It wraps only existing bound `mix` and `_down` methods plus existing `forward`
methods. Each original runs exactly once with its original arguments and result
object. The nine saved CPU clones are:

1. `embedding_output`
2. `hc_mix_input`
3. `hc_down_input` (the normalized `rn` argument)
4. `hc_down_output` (whole down-linear output before `_down` slices it)
5. `hc_up_input` (after SiLU)
6. `hc_up_output`
7. `hc_mix_output`
8. `gdn_qkv_input`
9. `gdn_qkv_output`

Each role records UID, linear slot, cached/device/extend coordinates, absolute
positions, CPU tensor shape/stride/dtype, class/method/source hashes, and leaf
operator metadata. The leaf metadata contains only declared class, dimensions,
quant-method fields where actually present, and weight shape/dtype/device; it
never copies weights or scale values. `unknown` is retained where runtime
attributes do not declare a quantization detail.

## Output and integration contract

Use a fresh per-arm output directory. Snapshot `.pt` files and the receipt are
created with `x`/`xb`; collision raises and leaves the existing bytes intact.
The terminal integration must retain the returned receipt only if `finalize`
succeeds, and bind that receipt to the service UID and startup source binding.
The observer has no model-forward, request, scheduling, state-pool, or GPU
control path of its own.

Comparing donor/cold receipts is meaningful only when all nine roles have the
same selected identity interval and real service bindings. It localizes the
first observed divergence; it does not establish a numerical cause or relax
the original canonical-prefix/T17 acceptance gate.
