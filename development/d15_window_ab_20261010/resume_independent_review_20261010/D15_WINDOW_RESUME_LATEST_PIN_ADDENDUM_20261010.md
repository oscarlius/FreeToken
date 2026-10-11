# D15 W128 resume latest-pin addendum

**Status: APPROVED_CODE_LEVEL_CONDITIONAL_ON_SEALED_APPROVAL.** Written `2026-10-10T22:25:56.645234+08:00`.

Latest local/remote `window_resume.py` is pinned at `785c1412900b855939c892b725acf968c90881fd9ba91e1527179f9638fe9c59`. The reviewed narrow change catches `UnsafeCleanupError` in `measure`, sets `cleanup_safe` false, and creates `unsafe_cleanup.json` before `finally`; main consequently retains the lock when startup or SSE fails before a process object is assigned. It does not alter W128-only selection, W98 reuse, mismatch suppression, calls, deadline, or successful cleanup conditions.

Fresh author plus independent fake-deps tests passed: local **4 in 0.25s**, remote **4 in 0.04s**. This remains CPU code-level review only; final launch still requires a sealed approval binding this pin, complete prior manifest map, original admission, and original deadline.
