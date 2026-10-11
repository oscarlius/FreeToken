# Independent-review request: D09 T17 current packet

Review `runner.py`, `SOURCE_MANIFEST.json`, and `CPU_FILEDRY_RECEIPT.json` together. The default path is off. `--run --admission <sealed-root-admission>` still requires root-created admission and a second independent review before any GPU action.

The output judge invokes `judge_boundary` before every real hot/cold equality comparison. It requires a startup-produced `t17-boundary` index row, all four real FT dump roles (`conv_states`, `recurrent_states`, `slot:ple_conv`, `slot:ple_ngram_ctx`), exact target UID/length/input receipt binding, and byte hashes. Missing or unequal state raises `BoundaryStateError`, recorded as `failed_harness`; no `not_met` output verdict is allowed in that case.

CPU FILEdry used the same controller, child, admission, receipt, six-arm and eight-call flow with fake process/transport only. It is not GPU or formal acceptance. Please independently check the actual D09 candidate supports the observer's `CacheManager.snapshot_message_boundary` hook and that the T16 retry1 closure hashes in any proposed admission are sealed before launch.
