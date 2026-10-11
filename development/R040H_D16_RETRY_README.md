# R040h D16 remainder retry preparation

This local CPU-only preparation defines a letter-suffix retry, `E2-R040h`. It
does not allocate a batch, create a GPU lock, start a model, or alter R040f or
R040g evidence.

R040g's original remaining collector had 14 services and 16 exact-ID calls:
parking (4/4), cache cold (2/2), cache warm (2/2), and interleave (6/8).
R040g completed the four parking and two cache-cold services before the first
cache-warm service failed during startup. R040h therefore scopes exactly eight
services and ten calls: `warm_0`, `warm_1`, and the six interleave services.
Independent R review determines whether R040g's six completed services are
accepted; this preparation only binds their source identity.

The only runtime source change is in the copied
`d16_exact_service_startup.py`: warm cache priming passes a contiguous
`torch.int32` `(1, 1)` expert-id tensor to `cache.ensure_experts`. The R040h
CPU test directly executes that patched `configure_expert_cache` warm branch
and asserts the mocked native boundary receives contiguous `int32` values.

`r040h_d16_runtime_prepare_v1.py::source_plan()` records the R040g entry and
startup SHA-256s, the resulting startup SHA-256, the retained R040f/R040g
evidence roles, and the exact retry totals. A fresh source capsule, dry-run
receipt, independent review, and explicit GPU approval remain required before
any launch.

Use [r040h_d16_remaining_prepare_v1.py](r040h_d16_remaining_prepare_v1.py)
only with an independent R-provided `ft_r040h_retained_sources/v1` proof. It
can assemble a new local runtime capsule, fail-closes when either retained
R040f/R040g source hash binding is absent, and exposes the actual warm2 plus
interleave6 collector flow through `run_remaining_body`; it has no `--run`
mode and cannot start a service.
