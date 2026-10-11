# D07 layer-major route-trace candidate handoff

- Worktree: `development/e2d07-trace-lm`
- Branch: `fix/e2d07-trace-layer-major`
- Parent: `effb9969706922ddad9e59b96377e46469ebe97f`

## Change

`RouteTraceCollector.begin_layer_major(chunks)` records explicit global token
ranges from the engine-built child batches.  While the model runs
layers-outer/chunks-inner, each capture is assigned to the next range for its
layer.  The writer waits for every D2H event, concatenates chunks per layer in
range order, and emits the existing `[moe_layer, token, topk]` array plus
`layer_major_chunk_ranges` metadata.

The collector rejects a short child capture, incomplete coverage, a repeated
chunk, revisiting a completed layer, or changing layers before finishing the
active layer.  Regular (non-layer-major) captures retain their single-capture
contract.

The engine now uses layer-major prefill with tracing enabled and passes the
actual chunks to the collector.  With no tracer, the same layer-major branch
is selected as before.  Decode CUDA graphs remain disabled only when route
trace is enabled by the existing `GraphRunner` route-trace guard; this change
does not claim graph-internal decode capture.

## Validation boundary

CPU tests cover reassembly across three uneven chunks and two non-contiguous
MoE layers, global range metadata, short/incomplete/duplicate/cross-layer
rejection, and engine-to-collector child-layout handoff.  No GPU, model
server, GPU lock, batch, or round artifact was started or written.  A Linux
CPU environment with PyTorch is required for the targeted pytest run because
the Windows interpreter has no `torch` package.

## Candidate identity

Local commit: `151ee718b88882b57dba75317bb53c697d5f235f`.
The remote test used an ephemeral `/tmp/ft-d07-trace-lm-cpu-23795fa` checkout sourced by a verified bundle; it did not alter a production or candidate worktree.
