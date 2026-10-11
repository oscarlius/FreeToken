# FTD-20261004-1 immutable erratum

`ftd_release_erratum_20261004.py` creates `FTD-20261004-1-erratum-1` as a new
immutable document. It verifies the read-only base manifest, its exact SHA-256,
the cited relative source documents, and that `E2-R009` is the actual
release-contained 60-question/multi-turn evidence. It changes no base manifest,
round record, raw artifact, or paper.

The erratum marks only these release-level claims as `hypothesis`:

- `E2-R006` and `E2-R017`: `prefix_hit_continuation_output` and
  `cold_versus_warm_output`.
- `E2-R008`, `E2-R009`, and `E2-R009-p64k`: `warm_replay_output_text`.
- `E2-R009`: `multi_round_60_quality`.

Cold timing/output claims and raw artifacts stay sealed in FTD-20261004-1. The
document records the confirmed E2-base layer-major state corruption and states
that the D14 candidate has no accepted GPU runtime evidence.

Run the CPU-only tests:

```bash
python development/test_ftd_release_erratum_20261004.py
```

Create a review proposal only (the output must be a new file):

```bash
python development/ftd_release_erratum_20261004.py \
  --mode prepare \
  --base-manifest plan/data_releases/FTD-20261004-1.json \
  --repo-root . \
  --out plan/data_releases/FTD-20261004-1-erratum-1.proposal.json
```

After independent review, create the immutable server/local pair. `--repo-root`
must contain the cited source references at their recorded relative paths.
The server directory must be exactly the sibling of the sealed base release
named `FTD-20261004-1-erratum-1`; existing paths, symlinks, writable bases, and
destination races fail closed.

```bash
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python development/ftd_release_erratum_20261004.py \
  --mode apply --confirm-apply FTD-20261004-1-erratum-1 \
  --base-manifest /data2/_shared/runs/ft_releases/FTD-20261004-1/manifest.json \
  --repo-root /data2/FreeToken/runs/dev_P0/release_erratum_stage \
  --server-erratum-dir /data2/_shared/runs/ft_releases/FTD-20261004-1-erratum-1 \
  --local-erratum-copy /data2/FreeToken/runs/dev_P0/release_erratum_stage/FTD-20261004-1-erratum-1.json \
  --out /data2/FreeToken/runs/dev_P0/release_erratum_stage/FTD-20261004-1-erratum-1.apply.json
```

The command compares the server and local erratum bytes before setting both
documents and the server directory read-only. It never uses `replace()`.
