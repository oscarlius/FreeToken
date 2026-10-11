# D10 owned execution handoff v8

Added `d10_owned_launch.py` with the D07 atomic controller/child lifecycle derived from the reviewed D09 owned launcher and retargeted to D10. It owns the atomic batch reservation, child receipt binding, process identity, D07 GPU lock, child cleanup, and the pinned D10 T16 adapter's eight arms. Its live admission requires a sealed D09 GPU terminal (`kept`), candidate HEAD/cleanliness/ancestry, native provenance, leaf review, and root scope approval.

Added `d10_aiperf_runner_v3.py`: `--run` now requires a sealed admission binding the exact runner SHA, D10 T16 `kept`, D09 GPU terminal `kept`, candidate, 1-service/8-call budget, endpoint, and output. It then runs four AIPerf profiles: original R045 input twice and ignore-eos-256 input twice, each at request-count 2/concurrency 2, for eight calls. It does not start a service or acquire another lock.

Remote CPU FILEdry evidence: `d10_owned_launch.py` prepare path and v3 AIPerf FILEdry both ran with GPU/service/HTTP false; v3 SHA `89f798041de4cb639ed77e8ada5b152f66ca776bcde296662458dfde292b6a58`, owned launcher SHA `31f087444b7244535dc12bb6b1aa2d7aed26f5eb3d88900c7a64bf432e77a7d2`.

The existing native provenance remains an explicit pre-admission blocker until root provides the verified copied 481 extension bytes to the candidate execution environment. This author package did not mutate candidate sources or native files, and did not launch GPU/service/HTTP/compile/JIT.
