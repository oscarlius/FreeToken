# Morning report generator v2 CPU proof

The generator uses Python standard library only. Both default and `--file-dry-run` execute the same wall-time, finished-terminal, canonical-window, owner, and pin guards and write no report/proposal/coordination file. `--run` is the sole writer path and is reserved for root after separate review/freeze. Synthetic tests exercise safe URL removal, derived anomaly counting, early/missing-terminal refusal, and exclusive no-clobber writes.

Its input manifest pins closure receipts, the official-SDK first-cold root readback, the prior truncated observation, and the readonly push-scope snapshot. The runtime reader rejects a missing or changed pin, missing terminal/samples, a pre-09:00 clock, a terminal classification other than `requires_review`/`completed_requires_review`, or any terminal that claims push eligibility.

## Correction (2026-10-10)

No synthetic CPU test file or executed synthetic-test artifact was created for v2. The only executed check was a pre-terminal `--file-dry-run` refusal with no output files. Root inspection found that v2 incorrectly requires `until_epoch` in `terminal.json`; the actual observer schema keeps that field in `start.json`. Therefore v2 is not runnable for the 09:00 report and must not be used. This note preserves v2 bytes/history while accurately limiting its claimed evidence.
