# r045_section14_draft_v18

CPU-only future T05 entry preparation. The entry consumes `E2-R040f` as `failed_harness`; it separately requires `E2-R040g` `measured`, with `base.commit` and `experimental.candidate_commit` both fixed to `effb9969706922ddad9e59b96377e46469ebe97f`. Historical T20 evidence stays explicitly marked as `0aa23431e5b800797543bdecbf35a01045131d7d`.

Its v18 FILEdry sibling, receipt schema, and startup-review path are distinct from v17. Dynamic loopback allocation rejects both reserved E3 ports 8095 and 8096 without changing measurement parameters.

Remote CPU evidence and the actual FILEdry receipt are mirrored under `evidence/`: the CPU suite passed 88 tests with `CUDA_VISIBLE_DEVICES` empty; FILEdry receipt SHA-256 is `5031c28f6fc8286536cc026bda79049333fa3c6af2c34cc6f9acc1235e6f5e0f`. FILEdry started no service, sent no request, took no GPU lock, allocated no batch, and created no formal RID. The v18 startup review and root admission remain required before any GPU action.
