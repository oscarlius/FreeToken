Validated this PR on an RTX 4090 (PCIe 4.0 x16) with Qwen3.8-Flash-Next NVFP4, cherry-picked onto a d3512b4-based fork.

Cold 32K prompt (32,012 tokens), prefilled in a single pass over the experts (we run a local layer-major prefill patch, so each layer's experts are streamed once):

| | without #578 | with #578 |
|---|---|---|
| MoE compute, summed over the 48 layers | 9.42 s | 2.22 s (about 4.2×) |
| Expert H2D bytes per pass | 68,136,468,480 | 68,136,468,480 |
| Expert copy time | 2.87 s | 2.86 s |
| TTFT | 13.28 s | 6.13 s |
| Decode | 37.10 tok/s | 37.13 tok/s |

The 128-token output on the same prompt was bit-identical to the unpatched build.

With the default 4096-token chunked prefill (8 passes for 32K), TTFT barely moved (about 21–25 s either way). Each chunk re-streams every expert (#579), so that path stays transfer-bound; the kernel speedup shows once prefill is down to one pass.

Thanks for the work!
