# D09 T16 night default-off adapter

This package is the D09-owned derivative of the pinned `r062` T16 protocol.
It binds parent `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` and candidate
`c17b69a46cd512fbf3d127d3879bce92caae457b` to
`E2-D09-T16-night-20261009`.

The failed historical packet remains untouched. Retry tooling is separately
bound to `E2-D09-T16-night-20261010-retry1` through
`d09_t16_full_runner_retry1.py` and `d09_owned_launch_retry1.py`. The retry
delegates all generated `_unique_suffix` PID validation to the reviewed base
`strict_args`: a valid PID change is accepted, while every business argument
other than `message_boundary_ckpt=False` is still rejected. Its CPU mock is
`d09_owned_launch_retry1.py --filedry --card D09`; it records the same eight
arms and 96 planned calls without starting a GPU, HTTP service, or compiler.

The candidate adds the public default-off CLI flag
`--enable-message-boundary-ckpt`. A real `ServerArgs` log names its dataclass
field `message_boundary_ckpt`; the adapter accepts that sole added field only
when it is `False`, and reports it canonically as
`enable_message_boundary_ckpt=False`. It permits no other parsed-argument
delta.

`d09_owned_launch.py --run --card D09` is an actual owned controller. It
performs source, worktree, native-provenance, sealed file-dry-run,
startup-review, user-scope, queue, lock, batch, and child-lifecycle admission
before it can start the pinned runner. The sealed user-scope record must bind
the current queue `E2-R047 -> Strata -> E2-R052a -> E2-R044`, eight arms, and
96 planned generation calls. This package does not create that record or start
GPU work.

The full runner retains parent/candidate D0-on and D0-off arms plus ordinary
prefill chunked arms. It retains real private-client input, output token/text
comparison, prefill checks, global lock ownership, batch lifecycle, and cleanup.
The planned budget is 8 arms x 12 generation calls = 96 calls.

CPU-only verification:

```powershell
python d09_t16_full_runner.py --self-test
python -m pytest -q tests
python -m py_compile d09_t16_full_runner.py d09_owned_launch.py
```

The Linux CPU file-dry path is `d09_owned_launch.py --dry-run --card D09`; it
must run only after this package and its immutable evidence are deployed under
`/data2/FreeToken/development/d09_t16_night_v1`. It writes no formal round,
takes no GPU lock, starts no service, and sends no request. It is not a GPU
acceptance result.
