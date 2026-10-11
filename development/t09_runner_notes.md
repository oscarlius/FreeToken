# T09 runner review notes

## 当前：第十二节98304新版Linux CPU交付

R048当前源 `r048_t09_prepare.py`（SHA `c991329cb117b33826fbb50fa23282b4ab84722a69511c88178622635a13156d`）已在FT venv完成26/26定向CPU回归，CVD空、socket guard生效、torch未加载。小报告 `/data2/FreeToken/runs/dev_R048/section12_cpu_20261007_131631/report.json` SHA `8f666e5706648d7492ef39a591d983d48b57a8ec4509b6755c5c83dd82dc7231`，本地[R048 CPU指针](R048_SECTION12_LINUX_CPU_20261007.json)。6输入含当前8bf候选的C++、executor、layer源码，与服务器clean候选按换行归一一致。

独立R在[CPU准备复核](SECTION12_CPU_READINESS_REVIEW_20261007.md)给出PASS，仅支持CPU工装。配置全部98304/.88、普通4096、同轮hybrid S/V0判据保持；R049 measured仍为正式前置。实际FILEDRY、R启动签字、GPU结果和T09判定均未完成，不能用历史26项或本次CPU代替正式准入。

## 当前 2026-10-07 11:27：第十二节配置迁移

第十二节当前R048五臂全部98304/.88，候选8bf与父eff及R051 kept证据不改，R049 measured仍为前置。dry schema v3、目录.dryrun_E2-R048_98304_v3，review schema v2/文件E2-R048_startup_review_98304_v2.json；旧v2源码/26项CPU不作为新版签字。性能开启原D0/native PCIe字段，route/pause关闭；本地新版目标回归通过，Linux和真实dry待队列执行。

本轮主判据只使用同窗口同批hybrid S/V0的服务开销、完成率及两路速度，scope=within_round_hybrid_S_vs_V0。SC4旧offload36.61只作历史背景，不作为98304放行或比较依据。R056的生产层优先/noD0/23-token短请求与T09普通prefill/D0/native/2000-token短请求口径不同，分别记录，不新增offload GPU臂或阈值。


`plan/01_测试与调研/batches/t09_runner.py` is local-only and dormant until the
formally assigned T09 `E2-R005`, batch, and `--run` are supplied on the Linux host. It
uses the reviewed `e2_runtime.CardRunner.round_scope()` and `.service()` APIs
without changing that helper.

`round_scope()` archives a matching `batch<BATCH>_<RID>_python.sh` wrapper. The
root executor must provide that wrapper before a future run; this bounded task
does not create or upload it.

The four single-request variants are exact card prefixes: V0 uses both NUMA
nodes, A excludes both busy physical CPUs and their SMT siblings (0, 2, 24,
26), B is node1 odd CPUs, and C is B with node1 memory binding. The runner
records the original SMT topology, node1 memory, and existing `llama-server`
rows read-only; it never kills or modifies them. C is skipped only when
`MemFree + FilePages < 120586240 kB`; a C startup failure is retained as
`NOT_READY` only after a readiness timeout before the service context yields.
Probe, parsed-argument, D0, service-body, and OOM failures always stop the
round. The original cold/argument probe MD5 values are checked before V0 starts.

All arms use hybrid, non-layer-major, 4096 prefill, checkpointing, and D0.
They require live service affinity plus the executor pin line to fit the arm's
CPU set. The runner records first 2000/64, cold `s3A` and `s3B` 32K/128, and
short 2000/512 samples; every cold sample requires cached tokens zero. Parsed
argument union is checked before probes through `CardRunner.service` and allows
only the generated PID. D0 requires real aggregate, steps, and prefill files;
only emitted hybrid fields are summarized. D08 service-time decomposition and
D06 two-request work remain explicit `pending`; HYB_TRACE is never enabled.

The 2026-10-03 E2 unification directive overrides the historical T09 worktree:
all new measurements run on `e2base@23f2e2c`. The old `40fd5d4` E1 material is
referential context only and is never reported as a same-generation baseline.


## 根集成：10-07 第十节队列与 Linux CPU

E2-R048 等待 E2-R049 measured + D04，前置 E2-R051-gate-D08 已 kept。冻结服务器执行源码为 `/data2/FreeToken/runs/dev_R048/r048_section10_source_v2/r048_t09_prepare.py`，entry SHA `2602696c6b9a9b6f6a44dea6b722f2e1a9f1ab242fbb952fef89a41da10252ee`，MANIFEST SHA `8e42d35c7cc6e0c3b0046c7398c696748c02dc9b310917e3486ef5fd3c0bc0a7`。

Linux CPU 26/26 PASS，报告 `/data2/FreeToken/runs/dev_R048/r048_section10_cpu_v2/report.json` SHA `50d9acbbab624bdc8d72f3b4bad8135a68a12b66e39861d2848bcd99b2e9364b`。源码 v1/CPU v1 因漏带三个候选源码测试 fixture 失败，已只读保留；v2 增加精确 clean 候选 8bf0ad39 的三个小源码文件，运行入口逐字未改。CPU 未占 GPU、未启服务、未写正式轮次/取锁/分配批号。

真实路径空跑、R 启动前签字和正式测量尚未执行。前置齐备后，在同一用户 dell、cwd `/data2/FreeToken` 运行上述入口 `--prepare --dry-run-dir /data2/_shared/runs/ft_rounds/.dryrun_E2-R048`，使用 CPU socket guard；签字通过后才 `--run`。
