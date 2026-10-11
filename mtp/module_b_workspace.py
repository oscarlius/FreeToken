"""Module B: MoE decode persistent static workspace (design + drop-in code).

Target: _fused_experts_decode_nvfp4 in
  /data2/FreeToken/src/FreeToken/python/freetoken/moe/fused_nvfp4.py
  (both marlin + serial entries share this body -> one workspace covers both)

Why decode-only: per-token allocator cost is 48 layers x 4 empties = 192
locks/token in decode; prefill amortizes 4 allocs over up to 4096 tokens,
so prefill keeps dynamic alloc (its static equivalent would cost ~340MB).

Dims (Qwen3.8-Flash-Next-NVFP4): H=2560, top_k=10, moe_inter=640,
two_i=1280, dtype=bf16(2B). M_max = max-running = cuda-graph-max-bs = 4.
(MTP verify reuses the same pool with M = gamma+1 <= 5 -> size M_max=8
to cover both; cost still trivial.)

Decode workspace @ M=8:
  ic1 (8,10,1280)  204,800 B
  ic2 (80,640)     102,400 B
  ic3 (8,10,2560)  409,600 B
  out (8,2560)      40,960 B
  total           ~ 0.72 MiB  (vs 28 MiB free -> safe, no planner change needed)

Graph-safety: slices [:M] of static buffers keep fixed backing storage and
strides; CUDA graph capture sees static addresses. No zeros init (empty).
"""


class MoEDecodeWorkspace:
    def __init__(self, m_max=8, top_k=10, two_i=1280, inter=640,
                 hidden=2560, device="cuda", dtype="bfloat16"):
        import torch
        dt = getattr(torch, dtype)
        self.ic1 = torch.empty((m_max, top_k, two_i), device=device, dtype=dt)
        self.ic2 = torch.empty((m_max * top_k, inter), device=device, dtype=dt)
        self.ic3 = torch.empty((m_max, top_k, hidden), device=device, dtype=dt)
        self.out = torch.empty((m_max, hidden), device=device, dtype=dt)

    def view(self, m):
        k = self.ic1.shape[1]
        return (self.ic1[:m], self.ic2[:m * k], self.ic3[:m], self.out[:m])


# Patch sketch for _fused_experts_decode_nvfp4 (add kwarg ws=None):
#   if ws is None:  # legacy path, remove after acceptance
#       ic1 = torch.empty((M, top_k, two_i), device=dev, dtype=dt)
#       ...
#   else:
#       ic1, ic2, ic3, out = ws.view(M)
# One workspace instance per worker process, created at init; flag:
#   --moe-decode-workspace {on,off}  (default off until acceptance passes)
#
# Caveats for implementation (verified 2026-09-27):
#   1. Stale reuse: empty_like was also uninitialized, so semantics match, but
#      cross-token reuse turns random garbage into deterministic stale data. If
#      the fused kernel ever reads a region before writing it, behavior changes
#      vs baseline -> greedy bit-exact acceptance test is the gate.
#   2. Stream ownership: one instance per worker assumes a single owner stream.
#      If decode and MTP-verify (or prefill) can overlap on different streams,
#      add per-stream instances or event-sync before reuse.
