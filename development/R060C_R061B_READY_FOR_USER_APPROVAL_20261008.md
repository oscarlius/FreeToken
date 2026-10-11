# R060c gate and R061b conditional OOM approval package

## Candidate and scope

- Parent: `0aa23431e5b800797543bdecbf35a01045131d7d`.
- New candidate: `4c878f6b3251cca273d8548e7f5cf58a56711d3a`.
- Isolated worktree: `/data2/FreeToken/wt/e2oom-recovery-r061fix`.
- R060c RID: `E2-R060c-gate-OOM`; the T16 contract is four arms (parent/candidate × D0 off/on), cold 32,064 input and 128 completion tokens, `98,304` / `.88`, with trace/pause disabled.
- R061b RID: `E2-R061b-OOM`; it retains the original DEV OOM fault-injection scope.  It is conditional on terminal R060c kept closure.

## Candidate CPU and native evidence

The exact former OOM product CPU suite was rebound with `FT_OOM_TEST_WORKTREE=/data2/FreeToken/wt/e2oom-recovery-r061fix`, empty `CUDA_VISIBLE_DEVICES`, and the CPU socket guard. It completed **69 PASS**: the retained 67 tests plus the two actual scheduler fault-branch regressions. The bound summary is in [report.json](/data2/FreeToken/runs/dev_OOM/r061b_r060c_cpu_prepare_20261008_052000/report.json), SHA `8f3a53715c79d51ed03fe2d2ee2b894a48b5bb7fcb5367afccefc406df902547`.

Native provenance is [r060c_4c878f6_native_provenance_20261008.json](/data2/FreeToken/runs/dev_OOM/r060c_4c878f6_native_provenance_20261008.json), SHA `e9cd249ad68029528688644a575d3b9411e69ba6a259b35b133346ecf2785ee8`. Both candidate `.so` files are regular `0444` copies, match the parent symlink targets by SHA/size, and CPU import resolved them from the isolated candidate without CUDA initialization.

The R061b adaptation of the actual v7 protocol/bootstrap suite completed **7 PASS** in the same CPU-only stage. Its source closure manifest is [source_manifest.sha256](/data2/FreeToken/runs/dev_OOM/r061b_r060c_cpu_prepare_20261008_052000/source_manifest.sha256), SHA `b5ea8fc37b7f91ea9f03919bb6d7df44c44787be9a8d740689d98460ba1f8585`.

## R060c same-entry FILEdry

The actual entry was:

```sh
CUDA_VISIBLE_DEVICES='' PYTHONPATH=/data2/FreeToken/runs/dev_R046/r046b_section12_source_v4/cpu_guard:/data2/FreeToken/wt/e2oom-recovery-r061fix/python \
/data2/FreeToken/venv/bin/python \
/data2/FreeToken/runs/dev_OOM/r061b_r060c_cpu_prepare_20261008_052000/development/r060c_oom_owned_launch_v3.py \
--file-dry-run
```

Its [receipt](/data2/_shared/runs/ft_rounds/.dryrun_R060c_v3_E2-R060c-gate-OOM/dry_run_receipt.json) is `0444`, SHA `6c441999e595579cdafb786ad0fc4cf9fc3f195f00b0a0b05a88cc1f94f76aac`. It binds the current source closure, isolated candidate, native proof, cwd/UID, and all four arms. It records `service_started=false`, `requests_sent=false`, `gpu_lock_taken=false`, `batch_allocated=false`, `formal_rid_directory_created=false`, and `popen_reached=false`.

## Approval boundary

R060c has passed independent startup review and pin. The sealed `0555/0444` directory is `/data2/FreeToken/runs/dev_OOM/reviews/E2-R060c-gate-OOM-v1`; `review.json` SHA is `f62891a84b71e4d8c5a455311d202ac057f80f9c28797ac574e918868c807431` and `pin.json` SHA is `0d38db29631ef50c968751609cd9872a1d75a05838f04af5999c3da211477896`. R060c is therefore ready for one separately authorized GPU gate attempt. This does not constitute a terminal kept result.

R061b has CPU preparation only. Its formal FILEdry, independent review/pin, controller start, and fault-injection measurement are forbidden until R060c has a real terminal **kept** closure whose SHA is bound into fresh R061b admission material. The preserved R061a/b103 failed-harness evidence remains historical failure evidence and cannot substitute for that prerequisite.


2026-10-08 16:15: R060c/b114 is independently kept and D04 closed (closure SHA1bdeae93d0652dc83d2a7e5d2404e42344167204f33667fcf7d98091cd0745a7). R061b v2 adds mandatory current-candidate kept pin/round/manifest binding to its fresh FILEdry and startup review. This preserves the approved fault-injection scope.
