# D03 phase-2 consumer commands and evidence gates

最新检查点（2026-10-04 14:40 CST）：T10 R017的72实际记录已复核封存，11实际token分叉；R013/b45/PID2977969已通过独立源码复核、Linux18PASS并实际启动，最新宿主机观察为2/22采集、1/11成对摘要，下一个新进程加载中。T04诊断传递修复已Linux26PASS/扩大447PASS（2原有FAIL、6SKIP），真实CPU边界构造10PASS，Y129预测archive12672；新候选默认GPU门及实际恢复尚待。D06独立本地树已开始客户端/服务端实现，离线检查及代码复核继续；未上传或过GPU门。历史观察保留为历史，以最新结果及快照为准。

This note prepares consumers of D03. It does not authorize or start a GPU run.

## Fixed D03 inputs

| item | value |
| --- | --- |
| candidate | `/data2/FreeToken/wt/e1r003st@c30ae0d7003c3bbbf56867ce74da797332fa7ed5` |
| parent | `/data2/FreeToken/wt/e2base@23f2e2caa3395837c9474735ffc83321f3b9b5a1` |
| prepared historical raw-ID manifest | `/data2/FreeToken/runs/dev_D03/historical_raw_ids_c30ae0d.json` |
| prepared manifest SHA-256 | `6a08e2e855acacab103eeb4ea0d07972f3e477506020783ec930dbca744fa1e2` |
| prepared T10 frontend manifest | `/data2/FreeToken/runs/dev_D03/t10_frontend_tokens_c30ae0d.json` |
| T10 frontend manifest SHA-256 | `bf1f38901055e79e0b4ae48615f4ce1f58a4efc02a31f88ff644d857c6bc0356` |
| historical trace | `/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json` |
| archived replay evidence | `/data2/_shared/runs/ft_rounds/E1-R003-stateeq/S_A_coldfirst.json` |

The prepared manifest is only valid when its `trace_sha256`, `messages_sha`,
`request_sha256`, `raw_ids_sha256`, and `input_length` agree with the D03
self-check. Do not reuse it for a different T10 round or a textual proxy.

The preflight-only self-check command is deliberately absent: `--run` is the
first operation that takes the GPU lock and creates its exclusive
`gpu_selfcheck_c30ae0d_urlfix` child beneath the already-existing
`/data2/FreeToken/runs/dev_D03`. This run has already been launched with PID
2291096 and has completed with independently checked evidence; the following command records its invocation and must not be rerun
against the existing output:

```bash
PY=/data2/FreeToken/venv/bin/python
$PY /data2/FreeToken/runs/dev_D03/d03_gpu_selfcheck.py --run \
  --raw-ids /data2/FreeToken/runs/dev_D03/historical_raw_ids_c30ae0d.json \
  --tail-k 64
```

It checks byte-identical `cold_eq` output for parent-off, candidate-off, and
candidate state+logits-on; records exactly the seven state boundaries
`448,4544,8640,12672,14144,18240,21504`; compares `archive/uid=1/12672` to the
new `boundary/uid=<actual request UID>/12672`; and compares two independent FP32-logits processes.
The actual UID is obtained from the terminal engine-token record and bound to
the owned service process group; it is not assumed to equal the historical UID.
It fails if the raw manifest, legacy replay binding, source commit, extension
fingerprints, port, GPU ownership, PID, or final stop proof differs.

The original `gpu_selfcheck_c30ae0d` failed before logits capture with HTTP
404 because the caller supplied `/v1` to a probe that adds `/v1/completions`.
Its output and manifest remain preserved. The replacement runner SHA-256 is
`4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453`.

The completed self-check manifest is
`4e8d18429ecaef5b8f856f73a4c913c1a08068f9f433acce73091a4cb27764c3`.
The assigned default-path T16 gate `E2-R002-gate-D03` completed batch 38,
passed independent review, and was sealed with the command below. Its
MANIFEST SHA is `2bc41220885af37386e0f365ef2fba3be97c39e96ec585b4a4cf9ed7dbd8526f`;
round SHA is `77bfb5d0cf57950fdbea4b02550a18fdc0acd5373affa17163257238e7cdfeb4`.
The completed close command is recorded for audit and must not be rerun:

```bash
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/dev_D03/d03_t16_close.py --batch 38 --close
```

This command requires the exact `review_batch38.json` PASS record inside the
open round and refuses an existing formal closure. It verifies every input
before writing and rolls back only its newly created files before sealing;
already sealed evidence is retained on a later validation failure. Five Linux
fault regressions using the real D04 tools passed before publication.

## Complete assigned consumer commands

