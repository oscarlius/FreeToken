# H2 deep read-only check: parser, argv values, and historical log

This supplement corrects the earlier literal `cached_rows` text search. The
relevant function is `development/r066b_canary_v2/sdk_adapter.py:70`; source
SHA-256 is `d62974a6ae455587a7ebd5bdd23814a40acb6a64f350cff613685843402e64fe`.
Its actual expression is:

```python
re.findall(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)', text)
```

Against the historical log SHA-256
`6bba876c6ecd21906e9478ea820c0aecdbc3a5a8cf3c9715c473c32d1fe1b65b`, the
exact regex finds 68 rows; its first four triples are `(1,8192,0)`,
`(1,8192,0)`, `(1,8192,0)`, `(1,7488,0)`. Therefore an old-format compatibility
parser is unnecessary: the current R066 parser already reads the historical
prefill rows.

The requested *physical* newline records 261/262/264 do not happen to be
prefill rows:

```text
261 Decode batch, #running-req: 1, #token: 256, token usage: 0.01, #mamba-slot: 4/12, mamba usage: 0.33, gen throughput (token/s): 33.96, #queue-req: 0
262 INFO: 127.0.0.1:46138 - "GET /v1/models HTTP/1.1" 200 OK
264 Decode batch, #running-req: 1, #token: 320, token usage: 0.01, #mamba-slot: 4/12, mamba usage: 0.33, gen throughput (token/s): 30.47, #queue-req: 0
```

Those lines only have the scheduler scalar `token usage`; the historical log
contains neither a `usage: {...}` dictionary nor `prompt_tokens`,
`completion_tokens`, or `total_tokens`. It cannot by itself support the R066
SDK usage projection. No exact historical req-SDK-report file was found.

The exact rollback `ft` argument list with `--help` appended returned 0 under
the previous empty-CUDA, rollback-PYTHONPATH environment. This validates parser
acceptance of every listed `ft` option/value without a service launch.

| launcher/ft option | value / admissible form | accepted |
| --- | --- | --- |
| `numactl --cpunodebind` | `0,1`; comma-delimited nodes | yes |
| `numactl --interleave` | `all`; valid node selector | yes |
| `--model-path` | overlay path string | yes |
| `--served-model-name` | model-name string | yes |
| `--host` | IPv4 host string `172.16.108.9` | yes |
| `--port` | integer `8095` | yes |
| `--memory-ratio` | numeric `0.88` | yes |
| `--moe-cache-auto` | boolean flag | yes |
| `--moe-prefill-hit-d2d` | boolean flag | yes |
| `--ple-backend` | choice `pinned` | yes |
| `--moe-strategy` | choice `offload` | yes |
| `--quant-backend` | backend assignment `moe.nvfp4=triton` | yes |
| `--max-running-requests` | integer `2` | yes |
| `--cuda-graph-max-bs` | integer `2` | yes |
| `--kv-reserve-tokens` | integer `49152` | yes |
| `--max-seq-len-override` | integer `49152` | yes |
| `--max-prefill-length` | integer `8192` | yes |
| `--enable-cache-report` | boolean flag | yes |
| `--enable-special-token-ckpt` | boolean flag | yes |
| `--tool-call-parser` | choice `qwen3_coder` | yes |
| `--reasoning-parser` | choice `qwen3` | yes |

Machine-readable receipt: `h2_deep_check.json`, SHA-256
`c9088be8f15dee6f2b51cbf30512bf26036ad9f17872d961934901a1c223c8b2`.
The terminal result remains `blocked_dirty_rollback_worktree`; no cleanup,
rollback startup, model service, endpoint call, or GPU operation was performed.
