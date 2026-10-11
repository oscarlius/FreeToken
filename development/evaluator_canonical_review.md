# Canonical evaluator c1 review (read-only, 2026-10-04)

## Scope and result

This review read the local evaluator, SSH alias `9` evaluator, frozen regrade
artifacts, and the three historical answer JSONL files.  It did not modify an
evaluator, a server round, a release, a GPU process, a lock, or a source tree.

The c1 premise that the **currently deployed** `250e197f` evaluator produces
`38/60` whereas local `39f10fa8` produces `47/60` is not reproduced.  With the
same E0 raw answer file and the pinned 60-question corpus, both evaluators
produce `47 PASS, 11 TRUNCATED, 2 ANSWER_FAIL`; no per-question status changes
occur.  Therefore `39f10fa8` is a reasonable canonical *candidate*, but its
selection cannot be justified as the cause of the historical 38-to-47 score
change.  A separate older, unpinned evaluator/runner must have produced the
raw `passed=38` fields.

## Exact evaluator comparison

| copy | SHA-256 | bytes | role |
|---|---|---:|---|
| SSH9 `/data2/_shared/evaluator.py` | `250e197f1c09716ae399d491537c396e3ba47706b7d289b6b95220b5a30f4a71` | 14,931 | current server copy |
| local `_shared/evaluator.py` | `39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330` | 15,964 | newer candidate |
| frozen `E2-R009-regrade/source/evaluator.py` | `39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330` | 15,964 | existing pinned regrade input |

The complete `250e197f -> 39f10fa8` functional diff is limited to two branches
of `grade_question`.

1. `chinese_extraction`: 39f accepts `expected_entities` when `expected` is
   absent; accepts an expected list as well as a dict; converts scalar values
   to strings before normalization; supports integer/float expected values;
   and returns `EVALUATOR_ERROR` for an empty/unsupported expected collection.
   The server version assumes a dict and indexes only its values.
2. `code_autotest`: 39f accepts `function_name` as an entry-point alias and
   converts `test_cases` into assertion text when `test_code` is absent.  The
   server version uses only `entry_point` and `q['test_code']`.

Those changes are sensible schema-completeness fixes and fail more explicitly.
They do **not** change the current corpus outcome: the frozen corpus SHA below
has executable `test_code` for all 15 code questions (and no `test_cases`), and all 15 extraction questions use dict `expected` (and no `expected_entities`).  It is therefore compatible with both implementations.

### Reproduction of the evaluator-only comparison

On SSH9, CPU-only `/data2/FreeToken/venv/bin/python` loaded both evaluator
source files as in-memory modules, then called `grade_question(question,
response, finish_reason)` for each of the 60 E0 raw records.  It did not write
an output file.

| evaluator | PASS | TRUNCATED | ANSWER_FAIL | status changes vs other |
|---|---:|---:|---:|---:|
| `250e197f…` | 47 | 11 | 2 | 0 |
| `39f10fa8…` | 47 | 11 | 2 | 0 |

This is the critical stop condition: do not describe a 63.33-to-78.33 change
as a difference between these two exact evaluator bytes.  The historical raw
`passed=38` was produced by the historical inline `benchmark_client.py`
`grade_response` path, whose exact executed byte SHA has not been retained.

## Historical answer protocol and evidence

All original quality files are JSON Lines with 60 records.  Their fields are:
`question_id`, `category`, `response`, `thinking`, `finish_reason`, `passed`,
`detail`, `content_tokens`, `thinking_tokens`, `in_tokens`, `latency_s`,
`model_id`, `ttft_content_s`, and `ttft_thought_s`.  They do not contain an
evaluator SHA or an evaluator `status`; their original status must therefore
be treated as unpinned historical metadata.

The frozen corpus is
`/data2/_shared/runs/ft_rounds/E2-R009-regrade/source/test_prompts_60.json`,
SHA-256 `bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad`.
It has 60 unique IDs and defines question category, expected data and code
test contract.  The exact source regrader validates all of: 60 unique IDs,
ID-set equality with the corpus, category equality, string `response` and
`thinking`, terminal `finish_reason` in `{stop,length}`, bool historical
`passed`, and code `test_code` or `test_cases`.

