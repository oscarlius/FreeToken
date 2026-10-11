# T16 D07 candidate adapter

`t16_candidate_runner_d07.py` is a new adapter; it does not alter the active
R018 `t16_candidate_runner.py`, `t16_candidate_launch.py`, their tests, or
historical rounds. It pins the reviewed base protocol SHA-256
`51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16`.

The D07 declaration is the immediate comparison
`e2d06@03692633df48456fb0baa78de7b64e5628a12ab1` to
`e2d07@fefb19cbac6bb1cb08835c411c895310600b3677`. It has exactly four
fresh-process layer-major arms: parent/new with D0 enabled, then parent/new
with D0 disabled. It does not add ordinary-prefill arms.

The pinned protocol clears inherited `FT_DEV_*` and `FT_D3_*` instrumentation
before enabling only `FT_DEV_D0=1` and the current arm's `FT_DEV_D0_PATH` for
an explicit D0 arm. Production arms retain no development flags. The original
protocol still owns full text/config comparison, compiled-extension identity,
tail and event sequencing, H2D/D2D checks, and no-RID/no-batch preflight.

Run local adapter checks with:

```powershell
python -m pytest -q development/tests/test_t16_candidate_runner_d07.py
python development/t16_candidate_runner_d07.py --self-test
```

The D0 regression enters the actual pinned `run_arm` through the owned process
launch boundary and verifies the command and environment. It reproduced the
pre-fix `KeyError: FT_DEV_D0`; mocked arm-coverage checks alone did not detect it.

This gate does not replace D07 route-trace G3/G4, CUDA D2H ownership tests, or
T06 analysis. It allocates neither a RID nor a batch and does not authorize a
GPU run; the main launcher retains queue and process authority.
