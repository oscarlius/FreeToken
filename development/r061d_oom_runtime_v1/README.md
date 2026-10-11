# E2-R061d-OOM preauthorized runtime preparation

The sole formal entry is `r061d_oom_owned_launch_v1.py`; it loads `r061d_oom_runtime_prepare_v1.py`, which loads the patched `r061d_oom_fault_prepare_v1.py`. No R061b or original R061 protocol file is selected by the formal entry. This is a self-contained CPU runtime copy for the `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` candidate against the kept R064 baseline. It changes one ordering boundary in `r061d_oom_fault_prepare_v1.py`: after the injection receipt, it first records `health.prequeue.json` only after the API reports `maintenance=restarting`; it then starts the queued request and independently requires `restart_waiters >= 1`.

The closure binds the official-SDK raw-byte transport shim with retained ORD3/ORD2 readers, the R064 adapter/proof, lifecycle helpers and observer sources. It remains a preauthorized 1-service/3-call recovery scope against candidate `481d3a…`; it does not claim that R061c was a failed-harness retry or that any R061d FILEdry/Linux suite has already run. Actual FILEdry remains fail-closed on the R064 kept closure; it must not be stubbed or bypassed. The unused historical `r061_oom_fault_prepare_v1.py` copy is excluded from the executed closure.

Run the CPU harness regression from `development`:

```powershell
python -m pytest -q tests/test_r061d_oom_protocol.py tests/test_r061d_kept_admission_v1.py tests/test_r061d_bootstrap_v1.py tests/test_r061d_full_protocol_v1.py
```

Current local SDK transport regression: `test_r061d_sdk_transport_v1.py` verifies exact payload forwarding, raw SSE retention, and 503 raw-error preservation. Linux CPU and actual FILEdry evidence are pending the R064 kept closure.

## Executed source closure v2 (2026-10-09)

`MANIFEST.sha256` remains the original 13-entry historical package list. It is not the formal entry's executed closure: it includes the unused historical `r061_oom_fault_prepare_v1.py` and omits the external read-only CPU guard and R064 native-provenance proof. [EXECUTED_SOURCE_MANIFEST_v2.json](EXECUTED_SOURCE_MANIFEST_v2.json) records the actual `r061d_oom_owned_launch_v1.py` CPU-imported `closure()` as 14 read-only paths, including those two external bindings; no runtime source or candidate was changed.