| logical set | historical input | input SHA-256 | raw historical PASS | pinned-39f output SHA-256 | pinned PASS |
|---|---|---|---:|---|---:|
| E0-R000 | `_e0/paper_headroom_20261003/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl` | `355398ab3f88e261afb0ad8b728b9fcd9851b41468b5a48cea8b8f73124f8233` | 38 | `55524848ad13d8e7b0ebc55393e1f937ec292ea7f9ae03ef959ad752ec2c55a5` | 47 |
| E2-R004 | `E2-R004/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl` | `8ca169dba9ec3b38e6d103e7d5e2cfbf093256def6dae3abd1d5b127f297031b` | 38 | `69226c1e9cee98d579efd16f0b311377e638aa7ac51135ff04fa0c12c02909c4` | 47 |
| E2-R009 | `E2-R009/P1/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl` | `2d0f2b5960ab3680884d0da0d2285648e5c1f7072d51d6f091ed980bc7d24adc` | 38 | `dd66f3d0ad5f32a1638c70bf92f37063e8087dc181ebf0e24849bc2cf6a8e5e6` | 47 |

`E2-R009-regrade/source/regrade.py` is the existing CPU-only pinned regrader
(SHA-256 `16459f18e415742197735c50915162cc866b54978cb7dfe5db43ece43a4444f7`).
Its `quality_summary.json` SHA-256 is
`52d82fe4f4e69518b7f3e0860b4bbd187e0de3bbf422c8400897d77388aff61f`.
For every set it records 47/60 with changed IDs:

`extract_07`, `code_02`, `code_06`, `code_08`, `code_09`, `code_11`,
`code_15`, `long_01`, `long_07`.

The E0 versus R004/R009 raw files have identical ID sets and historical verdicts.
R004 and R009 response and thinking are exactly equal for all 60 questions.
E0 differs from them in response for only `code_04`, `code_10`, `code_14` and
in thinking for seven records, while the pinned regrader reports all 60
regraded statuses identical across E0, R004 and R009.  This supports the
statement that the observed score difference is evaluation metadata rather
than a model-quality regression, but it does not identify the older evaluator
that generated `passed=38`.

## Existing canonicalization lane (read-only cross-check)

`development/quality_regrade_20261004/` is an existing external writer lane and
was not changed by this review.  Its `inventory.py`, `regrade.py`, `stage.py`,
`measure_receipt.json`, and archived `evaluator_previous_250e197f.py` implement
the same three-input pinned replay.  The lane records the local 39f evaluator,
the corpus hash, the three raw input hashes, per-record response/thinking/hash
provenance, and a CPU-only receipt.  Its archived prior client explicitly has
an inline `grade_response`, confirming that a bare available evaluator SHA does
not prove which historical judge produced `passed=38`.

The existing lane should be used as the implementation source for any authorized
sync/new analysis round; this review adds the independent 250-vs-39 exact replay
that rules out treating their byte difference as the score explanation.

## Recommended canonicalization and next analysis round

1. Select `39f10fa8…` only after recording the above limited semantic basis:
   it improves corpus-schema support; it is not an experimentally demonstrated
   score change relative to `250e197f…` for this corpus.
2. Before synchronizing server bytes, preserve `250e197f…` and create a
   rule record containing canonical evaluator SHA, corpus SHA, regrader SHA,
   Python executable/version, and a statement that old unpinned scores are
   incomparable.  A byte-for-byte copy must be verified by SHA after the
   authorized sync.
3. For a new, append-only CPU analysis round, use the existing regrader pattern
   but assign a new round ID/batch first.  Copy the canonical evaluator and
   corpus to that analysis round; refuse changed/symlinked input bytes; retain
   `original_record_sha256`, `response_sha256`, `thinking_sha256`,
   `question_sha256`, `evaluator_sha256`, status and detail per question;
   write no historical file in place.
4. Publish `47/60` only as the result of the explicit pinned regrade artifact
   above.  Preserve original `38/60` as its recorded unpinned historical
   verdict.  Do not claim the 39f-vs-250 diff itself explains it unless the
   actual old evaluator source and its SHA are recovered and replayed.

## Validation performed

- SHA-256 read-only checks on local, SSH9, frozen evaluator/corpus/regrader,
  all three original JSONL files, and all three existing pinned output JSONL
  files.
- Read-only structural diff of SSH9 `250e197f…` against local `39f10fa8…`.
- CPU-only in-memory 60-record replay of both exact evaluators on SSH9 against
  the E0 raw input and frozen corpus; no output written.
- Read-only parsing of all original and pinned JSONL files, including ID-set,
  field-schema, count, status and cross-set equality checks.

No GPU was started or contacted.
