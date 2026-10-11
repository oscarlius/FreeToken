# Strict constructor adapter plan

The adapter may temporarily replace only `torch.cuda.Stream`, `torch.cuda.set_stream`, and `torch.cuda.stream` while CUDA remains hidden. Each original is restored in `finally` and its identity is recorded. A fake CPU Engine/config must supply constructor resource fields only. It must not replace CacheManager, Scheduler._forward, Req.complete_one, matching, cache commit, or a request length.

The first constructor probe will be recorded separately. If construction succeeds, the next step is to feed SHA-bound raw pre-forward input through real Scheduler bookkeeping, with a token/sample-only engine seam calling `Req.complete_one`. No direct cached/device length assignment is permitted.