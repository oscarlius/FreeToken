# E2-R049b retry preparation — pending new user approval

Prepared on 2026-10-08 after `E2-R049a` batch 102 was sealed `failed_harness`.

- Candidate: `988c9e183c8dca4415fd9b5d02318b26664da619`; window `98304`; memory ratio `0.88`.
- b102 D04 closure: round `6b0fd937bb2095d734b8d74b66ffb01d508933052ea40af221a95238e4f87337`, MANIFEST `34e1f6b58139fda67504b9a35921fd50592af79e24691314c2644aaecdaa2191`, pin `d8ac8d5c9815672c1a53f4ab90442f75f2e1519e27cc61a493e16ae1e4b89399`, receipt `dae049b141af5b22ac3987a0e265828cda1d121f114e504cfbbec9dbd5113af4`, independent R retention review `e8759ebd95d6a444b37c553271e01a2029fe84c1881be3d9f99710da48a81e1a`.
- The sealed closure has zero accepted full groups. L1's four preserved workloads are partial raw only, so E2-R049b requires a fresh full nine-service measurement.
- v10 source stage: `/data2/FreeToken/runs/dev_T21/r049b_v10_cpu_20261008_0500/source/r049_t21_ordinary_prepare_v10.py`, SHA `d00fc6f29028586361e2556f5ebd7ba128ed9bc1354ae0ab83818edc6daf7b0b`.
- CPU evidence: local `41 passed, 5 skipped`; Linux `46 passed` with CVD empty and the CPU guard.
- Same-entry FILEdry: `/data2/_shared/runs/ft_rounds/.filedry_E2-R049b_v10_sourceclosure_r1/dry_run_receipt.json`, SHA `c332794a0f159bfd798cec481e324b6f4b76979787d53565293735defe2d9f80`, sealed 444/555. It created no formal RID directory, service, request, GPU lock, or batch.

Remaining gates: an independent R startup review and pin that bind this v10 source and FILEdry receipt, followed by a new explicit user approval. This note grants neither approval nor permission to launch E2-R049b.
