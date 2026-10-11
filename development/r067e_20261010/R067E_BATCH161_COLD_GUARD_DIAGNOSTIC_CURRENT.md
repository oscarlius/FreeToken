# R067e batch161 cold-guard hash-domain correction

Recorded: 2026-10-10T13:13:26.103222+08:00

The prior diagnosis is superseded. Historical HOT_RUN and batch161 `hot_p8192` have identical shape, dtype, and raw CPU bytes for `conv_states`, `recurrent_states`, `ple_conv`, and `ple_ngram_ctx`. The packet expected hash `b18f8621f3e4b6c8740bfc3aa8374fdefe7eb4f3dd4d0e95c5f2ca1791f7aed5` is their plain-name digest. Engine uses `slot_states/ple_conv` and `slot_states/ple_ngram_ctx`, yielding `2116edf91af9daa8e4a889202044b5377afa9d6d9ddf772424f44ac8bc691390`. The label-domain mismatch explains the guard failure; it does not prove a cold/hot tensor mismatch because no cold digest was emitted.

Only a future packet encoding correction to Engine's exact canonical labels/order is supported. Batch161 remains `failed_harness`; no guard relaxation, rebinding, retry, or D12 action follows from this CPU diagnosis. A separately authorized GPU retry must capture the cold preguard Engine digest and undergo independent terminal review.
