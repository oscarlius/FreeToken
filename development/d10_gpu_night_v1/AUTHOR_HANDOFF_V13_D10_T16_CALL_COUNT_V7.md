# D10 T16 leaf call-count correction v7

`d10_owned_launch_v7.py` is a new immutable controller copy. It preserves the frozen T16 body (`t16_private_port_dryrun_r062_v1.py` SHA-256 `22ed68905b64a19c75251bf7be9d9ac9ebfd5464e4565ab2c757cd8dbea2f1d1`) and the v3 runner unchanged.

The scope approval moved to `*_user_scope_approval_v3.json`, and requires `planned_generation_calls: 100`. The matching real-path dry-run and startup review paths are also v3. Existing v2 paths and all D09 sources/receipts were left untouched.

CPU FILEdry receipt: `LINUX_CPU_FILEDRY_RECEIPT_V7_T16.json`, SHA-256 `f3ae380a3c58c59925819e6c245addb4dd4cf60dce58f799ddad753ceb905182`.

- Four layer-major arms: ready 1 + one cold case + tax (single and multi, five each) = 12 per arm, 48 total.
- Four non-layer-major arms: ready 1 + short and chunked cold cases + the same tax = 13 per arm, 52 total.
- Total: 100 generation calls across eight services.

The remote CPU-only receipt proves no GPU lock, service, HTTP request, or formal round was created. It does not constitute public `--dry-run`, an independent startup review, a v3 scope approval, or a real T16 execution.
