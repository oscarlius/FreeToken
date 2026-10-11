# R045 v12 CPU readiness

Candidate `effb9969706922ddad9e59b96377e46469ebe97f`; window 98,304 and memory ratio .88 are retained.

The performance phase remains ordinary SSE with D0/trace/pause disabled.  The diagnostic phase enables D0/pause only for two-different-prompt timeline collection and H1.  SC3 stores parsed `#new-seq` lines and measured `k`; zero is valid.  SC5 binds D02 step/timeline/prefill SHA256 files and rejects missing two-UID decode coverage or incomplete per-layer copy/compute fields.

Linux CPU stage: `/data2/FreeToken/runs/dev_R045/r045_section14_v12_cpu_20261008_023838/report.json`, SHA `74e1ab12034bc02e83f8dfd7d15af294663176df7ae2cd13c4f246cb327965e2`; 67 tests passed under CPU guard. This is CPU-only: R040e is not measured, so no formal FILEdry, review signature, GPU service, request, or lock action is authorized.