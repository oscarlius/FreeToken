# T04 f506 / Y129 controlled measurement runner

`development/t04_f506_y129_runner.py` is the new T04 runner in this lane. It
binds E2-R021 to f506, its immediate c30 parent, the approved f506 selfcheck
manifest, the UID0/PID3762886 terminal record, and the v2 raw-ID manifest. It
never treats the old c30 result or Y129's 12801 branch scenario as the actual
G4 input: the G4 raw prompt is 21976 tokens.

The runner starts four owned f506 services and invokes the reviewed controlled
client for each arm. It passes `--branch-length 12672` and
`--branch-token-count 129` explicitly. This scientific lane fixes FP32 K=32; other K values are rejected before service startup. The restore arm needs a host restore
proof at exactly 12672. Its final result is the candidate probe's FP32 logits
comparison of restore, recompute, and legal captures over the exact P+X tail.

The probe pin is checked against the candidate Git blob and the server's LF
file bytes: `7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7`.
A Windows working-tree file can hash differently after CRLF checkout conversion;
that local representation is not source evidence and does not relax the pin.

This is development instrumentation only. It does not replace the T04 science
or formal acceptance gates. No GPU execution is represented by the local test
suite; the launcher and queue operation remain owned by the mainline.
