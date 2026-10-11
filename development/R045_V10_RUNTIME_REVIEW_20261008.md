# R045 v10 runtime review — 2026-10-08

Scope: read-only review of `development/r045_section14_draft_v10/source`; this is not startup approval. The reported Linux CPU result (63 PASS) was not repeated. R040e remains a future measured prerequisite.

## P0: stall callback blocks the decode SSE reader

`r045_d06_t05_prepare.py:run_stall_ordinary` passes `first` as `ordinary_stream_request(..., on_first_real=first)`. `first` synchronously waits for the physical observer token, sleeps `delay_s`, then performs the full prefill HTTP/SSE request before returning. The stream client invokes that callback while iterating decode SSE lines, so decode socket consumption is stopped for at least the 3-second delay and potentially for the whole prefill response. The resulting stall is partly created by withholding decode reads, invalidating TTFT/decode-rate and interference interpretation.

Minimal repair: callback must record the first-SSE marker and signal a separate prefill worker; that worker waits for the observer token, delays, dispatches prefill, and reports its error through a joined result. The decode reader must continue consuming its SSE loop. Preserve the existing UID/token-sidecar binding and fail on either worker error.

## P1: FILEdry does not exercise all real request-writer paths

`dry_workloads` probes top-level stall JSON only. Real `run_stall_ordinary` writes per-rep decode/prefill input files, API captures, bindings, and observer-dependent artifacts; these paths are not probed. It also does not probe pair-short per-rep input/API/binding files. FILEdry therefore cannot demonstrate exclusive-create/permission behavior for those actual writers.

Minimal repair: enumerate the per-rep filenames used by `run_stall_ordinary` and `_run_pair_ordinary` in `dry_workloads`, including both input/API/binding paths and observer sidecars, using the same arm/repetition names. No network or service is needed.

## Evidence retained

Performance service setup explicitly rejects D0, route trace and pause endpoint; performance uses ordinary SSE and physical observer bindings. H1 is separated into `run_t05_h1_diagnostic_arm`, where D0/pause are enabled and result reuse is marked forbidden. Two-decode uses `ignore_eos=True` and exact 512 only there. However, the callback defect means this separation does not by itself validate stall timing.

Source closure hashes copied startup/client/adapter, candidate probe, response parser, D06 sources, pause-generated sources, args parser, strict-args tool and cold helpers. The reviewed closure list does not establish FILEdry coverage for the omitted runtime writer paths above.

Risk: do not use v10 performance stall timing or any speed comparison as T05 evidence until the callback is made non-blocking and FILEdry covers its actual writer outputs. This review does not change sources, artifacts, GPU state, or approval status.
