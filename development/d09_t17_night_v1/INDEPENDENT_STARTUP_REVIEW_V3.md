# T17 v4 startup review packet

Candidate runner: `d09_t17_runner_v4.py`, SHA-256
`78c9c9811a1733fbc1ed300a1bf7e02f9bf1f9a205d2cb4b8c73c9534b1e4c88`.

The controller and child require a root-sealed admission that names a closed
T16 round `E2-D09-T16-night-20261009` with formal verdict `kept`, and binds both its `round.json` and `MANIFEST.sha256` digests. At
runtime they call `d07.require_closed_round()` before batch allocation. T17 is
not an admission prerequisite, avoiding a self-dependency.

Before the child takes the GPU lock it reads candidate HEAD and tracked status,
verifies the flag source, validates the D09 native-provenance hash, and hashes
both candidate extension files against that manifest. The live child saves
each endpoint response and its input-receipt, observation path, and serve-log
window digest. It saves each cold-A/cold-B/hot cell comparison and writes its
terminal only after group cleanup, GPU-idle proof, and lock release.

CPU FILEdry v6 created six actual fake subprocesses and executed eight fake
exact-ID transports through the production `evaluate()` path. It is not an
acceptance result and does not grant a live admission.
