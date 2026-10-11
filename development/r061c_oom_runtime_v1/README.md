# E2-R061c-OOM failed-harness correction

The sole formal entry is `r061c_oom_owned_launch_v1.py`; it loads `r061c_oom_runtime_prepare_v1.py`, which loads the patched `r061c_oom_fault_prepare_v1.py`. No R061b or original R061 protocol file is selected by the formal entry. This is a self-contained CPU runtime copy for the `4c878f6b3251cca273d8548e7f5cf58a56711d3a` candidate against the kept R060c baseline. It changes one ordering boundary in `r061c_oom_fault_prepare_v1.py`: after the injection receipt, it first records `health.prequeue.json` only after the API reports `maintenance=restarting`; it then starts the queued request and independently requires `restart_waiters >= 1`.

The formal closure has 13 bound paths: the formal entry, runtime wrapper, patched protocol, R060c adapter, owned-launch helper, D07 helper, port pair, ORD3, ORD2, startup observer, backend hook, plus the external sealed GUARD and R060c native proof. The candidate worker, injector, maximum-running policy, epoch-1 replacement checks, token equality, and full-text equality are unchanged. The local closure is bound by MANIFEST.sha256. Fresh actual FILEdry and independent startup review/pin remain required before any separately authorized GPU retry. The unused historical r061_oom_fault_prepare_v1.py copy is excluded from this closure.

Run the CPU harness regression from `development`:

```powershell
python -m pytest -q tests/test_r061c_oom_protocol.py tests/test_r061c_kept_admission_v1.py tests/test_r061c_bootstrap_v1.py tests/test_r061c_full_protocol_v1.py
```

Local result: 14 passed. The actual runtime-wrapper tests cover stale-serving-before-restart sequencing, failed/timeout transitions, bootstrap SHA rejection, kept-gate metadata binding, retained worker rejection, and token/full-text mismatch rejection. Linux/FILEdry results follow only after running this package.

Linux exact package: 14 passed; report SHA 19700a6dfe5ce1abc98ff28f542586bfc06a5a4569f878905a97bd23525b10c4. Actual FILEdry SHA d9ae4ee28ef36738156a006e1069785acf08be2783b5c5bacae0093667c162a5. Fresh independent startup review v2 SHA c68fa36a89c0f44759118cd6c043e45ce386f49ebd3140a612e63a3d9b6efb05 and pin d5352664e80939911a052f9d2ebfb99d9b9173e99e7da29acc29b69080e8c79e were accepted by the frozen entry. See ../R061C_READY_20261008.md for exact paths and pending GPU scope.
