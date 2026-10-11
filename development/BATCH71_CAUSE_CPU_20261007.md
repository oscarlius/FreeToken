# batch71 缺失交付文件与暂停缺陷的 CPU 复现

结论：两个独立缺陷。`effb996` 修复暂停循环的普通消息处理；旧采集进程收到 SIGTERM 后仍不调用封存函数，不能仅靠该补丁恢复 `service_delivery.json`。

依据为真实源码与 Linux 子进程回归，不构成模型放行：提取 0aa/eff 的 `_receive_dev_messages`，使用冻结采集启动器原有 `run_forever` / `except KeyboardInterrupt` 边界，发送真实 SIGTERM。默认路径控制臂只模拟消息已交付后的等待，不模拟或证明模型计算。batch71 两路批槽的历史环境没有暂停开关；旧环境构造器清除继承的开发开关，只有停靠臂主动开启。原日志已完成两次请求后进入关闭过程。

| 调度版本 | 暂停开关 | 普通消息处理/暂存 | 关闭版本 | delivery |
| --- | --- | --- | --- | --- |
| 0aa | 关闭 | 2 / 0 | 冻结原件 | 缺失 |
| eff | 关闭 | 2 / 0 | 冻结原件 | 缺失 |
| 0aa | 打开 | 0 / 2 | 冻结原件 | 缺失 |
| eff | 打开 | 2 / 0 | 冻结原件 | 缺失 |
| eff | 打开 | 2 / 0 | shutdown v3 | 封存一次 |

冻结启动器 SHA256：`91102843e3d2b3464b78e7a0431165ab3ca32d488a59e17f8c818f7c2879ee12`。

Linux CPU 报告：`/data2/FreeToken/runs/dev_D06/batch71_same_root_cpu_20261007_v2/report.json`，SHA256 `df00898e50c2e42d3158943bf74fa803c7893797ad3911b34fd775856a9d723c`。68 项通过，其中 5 项为上述原因矩阵，其余为当时的候选、native 与队列绑定回归；空 CUDA 可见设备，socket guard，无 GPU 或模型端口。报告目录已只读。首次包含三个旧绑定 fixture 失败的 CPU 包原地保留；v2 修正 fixture 后重测，不覆盖失败记录。

R040a 保留已经修好的 shutdown v3、collector v2。停靠臂需要暂停开关，按交接书第七节使用 eff 测量树，排在 R048 后、R045 前；启动前仍需当时前置 D04 控制记录和实际执行源码的独立 R 复核。旧性能、质量、Agent 和续算结果不重跑，生产基线保持 0aa。
