# T16 full-tail candidate protocol

`t16_full_tail_base_runner.py` is a byte copy of the frozen T16 base protocol
`plan/01_测试与调研/batches/t16_runner.py` at SHA-256
`51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16`, with
one live-probe change: D03, D06, and D07 treat the parent D0 terminal prefill
segment as published. Its SHA-256 is pinned by
`t16_candidate_runner_full_tail.py`; archived bindings record that new SHA,
not the frozen base SHA.

The adapter is derived from the frozen D07 adapter SHA-256
`3a85f8e378862e6971f1b72164107c54fefe3b0c858f84d4332979eb28bf0a9c`. It
retains the declared D03/D06/D07 case bindings, environment cleanup, full
configuration/text/prefill-sequence checks, and strict H2D/D2D and per-event
telemetry validation.

The defect addressed here is the D06 live comparison that treated its parent
as lacking the terminal D0 segment. The parent actually publishes all 13
prefill events and D0 rows; `prefill_seq.txt` intentionally contains only the
12 business events after readiness. The protocol remains strict: missing log
events, missing terminal marker support, or changed transfer counters fail.

Local verification:

```powershell
python -m pytest -q development/tests/test_t16_full_tail.py
python development/t16_full_tail_base_runner.py --self-test
python development/t16_candidate_runner_full_tail.py --self-test
```

These files prepare a reviewable runner only. They do not reserve a round,
start a service, or authorize GPU execution.
