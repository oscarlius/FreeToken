# D03 f506 G4/G5 self-check preparation

`d03_gpu_selfcheck_f506.py` is a continuation-specific wrapper for the
historical D03 GPU self-check.  It does not turn the historical c30 PASS into
evidence for `f5067bbe05da51d5f78185213435a8be095a684a`.

It pins and compiles exactly one copy of the historical runner:

| input | SHA-256 |
| --- | --- |
| `development/d03_gpu_selfcheck.py` | `4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453` |

The historical protocol remains responsible for these actual GPU checks:

- G4: every historical boundary, including `12672`, and terminal raw-token
  binding; and
- G5: two independent slots=0 processes with bitwise logits comparison.

G3 is a separate CPU tool regression against the historical three-length,
two-decimal conv/recurrent table. Its command and evidence are recorded
separately; this GPU wrapper does not execute G3.

The f506 wrapper sets the parent to
`/data2/FreeToken/wt/e1r003st@c30ae0d7003c3bbbf56867ce74da797332fa7ed5`,
the candidate to
`/data2/FreeToken/wt/e2d03-continuation@f5067bbe05da51d5f78185213435a8be095a684a`,
and the sole new output directory to
`/data2/FreeToken/runs/dev_D03/gpu_selfcheck_f5067bb`.

## Required raw manifest

An actual run requires `--raw-manifest <path>`.  The manifest schema is
`ft_d03_f506_raw_ids/v1`; it must contain the exact candidate commit/worktree,
trace/messages/request digests, int32 little-endian ID digest and length, plus
this candidate tokenizer provenance:

```json
{
  "candidate_tokenizer": {
    "manager_module": "freetoken.tokenizer.tokenize.TokenizeManager",
    "construction": "ChatCompletionRequest -> chat_request_to_genspec -> TokenizeManager.tokenize",
    "source_sha256": {"python/freetoken/tokenizer/tokenize.py": "<f506 hash>", "...": "<each API-chain source hash>"},
    "model_files_sha256": {"tokenizer.json": "<model tokenizer hash>", "...": "<each tokenizer asset hash>"},
    "absent_model_files": ["special_tokens_map.json"],
    "encoded_ids_sha256_int32le": "<same digest as raw_ids_sha256>"
  }
}
```

The runner computes the current candidate hashes for the real request/API
chain (`server/api_models.py`, `server/openai_api.py`, `message/__init__.py`,
`tokenizer/tokenize.py`, and `utils/__init__.py`) and rejects a manifest from
c30, a mismatched source, or IDs that are not the recorded
candidate-tokenizer output. It never produces token IDs from text.

The tokenizer, config and chat template are required. The optional special
token map may be absent, with that absence explicitly recorded and verified.
Existing model overlay symlinks are hashed through their actual targets.

## Execution boundary

Only the queue owner may execute the Linux GPU command:

```sh
/data2/FreeToken/venv/bin/python development/d03_gpu_selfcheck_f506.py \
  --run --raw-manifest /path/to/new-f506-raw-manifest.json
```

The child environment removes every `FT_DEV_*` and `FT_D3_*` inherited value,
then sets `CUDA_VISIBLE_DEVICES=0`. Both preflight and the launched service use
`python -S` with an explicit candidate `sys.path` bootstrap and verify the
loaded `freetoken/__init__.py`; this does not rely on a `.pth` ordering. Every
service starts in a new session. Cleanup signals only that owned group/session,
records and checks the service start time and boot identity, ignores zombies,
and retains the GPU lock if live descendants or port/GPU
release checks fail. It does not kill foreign processes.

Cleanup keeps the original leader unreaped until its whole group has stopped,
so the process number stays reserved while children remain. If birth identity
cannot be verified, it refuses the signal and retains the lock for recovery.

The historical scientific envelope stays fixed: 814 evaluated points, 199
outside the legal envelope, and maximum finite ratio `5.489091417`.  This
script neither changes those results nor widens a threshold.

## Local preparation check

This is the only allowed local check; it starts no service and uses no GPU:

```powershell
python -m pytest -q development/tests/test_d03_gpu_selfcheck_f506.py
python development/d03_gpu_selfcheck_f506.py --self-test
```

Passing these checks only validates wrapper preparation.  The f506 G4/G5
GPU evidence remains absent until the queue owner supplies a new manifest and
runs the command above.
