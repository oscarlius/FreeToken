# T04 / S-007 remaining evidence — bounded read-only inventory

Scope: round, manifest, history, review, and existing analysis-receipt metadata
only.  No raw tensor/logit reread, hash sweep, reader/tool change, GPU, service,
lock, or verdict mutation.  The parent-completed D03v2 four-group cross-arm
`max_abs` recomputation is outside this inventory and was not repeated.

## Facts

| Question | Metadata evidence | Result |
|---|---|---|
| Why is E2-R002 canonical verdict still pending? | `round.json` is sealed `444`, directory `555`; `verdict=pending_review`, `verdict_history=[]`. `review_batch30.json` is sealed and says PASS, but its own gap says relative-L2/logits await D03. | The independent review (`f0f428…1cdc3`) did not change the formal round verdict. |
| Is there a later D04 closure/pin? | `MANIFEST.sha256` exists sealed; exact closed-pin path `/data2/FreeToken/runs/plan_batches/closed_round_pins/E2-R002.json` is absent. The round has no `round_json_append.py`/history checker and no history entries. | No later D04 closure/pin is present in the checked canonical locations. Do not infer closure from the review PASS. |
| Can historical B (`UID 12`) map to R4096 (`UID 11`) by exact input IDs? | R002 `replay_validation.json` binds R4096 to 12 list-index `messages_sha` values, while the historical-B metadata inspected here has no cross-process UID-to-input-ID-SHA table. Existing S-007 records the `12 != 11` failure. | Not proven. Length and the 16-hex message digests are insufficient for the requested UID/input-ID-SHA mapping. |
| Do the four R036/R038 cold/reference pairs have an independent 128-output-ID/fulltext-diff result? | The sealed `S007_four_groups_20261007/analysis_receipt.json` records four input-ID SHA matches, UID 0, and state-envelope CSVs only (74 state points/case). It explicitly says cross-arm max_abs and logits unavailable. | No independent 128-output-ID or fulltext-diff result is registered; no logits capture is registered. |

The four existing exact input bindings are: R036/8192 `a14480…af4fc`,
R036/12416 `b28cdc…66b7d`, R038/12736 `b08abc…d825f`, and R038/18944
`db9b68…6983d`.  They prove the four state-envelope input pairs, not output-ID
or text equality.

## Next boundary

Autonomous CPU-only work can consume an already sealed, explicit B↔R4096
UID-to-full-input-ID-SHA crosswalk and an already registered output-ID/fulltext
comparison receipt. Neither exists in the reviewed metadata. Producing those
comparisons from raw artifacts would require a separately authorized reader and
scope; producing missing logits requires new capture data and therefore a
separately approved GPU round. This inventory leaves E2-R002 and S-007 verdicts
unchanged.
