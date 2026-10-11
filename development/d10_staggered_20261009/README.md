# D10 staggered overlap CPU preparation

This package is preparation only. The prediction is sealed in `prediction_manifest.json` before prototype files. The interval is a conditional additive-residual calibration, not a confidence interval or per-layer measurement.

The runtime is explicitly off by default. It emits an AIPerf command plan only; it does not start a server, acquire a GPU lock, launch CUDA, or claim synthetic overlap as performance evidence. Formal development requires both lanes above 30 tok/s and a passing T16 gate.
