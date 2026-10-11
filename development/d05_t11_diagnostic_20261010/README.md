# D05 T11 two-call diagnostic CPU packet

This is the executable CPU preparation for `E2-R052b-D05-boundary-20261010`, not a
GPU admission. It preserves R052a `not_met` and does not implement the proposed H-bug
repair.

The sole service makes at most two generation calls: retained trace round 7 as UID7 target
(max 200), then UID8 follow-up (max 64). It copies the retained R052 D0 startup bridge and
imports the retained R052 client/trace reader with their fixed hashes. The candidate is the
clean detached bd57 D05 worktree.

Before call 2 or any output comparison, `require_equal_p_state` reads the candidate's
actual `LinearStatePool.dump_state` index and requires all four roles—conv, recurrent,
PLE conv, and PLE ngram—at P=13504. Missing, malformed, or unequal donor/cold state
raises `failed_harness`; the continuation is not sent. The current candidate is expected
to take this path because decode does not create the P checkpoint. That result diagnoses
the H-bug; it is not product `not_met`.

`--filedry` uses the same plan, service materialization, startup argv, state reader,
controller-child receipt shape, fake child and owned cleanup. `--run` requires a root-sealed,
read-only admission naming this RID, candidate, two-call limit and independent PASS. No
admission has been issued.

No candidate native `.so` exists in the bd57 D05 worktree; this packet neither builds,
downloads nor links a native binary.
