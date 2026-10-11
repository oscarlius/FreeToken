# D05 R052a CPU diagnostic

The retained R052a independent terminal review records target UID 7 full
length 13,554, the 64-token threshold 13,504, and observed follow-up cache
13,376 with completion 64.  The deficit is exactly 128 tokens, or two 64-token
units.  It is therefore consistent with an alignment/anchor geometry boundary,
but is not proof of that cause.

The existing T11 evidence must remain `NOT_MET` / H-bug.  It records a
historical restore with cache 13,376 and recomputation 56; it does not prove
that a D3 entry wrote the expected donor state.  No source fix follows from
this diagnostic.

The next bounded diagnostic should reuse T11 inputs, use no more than two
generation calls, and record for target UID 7: full token length, every
candidate anchor, `align_down(anchor,64)`, donated page/state geometry, API
and native cached token counts, and the before-output state dump.  It must
classify `boundary-state mismatch` as `failed_harness` before comparing output;
only an equal state permits evaluating the 13,504 threshold.  This distinguishes
a two-page geometry gap from a write/restore failure without changing the
historical result.
