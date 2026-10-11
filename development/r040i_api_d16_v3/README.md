# R040i D16 SDK API execution adapter v3

This root-operated adapter is limited to the authorized six interleave services
and eight `/v1/completions` SDK calls. `--filedry` writes a development plan,
the same per-service environment and `SERVE_CMD` prepaths, and an immutable
source copy; it does not create a formal RID, reserve a batch, take the GPU
lock, start a process, or send a request.

`--run` requires a root D04 admission pin that binds the actual FILEdry digest
and an independent review. The review schema is
`ft_r040i_api_independent_review/v1` and must bind this RID, candidate, exact
source manifest/source hashes and `{services: 6, calls: 8, warm: deferred...}`.
It then reuses the pinned D07 lifecycle reserve,
receipt publication, child-receipt validation, lock and exact owned-PGID stop.
The formal output root is `/data2/_shared/runs/ft_rounds/E2-R040i-api-D16`.
It leaves D04 sealing to the root workflow. Results are SDK API behavior under
the approved text mapping and do not prove native token input, cache hits or
physical batching.

v3 removes the controller-only `os.chdir(WT)` from v2. The root D04 admission
therefore binds the inherited canonical controller/child cwd; each service
still uses `cwd=WT` in its own `Popen` call.
