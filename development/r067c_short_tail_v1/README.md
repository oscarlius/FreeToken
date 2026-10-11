# E2-R067c-d20-short-tail CPU-only preparation packet

This is a new, separate R067c preparation packet. It is not a replay or a
residual continuation of R067b. The packet is intentionally non-admitted:
`admit=false`, remote proof is `pending_root_remote_validation`, and it neither
starts a GPU/service nor makes HTTP generation calls.

The fixed scope is ten services and fourteen generation calls: hot P8192/P8256
seed plus T1/T64 queries, then cold A/B for each P/T schedule in the listed
execution order. Inputs, schedules, and existing tooling are source-bound from
the prior packet; `prepare_cpu_packet.py` rewrites every run/service path to
`E2-R067c-d20-short-tail` and copies no production state.

The future remote manifest binding is
`/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2/binary_manifest.json`
with SHA-256
`a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18`.
The required `cpu_moe` and `pinned` entries are respectively
`10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4` and
`07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68`;
`row_store` is forbidden. Hot remains release-e2 `481d3a…f2cfb9`; cold remains
D20 `d50be0…39b63`, with inherited engine hashes fixed in the generated config.

Run the local preparation and static checks:

```powershell
python freetoken/development/r067c_short_tail_v1/prepare_cpu_packet.py
python -m unittest freetoken.development.r067c_short_tail_v1.tests.test_r067c_cpu_packet -v
```

`R067C_PREPARED_RUNNER_PACKET.json` also carries the corrected R067b-v2
controller source retargeted to this R067c round. It is a review artifact, not
an entry point: `execution_prohibited=true` and the matching root command
configuration remains `must_not_run=true`.

Before root may seal or use it remotely, R045 must permit R067c; root must
produce a fresh remote file-dry proof, sign both FD and ADMIT bindings, obtain
an independent startup review, and own the production stop/restoration plan.
The fixed terminal contract is: cold A/B difference is `failed_harness` with at
most two root-controlled tooling retry rounds; equal A/B plus hot difference is
`not_met`, stops at first divergence, and then root restores production.
