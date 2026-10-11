# R044b pressure-duration CPU proof

Generated: 2026-10-10T09:24:19.038558+08:00

This is a read-only calculation over retained retry1/retry2 ordinary/B1 real artifacts. No GPU, HTTP, service, compiler, or formal-round mutation occurred.

## Evidence

Both retries contain exactly 24 real calls: cold UIDs 0-11 and warm UIDs 12-23. Their position-by-position messages_sha, prompt-token count, and completion-token count are identical. The full raw path, SHA-256, UID/call rows, response mtime, and recorded elapsed seconds are in PRESSURE_DURATION_CPU_PROOF.json.

The observed workload is not 32K: prompt tokens range 12443-21976; maximum prompt plus completion is 22176. The retained source cap is 200 output tokens, not 128 or 256.

| Retained service | birth-record to health | 24-call generation | response to owned cleanup | birth-record to cleanup |
| --- | ---: | ---: | ---: | ---: |
| E2-R044-night-20261010-retry1 | 252.830s | 447.670s | 22.372s | 722.955s |
| E2-R044-night-20261010-retry2 | 240.791s | 384.557s | 12.960s | 638.370s |

The retained runner executes six services serially. Applying the two actual per-service lifecycles produces a six-service wall estimate of **63.84-72.30 minutes**, before lock queueing, retries, or host contention.

## Pressure declaration

PRESSURE_DECLARED: the sequential six-service forecast exceeds 30 minutes. CPU, memory, PCIe, and disk utilization were not retained in these artifacts, so saturation is **unknown**. The user must be notified of this duration pressure.

A 25-minute generation-phase cap is evidence-supported only as a **negative candidate**: actual 24-call phases took 384.557-447.670 seconds. It must be root-sealed and A-reviewed before use; it cannot alter the frozen workload, and any exceedance must be failed_harness with immediate stop.
