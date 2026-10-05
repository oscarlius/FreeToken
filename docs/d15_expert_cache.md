# D15 development expert-cache policy

The runtime stays on `FT_DEV_EXPERT_POLICY=lru` unless explicitly enabled.  The modes are exact: `lru` is disabled-by-default and preserves the existing LRU path; `profile` preloads a supplied profile; `profile+adapt` is only armed until the engine supplies a decode-boundary proof.  The D15 offline tool reads the D07 trace contract: each `route-*.npz` contains `expert_ids` shaped `[moe_layer, token, 10]`; the matching JSON sidecar remains provenance data and is not rewritten.

Run `python tools/build_expert_profile.py ROUTE_DIR PROFILE.strp --num-experts E` to emit the `STRP` format used by Strata.  The layout reference is Strata's `tools/make_profile.py`, Copyright (c) Strata contributors, MIT License.  No Strata GGUF or GPU kernel is included or used.

Set `FT_DEV_EXPERT_POLICY=profile` and `FT_DEV_EXPERT_PROFILE=PROFILE.strp` to preload ranked experts.  With prefill overlap, slots `[0, 2E)` are reserved for the volatile double buffers, so the profile always starts at `2E`.  The code records profile hits, misses and replacement bytes.  `profile+adapt` may observe a completed event with `seal_decode_boundary(copy_done_event)`, but that only proves an earlier batch completed.  Without a runtime quiescent/no-inflight proof it returns an `indeterminate` non-mutating plan.  Only CPU synthetic fixtures can apply a plan through a private fixture proof; the live runtime has no mutation hook in this branch.

T06 supplies the real `seed12k` profile and parameter selection.  GPU/default-path equivalence and T21 are deferred to the D17 queue; this document makes no performance claim.
