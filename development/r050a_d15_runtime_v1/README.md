# R050a D15 T16 gate

Current candidate: `825655305d69df94d3d2f79c3f416234bfe890e6`; parent `effb9969706922ddad9e59b96377e46469ebe97f`. Adaptation remains default-off. GPU execution is not authorized by this CPU package.

The executable entry is `r050a_owned_launch.py`. It permits only D15, binds kept R041/R050 and not-met R049c metadata, and consumes a R050a-specific FILEdry, native-provenance proof, and independent startup review before allocating a batch. The declaration-only `r050a_d15_candidate_gate.py` has no direct execution path.

The pinned `t16_private_port_dryrun_r050a_v1.py` uses the 98,304/.88 D15 gate configuration. Four parent/candidate D0-on/off arms preserve offload/layer-major/full-tail and token/text comparisons. Each arm sends one readiness completion, one cold completion and five single plus five multi probes: 48 planned generation calls total.

R050a now has native provenance, Linux CPU, actual FILEdry and an independent startup review. The runner sets `FT_DEV_EXPERT_POLICY=lru` and both adaptation counters to `0` for every arm. Actual FILEdry SHA is `bc2ac2c33a231705554c406ab614d14c26df89ac9752706a28bf7ca555fd8fc7`; startup review SHA is `aaed919e0b7ff9071268199789a66b38863f1164ce7da97de6bdd23570d4c3a2`. Both are in `/data2/FreeToken/runs/dev_T16/reviews/E2-R050a-gate-D15_*_v1.json`. GPU execution of this corrected candidate still requires its scope approval; default-gate acceptance and enabled-policy T21 acceptance remain outstanding.

2026-10-08 16:04 root binding: native files were copied from the unchanged effb parent csrc build into each dedicated candidate; candidate files are regular 0444 and CPU imports did not initialize CUDA. Provenance binds the actual product CPU report (D15 19 PASS; D12 60 PASS / 3 skip). Combined local gate tests: 62 PASS. GPU permission and terminal acceptance remain separate.
