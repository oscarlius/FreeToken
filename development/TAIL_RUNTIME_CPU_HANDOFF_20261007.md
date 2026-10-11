# 后续实际批次工装CPU交接

依据交接书第十四节。root负责以下文件；CPU证据不代替真实路径空跑、R启动签、GPU原始测量或D04。

| 批次 | 当前执行源 | Linux结果 / 报告SHA | 前置 |
|---|---|---|---|
| R052/T11 | r052_t11_followup_prepare.py、r052_t11_replay.py、r052_d0_shutdown_startup_v1.py | 38PASS；b386bb997c65d0d290e133031e99207eda1fe45efa470a7f7bdf1036ef97a25a | R045 measured |
| R044/T10 | t10_e2_r044_prepare.py v5、t10_capture_startup_v2.py、t10_ordinary_replay_v1.py | 29PASS；750bc196e9ed4af96a7acc62ebb85e7e1108d3e806f6ca5b664d46b9b2dad236 | R052 measured |
| R047/T03b | t03b_e2_r047_prepare.py v6，复用R052 shutdown | 29PASS；c32d4ad3a7ce29d2dbae8ce51ed64f279b0b24509caf9602fb0923ee13b9afa8 | 合格R046d/T06、R045、R044 |

报告指针为同目录R052_RUNTIME_CPU_V5_20261007.json、R044_RUNTIME_CPU_V5_20261007.json、R047_RUNTIME_CPU_V6_20261007.json。源与CPU报告各在独立新目录封存；既有失败和旧版本不改。

Linux使用FreeToken专属venv、CUDA_VISIBLE_DEVICES空、现有冻结cpu_guard；只允许本进程登记的动态loopback fixture。候选为0aa23431、98,304/0.88。测试读取必要源码/小回执，没有正式轮次、模型、GPU、服务或批次分配。

R052真实spawn回归执行原scheduler worker的SIGTERM退出并验证shutdown只调用一次。R044保留原业务消息与200-token上限，真实普通SSE；trace/pause关闭。R047六臂共用一个API/TCPStore端口对，声明差异仅prefill_anchor_cut；实际最终日志计数与d0_decode.json必须一致。

FILEDRY必须使用正式入口、同一路径/cwd/UID与完整复制闭包，运行真实文件writer至Popen前边界，显式可写0600复制和输出探针；只在隐藏非RID sibling写typed probes。源、FILEDRY和R签SHA一同绑定；拒绝旧签、formal RID空跑、symlink和路径漂移。启动前前置只核清单/round SHA、只读位与D04 history。

这些源尚未正式FILEDRY/R签/GPU运行，不能标为业务接受。原T10随机数/argmax差异的历史发现仍待本轮实测，T03b必须实际观察非零快照，不能用模拟输出补齐覆盖。
