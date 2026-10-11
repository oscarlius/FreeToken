# T00 runner preparation (not an execution record)

`E2-R000` remains a reserved placeholder. This note and
`plan/01_测试与调研/batches/T00_runner_draft.py` perform no remote operation,
GPU allocation, source edit, or creation of a round artifact. The draft is
explicitly **not executable**: `--run-remote` always refuses until its runtime
contract is redesigned by the GPU executor.

The rendered TODO list records why it is withdrawn: wrong probe path, missing
worktree `PYTHONPATH`, insufficient `/v1/models` readiness, unproven `setsid`
PID ownership, missing per-arm gates/imports/strict argument diff/readonly
metadata, prior raw-output binding risk, an unauthorized 73728 prefill-length
change, and an unspecified D0/checkpoint arm matrix.

## Current stop condition

T00 requires both `E2-base@<7-char-commit>` and a passing `T16 (gate-D00)`. Current repository
evidence says `E2-base` is not yet tagged; D01/D02 gates are closed PASS and
gate-D00 batch26 is running. The replacement runner must prove the tag
points at the recorded full commit and must receive the actual gate-D00 evidence
path; a name or a planned result file is not proof.

`ft_probe_ckpt_tax.py` has five alternating single/multi pairs per process.
This matches T00: pair 0 is the cold first appearance for both shapes; pairs
1--4 are the four hot observations. The checkpoint tax result is the multi
shape, while the single shape remains recorded as its paired control. The draft
copies the original JSON/stdout and writes a separate classification record; it
does not call all five pairs hot or calculate a cold median from the hot pairs.

## Required preflight evidence

The eventual remote runner must capture, fail closed on, and retain in the
round directory:

- `git describe --tags --exact-match` equal to `E2-base@<short-commit>`, exact
  worktree path, full/short commit, clean tracked tree (`--untracked-files=no`),
  and each imported `.so` path plus hash. Normal compiled or verification files
  are not a clean-gate failure.
- gate-D00 PASS evidence for that same commit, the local and remote MD5/SHA256
  of both original probes, and an import assertion that `freetoken.__file__` is
  `/data2/FreeToken/wt/e2base/python/freetoken/__init__.py`.
- an atomic ownership lock at `/data2/_shared/gpu.lock` (prewritten temporary
  owner record plus atomic `ln`; never delete a foreign lock), PID/session/PGID
  ownership before termination, no listener on 8095, no competing batch/replay
  process, and each GPU at at most 100 MiB used.
- `taskset -c 1,3-47`, `--prefill-layer-major`, and all three window settings
  fixed to 73728 where applicable. Production is D0 off; only the D0 arm sets
  `FT_DEV_D0=1` and a per-arm `FT_DEV_D0_PATH`.
- server `Parsed arguments` logs. Compare intended-like arms using
  `serve_args_diff.py`; any unapproved difference fails the arm.

The runner must set the fixed runtime environment before every preflight and
server: `PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH`,
`LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64...`,
`VIRTUAL_ENV=/data2/FreeToken/venv`, and `PYTHONUNBUFFERED=1`. It invokes only
`/data2/FreeToken/venv/bin/ft`, after proving that executable and `ft --help`
work; `taskset`, `numactl`, Python imports of FreeToken and the compiled kernel
modules must also work. Record the original probe/helper hashes and make their
bad-argument, bad-length, and parsed-argument-pollution checks return nonzero
before starting a server. A helper that accepts malformed input fails the round.

## Measurement and raw-data handling

Use neutral case IDs such as `e2r000-case-01`; do not put an arm label in a
`cold_id` used for a whole-input equality comparison. Before calling the
unchanged cold probe, require that its hard-coded raw destination
`/data2/FreeToken/runs/cold32k_20261002/<cold_id>.json` does not exist. After a
zero return code, require a new JSON record with matching `cold_id`, valid
`prompt_tokens`, and `cached_tokens == 0`; copy it (do not move or overwrite it)
to the arm directory and record both source/destination hashes and source path.
Any bad return code, absent field, pre-existing ID, or nonzero cached tokens
fails closed.

The planned counts are: production D0-off cold32 first shots ×4, short ×3,
cold64 target 65412 ×2; D0-on cold32 ×2; and checkpoint on/off cold cells ×3
independent server processes. Cold records remain first observations and are
never replaced by a median from the alternating checkpoint hot sequence.

The withdrawn rendered draft's `T00_SHORT_TARGET` parameter is obsolete. The
leader selected the verified original `ft_perf_decomp.py --fixture short`
below; the executable replacement is `batches/t00_runner.py`. It has not run
against a GPU and requires independent review before admission.

## Read-only E1-R001 short-fixture evidence (2026-10-04)

Remote raw artifacts resolve the E1-R001 S1 fixture itself. Both
`_e1/E1-R001/groupA.jsonl` and `groupB.jsonl` use the exact source constant
`"用三句话介绍混合专家模型的前缀缓存。"` from
`/data2/FreeToken/scripts/ft_perf_decomp.py`. The payload requests
`max_tokens=128`, `temperature=0`, streaming usage, and
`chat_template_kwargs.enable_thinking=false`; it has no `ignore_eos` field.
Actual records report 23 prompt tokens, zero cached tokens, 120 completion
tokens, and `finish_reason=stop`.

| group | first short TTFT s | second short TTFT s | decode tok/s |
|---|---:|---:|---:|
| A | 2.645 | 2.672 | 40.68 / 40.68 |
| B | 2.696 | 2.708 | 41.16 / 40.74 |

This is not a `probe_ft_cold32k.py` input: that probe constructs a padded long
prompt and has no mode for the exact short fixture. T00 must either use the
existing `ft_perf_decomp.py` short section as its same-fixture comparison or
report the historical-short comparison as unavailable. The separate historical
90/2962-token, 1023-output claim is not represented by these E1-R001 raw
artifacts; no exact input/options artifact was found in the bounded lookup.

## Exact production flags resolved before execution

The v3.2 paper appendix B (local archive lines1009/1018) and historical
`/data2/FreeToken/runs/cold32k_20261002/SERVE_CMD.txt` explicitly carry
`--max-prefill-length 4096 --enable-special-token-ckpt`. The generic README
BASE omits both, while source defaults are8192/false, so omission would change
the protocol. T00 production/D0/ON explicitly use4096 and checkpoint on;
OFF uses4096 with checkpoint off. Window73728 and taskset1,3-47 are from T00.
Independent verifier `/root/d00_audit` confirmed these primary artifacts.
