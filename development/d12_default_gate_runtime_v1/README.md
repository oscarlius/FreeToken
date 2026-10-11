# R062 D12 default-off T16 gate

Current candidate: `8f6a912ea6066f192c37dc74435efc9da0c7591c`; parent `effb9969706922ddad9e59b96377e46469ebe97f`. Adaptation remains default-off. GPU execution is not authorized by this CPU package.

The executable entry is `r062_owned_launch.py`. It permits only D12, binds R041 kept and R046g measured, and requires a sealed matching user-scope approval record before controller allocation. FILEdry remains CPU-only and needs no approval.

The pinned `t16_private_port_dryrun_r062_v1.py` uses the 98,304/.88 D12 gate configuration. Four parent/candidate D0-on/off arms preserve offload/layer-major/full-tail and token/text comparisons. Each arm sends one readiness completion, one cold completion and five single plus five multi probes: 48 planned generation calls total.

R062 has no consumed FILEdry, startup review, native provenance SHA, Linux CPU receipt, or GPU evidence yet. Missing R062-native proof fails closed. The gate validates the candidate-only `moe_short_suffix_max_tokens` parsed option as `0`; every other parsed option must match the parent. This gate proves only the default-off path. Enabled D16 four-layer behavior and real short-suffix performance require a separate proposal.

2026-10-08 16:04 root binding: native files were copied from the unchanged effb parent csrc build into each dedicated candidate; candidate files are regular 0444 and CPU imports did not initialize CUDA. Provenance binds the actual product CPU report (D15 19 PASS; D12 60 PASS / 3 skip). Combined local gate tests: 62 PASS. GPU permission and terminal acceptance remain separate.
