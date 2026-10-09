# D10 actual Qwen4Exp eager decode prototype

The source candidate is default-off through `--d10-staggered-decode`.  It selects only an eager, exactly-two-request decode batch on CUDA with an initialized GPU `OffloadMoeCache`; all other batches use the ordinary forward/graph path.

For an eligible batch the engine creates two scalar `Batch` views, preserving each request's page-table row, KV metadata, GDN/PLE state slot and sampling row.  `Qwen4ExpModel.forward_staggered_decode` runs real attention and MoE routing for each lane, then the D10 stream coordinator enqueues `copy(A)`, `compute(A)+copy(B)`, `compute(B)` layer by layer.  Each lane receives a disjoint half of the offload expert-bank rows and independent mutable LRU metadata.  The base cache mapping is invalidated after the fenced D10 step so a later ordinary batch cannot interpret D10-owned physical rows.

PLE uses explicit per-lane metadata in this eager path.  The existing PLE object's single pending-prefetch slot is intentionally not shared across lanes; this preserves lane-local n-gram state and avoids cross-request metadata replacement.

No new CUDA or Triton kernel is introduced.  The prototype uses existing offload copy/GEMM kernels with disjoint tensor views plus `torch.cuda.Stream/Event`, so no CUDA compilation step applies.  GPU correctness/performance measurement remains pending formal admission.
