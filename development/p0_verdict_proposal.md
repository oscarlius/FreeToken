# P0 verdict and release proposal — review only

This proposal is read-only. It does not append a verdict, seal a directory, or publish `FTD-20261004-1`.

## Observed canonical state

`development/p0_round_inventory.json` is a read-only remote inventory of `/data2/_shared/runs/ft_rounds`. Each proposed kept round has a readonly directory, `round.json`, `MANIFEST.sha256`, and `round_history`. All currently have formal `pending_review` and empty `verdict_history`.

The seven requested failed-harness candidates (`E2-R001`, `E2-R004`, `E2-R005`, `E2-R012`, `E2-R014`, `E2-R015`, `E2-R016`) have directories but no `round.json`, `round_history`, or `MANIFEST.sha256`. They cannot receive a D04 append. Each needs a separate failed-harness closure first. `serve:none` may be recorded only where the retained original result proves no service launched.

## Proposed D04 appends

The leader may use the public D04 writer to append `kept`, strictly as a measurement-validity verdict, for:

- `E2-R000`, `E2-R003`, `E2-R008`
- `E2-R009`, `E2-R009-p64k`
- `E2-R006`, `E2-R017`
- `E2-R011`
- `E2-pre-gate-D00`, `E2-pre-gate-D01`, `E2-pre-gate-D02`
- `E2-R002-gate-D03`, `E2-R018-gate-D03`

Every append must include a CST timestamp supplied by D04, the actual old/new verdict, a nonempty reason, immutable evidence paths, and a named responsible role. The complete expected hash and evidence bindings are in [p0_verdict_proposal.json](p0_verdict_proposal.json).

`E2-R020-gate-D06` is separately eligible for a measurement-only `kept` proposal: its canonical `round.json` SHA is `a80eb0c3c66f4bfc248691f29b5b60324bff14c090f5d8cb703b3744d884e666`, its manifest SHA is `66eb455b51f927746014a3b31ef8c61f4c3347b25a6ba589a31804f015a33e01`, and its local independent raw-review SHA is `67a895cc4e6913e6e5530fa3a4b20ed13e9a1d2fc4bfeabde4713c98375c3dc4`. This does not claim that the still-running D06 development self-check or T05 is accepted.

## Scientific limits retained in the proposal

- T10 prefix-hit continuation / cold-vs-warm attribution remains `hypothesis` for `E2-R006` and `E2-R017`.
- T04 envelope (`E2-R002`) remains `hypothesis`; it receives no kept verdict in this batch.
- T11 restore attribution remains `hypothesis` even if `E2-R011` is kept as a valid measurement.

## Formal vocabulary blocker

The handoff requests `failed_harness`, but the current public D04 writer permits only `kept`, `reverted`, `rejected`, `blocked`, `not_met`, `kept_pending_gate`, `measured`, and `pending_review`. This proposal does not invent a mapping. The leader must select a permitted value or extend/revalidate D04 before any failed-harness append.

## Release proposal

Proposed release ID: `FTD-20261004-1`; previous release: `FTD-20261003-1`. Bind only final D04-produced hashes and evidence, with code versions `E2-base@23f2e2c`, c30, f506, and `03692633df48456fb0baa78de7b64e5628a12ab1` only if R020 is included. Publish remains leader-owned after all D04 checks and immutable hash-chain validation succeed.
