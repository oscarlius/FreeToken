# D15 window A/B independent terminal review

**Verdict: `not_met`** — the W128K cold request fit the 131072-token window (`129024 + 256`) but the model service raised CUDA OOM while only 63.69 MiB was free and 80 MiB was requested. This is a product capacity outcome.

- Original W98 run remains byte-preserved as `failed_harness` after A8; recovery receipt binds its cleanup.
- Resume supplied W128 A8 with all payload/input-ID/native-token/completion identities equal to W98, then B09–B12 at 100223/100353/100493/100617 tokens.
- Actual cache auto slots: W98K 2700; W128K 2400. A-only pooled network decode: 28.0448739773 vs 26.8667483125 tok/s, a 4.2008591862% decline.
- Combined accounting: exactly 2 services, 21 calls dispatched, 20 completed. The uncompleted cold call has no TTFT or decode claim.
- At cleanup time, the W128 owned group was dead, private ports were free, GPU was idle, and stop errors were empty. Post-restore GPU/lock state is excluded.

Raw inventory and all evidence hashes are bound in the adjacent JSON.
