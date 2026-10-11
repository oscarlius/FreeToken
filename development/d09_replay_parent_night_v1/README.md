# D09 T2/T03b replay parent

`d09_replay_parent.py` is a root-admitted, owned parent for one fresh enabled
candidate service followed by two fresh cold edited services. It binds the
independently reviewed `t2_actual_v5.py` SHA, D09 native provenance, candidate
commit, 32-token maximum, three-service ceiling, and 60-call ceiling.

The hot service sends the frozen 36-call T2 sequence. Cold A and B independently
send the same 12 edited payloads in physical round order 11 through 0. Each cold
result must report zero cached tokens. Cold A/B instability is `failed_harness`;
the first stable cold-vs-hot byte difference is `not_met` and stops the round.
No terminal result becomes an acceptance verdict automatically.

`--filedry` uses the original T2 client's fake clock and produces a local,
three-service/60-call topology without GPU, HTTP, service startup, or compilation.
`--run --admission ROOT_SEALED_FILE` requires an immutable root admission that
binds this source, T16/T17 gates, all services' exact argv/env, and their ports.

`d09_replay_parent_v3.py` is the current source. Its FILEdry runs the root
client's actual `execute()` three times with fake SSE transport: 36 hot, 12
cold A, and 12 cold B requests. It retains each request/SSE/result/terminal
artifact, reserves each API/TCPStore pair together, and uses the same bytewise
output judge as the live child path. Live terminal output is emitted only after
the final service cleanup, GPU-idle proof, and owner-lock release succeed.