The reviewed launcher and frozen helpers are present on the server. These
commands run sequentially only after the D03 self-check succeeds and the
assigned T16 gate is independently reviewed and closed. The launcher selects
the next batch number from the actual ledger, reserves it exclusively, checks
the prerequisite review hash and sealed manifest, and preserves all failures.
T04 E2-R014/batch39 exited at the restore arm: cache hit=21952,
restore_proof=null. Its failed raw artifacts are preserved. T11 E2-R011/batch40
is independently reviewed and sealed; finish-writeback classification remains
unresolved. T04 retry E2-R015 requires reviewed controlled history (competing
branch to L12672; recompute/legal direct fresh input), never the old warm-P
capture commands below. R012/batch41 failed before GPU loading because the
launch wrapper inherited CUDA_VISIBLE_DEVICES=''; its artifacts stay in place.
R016/batch42/PID2672941 failed after 12/72 records because the validator
rejected legitimate HTTP tool_calls endings mapped from engine stop. Its raw
evidence is preserved; it cannot be marked completed or closed as a successful
round. New R017 source/tests passed independent review and Linux28 tests;
the frozen launcher has already started batch44/PID2786369. T10
phase2 must consume actual successful sealed token evidence and derived forks;
the old R012/R016 commands remain history and must not be rerun.

R016's already-executed command (do not rerun against its existing RID):

```bash
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  /data2/FreeToken/runs/dev_D03/t10_retry_r016_ready/development/d03_t10_retry_launch.py --run
```

The R015 controlled retry is frozen and independently reviewed; Linux CPU20
passed. The following command has already launched batch43/PID2749339 after
confirming R016 exited and the shared lock/8095 were free. Do not rerun:

```bash
CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  /data2/FreeToken/runs/dev_D03/t04_retry_r015_71d4846/development/d03_t04_retry_launch.py --run
```

Its `diagnostic` boundary capture, `branch-bank` restore (exact cached/proof
length12672), and two direct `fresh` captures all consume the same frozen P+X.
The older `t04_retry_r015_ready` bundle predates the single-byte-buffer probe
load fix and is preserved but must not be executed.

R015 also failed at the controlled restore arm and is not a metadata preparation
or successful closure target. After R017 real completion and independent review,
prepare its initial metadata with the new independently reviewed, Linux55PASS,
read-only version. Do not use the old global or 6016 helper for R017.

```bash
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python \
  /data2/FreeToken/runs/dev_D03/phase2_close_r017_a52e39e/development/d03_phase2_prepare_r017.py \
  --prepare --round-dir /data2/_shared/runs/ft_rounds/E2-R017 --batch 44 \
  --review /data2/_shared/runs/ft_rounds/E2-R017/review_batch44.json
```

This only writes initial metadata after complete status, independent PASS,
source bindings and RUN_MANIFEST coverage; actual D04 closure remains separate.

The following original commands document earlier assignments. R014/R012 are
failed and not restart targets; R013's parent adapter needs actual successful
sealed token-parent identity before any GPU execution.

```bash
PY=/data2/FreeToken/venv/bin/python
LAUNCH=/data2/FreeToken/runs/dev_D03/d03_phase2_launch.py
$PY "$LAUNCH" --card T04 --run      # E2-R014: boundary, restore, recompute, legal
# R014 failed and is preserved; do not rerun.
$PY "$LAUNCH" --card T10-P1 --run   # E2-R012: 3 processes, 72 terminal records
# R012 and R016 failed and are preserved; R017 is under validation.
$PY "$LAUNCH" --card T10-P2 --run   # E2-R013: fresh pair per actual token fork
```

Each process receives its own `FT_DEV_LOGITS_DUMP=<arm>/logits`; the T04
boundary arm also receives `FT_DEV_STATE_DUMP=<arm>/state` and the seven
`FT_DEV_STATE_DUMP_AT` lengths. These variables are recorded in `SERVE_CMD.txt`.
T04 keeps the supplied G4 output tokens fixed across all arms and records
regenerated boundary output separately. T10 phase 2 uses actual engine IDs;
a zero-fork outcome is recorded before taking the GPU lock.

## T04 phase 2: state envelope and logits

T04 phase 2 consumes completed phase-1 dump arms. Substitute only the real,
closed phase-1 paths after their admission and output hashes are recorded:

```bash
PY=/data2/FreeToken/venv/bin/python
WT=/data2/FreeToken/wt/e1r003st
SOURCE=/data2/_shared/runs/ft_rounds/E2-R002
# OUT must be a newly allocated D03 phase-2 scratch/round path.  It is not a
# child of the sealed SOURCE round and must be created only by that runner.
OUT=/data2/FreeToken/runs/dev_D03/<allocated-phase2-output>

# Legal reorder envelope: R4096 reference versus R8192 test.  This is a
# template for the actual selected dump subpaths, and a measurement, not a verdict.
$PY "$WT/scripts/state_envelope.py" \
  --ref "$SOURCE/<R4096-dump>" --test "$SOURCE/<R8192-dump>" \
  --out "$OUT/R4096_vs_R8192_envelope.csv" --tier device

# Historical G4 boundary comparison is intentionally a separate kind/UID selection.
# The D03 self-check already emits the same command against its candidate_boundary arm.
# ACTUAL_UID must come from that arm's verified terminal-token binding, not a guess.
$PY "$WT/scripts/state_envelope.py" \
  --ref /data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_A \
  --test /data2/FreeToken/runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix/candidate_boundary/state \
  --out "$OUT/g4_envelope.csv" \
  --lengths 12672 --kind-ref archive --kind-test boundary \
  --uid-ref 1 --uid-test "$ACTUAL_UID" --tier device
```

