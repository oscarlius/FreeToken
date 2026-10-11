# T10 D14 / E2-base.1 replay preparation

This is CPU-only preparation.  It allocates no RID or batch, starts no service,
and has no GPU launch path.  The future owner must freeze a new payload on the
merged `E2-base.1` commit, supply its full SHA and source-file hashes to
`t10_d14_prepare.py`, then independently validate the emitted record before
using the established atomic launcher.

## Recorded R017 parent protocol

The sealed parent is `E2-R017` / batch 44.  Its baseline commit is
`23f2e2caa3395837c9474735ffc83321f3b9b5a1`, and its affected candidate is
`c30ae0d7003c3bbbf56867ce74da797332fa7ed5`.  Read-only local and server
evidence identifies its `round.json` as
`f3198a83789480c6bf2e4a2d333f036a3a12e3fd055241e6a5e55c91d4660c37`, phase-1
manifest as `31f1a9c190f2b529b8e4b2d2bc964af0b5cd5e084d4a16b05db797143c4df98e`,
and run manifest as `10f57ef07f85c772e8d01063b47776fb2d4d8f84e9654ea5dca962f0bd257b94`.

The actual phase-1 runner starts three separate owned services, B1/B2/B3.  In
each service it replays the sealed reverse trace cold and the sealed forward
trace warm, 12 canonical message snapshots each.  This yields 3 × 2 × 12 = 72
terminal engine-token records.  Each record binds raw `prompt_ids` and their
int32le SHA, raw generated IDs, UID, PID, PGID, HTTP finish reason, and mapped
engine finish reason.  `tool_calls` maps to engine `stop` only when the tool
name list is nonempty and nonblank.  Every replay is non-dry, error-free and
has 1..200 completion tokens.

The frozen parent flags are CUDA device `0`, `mamba_host_slots=0`,
`max_extend_tokens=4096`, ordinary (`prefill_layer_major=False`) prefill,
`enable_cache_report=True`, cap 200, model `Qwen3.8-Flash-Next-NVFP4`, and
`http://127.0.0.1:8095/v1`.  Parsed serve arguments must be equal across arms
apart from the real service PID. The canonical frontend manifest SHA is
`bf1f38901055e79e0b4ae48615f4ce1f58a4efc02a31f88ff644d857c6bc0356`; reverse
and forward trace SHA-256 values are respectively
`097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24` and
`055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899`. The exact
legacy `agent_trace.py` MD5 is `f81acb79c3dbc89999f5f76de4c9a070`.

The archived R017 runner SHA-256 is
`13326d9ce238a5066a89cc35eb5bace1be08a9ab69767e432bd94582dfeac551`; its
logits probe SHA-256 is
`7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7`.

R017 rederived forks from all six generated streams.  It retained 11 actual
forks at round/index `(0,2), (2,10), (3,0), (4,0), (5,154), (6,48), (7,1),
`(8,9), (9,4), (10,0), (11,107)`. The 36 comparisons for each same-phase
cross-process relation were all equal: cold/cold 36/36 and warm/warm 36/36.
The 36 same-process cold/warm relations were equal only 3/36, hence differed
33/36. The earlier 6/36 reading was an incorrect interpretation of the
six-stream/fork structure. These are historical D14-affected observations, not
an acceptance target.

## Required D14 / E2-base.1 deltas

Only the frozen candidate source changes: it must name `E2-base.1` and a new
full commit SHA rather than `c30ae0d`.  The 12 raw prompt-ID rows and both
sealed trace bindings are copied byte-for-byte from R017; text decode/re-encode
is forbidden.  Every staged runner, launcher, probe, and extension comparison
must be pinned in the new source bundle before a round is reserved.

All listed flags, arm layout, replay ordering, terminal binding, and raw-ID
finish-reason checks remain unchanged.  The rerun must rederive forks from the
six actual output streams and report cold/cold, warm/warm, and cold/warm counts
out of 36.  It must also keep the existing top-2 logit-delta classification.
For every actual fork, phase 2 uses two fresh processes, warms each prefix, then
captures `P+X` at K=1 and compares full FP32 logits.  This is a reproducibility
probe, not a direct cold-versus-warm causal comparison.

`plan/CODEX_HANDOFF_20261004b` §1.4 requires this 3-process × 12-round rerun
after the D14 gates; §2.3 places T10 rerun on E2-base.1.  It must not reuse an
R017/R013 output or compare against a retokenized substitute.

## CPU admission use

```bash
printf '{"t10_phase1.py":"<sha256>","launcher.py":"<sha256>"}' > bundle.json
python development/t10_d14_prepare.py \
  --e2-base-1-commit <40-hex-commit> --bundle-json bundle.json > admission.json
python development/t10_d14_prepare.py --validate admission.json
```

The validator fails closed on the old candidate, missing/new input provenance,
flag drift, incomplete terminal bindings, or absence of all three count classes
and the top-2 requirement.  It is an admission record only; the owner still
needs an assigned RID/batch, a frozen atomic launch payload, D14/T17 closure,
and independent review before any GPU work.
