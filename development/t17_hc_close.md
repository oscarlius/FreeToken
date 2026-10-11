# T17 HC diagnostic closure

`t17_hc_close.py` and `t17_hc_close_stage.py` are RID-scoped closure tooling
for a completed HC diagnostic only. They do not start GPU work or grant T17,
E2-base.1, T10, or performance acceptance. The original R023 `not_met` result
is a required retained binding.

The audit requires the actual server launch receipt, matching early monitor,
terminal batch/service PID birth identities, `hc_warm` and `hc_cold` arms, the
22-source frozen HC CPU stage at
`/data2/FreeToken/runs/dev_D14/hc_a5ba447e30df`, and the canonical D04 source
and prior Linux proof pins. It executes the frozen HC reader locally on the CPU
and derives 128-token counts, first fork, text/token flags, and exactly four
true restored roles from `raw_validator`; the reader itself is not changed.

All nine HC roles must be terminal-valid and retain 64 rows, but diagnostic
closure does not require numerical equality. The closer captures a raw-file map
and repeats its complete audit immediately before mutation. It validates the
wrapper, batch log, proposed metadata, and canonical `prepare()` on a private
copy before it writes any closure file to the actual round.

The stage driver sends the launch receipt and bindings through stdin to a
CPU-only SSH process. It writes every artifact exclusively, freezes the stage,
and archives the exact stage driver, closer, reader, receipt/bindings/early
monitor, all 22 runtime sources, launch CPU evidence, and canonical D04 tools.
`--close` requires the exact successful immutable stage receipt and cannot
re-close an existing round.
