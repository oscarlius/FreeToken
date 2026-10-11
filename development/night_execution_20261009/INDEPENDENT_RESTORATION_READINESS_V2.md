# Independent restoration readiness V2

**READY_FOR_ROOT_AUTHORIZED_RESTORE_EXECUTION_ONLY.** Approval `RESTORE481-NIGHT-20261009-01` is byte-bound to `ROOT_FINAL_REVIEW.json`, the package source manifest, commit `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`, and first-cold baseline SHA-256 `df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97`.

Root startup CLI:

`/data2/FreeToken/venv/bin/python -B /data2/FreeToken/development/night_restore_20261009/deploy_conditional.py --execute`

It permits exactly one RESTORE481 first-cold smoke. Any restore-start or smoke failure must run `stop_approved_restore.py`, require `RESTORE481-NIGHT-20261009-01/stopped.json`, then start/smoke ROLLBACK184 through `start_approved_rollback.py` and `wait_rollback_and_smoke.py`. Success enters `post_night_observer.py` read-only observation through 09:00.

No current GPU-idle assertion was made; active D10/R044 work is outside this historical restore admission.
