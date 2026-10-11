# R044b retry2 independent CPU review

- RID: `E2-R044b-retry2-20261010`
- Verdict: **PASS_CPU_REPAIR_AND_FILE_DRY_ONLY**
- GPU admission: **false**. No root admission was written.

The target source manifest is self-excluded and bound to `c94878fb43162a5edf2215c9accc4821be645a4d1c2e366a6fbb4679072752c3`. The independent target run used hidden CUDA and one OpenMP/MKL thread:

```text
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /data2/FreeToken/venv/bin/python -m pytest development/r044b_retry2_20261010/tests -q
14 passed in 0.07s
```

The run created no GPU work, HTTP request, service process, production action, or GPU lock. It covers the parser repair and the telemetry failure path: a timed-out dmon sidecar performs `terminate`, `wait`, `kill`, `wait`, while the other sidecar is still closed and errors are aggregated.

`CPU_STRICT_REPLAY_CURRENT.json` (`d265297b93abca5142d28c66da6d7594d6c1c06330be73b921ea0a0488d27253`) and its log (`96f6bba622410deddaffc81d6b043bcfa47840356f3bc5270c5ee144153927e1`) bind raw B1 and B2 inputs. Each has 12 cold and 12 warm rounds, 12 ordinary bindings per phase, and 24 total calls. Strict comparison passed with only `_unique_suffix` different. The raw `max_extend_tokens=4096` is retained and only materialized as `max_prefill_length` in the normalized strict-comparison map.

The actual file-dry receipt is `/data2/_shared/runs/ft_rounds/.dryrun_R044b_retry1_1429bba63c3a_retry2/dry_run_receipt.json`, SHA `589465c4eed31e76ed6c46a93c42143713e7b864569eb7c461145a22d8e8e39e`, mode `0444`. It binds the repaired parser SHA `d96f7d76bf58811ba7feb4cee3a04fa6099e46b50c864e970c67b0be911197b7`, materializes six services, and records no service start, request, or GPU lock. Its protocol remains six services, 144 replays, 24 per service, and B1/B2 first-not-met stopping after strict identity.

The separately produced canonical legacy file-dry receipt is `/data2/_shared/runs/ft_rounds/.dryrun_R044_retry2_root_canonical_20261010/dry_run_receipt.json`, SHA `8e88761f7159263f5fc618e31ea48dfebbce9f569b0905cc9d892c3fa590a104`, schema `ft_r044_file_dry_run/v3`. It carries the same retry2 RID, passed as a no-effect dry run, materializes six services, and binds the repaired parser and telemetry source copies to the reviewed SHAs. It records no service start, request, or GPU lock.

`ROOT_ADMISSION_R044B.json` is absent. The only active template has `admit=false` and `approved=false`. The copied file at `history/copied_retry1_evidence/ROOT_ADMISSION_R044B.json` was transformed during copying and retains stale 10:58 hashes; it is discarded as a control and historical-original evidence source. Batch157 remains `FAILED_HARNESS_PRESERVED`; this review does not change its terminal result or authorize any GPU/launch/HTTP/production action.
