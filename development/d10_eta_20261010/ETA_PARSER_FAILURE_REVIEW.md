# ETA parser failure review — window02

Written at: 2026-10-11T00:45:49.367713+08:00

**Scope:** local read-only source/argument-contract review after the reported window02 `failed_harness` before model loading. This file does not modify or supersede the sealed η script, does not retry the window, and makes no η mechanism conclusion.

## Confirmed cause

The sealed `eta_microbench.py` (`SHA-256 90534f53fa6dcf0d42f4ff4005103b10ed7f49c84718b519a04aefdf4453ae40`) builds `engine_argv = split_server_argv(baseline)` and appends `--moe-collect-stats` before calling `freetoken.server.args.parse_args`. The 481 parser rejected that appended option, so engine construction stopped before model loading, CUDA graph capture, warmup, copy timing, or any η sample.

The local 481-compatible source contract confirms the mismatch:

- `development/e2base/python/freetoken/server/args.py` SHA-256 `7610b9ac4fbe58ee3e0ecaa7846656ad26c5065fc90e730ceabbcae2923dc894` registers the MoE cache, CPU-layer, hybrid-fetch, prefill-overlap, and prefill-hit-D2D options in its MoE section, but contains no `--moe-collect-stats` registration.
- `development/e2base/python/freetoken/engine/config.py` SHA-256 `dce7a0c525919e3549688bfe0aecff5c7e6d597906d6ef0ea7c7101396c4424b` does define `EngineConfig.moe_collect_stats: bool = False`.
- `development/e2base/python/freetoken/engine/engine.py` SHA-256 `e7e4c5ccdb514c6482c9f86a271b5f5164cacdca39223ed55536220c4ba612d7` consumes that configuration field before CUDA-graph capture (`cache.collect_stats = config.moe_collect_stats or dev_d0_enabled()`).

A dataclass field is not a CLI option. `parse_args` accepts only options explicitly registered in `server/args.py`; therefore the engine/offload-cache support was unreachable from the script's appended argv.

## What the CPU gate missed

The prior CPU tests exercised pure helpers and admission receipt validation. The prior parser check only parsed the hybrid service argv; it did **not** parse the exact η `engine_argv` after `--moe-collect-stats` was appended against the materialized 481 worktree. It therefore proved neither the exact `run_gpu` parser call nor its option vocabulary. The failure occurred before any GPU-side behavior, so CPU-hidden pass results do not support a graph/copy/η claim.

## Bounded future correction proposal

Do not change this sealed script or use its failed window as a measurement. A new reviewed candidate would need to avoid an unregistered CLI append, for example by parsing the frozen baseline argv unchanged and then constructing an engine configuration with `moe_collect_stats=True` through an explicitly reviewed, task-owned adapter. Before any GPU attempt, run a CPU-only parser test against `/data2/FreeToken/wt/d10-eta-481-20261011` that exercises the exact final `engine_argv` and validates the post-parse configuration field. Rebind fresh admission/review receipts to the new script hash and run an independent review.

This proposal is conditional: the adapter's API and the exact 481 Git blob must be checked before implementation. It is not authorization for a retry.

## Status

**ETA_MECHANISM_UNMEASURED.** Window02 failed before loading; it supplies no CUDA graph, all-hit, copy, overlap, or η result.

## Evidence boundary addendum

The three local `development/e2base` source files are an available local implementation reference, not a locally verified Git-object extraction for commit `481d3a7`. The reported window02 parser rejection is the direct evidence for the actual materialized 481 worktree. This review uses the local files only to explain the observed field-versus-parser-registration mismatch. A future correction must verify its exact parser call against the materialized `d10-eta-481-20261011` worktree before GPU authorization.
