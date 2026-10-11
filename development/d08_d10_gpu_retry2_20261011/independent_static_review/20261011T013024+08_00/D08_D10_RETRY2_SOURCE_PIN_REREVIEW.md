# D08/D10 retry2 source-pin re-review

Verdict: **APPROVE_CPU_SCOPE**.

The previous HIGH is fixed. The master now demands exactly five controller pins, including d0_service.py; the D0 entry verifies its own hash before D07 loading, output creation, lock acquisition, or process spawning. Two targeted CPU regressions reject missing and mismatched D0 pins before Popen.

The retained CPU receipt reports 17 controller and 7 Restore07 tests passing. This does not represent GPU measurement execution. A fresh root-sealed admission must bind these current hashes before use.

