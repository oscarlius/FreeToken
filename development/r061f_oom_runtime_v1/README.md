# E2-R061f-OOM failed-harness retry preparation

R061f is the user-authorized first tooling retry of the same preauthorized one-service, three-call R061 recovery scope for candidate `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` against kept R064. It preserves the R061d input/config/native/toolchain bindings and carries the R061e `_api_error` repair. R061f fixes only the observed six-field D07 lifecycle snapshot mismatch: it strictly projects and compares `pid`, `start_ticks`, `execution_id`, `pgid`, and `session`, while treating the volatile `/proc` `state` field as non-identity.

`r061f_oom_owned_launch_v1.py` is the sole formal entry. `EXECUTED_SOURCE_MANIFEST_v2.json` lists its actual 14-path closure: 12 internal sources plus the external CPU guard and R064 native provenance. The unused historical `r061_oom_fault_prepare_v1.py` is intentionally absent. The manifest is local-preparation evidence until copied read-only and independently reviewed.

No GPU, service, model request, lock, formal RID, batch, Popen, or FILEDRY occurred while preparing this package. R061d remains unmodified failed-harness evidence.
