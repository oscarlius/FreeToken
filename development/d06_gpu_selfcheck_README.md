# D06 G3/G4 development GPU self-check

`d06_gpu_selfcheck.py` targets only `e2d06@03692633df48456fb0baa78de7b64e5628a12ab1`, after proving its direct parent `e2base@23f2e2c…`. It writes a new, exclusive `/data2/FreeToken/runs/dev_D06/gpu_selfcheck_03692633` directory and requires `--run` on Linux.

The service uses isolated `python -S` candidate imports, GPU 0, a private session/process group, the shared GPU lock, port 8095, `FT_DEV_PAUSE_ENDPOINT=1`, D0 plus a 20,000-step timeline, `max-running-requests=2`, and a 73,728-token window. Cleanup verifies the original process birth and the whole non-zombie process group before releasing the lock.

G3 runs the fixed `two-decode --ctx 32000 --max-tokens 512 --same-prompt 1 --reps 1` command. Both ACK-backed sidecars must contain 512 unit acknowledgements and each route must be within **25.36–38.04 tok/s**. It is a development tool sanity check, not T05 acceptance.

G4 runs H1 and uses the pause response's actual `pause_started_wallclock_s` and `deadline_wallclock_s`. After the entire owned service group exits, every timestamped `Prefill batch` and `Decode batch` line in the final `serve.log` is checked against each idle interval. Precise D0 timestamps resolve boundary-second log rows. Missing timestamps, overlap, or a still-growing final log fail the check; zero is never inferred. A passing result is written only after final validation. Cleanup also verifies surviving owned children when the original leader has exited.

Local-only checks:

```powershell
python -m pytest -q development/tests/test_d06_gpu_selfcheck.py
python development/d06_gpu_selfcheck.py --self-test
```

No GPU execution has been performed by this preparation artifact.
