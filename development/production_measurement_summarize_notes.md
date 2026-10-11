# Production measurement summarizer

`production_measurement_summarize.py` is an offline, stdlib-only reader for
completed E2 T07, T08, and T09 measurement directories. It writes only a
caller-selected new `--out` JSON file and never decides a scientific verdict.

It requires the card's exact assigned RID, one terminal batch status whose
filename matches its recorded batch number, matching status/admission RID and
card fields, the admitted full commit
`23f2e2caa3395837c9474735ffc83321f3b9b5a1` and short `E2-base@23f2e2c` tag,
archived runner inputs, and the four per-active-arm service
artifacts. T08 phases are independent: `--phase P1` emits `E2-R004` only;
`--phase P2` emits `E2-R004-p64k` only and rehashes every file named in its
exact five-file P1 source binding. The archived runtime also includes the
`t16_runner.py` and `t00_runner.py` dependencies. Successful T08 quality and
soak records must carry their actual counts/statuses/duration; successful
quality also retains its nonempty artifact path as diagnostics. Their boolean
usable-number flag stays diagnostic. T09 reports the permitted C `NOT_READY` or insufficient-memory path
as a diagnostic gap; it is not presented as an active measurement.

`results` contains only finite numeric measurements. First shots, text and
pending-dependency evidence, optional quality/soak outcomes, and source
bindings remain outside it for root review and initial closure.
