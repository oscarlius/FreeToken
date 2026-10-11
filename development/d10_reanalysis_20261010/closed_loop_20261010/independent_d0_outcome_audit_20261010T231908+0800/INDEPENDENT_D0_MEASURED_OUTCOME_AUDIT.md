# Independent D0 measured-outcome audit

Reviewed at: `2026-10-10T23:19:34.368723+08:00`

The 43-entry D0 raw manifest validates exactly. The source, admission, and input bindings match the archived inputs and controller sources. D0 recorded two AIPerf invocations, each at concurrency two and request count two: four HTTP-200 generation rows through one service (PID `3874033`, start ticks `173948152`).

Selected bs=2 rows are X `255` steps / `93618` misses / `m=0.382426470588` and Y `46` steps / `12234` misses / `m=0.277038043478`. Twelve bs=1 tail rows are excluded by the stated bs=2 definition. The calculation is a shared-batch equivalent, not a UID miss rate.

P1 is supported for the explicitly scoped X warm-speed lanes: ratios are `1.022632987385` and `1.026464495549`, within `[0.90, 1.10]`; the derived X ideal upper bound is `23.871478487392` TPS, below 30. P2 meets its threshold: Y is `10.538842710997` percentage points lower than X.

The original controller terminal remains `failed_harness` because its cleanup proof failed. The separate recovery receipt records the owner/service/group dead, private ports free, and GPU 4 MiB at recovery; this review does not convert that carrier into a successful terminal or formal kept decision.

The conclusion is limited to the registered P1/P2 arithmetic. D0 was fresh while speed was restored/warm; m is shared-batch only; X is about 1.2K tokens and Y is short with early EOS. The four paired raw receipts show equal payloads and equal emitted content/reasoning/finish fields, which is observed evidence only, not a native determinism guarantee.
