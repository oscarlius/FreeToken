# Author handoff: E2-R067d-d20-short-tail-retry1

Status: ready for an **independent CPU review**. This handoff does not admit a
GPU run, create a formal round, or change the historical R067d review bytes.

## Scoped retry

- RID: `E2-R067d-d20-short-tail-retry1`; failed-harness tooling retry `1/2`.
- Every one of the eight cold services with `FT_DEV_PREFILL_SCHEDULE` omits
  `--cache-type naive`. The candidate resolver from the frozen actual d20
  source maps the omitted default (`radix`) to `hybrid_radix`; an explicit
  `naive` value is rejected by the CPU guard.
- All other packet inputs, criteria, paired ports, service count (10), and
  generation-call count (14) remain bound. Cold observations require the first
  request on a fresh service and API `cached_tokens == 0`.
- The copied v1 `cold_A_p8192_t1/serve.log` has SHA
  `2d6c5df4a412e3356f5bc39a3124bde29f21cefb08dd2261baf574a26279f10b`.
  Its `cache_type='naive'` plus the exact rewind-checkpoint exception replay as
  `failed_harness`, not a product result.

## Frozen source and evidence

- Source freeze: `RETRY1_SOURCE_FREEZE.json`, SHA
  `0f97d38339dd53ebe5877b0e0925b983593cde7acd8d8f4e2e027382afd5c176`.
  The remote CPU job rehashed the frozen engine, scheduler cache, and linear
  attention sources against `/data2/FreeToken/wt/d20_short_tail_v1` before
  running tests.
- Effective remote config: `R067D_RETRY1_CONFIG_CPU_ONLY.json`, SHA
  `88a587c598cf53d0465d99e50d48286621ad0ed9b2313001fea5ca23482a8d92`.
- Effective remote prepared runner: `R067D_RETRY1_PREPARED_RUNNER_PACKET.json`,
  SHA `700931c266165954aed43ef98c2a8ee3568dc4a45c6f4f409eff52f88f8d7b14`.
- Linux receipt: `LINUX_CPU_RECEIPT_v1.json`, SHA
  `d7851e24a2b6c475124ae6b64697564b1798ff83e6329e6353951060fc35107e`.
  It records `/data2/FreeToken/venv` execution of packet preparation, 14 test
  passes plus 10 inherited subtests, and FILEdry.
- Remote FILEdry receipt: `evidence_cpu_filedry_remote_v1/receipt.json`, SHA
  `174702564883eff2edc85d600424ac0cf5535a1e2d72b40832a67ab401cacf3a`.
  It invokes the actual prepared-child launch helper 10 times and judgment
  helper 14 times with fake probe/Popen and synthetic transport only. Its
  `gpu_started`, `service_started`, `http_generation`, and `admit` fields are
  all false.

## Reviewer checks and remaining gate

1. Rehash the listed freeze, config, packet, Linux receipt, and FILEdry receipt.
2. Confirm every scheduled cold argv has no `--cache-type`, resolves to
   `hybrid_radix`, and retains `cached_tokens == 0` plus fresh-first-request
   enforcement.
3. Confirm the CPU receipt's test output is `14 passed, 10 subtests passed` and
   FILEdry reports exactly 10 services, 14 calls, and 20 unique ports.
4. Preserve the historical R067d independent review. The user-authorized
   reclassification to `failed_harness` is recorded separately by root.

Independent review remains the next gate. After it passes, root alone may
evaluate queue order, R044/R067d runtime admission, and the existing formal
GPU controls.

Predicted serialized GPU duration after admission is about 55–75 minutes:
the recorded cold startup was about 4.5 minutes, applied to ten services, plus
the 14 requests and owned cleanup. This excludes any occupied-port wait of up
to 120 seconds per affected pair.