`SOURCE` is sealed E2-R002 evidence: phase 2 must never add a CSV, log, or
other derived file beneath it. `state_envelope.py` rejects missing/extra selected records, roles, shapes,
dtypes, non-finite tensors, and ambiguous UID/prefix matches. It does not
silently intersect length sets. A legal-envelope command may add `--legal
<ref-dir>:<test-dir>` only for a separately admitted legal-reorder pair; do not
label a history-vs-boundary comparison as a legal envelope.

For logits, the service process, not the client, must receive
`FT_DEV_LOGITS_DUMP=<arm>/logits`. Every capture must use the same full raw-ID
sequence and same `K <= 64`; `logits_probe.py` verifies full input SHA, K,
input length, final positions, and FP32 vocabulary logits before comparison.
The restore capture must prove an actual restore:

```bash
# The three services must already be independently ready with slots 32/0/0:
# restore: FT_DEV_LOGITS_DUMP=$OUT/restore/logits
# recompute: FT_DEV_LOGITS_DUMP=$OUT/recompute/logits
# legal: FT_DEV_LOGITS_DUMP=$OUT/legal/logits
# Each arm uses its own prefix/tail JSON split from one verified manifest.
$PY "$WT/scripts/logits_probe.py" capture --base-url http://127.0.0.1:8095 \
  --model Qwen3.8-Flash-Next-NVFP4 --prefix <prefix-ids.json> --suffix <tail-ids.json> \
  --dump "$OUT/restore/logits" --require-restore
$PY "$WT/scripts/logits_probe.py" capture --base-url http://127.0.0.1:8095 \
  --model Qwen3.8-Flash-Next-NVFP4 --prefix <prefix-ids.json> --suffix <tail-ids.json> \
  --dump "$OUT/recompute/logits"
$PY "$WT/scripts/logits_probe.py" capture --base-url http://127.0.0.1:8095 \
  --model Qwen3.8-Flash-Next-NVFP4 --prefix <prefix-ids.json> --suffix <tail-ids.json> \
  --dump "$OUT/legal/logits"
$PY "$WT/scripts/logits_probe.py" compare --recompute "$OUT/recompute/logits" \
  --restore "$OUT/restore/logits" --legal "$OUT/legal/logits" --require-restore \
  > "$OUT/logits_compare.json"
```

The `restore_proof` must contain a valid host/device kind, positive source and
destination slots, matching UID, and positive length no greater than the
capture cached length. A slots=32 launch by itself is not restore evidence.

## T10 phase 2: required new input evidence

T10 phase 1 compares output `text`/`parts`. Its summary field
`first_token_proxy` is an `AutoTokenizer` index over completed UTF text. It is
not a model engine token index and cannot be used as `k`, a raw-ID position, or
a source for the preceding continuation IDs. The original trace also retains
messages/text/parts rather than the generated integer token IDs needed to form
`round-r prompt + common output-token prefix`.

Therefore phase 2 is blocked until the selected phase-1 divergence has an
immutable input record containing all of the following:

1. exact request payload/messages and canonical message SHA;
2. full raw prompt token IDs after the actual `ChatCompletionRequest ->
   chat_request_to_genspec -> TokenizeManager` frontend route;
3. generated integer token IDs up to the chosen divergence position, with the
   exact common prefix and K (`1..64`); and
4. per-arm input SHA, input length, UID, and process identity.

Once that record exists, run two fresh slots-0 services with
`FT_DEV_LOGITS_DUMP` set and invoke the two-process form:

```bash
$PY "$WT/scripts/logits_probe.py" capture --base-url http://127.0.0.1:8095 \
  --model Qwen3.8-Flash-Next-NVFP4 --prefix <phase2-prefix-ids.json> \
  --suffix <phase2-tail-ids.json> --dump "$D/B1/logits"
$PY "$WT/scripts/logits_probe.py" capture --base-url http://127.0.0.1:8095 \
  --model Qwen3.8-Flash-Next-NVFP4 --prefix <phase2-prefix-ids.json> \
  --suffix <phase2-tail-ids.json> --dump "$D/B2/logits"
$PY "$WT/scripts/logits_probe.py" compare --recompute "$D/B1/logits" \
  --peer "$D/B2/logits" > "$D/logits_peer_compare.json"
```

A non-bitwise result is evidence, not a transport failure. Preserve the
comparison JSON: it reports bitwise status, per-position top-1 agreement,
top-2 margins, KL, first bitwise input position, and first differing state
layer. Do not infer phase-2 input IDs by encoding `text`, concatenating
`parts`, or using `first_token_proxy`.
