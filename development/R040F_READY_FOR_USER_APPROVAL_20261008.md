# E2-R040f D16 remaining-14: ready for user approval

Status: **independent source and startup review passed; GPU execution remains unapproved.**

R040f is the bounded continuation after the closed `E2-R040e` `failed_harness` round. It schedules only the missing 14 D16 scopes: parking (4), cache (4), and interleave (6). It does not rerun slots4. The retained R040e slots4 evidence is a sealed prerequisite only; it is not represented as an accepted measurement.

## Bound scope and predecessors

- Candidate/worktree: `0aa23431e5b800797543bdecbf35a01045131d7d`, `/data2/FreeToken/wt/e2base1-ordinary-rewind`.
- Measurement configuration remains the D16 card configuration: window `98,304`, ratio `.88`; R040f is limited to the 14 scopes above.
- R040e closed D04 metadata: `round.json` SHA `7b34f0f319e78c1032cebaab3bfde930cb5ecbbb210cf8a8c636dc9b2afeb617`; `MANIFEST.sha256` SHA `ede21cc9c1c1c5c87eb1bca9c14d23570d35c3619adf45d5eb850d81b4e83e08`.
- R040e independent D04 review: `/data2/FreeToken/runs/dev_D16/reviews/E2-R040e_failed_harness_review_v1/review.json`, SHA `1928ac64c8bee653b0c8e290cc1dcf4bdc91c7b03adb12d552ac1857d25a98c1`.
- Retained nine-scope slots4 envelope: `/data2/FreeToken/runs/dev_D16/reviews/E2-R040e_slots4_batch_envelope_report_v1/review.json`, SHA `d770279fcfbfe913e31b2c7d88c1d437dd3999c67492a591d6047abbb8bbebcd`.

## Reviewed source and CPU evidence

- Final reviewed archive: `/data2/FreeToken/runs/dev_D16/R040f_collector_source_review_v7/source_archive`, manifest SHA `55cd9f260b55fa46eba32405672dcec713e050df8da4bc4d95dd8db4dc9846c1`, directories 0555 and files 0444.
- Source review: `/data2/FreeToken/runs/dev_D16/R040f_collector_source_review_v7/review.json`, SHA `c388e6bce0fb7e56b4d3bb5fbfeba3f06e27c79c0bba7564878f81663fe13c0e`; its strict v2 contract binds 18 semantic execution roles and the full archive inventory while preserving `model_admitted=false` and `startup_admitted=false`.
- CPU stage: `/data2/FreeToken/runs/dev_D16/r040f_v6_consumer_cpu_20261008_070607`, `45 PASS` with `CUDA_VISIBLE_DEVICES=''` and the actual CPU guard first on `PYTHONPATH`.
  - `cpu_report.json`: SHA `0f580b2c7f703c0098385dedc48fa220ff301316025217d864277f347bbe5c22`.
  - `pytest.log`: SHA `d56f68985db476a0340e48c90e7735424749889502a768730d304f1b002b6401`.
  - Stage source manifest: SHA `72777d04fb590aab56785484fa102a9859be6d76d6512e067fe9cb0cc9613a98`.

## Same-entry FILEdry

The archived entry was run as user `dell` from its required working directory `/data2/FreeToken`:

```bash
cd /data2/FreeToken
CUDA_VISIBLE_DEVICES='' \
PYTHONPATH=/data2/FreeToken/runs/dev_R046/r046b_section12_source_v4/cpu_guard \
/data2/FreeToken/venv/bin/python \
  /data2/FreeToken/runs/dev_D16/R040f_collector_source_review_v7/source_archive/r040f_d16_remaining_prepare_v6.py \
  --dry-run --after-round E2-R040e \
  --dry-run-dir /data2/_shared/runs/ft_rounds/.dryrun_r040f_v7_20261008_0714 \
  --collector-review /data2/FreeToken/runs/dev_D16/R040f_collector_source_review_v7/review.json \
  --collector-review-sha256 c388e6bce0fb7e56b4d3bb5fbfeba3f06e27c79c0bba7564878f81663fe13c0e \
  --anchor-seed-sha256 e923320b23537a59c6e001717af24bcf2f164ff08cf74cf301183cb49f0ad04f
```

- Receipt: `/data2/_shared/runs/ft_rounds/.dryrun_r040f_v7_20261008_0714/dry_run_receipt.json`, SHA `3a47fb08b5cfc95cc38e001f6220cb2742e87be7120507ad6d97f84b95fcad01`, directory 0555/file 0444.
- The archived entry's own `require_dry_run_receipt()` was re-run from `/data2/FreeToken` and passed.
- Receipt scope is `14 = parking 4 + cache 4 + interleave 6`; it records `service_started=false`, `requests_sent=false`, `gpu_lock_taken=false`, `batch_allocated=false`, and `formal_rid_directory_created=false`.

## Independent startup review

- Review: `/data2/FreeToken/runs/dev_D16/R040f_startup_review_v1/review.json`, SHA `ed796a580b976510442fe368353ea88c39ae21303634189d999ddf83778be6d6`.
- Pin: `/data2/FreeToken/runs/dev_D16/R040f_startup_review_v1/pin.json`, SHA `c441bd5ecefb15ff707bc21c9c3844895c6a3ae34e42fb6c4559960b14211655`.
- The review binds the final receipt and records `model_admitted=false` and `startup_admitted=false`; it is an execution-readiness decision, not a measurement result.

## Approval boundary

A GPU retry for exactly `E2-R040f` is required before any lock acquisition, service start, or formal round. No such approval or execution is included in this package.
