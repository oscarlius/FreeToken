# D08 diagnostic trace repair after R048a

The current T09 result is `failed_harness`, not acceptance. R048a/b106 retained six V0 performance observations, then its diagnostic service failed during CUDA Graph capture. The failure archive is `plan/01_测试与调研/results/T09-E2-R048a_20261008.md`; original evidence stays readonly.

## Cause and correction

At candidate `8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8`, `_decode_hybrid` synchronizes the current CUDA stream while `GraphRunner` captures `model.forward`. CUDA disallows that operation. Simply skipping Python tracing during capture would also be incorrect: replay launches the graph without rerunning the Python forward body. See [PyTorch CUDA Graph constraints](https://docs.pytorch.org/docs/stable/notes/cuda.html#constraints) and [NVIDIA capture restrictions](https://docs.nvidia.com/cuda/cuda-programming-guide/index.html#prohibited-and-unhandled-operations).

Implement only in the isolated `development/e2d08-capture-trace` branch, based on the existing D08 candidate. Preserve graph execution, the model/configuration and all measurement criteria.

1. In trace-enabled forward, retain stable per-layer/batch task handles and copy-event pairs; only record events. Do not synchronize, read native task timing, calculate elapsed time or append observations inside capture.
2. After replay/eager decode and the engine's step-completion event record, synchronize outside capture, then read current native task completion and per-layer PCIe CUDA-event elapsed times. Mark this as diagnostic timing that perturbs execution.
3. Keep graph/eager event lifetime sound across repeated decodes and clear stale references during rebuild/shutdown. Reject missing layers/events, zero/invalid native timestamps and stale observations. Warmup host enqueue timings must not be represented as current replay timings.
4. Allocate timing events with explicit graph-record semantics. [PyTorch Event documentation](https://docs.pytorch.org/docs/2.14/generated/torch.cuda.Event.html) distinguishes `external=True` event record/wait nodes from default internal dependencies. A text-only inspection of the actual FT venv found `torch 2.11.0+cu130` and confirmed its `Event.__new__` accepts and forwards `external`; no package change is required.
5. With tracing disabled, add no diagnostic events, synchronization, native timing reads or trace files.

## Evidence required before GPU approval request

- Execute CPU tests of actual observer methods with fake events/native tasks: ordering, consecutive replay freshness, eager/captured lifecycle, missing/invalid evidence and disabled-path behavior. An entirely skipped suite is not CPU validation.
- Verify actual engine integration ordering, not only a helper or source-text pattern.
- Commit the reviewed local change, synchronize it to a dedicated server worktree, and run Linux CPU checks after the active GPU batch ends.
- Bind a new default-path T16 candidate gate and a new T09 harness to that exact commit. Existing R051 `kept` covers the old commit only.
- Prepare exact source, default FILEdry and independent R startup evidence. Do not reuse old signatures.

## GPU boundary

R048a started model services and completed requests. HANDOFF section 8.4 therefore requires explicit user approval before another T09 GPU attempt. The concrete proposal must cover the new candidate's T16 gate and, conditional on acceptance, the complete V0/A/B/C/S performance and diagnostic phases in one new letter-suffix round. Do not combine retained b106 V0 results with later arms. Preserve the existing C-arm physical-memory exception exactly.

CPU tests cannot prove captured CUDA events refresh on replay. Real validation must retain graphs, show capture success, at least two consecutive decode replays with genuine native and per-layer event completion, and trace-free performance phases. No completion or performance claim is made by this plan.
