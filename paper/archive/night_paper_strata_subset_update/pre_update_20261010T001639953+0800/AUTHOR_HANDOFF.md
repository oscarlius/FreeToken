# Author handoff — Strata v0.1.41 subset update

## Scope completed

- `paper/src/body_v52.html`: only the C5 contribution row and §8 changed.
- `paper/FreeToken_MultiGPU_CoExec_v5.2.html`: regenerated from `src/build_v52.py` after that scoped source change.
- `paper/arxiv_night_20261009/`: English Markdown, TeX, claim/evidence map, README, and revision log now describe the same bounded evidence.

The update does not change the title, multi-GPU scope, §7.7 hybrid result, R045 rows, the serial 21–23 tok/s model, or D09/D10 prediction status. It adds no KTransformers or llama.cpp baseline. The independent-review files remain unchanged.

## Evidence binding

- Authoritative review: `strata/development/r002_v0141_night_execution_20261009/INDEPENDENT_RESULT_REVIEW_V3.json`, SHA-256 `9a3f29e877a1ad2fd462f867db514fcc48c8506237ff52a64fa3971c81392c58`.
- Preserved V2: SHA-256 `63eb2c0f7f4818cc3d3990c5a6d52ad67ce101d9f0dd9363c0c1c2b452e78e4a`. V3 corrects only its review-time placeholder and preserves V2 bytes and findings.
- Bound engine: `a1f4bc961395b8d347e3e73d48a35c372000006a42ca9c3ea8abd09fb46aa7a0` at Strata commit `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`.
- Status: `PARTIAL`. S1 is the valid no-MTP subset; fixed-256 is `not_met`; S2 made zero generation calls after its harness inspected the wrong log source. No MTP delta, product acceptance, hybrid causal claim, or multi-GPU result follows.

## File hashes after update

| File | SHA-256 |
| --- | --- |
| `paper/src/body_v52.html` | `932c3e2ac4830448738a91b8a9a7ad97f67919a7a62a3952d6075d94ff7fa01c` |
| `paper/FreeToken_MultiGPU_CoExec_v5.2.html` | `f4ee6c26ae4a2ab5fd79fa98ade6adfbf35a26e1f5e9f1fea56bd7ff75c71574` |
| `paper/arxiv_night_20261009/manuscript.md` | `0f6cc7e94837601e1e498a22470fab6c877c4ddfa9d35e6156932bba5641ceba` |
| `paper/arxiv_night_20261009/main.tex` | `5186f453737e329d7e874d586587f78fb949e0423157b676c7128341b9216ad4` |
| `paper/arxiv_night_20261009/CLAIM_EVIDENCE_MAP.md` | `c2ba1af9ab05789038b16ab72dc3315dc295d5dc3e4ba3b30cfbe91d1b0eb5f6` |
| `paper/arxiv_night_20261009/README.md` | `1d0dcdde88aa6c08528c88d6c223c3d71a7bf33c2b03cdc6128ea06438b2b09c` |
| `paper/arxiv_night_20261009/REVISION_LOG.md` | `254a7e681759d297d94c571ba573c6a2ed7bc2d515761ae938e8e0ebbb0e4f8b` |

## Verification boundary

`py .\\build_v52.py` regenerated the v5.2 HTML. A source/generated scope diff confirmed that every changed line is the C5 row or inside §8. The pre-update archive verifies 7/7 byte-for-byte against `ARCHIVE_MANIFEST.json` (manifest SHA-256 `9ca8d4f7f8e28b59ba448b91f78c6bb13fe84036c3a659c6c82b016f417a389b`).

The English sources are source-ready. `pdflatex` and `bibtex` are unavailable on this workstation PATH, so the PDF remains unbuilt and final rendering remains unverified. No GPU, model service, HTTP generation, compilation, installation, remote action, upload, or submission occurred.
