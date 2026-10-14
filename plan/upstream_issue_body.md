## Summary

On a dual-socket Xeon + RTX 4090 host, `ft bench bw` measures a CPU-MoE / PCIe-gather bandwidth ratio of 1.90–1.96 for NVFP4 experts (two bench runs). That is just under the default 2.0× threshold, so `--moe-strategy auto` resolves to `offload`. In a same-window A/B test, explicitly selecting `--moe-strategy hybrid` decoded about 21% faster with one stream and about 55% faster per stream with two concurrent streams.

This is one more data point that the bandwidth-ratio verdict does not predict end-to-end decode, here in the opposite direction from #151 and #436 (hybrid picked but slower). It is also related to #278: the served model's experts are about 2.77 MB (H=2560, I=640), whereas the nvfp4 tuning geometry uses 7.97 MB experts.

## Environment

- GPU: 1 × RTX 4090 24 GB, PCIe 4.0 x16 (bench linear H2D: 24.26 GB/s)
- CPU: 2 × Xeon Silver 4310 (24 physical cores in total, AVX-512 VNNI, no AMX), 2 NUMA nodes, 16 × 16 GB DDR4-2666, all channels populated
- Model: Qwen3.8-Flash-Next, NVFP4 checkpoint
- `ft bench bw` profile (nvfp4 tuning geometry, 7.97 MB per expert):
  - latest run: cpu_moe 46.12 GB/s (`avx512f+avx512vnni`, nvfp4-w4a8), pcie_gather 24.25 GB/s → ratio 1.902 → `offload`
  - earlier run: 47.62 / 24.27 GB/s → ratio 1.962 → `offload`
- FreeToken: a fork based on upstream d3512b4, with #577 and #578 cherry-picked plus local instrumentation (disabled in these runs) and OOM-restart patches. The fork does not modify `benchbw.py`, `bench_profile.py` or the CPU MoE executor. I have not re-measured on current main; I see that #610, #619 and #662 have touched the CPU MoE path since.

## Measurement (same window, same build)

Services were started in sequence: offload → hybrid → hybrid (fresh, not warmed) → offload.

- The only differences for hybrid were `--moe-strategy hybrid` and CPU pinning. The fetch fraction was the automatic value (27.7%).
- Prompts were about 1.2K input tokens (two distinct prompts for the two-stream case), with 256 output tokens and temperature 0.
- Each service got two unscored warm-up requests first, except the fresh hybrid service.

| Decode (tok/s) | offload | hybrid |
|---|---|---|
| 1 stream | 29.62–30.19 | 35.55 / 36.59 |
| 2 streams, per stream | 16.81–16.98 | 25.96–26.27 |

- The two offload services differed by 0.20% in two-stream throughput, so the gap is not drift.
- The fresh, unwarmed hybrid service measured 30.81 tok/s single-stream, so most of the single-stream gain appears after warm-up.

## Notes

- With two distinct streams, offload sits close to its PCIe bound at the measured miss rate (about 38%), roughly 23.9 tok/s per stream. Hybrid exceeds that bound because experts computed on the CPU do not cross the link.
- Hybrid is not numerically identical to offload on this CPU, for two reasons:
  - the CPU path quantizes activations to int8 (W4A8);
  - outputs depend on cache history: a fresh and a warmed hybrid service diverged on the same cold request.

  So this is a speed/numerics trade-off, not a free win.

## Questions / suggestions

1. Taken together with #151, #436 and #278, it looks like the bandwidth ratio misses in both directions. Would a short end-to-end decode probe (offload vs. hybrid on the served model, a few dozen steps each) be an acceptable basis for the auto decision, perhaps cached like the bench profile?
2. Short of that: could startup log the measured ratio and the threshold when auto keeps `offload`? Users near the boundary would then know to try `hybrid`. (`ft bench bw --threshold` exists, but a `ft serve` user doesn't see the ratio.)

Caveat: these numbers are from a d3512b4-based fork. Given #436, I'm not assuming hybrid behaves the same on current main, and I'm happy to rerun there or share logs.
