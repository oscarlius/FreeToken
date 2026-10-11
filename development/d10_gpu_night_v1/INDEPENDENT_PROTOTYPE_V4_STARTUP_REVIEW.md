# Independent D10 prototype v4 startup review

Reviewed at `2026-10-09T16:54:55.3439459Z`. This review added only these review artifacts. It ran no GPU, HTTP, service, native compile, AIPerf profile, or product acceptance.

## Verdict

**PARTIAL — the CPU startup/control path is conditionally approved; the complete v4 runtime packet is not approved.** The prior v3 bootstrap defect is fixed: the real `ft serve` wrapper installs the observer in `__main__` and multiprocessing `__mp_main__`, and the spawned interpreter confirmed that installation. A future root admission remains necessary, but it does not require a D09 PASS or GPU evidence for this CPU-only conclusion.

## Evidence

- Current local and remote `test_d10_prototype_owned_parent_v4.py` each report **3 passed**. These are intentionally reported as mock control-flow tests, not service or generation evidence.
- The direct remote command `/data2/FreeToken/venv/bin/python d10_branch_startup_v4.py --cpu-spawn-probe` exited 0 and returned `probe_installed=true`, `cuda_visible_devices=""`, `gpu_started=false`, and `http_started=false`.
- Candidate `22ff3a389eae3724cdca9a45f2e19577082a2032` is clean on the FT host. `ServerArgs(server_port=31791).distributed_addr` evaluated to `tcp://127.0.0.1:31792` without CUDA initialization. The candidate scheduler passes `ServerArgs` into `Engine`, whose distributed initialization consumes `config.distributed_addr`; the v4 service admission also rejects all TCPStore CLI tokens.
- The current group receipt SHA-256 is `38221d74df59cc50db0cfe367865ce6df8a4087fae353c145c21b810cee504b3`, and its seven recorded source hashes match both local and remote source bytes. The bound native provenance file is `7c7aaaec99b8082b939eb7b03950db0d5d11444f0a8b3aac2175d45a96a14982`.
- The observer records the actual `Engine._forward_d10_staggered_decode` call, `len(argbatch.reqs)`, `argbatch.can_use_d10_staggered`, worker PID/start ticks, and worker PGID. The parent rejects a future run unless the event is a two-request eligible batch in the owned service group. This is static control-path proof only until a separately authorized runtime event exists.

## Blocking gaps

- `d10_aiperf_parse_v4.py` does **not** parse the retained genuine AIPerf 0.11.0 `profile_export.jsonl` (SHA-256 `4d4bf1ebabcd7237bf0c5bf6cb14dfe7dd5f7d81b87d7ebce43f03594c6bac12`): `parse_profile(...)` returned `[]`. The real record uses `metadata.x_request_id` and metrics value objects such as `usage_completion_tokens` and `time_to_first_token`; the parser expects manufactured flat sibling fields. The three v4 tests do not prove this compatibility, and no Strata/R045 genuine raw-export fixture was supplied.
- The remote group CPU receipt is mode `0664`, so its matching hash does not make it immutable evidence. All seven bound source files are `0444`. A new immutable receipt must be created rather than overwriting this one.

## Required before any runtime

Repair and test the parser with a retained non-manufactured Strata/R045 AIPerf raw fixture that demonstrates per-request ID, TTFT, decode rate, and output-count extraction. Seal a new receipt for the unchanged/repaired packet. Then obtain a fresh independent review. Future root admission must still bind source hashes, native provenance, kept T16 closure, and completed D09 terminal/manifest safe-cleanup records; its terminal classification may be `not_met` or `failed_harness` and does not need a fabricated aggregate PASS.
