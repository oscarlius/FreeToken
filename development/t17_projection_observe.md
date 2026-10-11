# T17 projection observer

`t17_projection_observe.py` is a test-only runtime observer for the next
**default `FT_LM_CHUNK=4096`** diagnosis.  It does not patch FreeToken source,
run an extra forward, change a request, or alter a returned tensor.  It wraps
only the real layer-0 GDN and layer-1 PLE paths and stores at most six CPU snapshots
of the 65 absolute continuation rows `8192..8256`.

## Verified model path

The e4f3202 model establishes this path rather than relying on a guessed QKV
name:

- `python/freetoken/models/qwen4_exp/model.py:130-145` embeds `batch.input_ids`,
  then calls each `layers.op_list` decoder; `:167-178` repeats the same decoder
  call for each layer-major child, embedding each child and setting the global
  context batch before its layer call.  The same coordinate mapping therefore
  applies to normal prefill and a layer-major child.
- The protected HF JSON stores `text_config.ple_layer_ids=[2]` one-based.
  Before any Engine/weight construction, `t17_projection_startup.py` loads that
  exact JSON through the candidate `qwen4_exp/config.py:parse_config`, bound to
  `/data2/FreeToken/wt/e2d14/python/freetoken/models/qwen4_exp/config.py` SHA
  `72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607`.
  Its zero-based `qwen4_args.ple_layer_ids` is `[1]`; `model.py:115-118` then
  attaches the unique PLE to decoder 1. The receipt records raw HF `[2]`, parsed
  decoder `[1]`, and parser path/SHA separately. The observer never equates
  raw HF IDs with decoder indices.
- `gdn.py:126-159` resolves its active batch through `get_global_ctx().batch`
  and calls either `in_proj_qkvz` or `in_proj` for decoder-0 GDN; the observer
  selects the former only when `_split_in_proj` is true.
- `ple.py:610-696` calls `value_proj.forward` and the bound PLE instance method
  `_short_conv(x, meta, states)`. The observer wraps that method on the PLE
  instance rather than treating it as an OP with `.forward`; its source binding
  records the owning PLE class and `_short_conv` qualname.

The text path has no `batch.position_ids` field.  It uses the actual request
coordinates carried by the batch: a prefill tensor row `i` means absolute
position `req.cached_len + i`, and the observer requires
`device_len - cached_len == extend_len`.  This selects rows 0..64 for a warm
`cached=8192, extend=65` request and rows 3584..3648 for a cold final child
`cached=4608, device=8257, extend=3649`. A donor ending before 8257 is ignored.
`batch.is_decode` is ignored before any coordinate validation, preventing the
128 decode callbacks from becoming evidence.
A segment reaching 8257 but starting after 8192, a multi-request target, a
missing row, or differing target UID/slot/coordinates fails closed.

## Saved roles

A valid terminal receipt contains these and only these 65-row snapshots:

1. `embedding_output`
2. `ple_input`
3. `ple_value_projection_output`
4. `ple_conv_output`
5. `gdn_qkv_input`
6. `gdn_qkv_output`

Each role is copied immediately with `detach().to("cpu").clone()`, written once
at terminal, and records its CPU shape, dtype, file SHA-256, UID, linear slot,
actual cached/device/extend coordinates, all absolute positions, and the
wrapped module's module/class/source-file/source-SHA binding.  Repeated role
capture, repeated terminal, a wrong terminal UID, or an existing artifact is a
hard error. Tensor files use exclusive `Path.open("xb")` before `torch.save`,
so a competing writer between any caller check and creation is rejected without
overwriting its bytes; the JSON receipt likewise uses exclusive creation.
The receipt and PLE roles bind decoder index 1 / runtime layer id 1; GDN roles
bind decoder index 0 / runtime layer id 0. These identities are selected from
the loaded model objects, not inferred from a global layer counter.

## Startup and runner contract

The startup wrapper must, after `Engine.__init__` and before user work, pass the
inner Qwen model (currently `engine.model.model`) and the active global batch:

