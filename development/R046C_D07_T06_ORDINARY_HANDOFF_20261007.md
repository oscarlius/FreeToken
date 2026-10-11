# R046c ordinary T06 route-analysis preparation

Candidate: `151ee718b88882b57dba75317bb53c697d5f235f` in
`/data2/FreeToken/wt/e2d07-trace-lm`; round: `E2-R046c`.

`r046c_ordinary_seed_driver.py` uses the frozen ordinary session/tool flow, but
binds every dispatched request to the R046c v3 worker observation: `UserMsg`
input IDs and the scheduler's `DetokenizeMsg` token sidecar.  It does not ask
for, synthesize, or rename pause ACKs.  A session stops before dispatching a
request above 96,256 prompt tokens; it does not truncate the request.

`r046c_route_analyze_ordinary_v1.py` retains the existing route-record math and
legacy `ft_route_ack/v1` branch.  Its ordinary branch accepts only
`ft_r046c_ordinary_seed_trace/v1` / `ft_r046c_ordinary_two_decode/v1` evidence,
then validates worker UID, input-ID SHA, the full contiguous DetokenizeMsg
sequence, terminal marker, and API completion count.  It reports
`ordinary_worker_token_bound_requests` and the source
`SchedulerIOMixin._reply_tokenizer_rank0(DetokenizeMsg)`.  It never serializes
an ordinary event as `ft_dev` or `ft_route_ack/v1`.

The prepare packet source-binds this analyzer alongside the ordinary startup,
client, driver, and D07 lifecycle helper.  Its four T06 arms retain only
`G_seed12k/route` as D15 training input; `seed_45k`, `seed_real`, and `two` are
held out.

## CPU evidence

- Local: `python -m pytest -q development/tests/test_r046c_d07_t06_prepare.py development/test_r046c_t06_ordinary_v3.py` → `16 passed`.
- Linux FT venv: `CUDA_VISIBLE_DEVICES=''`, an import-time socket guard blocking
  connect/bind/listen, and a mirrored `development/tests` directory → `10 passed`
  for the R046c prepare/analyzer suite.  No server, GPU, lock, or batch was
  touched.  The earlier `/tmp/r046c-ordinary-cpu-20261007-1528` path-layout
  failure is retained separately; corrected evidence is
  `/tmp/r046c-ordinary-cpu-20261007-1534`.

## Source hashes

- `r046c_d07_t06_prepare.py`: `801ac950c209818e235a7b1a4f73d7c40b0fc8784516eea1536f407b59104654`
- `r046c_ordinary_seed_driver.py`: `4cd8842127e03e6ad210598e5db926970cd054d6e5663769bed302ac42f99d62`
- `r046c_route_analyze_ordinary_v1.py`: see final source receipt reported with this handoff.

## Runnable controller boundary

`--file-dry-run` performs no GPU or batch action, but creates a new temporary
tree, copies the owned runtime/client/analyzer/native-source and exact seed
inputs as writable files, records SHA-256 plus MD5 and mode for each copy, and
prepares all six service command/environments.  Each uses one private
API/TCPStore adjacent-port receipt from `ft_batch_port_pair_v1.py`; it does not
listen or connect.

`--run` now implements the existing owned controller/child receipt protocol.
The controller rejects a foreign lock before global batch reservation, writes a
per-batch receipt, and publishes normalized child birth.  The child repeats
admission, validates the receipt before its only GPU lock, runs serial G3
off/on and four T06 arms, and releases the lock only after owned cleanup.
Ordinary services use `r046c_ordinary_memory_startup_v1.py`: the spawned model
worker receives both the v3 UserMsg/Detokenize binding and R056 load/request
memory observer. Missing model-load, request-before, or request-after rows
fails the arm. A non-bitwise G3 comparison emits pending-review `not_met`, not
`measured`.

Formal admission requires only registered `E2-R059-gate-D07 kept`, `E2-R058
measured`, and `E2-R041-gate-D17 kept`. `E2-R040 failed_harness` remains packet
history, not an extra startup gate. The independent review must additionally
bind the sealed file-dry receipt SHA and its runtime/native/seed copy records.

## Latest CPU evidence

- Local complete suite: `21 passed`.
- Linux FT venv guarded suite: `15 passed` at
  `/tmp/r046c-runnable-cpu-20261007-1602`, with `CUDA_VISIBLE_DEVICES=''` and
  socket `connect`/`listen`/`connect_ex` blocked. Pair-bind probing remains the
  only permitted loopback socket operation; no service was started.

Latest source hashes:

- `r046c_d07_t06_prepare.py`: `648f198ee52564a089611c9ef24a620011570c37cd40fd93545aa56f84007304`
- `r046c_ordinary_memory_startup_v1.py`: `d989a159d076d0b0791056fdf4e6327d1c442810aad70783d8150f303fe9ff4f`
- `test_r046c_d07_t06_prepare.py`: `8e7713d22ee26bb9974f6a65b47b4204e60d75c021ca2d009827aff42434938c`


## 2026-10-07 16:24 锁定版CPU与源码冻结

Linux guard 25PASS，真实candidate packet（clean151ee）及两.so实际import完成；CUDA未初始化。修正D0前缀/实际prefill路径、G3输出路径差异完整记录与标准化、G3同一API/TCPStore对、memory父/worker birth绑定；packet读取真实checked_worktree.commit。当前源码包 `/data2/FreeToken/runs/dev_R046/r046c_section13_source_v1_20261007_162252`，源MANIFEST SHA `8b7d1f368abbf0fc8aabaf858b0843a7c5e7eae3de39ca67da611a5b6bb40236`，LinuxCPU冻结回执SHA `784cb72958f68d7de7790296b6f1cb66a2facf8016b33a50339c5ae4ad053358`。全部14个源码/测试文件逐字节等于实际Linux25PASS来源；小报告原样保存，未复制失败轮次。

本包仅源码/CPU准备，不是R启动签。R059用户纠正裁定尚待，故未执行正式FILEDRY、未拿锁或启服务；获裁定且R059 kept D04闭合后才用本入口同路径同用户空跑，再由R正式启动复核。

## 2026-10-07 17:22 最新冻结v2

权限修订源 `/data2/FreeToken/runs/dev_R046/r046c_section13_source_v2_20261007_164507`；
MANIFEST `c02939113b5625af1d096ec27977abcaf524057d5746e6ba2084477ac2a0dd2e`，
CPU冻结回执 `fde2e9adaf54614a4843c601e106d0f34241dde90ea86daecc76b1dad179ac0f`。
Linux25PASS日志 `60729b5b3c9cc644fa4eba971ff1860d948cea64a6e4f7849ff1c8caba43fbf8`；
入口SHA `d908ae178bd578e1fea0c0d376e24cc117a82f14476b2106a1eec90dd5c53635`。
正式与FILEDRY共用0600可写嵌套复制；冻结原件维持只读，旧v1保留。尚缺R059纠正裁定/kept、正式FILEDRY与独立R启动签，不据此启动GPU。
