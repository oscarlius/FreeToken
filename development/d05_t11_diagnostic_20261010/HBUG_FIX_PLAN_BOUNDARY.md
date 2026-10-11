# D05 H-bug repair and bounded-diagnostic plan

## Current conclusion

The current packet cannot reproduce the original T11 protocol in two generation calls. It needs eight trace requests before the target plus one follow-up (`retained_r052_t11_replay.py:129-161`): **one service, nine generation calls**. This is a new scope and needs separate authorization; it is not requested here.

A two-call path could be reviewable only if a new, source-bound service-state import exists before request 1. The imported artifact must bind donor UID, prompt/token prefix at P=13504, all four logical-state roles, candidate source/ABI, and actual Radix/host-slot ownership. The current packet has no importer; merely writing `.pt` files or an index cannot create the `mamba_restore_host` path that emits `resume` (`candidate scheduler.py:793-814`). Therefore **<=2 calls cannot replay original T11 today**.

## Minimal repair lane (1–2 person-days; no action authorized)

1. Confirm the candidate finish path invariant: the source diagnosis says the final full length 13554 aligns down to 13504 and skips donation when those differ (`d05_morning_20261010/D05_SOURCE_FINDINGS.md:24`). Apply one guarded finish-donation repair only if that invariant is reproduced in a CPU-level scheduler test.
2. Add a regression for restored short-tail completion donation, including donor/cold state roles and map ownership; preserve default behavior with T16 bit-exact gate. The existing D05 card names `tests/scheduler/test_restore_short_tail_donation.py` and requires T16 plus new T11 stage 2 (`plan/02_开发任务/D05_uid8缺donate_补钩子或修缺陷.md:34-51`).
3. If a new formal diagnostic is approved, use the original protocol: 1 service / 9 generation calls, fresh RID, sealed admission, exact child birth and D07 lifecycle, durable raw states/SSE/usage, and independent review. Do not repurpose the present two-call authorization.

No GPU quota, service count, or generation quota is requested by this plan.
