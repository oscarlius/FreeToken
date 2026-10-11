# R052a independent actual terminal review

**Verdict: NOT_MET.** The completed R052a measurement is source-classified **H-bug**: the follow-up returned `cached_tokens=13,376`, below the runner’s `threshold_64=13,504` by 128 tokens. The raw record’s `pending_review` / `measured` status is therefore not product success, and this independent terminal review sets `product_acceptance: false`.

The evidence binds to `r052_t11_followup_prepare.py` SHA-256 `41302fce1ed404a5d83a55e3554781254e3a835d304325f6aeeda43b25d9cfd4` and reviewed-v8 SHA-256 `82c8243f1d54a024fe9f2d8bc5618e49d3c081c2fcb0af6d9375f3007f1734cd`. The actual result has SHA-256 `14df3c9a04451015bc057a9cc4dad8824678beb9b8665ca88837ecb06982b3cd`; it binds eight replay artifacts and one follow-up artifact (`ca74b64fa510fe047443b2833e83c7366d970b4d1f0736ca9b73a742e42e8082`).

D0 reports GPU decode, 71,280 layer calls, `missing_per_layer=3.5920454545`, `miss_rate=0.3592045455`, and zero fetch rate. The worker shutdown receipt is complete with no error. Owned cleanup SHA-256 `f2da9d5d38064238de71f4d471463689da32ecbf580b03a535abfb1fe7d88bb7` records `lock_released: true`; the R052 child, server owner, and worker PIDs are absent afterward.

R044 began only after watcher v2 bound and observed that cleanup. Its driver receipt records the identical predecessor-cleanup hash, so its active GPU work is a later authorized round and does not invalidate R052a cleanup. This review does not evaluate R044.
