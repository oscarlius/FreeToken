# D09 CPU value preregistration

**Decision: value is nonzero; D09 implementation may proceed after a separate implementation-lane handoff.**

The independently executed strict Scheduler v7 replay records the actual T17 round-7 geometry `0→20224→20282→21302`, native reusable point `20160`, and failed literal boundary commit at `20282`. From the old 20160 reuse point, scheduling needs two resumptive prefill segments: `20160→20224` and `20224→20282`; exact 20282 reuse removes those and leaves the single tail/continuation `20282→21302`. This is a **2→1 forward-count change**. No CPU seconds are inferred.

The sealed v4 prediction population has five reproduced rounds (5, 6, 7, 8, 10). Its affected list is round 7 (`P=20282`, tail 1020) and round 10 (`P=22558`, tail 197): 2/5 of that sealed analyzed population. Round 10 is tokenizer/prediction eligible here, not a separately raw-Scheduler-replayed T17 input.

The implementation is bounded: default off; preserve the old 20160 prefix ownership; give the exact boundary only controlled metadata and private/COW partial-page behavior; keep the existing false-return guard as the fallback. Required CPU proof is conv/recurrent/PLE state at P, page/slot/ref conservation through restore/evict/two readers, default-off equality, and v7 enabled admission 20282 versus disabled 20160.
