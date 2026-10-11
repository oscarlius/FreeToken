# 481 state snapshot geometry pre-registration

Source: remote read-only `Qwen3.8-Flash-Next-NVFP4-overlay/config.json`, parsed against the 481 source formula in `python/freetoken/kvcache/linear_state_pool.py:403-422` and Qwen4 PLE declaration in `python/freetoken/models/qwen4_exp/config.py`.

The service is single TP rank. Actual config geometry: 48 layers, 36 linear layers; 16 key heads × 128; 48 value heads × 128; linear convolution kernel 4; one PLE layer; `hc_count=4`, `hidden_size=2560`, PLE convolution kernel 4, ngram size 3. The model execution dtype must be re-read when constructing the 481 worktree runtime; the pre-registration calculation uses bfloat16 state as the standard 481 runtime dtype and recurrent fp32, exactly as the source formula specifies.

| State | Per-slot elements | dtype bytes | bytes |
|---|---:|---:|---:|
| conv | `36 × (2×16×128 + 48×128) × 3 = 1,105,920` | 2 | 2,211,840 |
| recurrent | `36 × 48 × 128 × 128 = 28,311,552` | 4 | 113,246,208 |
| PLE conv | `1 × (4×2560) × ((4-1)×3) = 92,160` | 2 | 184,320 |
| PLE ngram | `3-1 = 2` | 4 | 8 |
| **total device snapshot** | — | — | **115,642,376 B (110.29 MiB)** |

The implementation target is GPU-resident ping-pong slots in `LinearStatePool`, using `copy_from` semantics for conv, recurrent, and declared slot states. It will take at most one 110.29 MiB device-to-device snapshot per decode 64-token boundary. No copy time or enabled decode-rate penalty has been measured; `≤1%` remains a preregistered GPU acceptance criterion, not a claim. Host staging is excluded because it changes this one-copy device contract into a PCIe transfer and can introduce CPU synchronization.
