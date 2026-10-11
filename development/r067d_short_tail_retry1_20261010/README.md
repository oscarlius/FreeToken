# E2-R067d-d20-short-tail-retry1 CPU packet

This packet retries only the recorded cold-arm harness defect: every arm with
`FT_DEV_PREFILL_SCHEDULE` omits `--cache-type naive`, so the frozen candidate
engine resolves the default cache type to `hybrid_radix`. Inputs, criteria,
ports, 10 services, and 14 calls remain bound to the original R067d packet.

Run CPU preparation with `/data2/FreeToken/venv/bin/python`:

```text
python prepare_runner_packet.py
python -m pytest tests ../r067c_retry2_short_tail_v1/tests -q
python run_cpu_filedry.py --out evidence_cpu_filedry_remote_v1
```

`--run` remains prohibited. FILEdry uses fake probe/Popen only; it does not
start a GPU, service, or HTTP generation. `AUTHOR_HANDOFF.md` is a request for
an independent review and does not admit a GPU run.
