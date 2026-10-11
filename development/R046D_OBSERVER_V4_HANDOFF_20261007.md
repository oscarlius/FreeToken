# R046d observer v4 CPU handoff

R046c failed before its first request because `service_files` created the
ordinary observer directory and v3 required it not to exist. R046d uses new,
separate sources only:

- `r046c_t06_ordinary_startup_v4.py`: accepts a service-created directory only
  when it is empty, nonsymlinked, and writable. Input, token, input-ID, and
  shutdown receipts remain exclusive. A second `flush()` is locally idempotent;
  an existing shutdown receipt before the first flush is an error.
- `r046c_ordinary_memory_startup_v2.py`: composes the new observer with the
  existing memory observer.
- `r046d_d07_t06_prepare.py`: RID `E2-R046d`, v4/v2 source references, new
  review directory. It remains a fail-closed preparation entry; no FILEDRY,
  batch, GPU lock, service, or formal directory was started.

Linux CPU source capsule:
`/data2/FreeToken/runs/dev_R046d/r046d_entry_cpu_20261007_1820_v2`

- `pytest.log`: 33 passed under `CUDA_VISIBLE_DEVICES=''` and a
  `sitecustomize` guard that rejects socket `connect` and `listen`.
- `packet_native.log`: actual R046d packet binds candidate
  `151ee718b88882b57dba75317bb53c697d5f235f`; both native extensions import
  from the candidate worktree and bind the existing R059 provenance record.
- readonly `source_manifest.json` SHA
  `b126033df6fdb1c4a0cf7a5e1c582c72ae93b469493cc689e98ecd6bcbb1d20a`.
- readonly `report.json` SHA
  `1da6588972183acbdf8bde91a4f0de00ab944d9309ecd455ef059056d1de3c23`.

The earlier observer-only capsule remains readonly evidence; the v2 entry
capsule supersedes it for full entry validation. R046c closure and any failed
round artifacts were not modified.
