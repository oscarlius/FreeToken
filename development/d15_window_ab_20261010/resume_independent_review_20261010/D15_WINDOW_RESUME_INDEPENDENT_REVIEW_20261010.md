# D15 W128 resume independent CPU review

**Status: APPROVED_CODE_LEVEL_CONDITIONAL_ON_SEALED_APPROVAL.** Written `2026-10-10T22:24:58.163734+08:00`. This is a CPU-only non-author review of `window_resume.py`; it does not approve GPU execution, measurements, or product acceptance.

The local/remote identical pins are `window_resume.py` `785c1412900b855939c892b725acf968c90881fd9ba91e1527179f9638fe9c59`, `test_window_resume.py` `300f4e89696218ff087806e6ef9e47206f961e45639d2f421677a859c17e1af2`, recovery receipt `f23838b44c4d0b579e27a984dae7d0f4bcdb85948b5b0db8721d8144b8ee015e`, and independent test `4c3a6614fcd52b73831d636ce2d3950e997fa412a8b5a31854ee42a9b1e8d214`. The recovery receipt preserves the original failed run and records one prior service/eight calls, both old process identities dead, private ports free, and GPU memory 4 MiB. It explicitly leaves the initial cleanup exception undetermined.

The wrapper requires root approval, its own exact hash, the original admission through `require_seal`, and the pinned review. It checks every supplied prior hash for type, no symlink, immutable mode, and digest before reusing W98 A0-A7 verbatim. It starts only arm index 1/W128, compares each A native digest to the matching reused W98 result, then runs B09-B12 and cold under the original deadline. Cleanup records stop exceptions but returns success only after group death, both ports free, and GPU idle.

Fresh local and remote runs of author plus independent tests passed **4** tests. The review fixture proves one W128 start plus exactly 13 invokes (8 A, 4 B, cold), aggregate service count 2, and first-A native mismatch after one invoke with B/cold suppressed.

Before any launch, root must seal `prior_hashes` as the complete original read-only manifest map and bind prior run, original admission, deadline `2026-10-10T22:41:56+08:00`, and these exact hashes. The wrapper validates every provided map entry but cannot detect an omitted artifact from source alone.
