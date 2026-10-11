# D10 two-lane static independent review

**Status: STATIC_REQUEST_CHANGES_BEFORE_CPU_REPLAY_OR_CONCLUSION.** Written `2026-10-10T22:42:33.869953+08:00`. No simulation was run.

The script matches D15's basic flat-ID, unique-route, hit-before-victim, `(usage,slot)` LRU and `[0,1024)` clear mechanics, but the existing output is unpinned historical model output only.

- `load_pair` removes all source prefill events and substitutes only step-0 clear.
- Stagger retains `prev` slots across physical clear, so freed slots may be protected.
- Stagger omits first-half B work at warm-up and final-half B drain while counting a full two-lane denominator.
- Global misses divided by nominal `lanes × 480` cannot establish actual per-lane distinct-active/miss counts.

Only after an explicit CPU window, baseline reproduction may use:

```powershell
python freetoken/development/d10_reanalysis_20261010/two_lane_share_sim.py freetoken/development/d15_sim_20261010/review_r4 > freetoken/development/d10_reanalysis_20261010/two_lane_independent_static_review_20261010/UNTRUSTED_EXISTING_SCRIPT_REPLAY.txt
```

It cannot clear these defects or support D10/GPU timing conclusions.
