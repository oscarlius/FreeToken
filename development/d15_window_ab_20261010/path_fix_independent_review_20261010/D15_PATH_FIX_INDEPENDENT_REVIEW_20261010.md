# D15 PATH-fix independent CPU review

**Status: APPROVED_FOR_PRE_GPU_PATH_FIX_SCOPE_ONLY.** Written at `2026-10-10T22:11:08.660510+08:00`. This is a non-author, read-only review of the deterministic `PATH` repair only. It is not approval to launch GPU work or a runtime/acceptance conclusion.

The preserved attempt receipt [`PRE_GPU_FAILED_220455.json`](../PRE_GPU_FAILED_220455.json) is pinned at `80e496669a2999e946bee32478c4d921db3694935b519b750568127197bfa5ca` and records `pre_gpu_failed`, zero owned services, zero API calls, zero retry debit, GPU idle, and private ports free. Its stated cause was an isolated environment with no `PATH`, so `taskset` could not resolve.

`window_startup.py` is identical locally and remotely at `615c420d28207939423be78dab0cf4db3c81cdd3a843546c925c0d824c78d3d9`. It projects the release environment, retains the release taskset binding/virtualenv observer form, arm port/window replacements, and the two-request guard, then sets `PATH` to `/data2/FreeToken/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. It rejects and removes all five FT development variables: D0, D0 path, route trace, pause endpoint, and adaptation.

Fresh checks passed: local `pytest` **11 passed, 1 skipped**; remote CUDA-hidden `pytest` **12 passed in 1.15s**. In an independently constructed clean projected environment, remote `taskset --version` returned `taskset from util-linux 2.37.2`. A fresh CUDA-hidden child ran the observer `__mp_main__` install plus prefill-hook-install path using a temporary observer directory; `torch.cuda.is_initialized()` was false before and after. Remote `PATH_FIX_CPU_TEST.txt` is pinned at `cb84bd6598b68cff9d05438c08e42b5190fc221410d7cde9ead503a3306b2c0a`.

This did not create a service, make HTTP/API calls, take a GPU lock, instantiate Engine, or invoke CUDA. Root remains the launch/admission owner; source changes after these pins require a new review.
