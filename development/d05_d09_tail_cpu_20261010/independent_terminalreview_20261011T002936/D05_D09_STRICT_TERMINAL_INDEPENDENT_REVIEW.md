# D05/D09 strict replay independent terminal review

**Verdict:** `ACCEPTED_CPU_SCOPE` for `bd57cfdccc2a935d46cb0a89b8b36be7a18706de`. This is not GPU, T16, service, or product-acceptance evidence.

I independently reran both scripts remotely in the FT venv with CUDA hidden and the explicit candidate import root. Both exited zero. D05 reported `cached_tokens=13376` and `forward_cached_len=13554`. D09 v7 asserted the raw/source pins, recorded exactly one successful native boundary snapshot at 20282 (index 1), one original exact-commit call returning false with old cached length 20160, and UID1 native admission at 20160.

The D09 raw inputs and bindings are content-bound. D05 remains a permitted `torch.arange` geometry replay rather than raw R052a content. The two results share bd57 code but are not the same rejection predicate: D05 is page-alignment/tail behavior; D09 is `cache.py:655` rejecting a non-D09, nonzero old handle. The two default-off ideas in `SUPPLEMENT_Q1_Q5.md` remain proposals requiring separate CPU state-ownership coverage and a separately authorized T16.

## Finding

**MEDIUM — launch binding is late.** `strict_scheduler_d05_pinned_v6.py:12-19,74-85` and `strict_scheduler_d09_pinned_v7.py:13-21,90-98` import and construct before `source_receipt()` can reject a wrong checkout. Under the default FT venv only, D05 imported `/data2/FreeToken/src/FreeToken` and failed in `Scheduler.__init__` before its candidate-root assertion. The reviewed command used `PYTHONPATH=/data2/FreeToken/wt/d05_hbug_candidate_20261010/python`, where both produced candidate-root receipts. Record that command next to the scripts and assert the import root before construction. It does not invalidate this exact run because its output includes the candidate source pin.

## Evidence

- D05 v6 SHA-256: `aec28686989179bae8f3369aeb37044d8490e0bda94af41418b7eec3c61995d9`
- D09 v7 SHA-256: `e12e67b8a600e0df45c402adadfb87d5ac642a27d403082a06175cec21d1d77a`
- V7 assertion receipt SHA-256: `31c41cf4146d92116908a7a1ea0ab2bb922ad98537025176ab2b8ae84eb21a77`
- Complete data: `D05_D09_STRICT_TERMINAL_INDEPENDENT_REVIEW.json`
