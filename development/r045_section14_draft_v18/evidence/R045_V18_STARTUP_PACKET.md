# R045 v18 startup-review packet

Candidate entry is `effb9969706922ddad9e59b96377e46469ebe97f`; the remote candidate status capture is empty. The local release/e2 branch is not an input to this packet.

## CPU evidence

- Remote stage: `/data2/FreeToken/runs/dev_T05/r045_section14_v18_cpu_20261009_1340`.
- `cpu_test_output.txt` records empty `CUDA_VISIBLE_DEVICES`, both self-tests passing, and `88 passed in 1.96s`.
- `source_manifest.sha256` SHA-256 is `286bc4ccbf48a698d691a55b1116c0d13cb708aaa2d4871b62f308d421dfc245`.
- Entry source SHA-256 is `2c3a9162052c9004186c779db05098c75a111fe9fa249445395cca38cbd9d86d`.

## Actual FILEdry evidence

- Receipt: `/data2/_shared/runs/ft_rounds/.dryrun_R045_section14_v18_E2-R045/dry_run_receipt.json`.
- Receipt SHA-256: `5031c28f6fc8286536cc026bda79049333fa3c6af2c34cc6f9acc1235e6f5e0f`.
- Receipt records `formal_rid_directory_created=false`, `service_started=false`, `requests_sent=false`, `gpu_lock_taken=false`, and `batch_allocated=false`.
- The only FILEdry loopback ports were `58321` and `55323`; v18 rejects reserved E3 ports `8095` and `8096` without altering scientific cases, repeats, context, or memory ratio.

## Planned measurement scope — not FILEdry activity

The approved measurement plan caps at five serial services and 107 network calls, excluding readiness polling: P1 ordinary 27, P2 ordinary 27, P1 H1 diagnostic 21, P2 H1 diagnostic 21, and D06 G3/G4 plus pause chain 11. FILEdry sent zero requests and started zero services.

GPU launch remains forbidden until this packet receives an independent startup PASS and root admission.
