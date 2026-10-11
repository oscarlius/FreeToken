# D15 Window A/B terminal review checklist

This is a read-only terminal-review plan. It does not authorize any runtime action.

- terminal/run path and SHA-256; parent process PID 3719668:start_ticks 173600516 dead before closure
- admission SHA da9f4bc566ecb550ae5356b1d76a7a676d8fe6e2f96fe9e15bb1daa918c0ed03; launch SHA ec389cfc5abc96f73f6efa9eb8ed05165fadb44b9152e269f67cd3c64dbf82b1
- candidate 481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9 and all admission runtime/source pins remain exact
- exactly two owned service starts, serial concurrency=1, no more than 21 generation calls, shared 1800-second deadline
- preserve prior 0-service PATH pre-GPU failure as no-debit evidence; do not merge it into this terminal
- A: eight frozen inputs for W98K and W128K; input IDs/prompt token count/native token SHA equal pairwise, and raw SSE/binding receipts exist
- W98K slot receipt is unique and actual_slots=2700; record W128K slot receipt actual value separately
- B09: request 9 candidate frontend has exactly 100223 planned input tokens; every dispatched B request fits prompt plus max_tokens within W128K
- cold: canonical cold payload fit within W128K; cached_tokens=0 and per-call min_free_gpu_mib non-null
- metrics: prefill duration is async Engine.forward_batch interval through original return, not kernel sum or TTFT; decode rate uses network first-output-to-terminal monotonic interval and reports pooled formula/scope
- telemetry 1Hz: usable rows cover calls; record uptime and R-thread counts; no claim of identical environment
- preserve terminal/failure/result bytes and carrier verdict; incomplete comparison or harness failure cannot become kept
- each owned PID/PGID/session birth proof closed; service and master ports rebind; telemetry sampler closed; GPU compute idle; D07 lock absent
- hash every regular raw artifact and compare terminal counts/services with receipts before any formal closure
- only complete all-gate evidence may support a formal kept mapping
- product acceptance stays false for failed_harness, not_met, incomplete B/cold, or missing required receipts
