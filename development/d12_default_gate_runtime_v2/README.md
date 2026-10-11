# R062 D12 default-off T16 gate

Current candidate: `8f6a912ea6066f192c37dc74435efc9da0c7591c`; parent `effb9969706922ddad9e59b96377e46469ebe97f`. Adaptation remains default-off. GPU execution is not authorized by this CPU package.

The executable entry is `r062_owned_launch.py`. It permits only D12, binds R041 kept and R046g measured, and requires a sealed matching user-scope approval record before controller allocation. FILEdry remains CPU-only and needs no approval.

The pinned `t16_private_port_dryrun_r062_v1.py` uses the 98,304/.88 D12 gate configuration. Four parent/candidate D0-on/off arms preserve offload/layer-major/full-tail and token/text comparisons. Each arm sends one readiness completion, one cold completion and five single plus five multi probes: 48 planned generation calls total.

The v1 FILEdry and startup-review paths are sealed and may not be reused. This v2 source requires new `*_file_dry_run_v2.json` and `*_startup_review_v2.json` artifacts. The v2 Linux entry tests passed 33/33; the native provenance still binds the unchanged candidate and parent binaries. Actual FILEdry SHA is cead8f032b24eebee84990997f6073ce818955785363ef1d1544bfe6b5cbf81e, and independent startup-review SHA is f6dacecf2bd17866f736d16588d9f91a8f8cfcba41ea41316f1409eecacffa6f. Missing R062-native proof fails closed. The gate requires the candidate's actual parsed `moe_prefill_routed_only_max_tokens='0'` option; every other parsed option must match the parent. This gate proves only the default-off path. Enabled D16 four-layer behavior and real short-suffix performance require a separate proposal.

Historical v1 denial remains preserved. The fresh v2 review independently binds v2 sources/CPU/FILEdry to the unchanged product and native evidence. GPU permission and terminal acceptance remain separate.
