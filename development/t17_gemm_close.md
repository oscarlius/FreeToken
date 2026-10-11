# T17 GDN replay diagnostic closure

`t17_gemm_close.py` audits an exact, completed operator-only GEMM diagnostic.
It pins the 17-source CPU stage at
`/data2/FreeToken/runs/dev_D14/gemm_e1154756dd3c`, its CPU report SHA, the
server launch receipt, terminal status and process identity, a retained monitor
observation, frozen reader/runtime sources, and canonical D04 tools and prior
Linux proof. The monitor may be collected after the batch exits; it is bound to
the retained `process_identity.json` rather than requiring an invented live
handle.

The audit imports the frozen `t17_gemm_read.py` program and CPU-recomputes the
actual checkpoint fusion and all three retained replay outputs. It requires
real matching inputs and repeat evidence, but does not interpret equality or
inequality as a T17 acceptance result.

The proposed canonical metadata uses `serve: "none"`: this is an
operator-only replay, so no service artifacts are fabricated. Before any real
round file is added, the closer runs canonical `round_close.prepare()` on a
private copy containing the actual batch wrapper and log binding. It then
records immutable runtime, CPU-stage, audit-stage, reader, monitor, receipt,
bindings, and D04 sources; seals pending review; and appends `kept`. Original
R023 remains `not_met`; no T17, E2-base.1, T10, or performance acceptance is
granted.

Stage a review only after the terminal batch exists:

```bash
python development/t17_gemm_close_stage.py --receipt development/t17_gemm_<RID>_launch_receipt.json --bindings development/t17_gemm_close_<RID>_bindings.json --monitor development/t17_gemm_<RID>_monitor.json --stage-receipt development/t17_gemm_close_<RID>_stage_receipt.json
```

`--close` additionally requires the exact stage receipt and a distinct
RID-scoped closure receipt. Neither command is invoked by this module on
import.
