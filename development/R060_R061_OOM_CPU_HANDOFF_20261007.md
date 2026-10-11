# R060/R061 OOM CPU preparation

`r060_oom_t16_prepare_v1.py` and `r061_oom_fault_prepare_v1.py` are inert by
default, but their explicit Linux `--run` paths now use controller/child launch
receipts, the D07 O_EXCL owner lock, a shared private API/TCPStore pair, owned
service PGIDs, and exclusive formal writers.  CPU verification never invokes
those paths.

R060 fixes the four required measurement arms (`base`/`candidate` crossed
with D0 off/on), 98,304/.88 service settings, and the cold request contract:
32,052 requested tokens, 32,064 observed input tokens, 128 tokens,
temperature zero, cached tokens zero.  Cold output comparison requires both
token IDs and full text.  D0 evidence is separately required to contain
prefill H2D and D2D rows.  Recovery is enabled by default; fault injection is
explicitly disabled.  `file_dry` uses the same exclusive JSON writer that a
formal artifact path can use, but writes only a developer dry directory.

R061 consumes only ordinary-v3 UserMsg/Detokenize token sidecar bindings; it
does not reconstruct token IDs with a tokenizer or claim FT development ACKs.
Its generated worker startup wraps the real `Engine.forward_batch`, emits one
durable `before_forward_oom` row for the target API UID, and raises an actual
`torch.cuda.OutOfMemoryError`.  It binds the product's existing restart queue
contract, captures the API process birth, checks the former worker PGID has
exited, and validates the post-restart ordinary token/full-text result.

## Pending product binding

The candidate product worktree and stable full commit for
`development/e2oom-recovery` remain deliberately unbound.  The run paths are
parameterized by a full 40-character commit and clean worktree, and fail closed
unless the product exposes its existing `backend_epoch`, restart queue, and
supervisor contract.  No CPU result authorizes GPU startup.

## Validation boundary

The tests cover inert preparation, candidate format rejection, exact cold
comparison, D0 evidence, exclusive dry writing, ordinary-sidecar-only input,
single injection identity, replacement epoch handling, all-worker-exit proof,
API birth invariance, and stale reply rejection.  They do not load a model,
open a listener, connect to a model endpoint, or inject OOM.

Linux CPU evidence is sealed at
`/data2/FreeToken/runs/dev_OOM/r060_r061_cpu_20261007_1900_v4`.
It ran nine targeted tests with `CUDA_VISIBLE_DEVICES=''` and a
`sitecustomize` guard that raises for `socket.connect` and `socket.listen`.
`report.json` SHA-256 is
`5987a9199356db5ad2c89f43caad10aa1ebfcd87af15b94a157dc7036b4594e8`.
The first staging attempt at `...1825` is retained as failed evidence: its
source inventory omitted `ft_batch_port_pair_v1.py`; v2 adds that required
runtime dependency and is retained.  V4 supersedes it with the real
controller/child and worker-hook CPU coverage.

## 2026-10-07 18:51 correction

R061 no longer installs an external `Engine.forward_batch` fault hook.  The
runtime accepts only the candidate scheduler's `FT_DEV_OOM_INJECT=1`,
`FT_DEV_OOM_UID`, and `FT_DEV_OOM_POINT=before_forward` path; trace, pause,
and D0 are removed from its service environment.  The startup wrapper installs
only the ordinary-v4 worker observer.  R061 now requires raw ordinary API/SSE
plus physical worker token sidecars, rechecks API birth after recovery, and
requires read-only file-dry and startup-review receipts before controller
reservation (and again in the child).  Queue timeout is 900 seconds pending
candidate-source binding to the product's restart timeout.

The current product source does not yet emit a UID/epoch/waiter receipt for the
injected OOM.  `run_fault_protocol` therefore cannot prove the affected UID or
that a queued request entered `maintenance=restarting`; this is an intentional
formal fail-closed gap.  The 10 local CPU tests only validate these admission
and evidence boundaries and supersede the prior 9-test local claim; no new
Linux capsule was created.

R060's current bespoke live body remains insufficient: its cold JSON lacks
physical token sidecars and its single probe does not satisfy the complete
T16 closure.  The accepted R059 `CandidateRunner` supplies the complete
four-arm cold/multi-probe/prefill/D0 closure, but it has fixed D07
identity/native-provenance bindings.  A R060-specific identity/native review
adapter is required once the OOM candidate SHA and provenance are sealed.
