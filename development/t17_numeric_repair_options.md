# T17 original-4096 numeric repair options

Current update: R030 found byte-equal first-HC/GDN inputs and a differing BF16
GDN projection output. R031 then reproduced R030 warm exactly at M3585 and
cold exactly at M3649/M4096 with the actual checkpoint and `TorchLinearKernel`;
all three repeats were stable. Full-M unobserved rows were artificial zeros.
This establishes a sufficient reproduction factor for this bounded operation,
not a sole full-model cause or an accepted repair.

The authoritative `plan/PLAN_20261005_重新规划.md` now replaces future T17
ordinary-all-cold equality with exact state handoff and an automatically
derived, twice-repeated same-structure cold reference. 卡D14 schedule injection
and 卡D16 coverage are the next development targets. No fixed-shape numerical
kernel change is selected from R031 alone; R023 historical `not_met` remains.

The following is the retained earlier source/evidence analysis for R027 while R029 was loading. It
makes no claim that any listed mechanism caused the divergence or that normal
rounding is acceptable: the canonical prefix state/128-token/full-text gate
remains unchanged.

## Established evidence

R027 retained CPU review proves equality over `[512,4608)` and a first recorded
mismatch at absolute 4608 in first-linear `conv_in` (30,515 differing bytes,
max abs `0.125`), then q/k/v/g/beta and `h[56]`; the cold/hit token fork is 36.
The state copy/restore roles were exact before continuation. The second actual
GDN calls differ in logical M: donor `extend_tokens=3585`, cold `3649`, with
both saved tensor windows restricted to their common 3584 prefix. See
`development/t17_r027_independent_cpu_review.md:21-40`.

That is evidence of an output difference at `conv_in`, not evidence identifying
the first operation that produced it. The R027 raw `first_gdn_quantization`
records for `in_proj_qkvz` and `in_proj_ba` are null; they do not establish an
NVFP4 GDN projection kernel. Do not use them to attribute the defect to NVFP4.

## Concrete upstream path and shape branches

1. `model.py:151-158` embeds each layer-major child separately. For the first
   decoder, `Qwen4ExpDecoderLayer.forward` (`model.py:98-106`) first calls
   `attn_hyper_connection.mix`, then GDN. `gdn.py:126-136` obtains `conv_in`
   directly by applying `in_proj_qkvz`/`in_proj` to that mixed hidden tensor;
   therefore the recorded `conv_in` mismatch can originate either in this
   projection or any prior `mix` operation.
2. `hc.py:114-133` makes `mix` a per-row RMSNorm, `LinearReplicated` down GEMM,
   SiLU, a second `LinearReplicated` GEMM, then a per-row gate mix. The visible
   Triton norm/gate kernels (`kernel/triton/hc.py:66-89,174-196`) launch with N
   but use one row per program and do not reduce across rows. Source alone does
   not prove their outputs vary with N.
3. `LinearReplicated` is quant-configured in `hc.py:99-111`; if its actual
   scheme is NVFP4, `layers/quantization/linear/nvfp4.py:20-31` dispatches to
   `nvfp4_dense_linear_t`. `kernel/triton/nvfp4_linear.py:742-755` branches only
   at M=64. Both 3585 and 3649 take the same dequant-to-scratch path, but that
   path calls `torch.nn.functional.linear(a,w)` with the full M (`:705-727`).
   Thus cuBLAS receives different M shapes, a concrete possible algorithm/
   reduction-layout difference. The source does not show which cuBLAS algorithm
   was selected or prove it is the cause.
4. The NVFP4 W4A16 method has static per-weight group/global scales and comments
   that no W4A16 kernel reads `input_scale` (`layers/quantization/linear/nvfp4.py:77-79`).
   This source does not expose a cross-token activation amax/global scale.
5. PLE cannot precede first GDN layer 0: candidate model construction attaches
   PLE only when the parsed layer ID matches (`model.py:80-97`); the protected
   config is HF one-based `[2]`, parsed decoder `[1]`. QSA/MoE occur later in
   decoder 0 (`model.py:102-106`) and cannot explain a divergence already present
   in its `conv_in`. FLA/causal conv only consume `conv_in` afterwards
   (`gdn.py:138-165`), so they can amplify it but are not its upstream source.

## Smallest repair candidates, not accepted fixes

| Option | Intended boundary | Cost/risk | Required evidence before proposing source change |
| --- | --- | --- | --- |
| Fixed-M pad-and-mask for affected prefill GEMMs | Pad each compared child GEMM to a fixed calculation M (for example 4096), discard padded rows. Start with HC down/up and first GDN input projection after proving which first differs. | Extra FLOPs/memory on short children; can change default cold outputs and T16. | Capture pre/post HC down, HC up/gate, and GDN projection input/output at 4608. Then fixed-M candidate must pass original T16 cold outputs before any T17 claim. |
| Internal canonical calculation cuts | Split a long child at stable absolute boundaries so common prefix `[4608,8192)` is computed independently of the later 1 vs 65 tail. | Changes layer-major and ordinary prefill call schedule; FLA state and PLE commit timing must remain exact. | Prove all layer0 projection inputs/outputs through 8192 equal; test GDN conv/recurrent state at cut, PLE decoder1 context, QSA cache, and MoE output against unsplit baseline. |
| Deterministic fixed-K projection kernel | Replace only demonstrated M-sensitive GEMM path with an implementation whose K tiles/reduction order do not depend on M. | New CUDA kernel/throughput and numerical-risk surface; not justified until the first divergent GEMM is captured. | Same M=3585/3649 common-row probe plus fixed algorithm identity; compare bytewise tensor rows and full T16 default output. |
| M=1/per-row oracle | Use GEMV only as a diagnosis oracle for the common 3584 rows. | Not a production repair; prohibitive prefill performance. | If both current shapes differ from oracle in different directions, it localizes GEMM arithmetic; otherwise inspect HC input first. |

A repair must not be restricted to a cache-hit branch unless an identical
ordinary cold path also passes T16. It must preserve PLE’s decoder-1
build/commit sequence, later QSA/MoE semantics, and all original acceptance
checks.

## Needed R029 evidence

R029 records six suffix roles only, at absolute rows `8192..8256`:
`embedding_output`, `gdn_qkv_input`, `gdn_qkv_output`, `ple_input`,
`ple_value_projection_output`, and `ple_conv_output`. It does not capture HC
normalization/down/up, the GDN `conv_in` value, or the common prefix
`4608..8192`. It can therefore narrow a suffix difference to an input versus
projection boundary in those recorded roles, but cannot establish where the
common-prefix mismatch began or prove an HC/GEMM cause.

A separate, explicitly staged diagnostic would be required to capture the
common prefix and HC/GDN boundaries: embedding output, HC normalized input, HC
down output, HC up/gate output, GDN projection input, and `conv_in`, with the
actual M/stride/kernel identity. Only that later protocol could test whether a
matched input diverges in HC or the GDN projection, and it would still need an
actual cuBLAS/kernel algorithm record where available. Source inspection and
the current R029 six-role suffix capture alone cannot assign causality.
