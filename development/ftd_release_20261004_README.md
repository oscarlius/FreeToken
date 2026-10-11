# FTD-20261004-1 release preparation

`ftd_release_20261004.py` reads the sealed canonical round directories and
generates a review record plus a local release-manifest proposal. It never
copies raw logs, tensors, or JSON payloads. The review includes source hashes
for each `round.json` and `MANIFEST.sha256`, the D04 writer `check` result, and
the current formal verdict.

For a no-file-write remote review, use `--out -`; it writes the review JSON to
standard output only.

Prepare on the server in read-only mode (no GPU):

```bash
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python development/ftd_release_20261004.py \
  --mode prepare --rounds-root /data2/_shared/runs/ft_rounds \
  --writer /data2/FreeToken/scripts/round_json_append.py \
  --out /data2/FreeToken/runs/review/ftd-20261004-1-review.json \
  --release-out /data2/FreeToken/runs/review/FTD-20261004-1.manifest.proposal.json
```

`review` fails closed if a target directory is missing, the existing D04 writer
rejects its history, evidence is absent, an old verdict is neither
`pending_review` nor the expected value, or a prefix-hit/T04/T11 attribution
conclusion lacks a `hypothesis` status. `failed_harness` is not invented here:
the installed D04 writer explicitly allowlists it, and the prepared records use
the retained `status_batch*.json` evidence from the round itself. Failed-round
entries also carry a path and SHA-256 for their local result document; this adds
release traceability without changing the immutable D04 history.

Only after an independent mainline review may the same script run `apply`. It
requires the literal confirmation token, calls the installed D04 writer once
per outstanding verdict, then creates the server `manifest.json` without
overwriting an existing release, changes the manifest and release directory to
read-only, and copies its bytes to the specified local destination. It compares
both files byte-for-byte before returning success. The server directory must be
the new canonical `<rounds-root>/../ft_releases/FTD-20261004-1` directory; the
local copy and result output must be distinct new files outside it. The release
records the identity and SHA-256 of `FTD-20261003-1`, a complete observed
code-version/commit inventory, and only emits fields from bytes revalidated
after the final D04 review.

```bash
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python development/ftd_release_20261004.py \
  --mode apply --confirm-apply FTD-20261004-1 \
  --rounds-root /data2/_shared/runs/ft_rounds --writer /data2/FreeToken/scripts/round_json_append.py \
  --out /data2/FreeToken/runs/review/ftd-20261004-1-apply.json \
  --server-release-dir /data2/_shared/runs/ft_releases/FTD-20261004-1 \
  --local-release-copy plan/data_releases/FTD-20261004-1.json
```

The script deliberately has no paper-writing behavior. The data manifest names
paper v4.1 as the downstream owner action; the mainline owner updates paper
artifacts separately. Its release-only overlays preserve source artifacts while
marking affected prefix-hit continuation and multi-round 60-question scientific
quality claims as `hypothesis`: the E2-base layer-major prefix-hit path causes
actual FLA/GDN/PLE state corruption when its remaining extension triggers
layer-major chunking, and the wrong-donor snapshot plus cached first-subchunk
new-request defects are separate confirmed issues. No candidate repair is
represented as GPU-verified or accepted.
