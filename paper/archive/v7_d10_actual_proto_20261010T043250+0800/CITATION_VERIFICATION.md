# Citation verification ledger

Verified: 2026-10-09 (Asia/Shanghai). Each entry below was checked against its primary paper, official documentation, or upstream GitHub repository. The bibliography intentionally asserts no DOI and no repository version beyond the local experimental commit already named in the manuscript.

| BibTeX key | Primary source verified | Metadata checked | Access date |
| --- | --- | --- | --- |
| `freetoken` | https://arxiv.org/abs/2608.16157 | title, author list, year, arXiv identifier | 2026-10-09 |
| `layeredprefill` | https://arxiv.org/abs/2510.08055 | title, author list, year, arXiv identifier | 2026-10-09 |
| `flexgen` | https://arxiv.org/abs/2303.06865 | title, lead authors, year, arXiv identifier | 2026-10-09 |
| `moelightning` | https://arxiv.org/abs/2411.11217 | title, author list, year, arXiv identifier | 2026-10-09 |
| `moeinfinity` | https://arxiv.org/abs/2401.14361 | title, author list, year, arXiv identifier | 2026-10-09 |
| `hybrid` | https://arxiv.org/abs/2606.10493 | title, author list, year, arXiv identifier | 2026-10-09 |
| `strata` | https://github.com/Niko1221/Strata | repository owner, repository name, project description | 2026-10-09 |
| `vllmrepro` | https://docs.vllm.ai/en/stable/usage/reproducibility/ | official page title and reproducibility guidance | 2026-10-09 |
| `vllmbatch` | https://docs.vllm.ai/en/latest/features/batch_invariance/ | official page title and batch-invariance scope | 2026-10-09 |
| `sglang` | https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/deterministic_inference.mdx | official page title and deterministic-inference scope | 2026-10-09 |

## Upstream MTP source check

The proposed Strata S1/S2 control is not reported as a result. The upstream repository documents MTP as an opt-in path using `--mtp` together with `--spec`; it also states that `--batch-mtp` is opt-in. Source: https://github.com/Niko1221/Strata/blob/main/docs/BATCHING.md, accessed 2026-10-09. This confirms only the upstream option surface; it does not validate the local v0.1.41 S1/S2 experiment, its argv, or any GPU result.

## Submission-time re-check

Before submitting, re-open every URL above and update this ledger if an entry is moved, withdrawn, or superseded. Re-checking bibliographic metadata does not change the evidence labels of D09, D10, R067d, Strata S1/S2, or the multi-GPU design.
