# R067e batch166 independent terminal review

- Review time (remote): `2026-10-10T22:01:48+08:00`
- Formal carrier: **failed_harness**. Product acceptance: **false**.
- Raw terminal: `E2-R067e-20261010` / SHA-256 `ce38268cbb489638fc1064a3a28b3b80391c9fbed1dd660f388ed8ba73ce4422`. Its parent RID is retained byte-for-byte; batch 166 retry2 is bound by launch/admission/budget/candidate manifests.
- Counts: 3 service starts, 7 dispatched generation calls, 6 completed terminal response records. The seventh cold-A call reached the preguard and then disconnected; it is not silently dropped.
- Failure evidence: `services/cold_A_p8192_t1/cold_preguard_engine_hash.json` SHA-256 `dcde28a1964fd2e40fb05c66aa714b48ba04a9554aef8fa821ca8f5c9315b7b8` has `equal:false`; raw terminal carries `RemoteDisconnected`. The 10-service/14-call comparison was not completed.
- Cleanup recheck: controller absent, all three recorded service groups closed, API/tcpstore ports rebind, GPU compute empty, and `/data2/_shared/gpu.lock` absent.

The full raw regular-file SHA-256 inventory is in the adjacent JSON and must match before a hard-link closure.
