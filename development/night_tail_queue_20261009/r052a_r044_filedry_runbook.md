# R052a and R044 FILEdry handoff

These are exact existing-entry commands for the Linux FreeToken environment.
They are preparation only: each existing entry owns its gate/lifecycle/D04
checks and must reject before any output write when a required closure is
absent.  Do not substitute the current `481d3a7` product candidate for the
entries' embedded E2-base.1 `0aa23431...` identity.

## R052a / T11

Current source: `development/r052_runtime_v8/r052_t11_followup_prepare.py`
(SHA must be re-read on the host before launch).  Its direct CPU FILEdry branch
is `--dry-run`; it requires R041 kept, T20 failed_harness, R045 measured and
R052 failed_harness before creating its canonical hidden sibling.

```bash
cd /data2/FreeToken
source /data2/FreeToken/venv/bin/activate
python development/r052_runtime_v8/r052_t11_followup_prepare.py --dry-run
```

The later live branch has exactly one continuation after the actual uid=8
target response.  A missing/failed R045 must write nothing and leaves R044
unaffected.

## R044 / T10

Current source: `development/r044_runtime_v7/r044_prepare_v6.py`.  Its
FILEdry needs T20, R052 and R040f `failed_harness`, plus R052a and R040g
`measured`; R040g remains pinned to `effb996...` in both base and experimental
candidate fields.

```bash
cd /data2/FreeToken
source /data2/FreeToken/venv/bin/activate
python development/r044_runtime_v7/r044_prepare_v6.py \
  --file-dry-run /data2/_shared/runs/ft_rounds/.dryrun_R044_night_20261009
```

The existing FILEdry writes six plans only.  The later live T10 budget is two
modes × three services × 24 requests × a 200-token cap: 144 requests and no
more than 28,800 generated tokens.  A `not_met` outcome stops that R044 item;
it does not change the queue or authorize an extra service attempt.
