# Corrected projection diagnostic close preparation

This is a CPU-only, future-use closer for the corrected frozen projection stage
`/data2/FreeToken/runs/dev_D14/projection_95638b538008`, CPU report SHA
`5336d493a67695f46e1ba634d34556678ab9af907ee503640491f3cda11428f4`. It is
not a launch tool and does not allocate an RID, batch, GPU, or lock.

## Required future inputs

The launch receipt must be the exact server `launch_<RID>.json`, with a future
RID matching `E2-RNNN-diagnostic-T17`, candidate `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`,
`FT_LM_CHUNK=4096`, the corrected CPU-stage SHA, all 19 source hashes, and
`baseline_acceptance: not_granted; R023_not_met_retained`.

A separate `ft_t17_projection_close_bindings/v1` JSON must supply:

```json
{
  "rid": "<same RID>", "batch": 0,
  "early_monitor_sha256": "<raw early-monitor sha>",
  "batch_early_identity": {"pid": 0, "pgid": 0, "session": 0, "start_ticks": 0},
  "batch_status": {"sha256": "<raw status sha>", "identity": {"batch_pid": 0, "batch_start_ticks": 0}},
  "services": {
    "projection_warm": {"process_identity_sha256": "<sha>", "stop_identity_sha256": "<sha>", "identity": {"pid": 0, "pgid": 0, "session": 0, "start_ticks": 0}},
    "projection_cold": {"process_identity_sha256": "<sha>", "stop_identity_sha256": "<sha>", "identity": {"pid": 0, "pgid": 0, "session": 0, "start_ticks": 0}}
  }
}
```

Pass the retained early monitor separately with `--early-monitor`. Terminal
status supplies only `batch_pid` and `batch_start_ticks`; the closer obtains
batch PGID/session from that frozen monitor and checks them against the launch
receipt instead of requiring nonexistent status fields.

The audit reads the server launch receipt, batch status, and both service
`process_identity.json`/`stop_identity.json` records directly and requires
byte-hash plus identity equality and terminal process birth. It rejects failed,
incomplete, live, reused, source-different, protocol-different, or already
closed rounds. It invokes the retained `t17_projection_read.py` `PROGRAM` for
CPU tensor/token/restore recomputation and requires 128 cold/hit tokens,
all restored roles, and CUDA uninitialized.

## Usage after an authorized completed diagnostic

```powershell
python development/t17_projection_close_stage.py --receipt <launch.json> --bindings <bindings.json> --early-monitor <initial-monitor.json> --stage-receipt t17_projection_close_<RID>_stage_receipt.json
python development/t17_projection_close_stage.py --receipt <launch.json> --bindings <bindings.json> --early-monitor <initial-monitor.json> --stage-receipt t17_projection_close_<RID>_stage_receipt.json --close --close-receipt t17_projection_close_<RID>_closure_receipt.json
```

The first command create-exclusively freezes a separate remote CPU audit stage
containing the closer, stage driver, reader, launch/binding inputs and canonical
D04 tools. The second can run only from that frozen stage receipt and creates
all closure files exclusively. Raw round files are mapped before additions;
closure sources are stored in `source_tools/closure`, runtime sources in
`source_tools/runtime`, and corrected CPU-stage transport in
`source_tools/launch_cpu`; the whole frozen close stage is separate in
`source_tools/closure_stage`. Before mutation, close verifies the staged audit
JSON/log hashes, re-runs CPU audit for exact review equality, then maps raw
files. It also records the bound batch wrapper/log and checks canonical D04
sources plus the retained prior Linux D04 proof. The proposed metadata declares
both verified normal services in `serve.arms`, each with the candidate commit
and captured identity. Before any raw-round write, the closer copies only the
two arms' canonical required artifacts plus the frozen wrapper to a private
temporary directory and calls canonical `round_close.prepare`; this preflight
does not write the real round.

A `kept` diagnostic closure is limited to the projection measurement. Original
R023 remains `not_met`; this never grants T17, E2-base.1, T10, or performance
acceptance.
