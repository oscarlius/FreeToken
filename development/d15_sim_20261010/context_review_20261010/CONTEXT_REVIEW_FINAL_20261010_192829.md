# Final independent context review

Verified-at read time: 2026-10-10 19:28:29 +08:00.

`position_context.py` is a narrow refinement of the original audited context calculation. It imports `audit` from `reconstruct_context.py`, preserves every group/UID/accounting/hash field, changes only the declared definition, and adds one token to each full-trace and calibration-prefix median. `position_context_proof.json` pins its base audit with SHA-256 `e1a3855f79f8699412d929cb7d5eb7bc9f2ade9cfa2ad4023ee9179ff38922aa`, which matches the read source file. Both scripts passed `py_compile`.

The final model-input context medians are `22.193`, `20.647`, `90.955`, and `0.675` ktok for seed12k, seed_45k, seed_real, and G_two full trace. G_two's D0-calibration prefix remains distinct: 79 complete decode steps plus layers 0–10 of the 80th, 149 request tokens, and `0.674` ktok. The full route trace remains 85 steps and 154 request tokens. This is an input-position refinement only; source bindings, binding hashes, UID route accounting, and D0 miss-rate calibration are unchanged.

The previous review documents with future-looking textual time labels are historical draft notes only. Their filesystem timestamps precede this read, and this file is the terminal timestamped review record.

Recommendation: the position-context proof is ACCEPTED for future speed-only recomputation. It corrects the L input; it does not by itself regenerate or validate the existing speed table, alter miss-rate calibration, establish GPU behavior, or approve T21.
