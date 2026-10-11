# Night restore package

The only execution identities are `RESTORE481-NIGHT-20261009-01` and
`ROLLBACK184-NIGHT-20261009-01`. This package is pending root independent
final review; `conditions_met` remains false and `--execute` refuses work until
the root writes a matching `ROOT_FINAL_REVIEW.json`.

One RESTORE481 smoke is permitted. Any nonzero restore-start or restore-smoke
result invokes `stop_approved_restore.py` and requires the frozen controller to
publish RESTORE481 `stopped.json`; only then can rollback184 start and smoke.
There is no candidate retry and no GPU continuation on that path. A passing
RESTORE481 smoke enters the task-owned read-only observer through 09:00.

`SOURCE_MANIFEST.json` binds this package. Frozen OPS source/binary manifests
and first-cold baseline hash
`df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97` are
references only; old CPU test counts are not an admission condition here.