```python
from freetoken.core import get_global_ctx
import t17_projection_observe
observer = t17_projection_observe.install(
    engine.model.model,
    lambda: get_global_ctx().batch,
    output_dir=projection_arm_directory,
    sink=observation_sink,
    source_ple_layer_ids=(1,),
)
```

The frozen startup receipt must record this observer's own SHA-256 and the
observer output directory, plus the source configuration PLE ids supplied to
`install`. The runner binds each cold/warm query UID from the
existing exact-ID request receipt.  On that UID's one terminal `DetokenizeMsg`,
it calls `observer.finalize(uid)` exactly once and requires the receipt before
comparing snapshots.  Do not attach it to the donor request.  Cold and warm
services use separate output directories, so their output files are never
replaced.

This observer is diagnostic only.  It does not accept or weaken the T17 state,
128-token, or full-text gates.

R026 stopped during initialization because the prior observer incorrectly
assumed `layers.op_list[0].ple` existed. R028 then stopped because it equated
raw HF ID 2 with decoder index 2. Neither round produced a warm/cold comparison;
both are harness failures rather than T17 comparison evidence.

## CPU validation

```powershell
python -m pytest -q development/tests/test_t17_projection_observe.py
```

The seven tests cover warm and internal-cold absolute row selection, original
method invocation/returns and request immutability, non-target donor omission,
partial/multi-request rejection, immediate snapshot copying, duplicate capture,
unique terminal enforcement, and an exclusive-create collision race. They use a CPU tensor stub because this
Windows host has no PyTorch package; they do not claim CUDA/model execution.



## Corrected parser CPU stage

The original R028 attempt failed before measurement because its observer expected raw HF
`ple_layer_ids=[2]` to name decoder 2. That failure remains retained; it is not evidence
for this corrected harness. The replacement create-exclusive CPU stage is
`/data2/FreeToken/runs/dev_D14/projection_95638b538008`, frozen read-only after
completion. Its `cpu_validation.json` SHA-256 is
`5336d493a67695f46e1ba634d34556678ab9af907ee503640491f3cda11428f4`.

It ran 17 Linux tests and normal multiprocessing spawn with CUDA uninitialized. The
spawn proof binds protected config SHA
`deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80`, raw HF PLE
IDs `[2]`, parsed decoder IDs `[1]`, and the candidate parser path/SHA stated above.
The 19-file source table is retained in
`development/t17_projection_cpu_95638b538008.json`; changed harness hashes are
observer `ab36cb6f561995b51d95e9af507bc850f81316e0e7c0125fda5a6634ab7c66c8`, startup
`07111198786cf402c5e89c52f8bf21b01fa593ae0e8a419faba7ce780fa68f43`, runner
`7c130dfe34572b8b6343d793fca55140d456bd865c956848014f96fbfe9d943a`, stage
`764ecf7cd9688d41d66b47ed8c68b45f8991ee8dbf5c48a5b373bd28a69b3bf2`, observer
unit test `aa2a0f15869ea7d90cbe0c39da12cbabf6891efdae476eeb06c1ca1760c9da1a`, and
config unit test `042cebc51100ab15cc665a935fe672300dc416fb4f4c653cbb1151937e0885bf`.
The retained log SHA-256 values are observer tests
`3d81d90a2a96b7060ae62c03efd0f1eafb10562798cb57623da39e33ca7606d8`, gate tests
`06cdf8bcb89efbe1e002f486792f1f4e5041790a94a9ede6adf87e5214f877f9`, compile
`85df89b07ca32c1bcd3b40a8c43e389da9adaf5ab4038d893dec29143c4424f0`, and spawn
`28259392883cb9d674bfe3a1defeb274becb7b55823b1c81e46e8acc4f7c3797`.

This stage is CPU-only harness evidence. It does not revise R028's failure, launch a
new diagnostic, or grant any T17/E2-base.1/T10 acceptance.
