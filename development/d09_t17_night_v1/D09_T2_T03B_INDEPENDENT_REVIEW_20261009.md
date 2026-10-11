# D09 T2/T03b independent review — not approved

Reviewed package: `freetoken/development/d09_replay_parent_night_v1` and `/data2/FreeToken/development/d09_replay_parent_night_v1`. The local and remote runner SHA is `4532c966ffd968937c6f37ad5dac0b7a3d60b9b56729ff292ea8aa075331a3a2`; its imported root T2 client SHA is the required `9407d83c5b76955592c9524297047ec90f64a2f321b20aee3adc3cd89ee08db6`.

The actual runner has useful static controls: candidate/worktree/D09 flag and native provenance are bound; a sealed admission requires the T16/T17 status strings; the three production paths call the root client with budgets of 36/12/12 at 32 tokens; cold results are required to have zero cached tokens; stable cold A/B and bytewise hot/cold comparison stop on the first difference. It also uses the D07 owned lifecycle, atomic batch receipt, PID birth binding, and preserves the GPU lock if final cleanup throws.

The FILEdry evidence is not admissible. `filedry()` invokes `client.file_dry(...)` only for `hot_plan`, which exercises 36 fake T2 transport calls. It then directly creates `cold_a` and `cold_b` result dictionaries and writes `actual_mock_calls: 60`. Those 24 cold calls never go through the client request, SSE, backend-window, cache-geometry, or comparison-input capture path. The existing two tests pass because they only validate the topology and self-reported total. They do not establish execution of 60 calls.

There are two additional closure gaps. Ports are merely range checked and probed one-by-one, so the package neither enforces six unique ports nor reserves each API/TCP pair atomically. Also, `terminal.json` is written before the final GPU-idle and lock-release actions, with no post-cleanup receipt proving group death, idle state, rebindable ports, and released lock.

The package must not receive a real-run admission until the three findings in the paired JSON review are resolved and a new independent FILEdry shows all 60 request/judge paths. This review performed no GPU, HTTP, service, compile, or lock action.
