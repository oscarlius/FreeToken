# D08 补遗：E1-R002 / 声称的 E1-R002b 绑定复核

本补遗不覆盖 D08 原一页或其哈希清单。只读检索 `/data2/_shared/runs/ft_rounds` 与 `/data2/FreeToken/runs` 后，仅找到原始轮次 `/data2/_shared/runs/ft_rounds/E1-R002`；未找到名为 `E1-R002b` 的目录、文件或服务运行目录。因此不能把 E1-R002 的证据改称为 E1-R002b 的独立测量证据。

E1-R002 的 `round.json` 标注日期 `2026-10-03 14:22`。其 `batch6.log` 给出更精确边界：`14:14:47` 开始，`14:22:17` 完成；`hyb_serve.log` 记录服务 PID `3118187` 于 `14:14:51` 启动、`14:18:41` 完成 CPU MoE 初始化。日志明确证明 hybrid 运行及执行器为 23 线程、`pinned to cores 0..22`。这与现有 `ollama` 容器的历史 `CpusetCpus=0,2` 构成可能的 CPU 集合重叠：若容器内 llama-server 当时活跃，0 和 2 两个逻辑 CPU（及其物理核）可能被共同竞争。

但 E1-R002 原件没有启动 argv、`numactl`/`taskset` 记录、`/proc/3118187/status`、`taskset -pc`、`numactl --show`、`numa_maps` 或 `numastat -p` 快照。故不能从本原件证明 E1 的 CPU mempolicy、进程允许 CPU 集合、每线程实际 CPU，或专家权重/47.7 GiB PLE/73.4 GiB experts 的历史 NUMA 页驻留。配置中若存在 `--interleave=all` 只能证明策略允许跨 NUMA 分配，不能证明这些页实际跨节点；本 E1 原件甚至未保存该启动策略。

当前主机拓扑（此前 D08 采集）显示 GPU0 NUMA affinity=node1、node1 为奇数 CPU。E1 的 `cores 0..22` 日志不等同于一个可核验的 OS CPU 列表，也没有与 GPU node1 对齐的 mempolicy 证据。因此 E1 仅可用于“23-thread executor 与 Ollama 0/2 cpuset 存在潜在超订/竞争路径”的历史假设，不能单独证明跨 NUMA、GPU 本地内存或权重驻留。

来源及哈希见 `D08_E1_BINDING_ADDENDUM_20261010.json`。补充检索路径和未找到项已写入该文件；容器生命周期只支持日期级并发，不替代本补遗要求的线程/NUMA 绑定证据。
