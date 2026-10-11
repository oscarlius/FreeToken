# R051a D08 T16 gate

Current candidate: `76af7584d7595d9cc52dcd60deff3aacdae1d9d6`; parent `effb9969706922ddad9e59b96377e46469ebe97f`. GPU execution still needs user approval.

The executable entry is `r051a_owned_launch.py`. It permits only D08, binds the closed R041/R051 and failed R048a metadata, and consumes the current default FILEdry and independent technical startup review before allocating a batch. The declaration-only `r051a_d08_candidate_gate.py` has no direct execution path.

The new pinned `t16_private_port_dryrun_r051a_v1.py` differs from retained `t16_private_port_dryrun_base_v2.py` only in the two 49,152-to-98,304 window values. Four parent/candidate D0-on/off arms preserve offload/layer-major/.88, full-tail and token/text comparisons. Each arm sends one readiness completion, one cold completion and five single plus five multi probes: 48 planned generation calls total.

Local and Linux harness tests: 29 passed. Exact frozen source is `/data2/FreeToken/runs/dev_T16/r051a_v1_cpu_20261008T022956Z/source`. Default four-arm FILEdry and independent technical startup review passed; root consumed both with the real entry. Current native provenance SHA is `a27531136810e6dd84bb896fef688644b01eb0ca7f3acb68fbbe163c9a26cadf`; it separates verified native reuse from the current 17 Python CPU tests and real candidate module imports. No GPU equivalence has been established for this new candidate.

See `../R048B_R051A_R052A_READY_FOR_USER_APPROVAL_20261008.md` for full paths, SHA bindings, request counts and conditional T09 scope. This README is a live handoff; the previously frozen source snapshot remains unchanged.
