# R067d batch154 CPU route diagnosis

Written: 2026-10-10T09:21:01.9892309+08:00. This is a CPU-only, read-only diagnosis. It preserves the existing batch154 result: the first private exact-ID POST returned 404, so there were zero valid calls. No service, retry, product/runner change, build, push, or sealed artifact mutation occurred.

## Bound failure

The launch receipt is `runs/launch_E2-R067d-d20-short-tail-retry2_batch154.json`. The sealed batch log is `/data2/_shared/runs/ft_rounds/batch154.log`, SHA-256 `5ddeb52186189b7cf57d0f216ee666c39aef13bf984725e6b5f3030d157491d1`; line 10 records the private request response `{"detail":"Not Found"}`, status 404. This is an API-surface failure before any valid generation call, not an engine-guard failure.

## Exact missing registration

The executed retry2 entrypoint is `r067d_retry2_startup.py`, SHA-256 `739278adce41a8ede42ee6d462e59fc977675e73dc023d10e90b0ec770853b37`.

- Lines 13-21 pin the worktree and prepend `<worktree>/python`.
- Lines 23-28 load only `t17_d14_observe.py` under the synthetic module name `r067d_retry2_observer`, then call `module.startup()`.
- Line 30 invokes those two steps. Lines 31-33 enter the CLI only for the main process.
- The loaded observer (`t17_d14_observe.py`, SHA-256 `4e63de8927da7b8687c9ef3efeeb908918f0fdcf09987e6703de07a5a3460a2c`) installs scheduler/engine/I/O wrappers at lines 16-101 and its `startup()` only imports and wraps them at lines 104-114. It never imports `t17_d14_exact_ids`, `freetoken.server.api_server`, FastAPI, or a router.
- Its spawn branch at lines 117-124 also only repeats observer startup and CLI handling. The retry2 wrapper's synthetic import bypasses that branch, then explicitly calls the same observer-only `startup()`.

Therefore no code path from the actual retry2 startup registers the private endpoint. The Engine guard can be present while the endpoint is absent: the two surfaces are independent.

The prior valid hot-startup source is `r067d_short_tail_retry1_20261010/tooling/t17_d14_startup.py`, SHA-256 `5d205e6e1c5ef5e0b807431d5e54d8088af168c98a5cb52cb74c1c72b9ec0eef`. Its line 3 imports `t17_d14_exact_ids` (SHA-256 `beeed7bbb48786aa336263fb69a94e464806a244bfe96cfe1c324d67b14ede89`), lines 6-10 import FastAPI/API-server dependencies, and lines 13-14 execute `@_api.app.post('/internal/t17/exact-ids')`. Those imports and decorator are absent from retry2.

## Controlled factory evidence

A fresh target-FTvenv import was run with `CUDA_VISIBLE_DEVICES=""`, `PYTHONDONTWRITEBYTECODE=1`, the exact batch154 worktree/commit/source pins, the actual startup module, and no CLI/service/health/request action. It returned:

```json
{"cuda_initialized": false, "engine_guard": true, "exact_route_present": false, "exact_routes": [], "route_count": 20, "startup_imported": true}
```

An isolated import of the previous hot-startup source against the same pinned worktree, likewise without CUDA/service/HTTP, returned:

```json
{"cuda_initialized": false, "exact_route_present": true, "exact_routes": [["/internal/t17/exact-ids", ["POST"]]], "route_count": 21, "previous_startup_imported": true}
```

This proves the 404 root cause at the factory route-registration boundary, rather than inferring it from the HTTP path alone.

## Bounded follow-up

The tool-attempt budget is exhausted. Preserve batch154 as-is. Any later separately authorized repair must first add a CPU-only import/factory route assertion for the exact executed startup, including spawn semantics and route presence, before a new admission can be considered. This document proposes no retry.

