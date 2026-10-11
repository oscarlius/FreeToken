# D09 parent v5 independent Linux CPU review

**Verdict: APPROVE_CPU.** The v5 delta is limited to retaining sockets before bind, setting `SO_REUSEADDR`, and selecting a fresh `FILEDRY_v5` root. Its local and remote SHA-256 is `79241e0ed911cb0b97561cf913e84ad7b2ba83b2cc4f7390ccb21265b59b7fd1`.

The Linux TCP lifecycle test passed 2/2 and covers the active-LISTEN exclusion, plain-bind TIME_WAIT failure, and explicit reuse success. The v5 FILEdry terminal has SHA-256 `36c0792a671008266140f351d3102b8f97ae436d84bcc1340ff96c3b75df935d`; its eight root-client source bindings were recomputed with no mismatch.

The terminal records the canonical 3-service/60-call topology: `fresh_on=36`, `edit_cold_A=12`, and `edit_cold_B=12`, with 12 comparison rows and zero cold cached tokens. It also records that no GPU, service, HTTP, or compile path started. Its comparison verdict remains `measured_pending_independent_review`.

The existing parent regression suite passed 6/6. Its v4-to-v5 delta leaves plan order, source/admission bindings, and native-source controls unchanged. This review is CPU readiness evidence only; formal T16/T17 GPU acceptance and admission remain withheld.
