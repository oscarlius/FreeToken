# D05 independent CPU review

**Verdict: REJECT / pre_gpu_failed.** This review records 0 services, 0 generation calls, and no budget debit. It does not alter R052a `not_met`/H-bug or its raw evidence. Written 2026-10-10T12:15:41.076815+08:00.

Target FT venv ran the five supplied tests with CUDA hidden: `5 passed in 0.15s`. That evidence is limited: the filedry receipt explicitly says `filedry_fake_child: true`, and the test generates synthetic donate/resume state bytes. It cannot prove the actual service, HTTP, or state-resume path.

1. **Original T11 path exceeds two calls.** The real retained replay executes trace rounds 0..7 before its follow-up (`retained_r052_t11_replay.py:129-161`). This runner sends only the final trace payload (`d05_t11_two_call_runner.py:267-286`). It therefore cannot retain both original request history and the two-call limit.
2. **UID provenance is absent.** `history_uid=8` is a historical label, while live UID comes from SSE. The runner then uses call-1 UID for both donor and cold state (`:286-291`), so it creates neither UID7 donor nor UID8 cold state.
3. **P=13504 gate is unreachable.** Candidate resume dumping occurs only after host-checkpoint restore (`candidate scheduler.py:793-814`); donate occurs at a commit (`cache.py:587-612`). A fresh service has no imported donor. The gate runs before call 2, so a valid donate/resume pair cannot arise.
4. **Lifecycle is not launch-safe.** Receipt omits child birth after Popen (`runner:241-250,304-312`); Effects has no D07 ownership/birth proof but reports `lock_released` (`:154-176,299-301`).
5. **No actual-state proof.** Synthetic dump/filedry cannot establish BD57 donor/cold P state or a same-kernel diagnostic.

Sources: manifest `70659ebfebf90f4054a3fd43bd51c6e99c382d218bee5f9127cfb62b6893e359`, filedry `0cb17986a9cdfeb6c3c33fc1cc32046b19183bf08f4cf3bceacca54e1af87997`, lifecycle `6c579e09369e0c8fe23b8e4b1d269fa9efeea16a916d86a232f1a5c69cb69258`. Full findings, exact source hashes, and line bindings are in the JSON companion.
