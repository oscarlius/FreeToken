# R045 v18 pre-reservation block

The actual frozen v18 entry was invoked with `--run` after root admission and exited before reservation because canonical `E2-R040g` is sealed as `failed_harness`, not `measured`.

- Archive JSON: `R045_V18_PRE_RESERVATION_BLOCK_20261009.json`
- Archive SHA-256: `3738f8ed042b621f7b6494e0c649d56de9e70c505b2c44905e6113b74cecedf8`
- Actual activity: zero R045 services, zero network calls, zero batch allocation, no formal R045 directory, and no GPU lock.
- The R040g identity is retained as metadata only. Its verdict is not changed and it does not authorize a retry.

Startup-source and FILEdry evidence remain PASS, but the full R045 gate is blocked. No R045 D04 closure exists because no R045 round was reserved or created.
