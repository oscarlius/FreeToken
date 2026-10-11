# D10 persistent-cache prototype review request

Candidate source is remote `/data2/FreeToken/wt/d10-cache-persistent` at
`54955f7343fe11c5c0936d18570cfbd826c0f155` (local equivalent
`2b6f6e8da011c0a4694d30a626e03c9937fb1aef`). This packet is CPU/filedry
only. Its default action is `--filedry`; `--run` exits before GPU, service,
HTTP, lock, or compilation activity unless a root-owned independent admission
later replaces that guard.

The frozen plan remains exactly one service and no more than eight calls:
four AIPerf 0.11 profiles, each request-count 2/concurrency 2, in the order
R045 original, R045 original, ignore-eos fixed-256, ignore-eos fixed-256.
The copied runner/parser and frozen inputs retain their exact imports and
hashes inside this packet. Its AIPerf arguments preserve R045 affinity policy
outside this consumer; root admission must bind the existing `taskset 1,3-47`
service argv unchanged.

The branch probe is corrected to call
`Engine._can_use_d10_staggered(actual_batch, route_tracer)` after real method
return, rather than reading the nonexistent Batch metadata attribute.

Independent review must decide whether the old default-off T16 evidence can
transfer. This candidate adds entry/exit cache ownership handling on the
ordinary-batch path; this packet makes no transfer claim. If a new T16 is
required, root must queue its bounded 100-call default-off gate before GPU
prototype admission. No stress test is proposed here.
