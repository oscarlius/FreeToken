# D08 CPU/NUMA 环境只读复核（2026-10-10）

**结论。** `E1-R002b`（2026-10-03）和 `E2-R048b`（2026-10-08）的测量日期均落在 `ollama` 容器的单次连续运行区间内：容器从 `2026-10-01T07:19:49.034580784Z` 运行至 `2026-10-10T12:35:15.573350379Z`（即 20:35:15 +08:00），`CpusetCpus="0,2"`。本次复核时容器为 `exited`，没有恢复或启动任何服务。

R048b 原始 `SERVE_CMD.txt` 和 `serve.log` 可证明配置与实际执行器初始化：V0 为 `numactl --cpunodebind=0,1 --interleave=all`，并报告 23 个执行器线程（`cores 0..22`）；A/S 为 `numactl --interleave=all taskset -c 1,3-23,25,27-47`，并各报告 21 线程（`cores 1..22`）；B 为 `numactl --interleave=all taskset -c 1,3,...,47`（全部奇数逻辑 CPU），并报告 11 线程（`cores 1..21`）。主机当前拓扑仍显示 node0 为全部偶数 CPU、node1 为全部奇数 CPU，超线程同胞为 `0,24`、`1,25`、`2,26`、`3,27`；GPU0 的 NUMA affinity 是 node1，CPU affinity 前缀为 `1,3,5,7,9,11`。

因此，R048b 可以证明：

- V0 与 `ollama` 的 `0,2` CPU 集合重叠，且其执行器日志包含 `0..22`；A 的 taskset 排除了 `0,2,24,26`，避免了已知 `ollama` 两个物理核及其同胞；B 的允许 CPU 集合完全位于 node1，和 GPU0 的 node1 拓扑一致。
- 这使 A/V0 的差异可支持“避开被占用物理核是性能差异的因素之一”的受控解释；B/A 仍同时改变了可用核数和 NUMA CPU 节点，不能单独量化 NUMA 效应。R048b 的 C（`--membind=1`）因 node1 可用内存 `120,187,368 KiB` 低于门槛 `120,586,240 KiB` 而跳过，故没有“node1 内存绑定”测量。
- B 使用的是 `--interleave=all`，不是 `--membind=1`。它保证线程许可集合在 node1，却不保证专家权重或 PLE 的物理页在 node1。原始目录中没有服务存活期间的 `/proc/<pid>/numa_maps`、`numastat -p` 或等价的按节点页计数；服务也已退出。因此不能从当前主机 NUMA 状态、启动参数或加载进度反推历史专家权重/PLE 的实际 NUMA 驻留，更不能宣称与 GPU node1 的内存本地性已证实。

**超订/跨 NUMA 的证明边界。** 现有证据证明运行时 CPU 集合重叠/隔离策略，以及允许 CPU 节点与 GPU 拓扑的关系；它不证明测量期间 `ollama` 的瞬时 CPU 利用率、每个执行器线程实际调度 CPU、CPU 内存带宽争用，或 CPU/PCIe 的实际时间重叠。容器生命周期区间是日期级并发的强证据，但若要把历史 `llama-server` 驻留、CPU 百分比或内存占用作为独立事实，仍需要当时的原始 `ps`/`docker stats`/进程日志，而非从今日 `docker inspect` 回推。

**后续。** GPU 复测应另行批准并在服务存活、加载完成后采集：`taskset -pc`（服务及 executor TID）、`/proc/<pid>/numa_maps` 或 `numastat -p`、node 内存快照、GPU/CPU 拓扑和 Ollama 状态；将其与轮次 manifest 一同封存。本交付没有占用 GPU、启动压力、修改远端原件或恢复 `ollama`。

## 证据定位

- 原始轮次：`/data2/_shared/runs/ft_rounds/E2-R048b`，round SHA `32e0dc755d79e9e4788c2905b9150611bff67a65a9b3933a8146abf75d94707e`，409 文件 / 397,916,016 B（已关闭）。
- 命令与日志：`batch111/{V0,A,B,S}/{performance,diagnostic}/SERVE_CMD.txt` 和 `serve.log`；B/C 状态见 `terminal_observation.json`。
- 本次只读采集的精确字段、时间和来源见同目录 `D08_CPU_NUMA_ENV_EVIDENCE_20261010.json`；文件哈希见 `SHA256SUMS.txt`。
