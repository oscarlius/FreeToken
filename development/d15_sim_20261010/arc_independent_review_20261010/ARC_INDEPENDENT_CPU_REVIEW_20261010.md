# Independent ARC CPU review

**Status: REQUEST_CHANGES — execution evidence missing.** Written at `2026-10-10T22:02:52.657776+08:00`. This is an exploratory CPU-model review only; it makes no ARC strategy, production, GPU, or formal-acceptance conclusion.

The reviewed v3 source pins are `adaptive_arc.py` `bb1b31d5fbd20e84c25455d70e0bc697d3b3cc8a4c00f8106298643f8610dd13`, `run_cpu_scan.py` `1957a5fbd307453ff2b68c2a08669002fa31de25b24d6972d6b02235689b040f`, and `test_adaptive_arc.py` `3f52a0172574883b0f42dbed60c3b41184d6d8076a94f9d68ac2118d8b235d76`. The author suite passed **5** fresh CPU tests. The independent [scalar oracle](arc_scalar_oracle.py) (`94c7e311d0e9559cb340518006e1ef1633f4ffd3926a79675e171b7617611819`) passed **3** checks: both Figure-4 Case-IV branches, plus the explicitly non-paper physical extension for a protected same-call batch and physical prefill clear.

The oracle uses [Megiddo and Modha, *ARC: A Self-Tuning, Low Overhead Replacement Cache*, FAST 2003, Figure 4](https://www.usenix.org/legacy/event/fast03/tech/full_papers/megiddo/megiddo.pdf): `T1+B1 <= c`, all four lists `<= 2c`, and the two Case-IV new-page branches. The implementation's global physical slots, sorted unique routes, same-call hit protection, and retained ghosts after physical `[0,1024)` clearing are extensions, not claims of runtime-equivalent paper ARC.

Re-review is blocked because the v3 process ended without `results_v3.json`, `ONE_PAGE_CONCLUSION_v3.md`, a completion receipt, or error text; both `cpu_scan_v3.stdout` and `cpu_scan_v3.stderr` are zero bytes. Thus the actual LRU/LRFU reference equality for all four groups at 2700 and 2401 slots, and the corrected per-original-round regressions, remain unproved. Existing v1/v2 results are superseded and were not used.

Publish a compact v3 summary with source/input hashes and all group-by-capacity LRU/LRFU comparisons, then rerun this oracle against the final immutable pin.
