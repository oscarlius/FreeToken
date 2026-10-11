# R040f collector CPU source review — 2026-10-08 (updated)

## Scope

Read-only CPU source review of the new R040f collector safe slice. This is not a startup signature, Linux capsule review, FILEdry review, or model acceptance.

Reviewed files:

- `development/d16_native_process_collection_v4.py`
- `development/d16_native_process_collection_v5.py`
- `development/r040f_d16_process_collection_v1.py`
- `development/multisession_probe.py`
- `development/tests/test_r040f_d16_process_collection_v1.py`
- entry binding in `development/r040f_d16_remaining_prepare_v1.py`

## Cleared boundaries

1. **Probe byte identity before execution.** `d16_native_process_collection_v4.py:296-307` first calls `verify_source_review`, extracts the exact same-directory `multisession_probe` binding, and then passes its SHA to `_multisession_probe`. The loader checks path regularity, readonly mode, and SHA before `exec_module` (`27-41`). The actual regression at test lines 176-193 places an import-time marker in a mismatched probe and proves no marker is written.

2. **Collector v4/v5 bootstrap before execution.** `r040f_d16_process_collection_v1.py:13-60` now requires a readonly same-directory `MANIFEST.sha256`, validates v4 and v5 bytes before loading either module, rejects a pre-existing v4 whose `__file__` differs, loads v4 by verified exact path, and installs that exact v4 only for the v5 import before restoring `sys.modules`.

   The committed regression at test lines 54-72 proves a tampered v4 import-time marker is not executed. Independent read-only CPU probes additionally proved both:
   - an already-populated wrong `sys.modules['d16_native_process_collection_v4']` raises before import; and
   - a tampered v5 import-time marker raises on its manifest SHA before execution.

3. **Formal source closure, not a detached self-signed collector manifest.** The formal entry includes adapter/v4/v5/probe in `EXTRA` and `RUNTIME_CAPSULE_FILES` (`r040f_d16_remaining_prepare_v1.py:23-40`). `source_bindings()` verifies the entry capsule manifest, regular readonly sources, SHA for every declared file, and requires the complete execution dependency set (`274-291`). Dry receipt and startup-review checks bind `source_bindings()` (`399-404`, `427-445`). The local collector manifest is therefore a second bootstrap check within the entry's sealed closure, not the sole formal trust source.

4. **Remaining-scope and predecessor separation.** The adapter blocks native slots4 and accepts only two-way interleave (`r040f_d16_process_collection_v1.py:60-65,137-146`); parking/cache remain four actual state arms each, giving 14 total. The entry seals the retained R040e slots4 envelope `d770279fcfbfe913e31b2c7d88c1d437dd3999c67492a591d6047abbb8bbebcd`, candidate, D04 metadata, 128-token result, and no first divergence (`304-339`), then requires exactly parking/cache/interleave with 14 measured arms (`469-476`). It does not re-run the old nine scopes.

5. **No whole-collector mock on operational paths.** Parking/cache delegate to v4's actual state collector and service operation; v5 native arms enter actual owner service lifecycle, require sealed delivery, process identity, and interleave scheduler geometry. File-dry intentionally uses the same writers/configuration for 4 + 4 + 6 output arms while stopping before process start/request issue. The formal-loop regression now enters parking/cache loop structure and validates four arms per kind (`220-276`).

## Verification

- `CUDA_VISIBLE_DEVICES='' python -m pytest development/tests/test_r040f_d16_process_collection_v1.py -q` → `11 passed`.
- Independent ephemeral CPU bootstrap check → wrong preloaded v4 origin and tampered v5 each rejected before marker execution.
- No GPU, service, listener, lock, raw evidence, verdict, or collector source was modified by this review.

## Result

The two CPU loader boundaries identified in the preceding review are now closed in the current local source. **This clears only the collector CPU-source slice.** A formal R040f startup decision remains pending the separate full entry source-capsule, Linux CPU report, same-entry FILEdry, and independent startup-review evidence.

## Current v2 reader blocker (2026-10-08)

The first v2 CPU source stage is **not** eligible for a collector source review. I ran its archived, same-closure `r040f_d07_g3g4_prepare_v1.py` against the actual sealed R040e pin:

```text
require_closed_round('E2-R040e', 'failed_harness')
RuntimeError: E2-R040e pinned round-json checker is absent
```

The pin legitimately uses `round_json_sha256` and has no `round_sha256`; the new alias logic reaches the later history-check path correctly. It then fails because R040e has neither an in-round `round_json_append.py` nor an immutable external checker binding. The live canonical root checker has the expected `67c36b…4d48ff` bytes but mode `0644`, so it cannot become a fallback trust source.

A replacement source closure must carry a same-directory readonly checker with the canonical SHA, use it only for the explicit R040e failed-harness fallback, and prove: actual R040e canonical pin -> `require_closed_round` -> checker `check` succeeds; tampered, writable, or replaced checker rejects. This report remains collector-CPU evidence only and does not sign FILEdry or startup.

## Current v4 source-capsule blocker (2026-10-08)

The v4 CPU stage's claimed metadata preflight does not yet prove the final source archive can be assembled. I invoked the actual `prepare_source_capsule()` from `/data2/FreeToken/runs/dev_D16/r040f_v4_preflight_cpu_20261008_064546/source_tools/r040f_d16_remaining_prepare_v4.py` with a fresh R-owned destination. It stopped at line 248 before any archive review/pin:

```text
R040a capsule source is absent, symlinked, or writable:
.../source_tools/r040d_capture_v5/d16_exact_service_startup_v5.py
```

`CAPTURE_ORIGINS` requires the nested readonly `r040d_capture_v5/...` origin, while the stage currently carries only the flattened capture files. The empty/partial R-owned destination was removed; no source archive, SOURCE review, or pin was sealed. This blocks same-entry FILEdry until a new closure supplies the declared origin or updates the actual source-origin contract with fresh CPU proof.

## Current v5 consumer-contract blocker (2026-10-08)

The v5 entry/source archive passes only its **inventory and metadata preflight**. It does not execute the formal FILEdry collector consumer. The actual consumer is `d16_native_process_collection_v4.py:51-121`, reached by `r040f_d16_remaining_dryrun_v5.py:75-78` through `r040f_d16_process_collection_v1.py:154` and the native interleave path.

That consumer requires schema `ft_d16_collector_source_review/v1`, scope `owned-gpu-test-startup-only`, a fixed execution-role map, and an exact CPU inventory report. The sealed v6 producer has schema `ft_d16_collector_source_review/v2`, scope `source-archive-and-preflight-only`, and a 48-file archive map, so it must be rejected. The prior archive preflight did not call this consumer; its PASS was not a formal FILEdry consumer proof.

No old source review, pin, FILEdry receipt, round, or verdict was modified. A new private v2 consumer must be exercised through the actual parking/cache/interleave FILEdry paths before a replacement SOURCE review can be used.
