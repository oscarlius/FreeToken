# R067b T17 startup async-API tooling patch

Current result: **E2-R067b / batch134 failed_harness**, one service, zero
generation calls, zero comparable cells. The new controller copy loop reused
the service `name` variable; root detected it during loading and terminated
the verified owned controller before generation. GPU returned to 4 MiB,
compute processes and owned lock were absent. The original batch, command,
and artifacts are preserved in the read-only formal round.

The separate CPU-only correction uses `artifact_name`. Local and Linux
unittest discovery pass all five tests, including reproduction of the old
fault and execution of the actual corrected copy loop for all ten service
identities. Independent terminal and repair review passed. A complete new
matrix requires ten additional services and new round authority; no further
GPU execution has occurred. The short-tail limitation and paper C3 remain.

Evidence: [terminal review](R067B_INDEPENDENT_TERMINAL_REVIEW.json),
[formal closure](R067B_FORMAL_CLOSURE_RECEIPT.json),
[controller fix diff](R067B_CONTROLLER_FIX.diff), and
[Linux correction CPU receipt](evidence_cpu_v2/receipt.json).

This directory is a tooling-only frozen-copy patch. It does not modify FreeToken
product, engine, existing R067/R040/T17 evidence, operational code, or release
manifests.

## Artifact binding

- Source frozen from `r067_d20_short_tail_v1/formal_evidence/E2-R067a-d20-short-tail/hot_p8192/t17_d14_startup.py`.
- Frozen baseline: `tooling/baseline/t17_d14_startup.original.py`, SHA-256
  `ede1ddb885b7e359838be8aad042ee84f904705aa875be48317ef2452c146b0d`.
- Reviewed replacement: `tooling/t17_d14_startup.py`, SHA-256
  `5d205e6e1c5ef5e0b807431d5e54d8088af168c98a5cb52cb74c1c72b9ec0eef`.
- The standalone patch is `tooling/patch/t17_d14_startup.async481.patch`; its
  sole behavioral change is `uid=await state.new_user()`.

The local product snapshot used to inspect the asynchronous API has worktree
commit `d50be0f8f84ab1105f788be8f1354773ad539b63`. Its API server SHA-256 is
`ee791e763adf12f081f9c537781557b0b488a9e3e45e7976c15969494c2d3577` and
engine SHA-256 is `63afeedfd12ff3e46b66879ef7f38c53122a352689f99cf457f4a857b28fa517`.

## CPU validation

Run from the workspace root:

```powershell
python -m unittest freetoken.development.r067b_short_tail_v1.tests.test_t17_exact_ids_async_route -v
```

The test imports the reviewed startup artifact and calls its actual registered
`_t17_exact_ids` coroutine with an async fake frontend. Its four formal route
cells use exact input lengths `P+T` for `P={8192,8256}` and `T={1,64}`, each
with `max_tokens=128`; two separate seed cells use `P+1` and `max_tokens=2`.
They assert an integer awaited UID, fake-wire `T17ExactIdsMsg` serialization,
the actual int32 little-endian request digest, sampling (`temperature=0`,
`top_p=1`, `ignore_eos=True`), cached/prompt/completion usage aggregation, and
full assembled text. Separate cases cover invalid inputs and a terminal
acknowledgement error. It starts no HTTP service, GPU process, or model.

The route unittest uses fake-wire CPU coverage. Separately, Linux executed
the retained spawn probe with real T17 serialization and observer hooks;
it passed with CUDA uninitialized. Its max_tokens=7 transport message is
separate from the formal route sampling cases. See
[initial Linux CPU receipt](evidence_cpu_v1/receipt.json).

`t17_d14_observe.startup()` and the existing `__mp_main__` installation branch
are byte-for-byte retained from the frozen baseline.
