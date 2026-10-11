# D08/D10 GPU window independent orchestration review

Scope: read-only review of `gpu_window.py`, `hybrid_service.py`, `window_measure.py`, their local CPU tests, and `plan/D08_D10_GPU_TEST_DIRECTIVE_20261010.md`. No GPU, process, lock, or source-controller mutation was performed.

## Result: REQUEST_CHANGES — three concrete HIGH findings

### HIGH-1: the 35-minute whole-window deadline does not bound restore

The directive requires one window of at most 35 minutes **including restoration** (section 0). `gpu_window.execute` defines `deadline=started+2100`, but calls `restore(output)` in `finally` without passing or checking that deadline. `restore` starts `start_approved_release.py`, `wait_release_and_smoke.py`, and observer launch via unbounded `subprocess.run` / `Popen`; `terminal.json` only records `deadline_exceeded` after they return. Thus a hung restore/smoke can exceed the authorized window while processes continue.

Required correction: make restore receive the absolute deadline, give every restore subprocess a bounded remaining-time timeout and a reserved cleanup budget, then stop/record recovery before the 2100-second cutoff. The terminal must distinguish “measurement deadline” from a bounded restoration/recovery allowance.

### HIGH-2: process can survive a birth-record failure without cleanup

Both `hybrid_service.execute` and `gpu_window.eta` call `Popen`, then obtain `birth=d07.process_identity(proc.pid)`. If that lookup fails or the PGID/session assertion fails, `proc` is non-null while `birth` stays null. Their `finally` clauses only invoke `cleanup(proc,birth,...)` when **both** are non-null; the `proc is None` idle branch does not apply. The owned service/eta process can remain live, with a retained lock. In outer `gpu_window.execute`, `idle(d07)` then prevents restore, extending the production outage.

Required correction: record an immediately usable owned identity at Popen time or make the failure branch perform bounded PGID-based cleanup only after proving `pid==pgid==session` for that freshly created process. Do not release the lock until group death, ports reusable, and GPU idle are all proved. Add CPU regression tests for identity-missing and PGID/session mismatch after Popen.

### HIGH-3: auto max-fetch is accepted without an actual resolved value/semantics

Directive §1.4 requires the actual `moe_hybrid_max_fetch` value and semantics. `hybrid_service.execute` accepts `doc['max_fetch']==-1` when any auto-branch log line exists, but writes `resolved_fixed_fetch_cap=None` for that branch. It does not parse or prove the resolved automatic cap/semantics. `runtime_config.json` can therefore pass preflight with the required measurement confounder unknown.

Required correction: fail closed unless logs/API expose a parseable resolved auto cap and its semantics; write both raw source line(s) and normalized value. Existing fixed-cap evidence may remain accepted only when it explicitly proves the fixed numeric cap.

## Checks that are present

- Admission is inert by default and verifies source SHA fields, root admission shape, baseline owner identity, and sealed/non-writable admission file.
- Hybrid argv construction preserves baseline tail and allows only affinity prefix plus strategy replacement.
- Ready loop uses a proxy-disabled opener and requires `status=ok` plus `maintenance=serving`.
- Cleanup verifies owned process-group membership, HTTP/master ports 8095/8096 bindable, `nvidia-smi` no compute process, and D07 GPU idle before lock release.
- Measurement checks frozen X SHA, exact X parameters, two-request scope, response `length`/256 completions, and AIPerf ITL milliseconds.
- NUMA and thread-affinity observations are captured, but no acceptance conclusion is claimed by this review.

## Local CPU verification

`python -m pytest development/d08_d10_gpu_window_20261011/test_hybrid_service.py development/d08_d10_gpu_window_20261011/test_window_measure.py -q` → `6 passed in 0.21s`.

Those tests cover argv and command-shape contracts. They do not cover any of the three HIGH failure paths above.
