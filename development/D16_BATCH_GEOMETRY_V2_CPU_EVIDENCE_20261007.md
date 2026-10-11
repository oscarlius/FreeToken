# D16 batch geometry v2 — CPU evidence

At `2026-10-07 19:38` (`ssh 9 date`), the isolated remote CPU stage
`/data2/FreeToken/runs/dev_D16/geometry_v2_cpu_20261007_1937` completed with
`CUDA_VISIBLE_DEVICES=''`, the frozen R046b socket guard enabled, no `torch`
import, no listener, and no model/service/GPU process.

`/data2/FreeToken/venv/bin/python -m pytest -q development/tests/test_d16_batch_geometry_v2.py`
reported `4 passed` (log SHA-256
`988344a7589dd35ded61b8e784dcd5bc43cb64ba0f19a2bda1a7ec44b380abcb`).
The guard proof log SHA-256 is
`3592ec1893818549d03541c1bab8786295a47ff98b01a3b433cdc0b46208eac8`.

The regression extracts, removes annotations from, compiles, and executes the
production `Scheduler._forward` AST against a minimal CPU fixture. It proves
the `batch.input_ids` assignment precedes `engine.forward_batch`, reproduces
v1's pre-forward `AttributeError`, then proves v2 reads the actual `[1, 3]`
shape at that boundary. Duplicate, absent, changed-shape, write-failure, and
budget failures each record indeterminate evidence while preserving the native
forward result or its native exception.

Remote `SHA256SUMS` binds the staged sources: v1
`9cd0c09328f16f6191ca1f101747379cbf4e632fbcfa2ff6b05faf25a5d8964a`, v2
`1aebdf47c1806fcd1c7dc5710b26fdf8c924aabbd40e47975565d20b4917b1b4`, test
`b8e1da4d6e897b970d7f599911852ea617ec02db9b45b9bdfd595d10bca0a7d4`, and
the inspected scheduler source
`07f431459052f67e8cfc60926074bbb43eb050856363bc9a9708e35e7f269014`.

This is CPU-only observer evidence. It does not authorize an R040b launcher,
service start, port use, GPU lock, model admission, or formal equivalence
acceptance.
