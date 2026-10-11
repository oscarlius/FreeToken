# Morning report generator CPU proof

The generator uses Python standard library only. Both default and `--file-dry-run` execute the same wall-time and actual-terminal guards and write no report/proposal/coordination file. `--run` is the sole writer path and is reserved for root after separate review/freeze.

Its input manifest pins closure receipts, the official-SDK first-cold root readback, the prior truncated observation, and the readonly push-scope snapshot. The runtime reader rejects a missing or changed pin, missing terminal/samples, a pre-09:00 clock, a terminal classification other than `requires_review`/`completed_requires_review`, or any terminal that claims push eligibility.
