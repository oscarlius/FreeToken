# D10 prototype v4 author handoff

`d10_prototype_owned_parent_v4.py` replaces v3 only for the new v4 scope.  It
launches `d10_branch_startup_v4.py` as `ft serve`; there is no `--program`,
`runpy`, TCPStore CLI option, or eligibility environment claim.  Candidate
`ServerArgs.distributed_addr` owns TCPStore as API port plus one.

The startup wrapper installs `d10_branch_probe_v4.py` in both the original
process and multiprocessing `__mp_main__`.  The one-time event is emitted only
after the real D10 method returns, records `len(argbatch.reqs)`, actual
`can_use_d10_staggered`, and the engine worker PID/start tick.  The parent
requires the engine PGID to equal the owned service group leader, so API PID
identity is never used as engine proof.  It adds no CUDA
synchronization or timing.

The controller waits for an atomically published `launched` receipt matching
the reserved child PID/birth.  Admission pins every v4 bootstrap/probe/parser
source, native provenance, kept T16 closure and prior D09 terminal/manifest
safe-cleanup records; D09 PASS is deliberately not required.

`d10_aiperf_runner_v5.py` freezes four profiles and eight actual requests.
`d10_aiperf_parse_v4.py` accepts only per-request raw responses that supply a
request identifier, completion count, TTFT and decode rate.  The two original
profiles each need two completions over 30; the ignore-EOS profiles must each
be exactly `[256, 256]`.  Missing branch/rates are `not_met`; request or
harness errors are `failed_harness`.  Cleanup validates the owned group and
API port, retaining the lock when cleanup fails.

This is source/control-chain preparation only.  It does not grant GPU run,
T16 acceptance, product acceptance, or independent review.
