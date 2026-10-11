# Independent Strata subset review V2

Reviewed at **2026-10-10T00:28:07.956985+08:00** against the preserved pre-update archive and Independent Result Review V3 (`9a3f29e…2c58`). V2 supersedes V1 (`1fed4d30…9aaa`) after the recorded correction to the stale TeX limitations sentence. V1 is preserved.

## Verdict

**SOURCE_READY / PDF_UNBUILT.** The current English sources correctly state that S1 is a limited no-MTP measurement subset, that concurrency two queues one engine lane, that `ignore_eos=true,max_tokens=256` is `not_met`, that S2 has no generation measurement or MTP delta, and that the historical 52/60 observation is confounded provenance. No PDF was built or inspected, so this is not a publication or submission approval.

## Evidence

- Current `main.tex` is SHA-256 `90cfe5a6…f662`; the revision log is `2e83b50b…bb63`. The log records the root correction and V3 binding.
- `main.tex:204-210` and the matching Markdown/HTML text bind the S1 data to V3, including no-MTP admission, actual probe values, single-lane queueing, the 45/60 fixed-256 stops, and S2's pre-request harness failure.
- `main.tex:216` now says the valid boundary directly: limited S1 subset, fixed-256 not achieved, and no matched MTP on/off comparison. This resolves V1's identified contradiction.
- Source parsing found balanced TeX and BibTeX braces, valid nested environments, ten cited keys all present in the bibliography, and no `VERIFY BEFORE SUBMISSION` marker.
- Every seven-file difference is bound to the pre-update archive. The updated HTML/body each have 9 additions and 2 deletions; `main.tex` has 8 additions and 4 deletions; the English support files contain the corresponding bounded edits.

## PDF boundary

No PDF exists in the arXiv-night directory and none was rendered in this review. Build and visually inspect an authorized final PDF, bind its SHA-256, and review it separately before release.
