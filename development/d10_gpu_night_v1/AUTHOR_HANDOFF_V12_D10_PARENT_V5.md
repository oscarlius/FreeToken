# D10 actual parent v5 handoff

`d10_prototype_owned_parent_v5.py` is the only repaired actual entrypoint.
It reuses the v4 D07 controller/child lifecycle body, but patches its resolved
globals before either path runs: `runner` is v6, `parser` is v5,
`require_admission` pins the complete v5 actual source set, and `child_argv`
executes v5 itself.  Thus a v4 parser or runner hash cannot satisfy a v5
runtime admission.

The packet owns byte-for-byte copies of the retained R045 wave1/wave2 raw
fixtures under `fixtures/`; their SHA-256 values are bound into the fresh CPU
receipt. `--filedry` executes the same v5 module binding and reports the frozen
four-profile/eight-call plan without GPU, HTTP, service, or compilation.
The separate CPU spawn receipt proves the unchanged bootstrap worker hook.
This remains author preparation only; independent review is required before
any runtime action.
