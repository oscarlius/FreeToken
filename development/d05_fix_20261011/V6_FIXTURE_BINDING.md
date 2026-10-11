# D05 v6 fixture binding for default-off regression

This is a preparation receipt for the post-GPU-window CPU run.

- Historical carrier: `development/d05_d09_tail_cpu_20261010/strict_scheduler_d05_pinned_v6.py`
- Carrier SHA-256: `aec28686989179bae8f3369aeb37044d8490e0bda94af41418b7eec3c61995d9`
- Historical final receipt SHA-256: `00cd49af9aa2eed62f649caf3e99ceb542f15d956ca29b64fd6a4903a65fece4`
- Target int32 carrier: `torch.arange(13555)`, little-endian raw byte SHA-256
  `1dd6711b108d018c3fee019657b98055cc667dc126e3aa53c7b13e2c5eae18b5`.
- Donor int32 carrier: the target prefix `[0,13377)`, SHA-256
  `74bca9854a36f022b5c7ec8b959c9f5acee39550aefad97ed7a39a79e33470a3`.
- Enabled split: UID 8, pre-forward `cached_len=13504`,
  `device_len=13554`; real `Scheduler._forward` calls real
  `Req.complete_one`, so finish observes 13554.
- Default-off donor split: pre-forward `cached_len=13375`,
  `device_len=13376`; real `Scheduler._forward` calls real
  `Req.complete_one`, preserving the original aligned finish at 13376.

The historical v6 receipt expressly labels these arrays as a permitted geometry
stand-in, not raw R052a token content. This implementation preserves that limit:
it binds all v6 geometry and source bytes, but makes no R052a content claim.
A true raw-content regression remains blocked unless a frozen R052a token array
and its source binding are supplied.
