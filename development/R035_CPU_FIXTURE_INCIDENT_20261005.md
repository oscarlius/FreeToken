# R035 工装误请求事故

## 已确认事实

2026-10-05 20:09:47、20:09:57，新 CPU 夹具 `test_d16_native_process_collection.py` 创建了动态端口 HTTP 服务器，却未把客户端接到该端口。root 执行冻结阶段 `exact_startup_cpu_46acaff307cc` 后，采集器默认地址 8095 收到了两条真实模型请求。这是测试接线及执行隔离缺陷。

污染位于原始 `E2-R035/prefix_8192_tail_8191_warm`：

- `inputs/1.json`：2 个输入 token，SHA `527434a55f745fd61afdc8f3114f88e538050f3ea6a0e68258c6403f9cee021c`，max_tokens=128。
- `inputs/2.json`：2 个输入 token，SHA `ba7ef9af6796ba63d48b9fe492e418ab555c1dd3480f65e2853b181d88bb0394`，max_tokens=128。
- 该臂的 UID0 是供体，UID3 才是原计划 16383-token 请求；缺少 hit.json 和最终用例结果。

46ac 的报告 SHA `3d90b58d09e189230c90c97db529b9efa550259458ff9970f21bac395d82abe8` 为 FAIL/pytest 超时 120 秒。其 `gpu_started:false`、`service_started:false` 只描述没有新启动服务，不能证明未接触已有 GPU 服务；本次确实发送了请求。该包不能作为 CPU-only 或启动放行证据。原报告保留，事故澄清另立本文件。

## 清理和轮次状态

root 先核实控制 PID3468758 的出生 ticks129058853 和进程组，再对该 PID 发 SIGINT，由原 owned lifecycle 清理。20:13:52 CST，status_batch64.json 记录 failed/KeyboardInterrupt；failed_harness.json 为 admitted=false。随后控制进程与服务 PID3771691 均消失、8095 无监听、共享 GPU 锁释放。泳道 R 已独立确认。

四个先前完成的用例原件保留，但本轮不作 T17 接受，也不把工装污染判为模型 not_met。原 R035、batch64、冻结依赖不修改。下一步在新的独立 inode 快照/封存克隆中保存事故，使用新轮次重跑。

## 修复方向及验证状态

1. 采集器支持显式 request_factory，使 CPU 夹具传入动态 HTTP 地址；生产调用仍须冻结完整调用源并经复核。
2. CPU 包安装独立 sitecustomize socket guard，只允许本进程仍在监听的 loopback listener，永久拒绝 8095 和未注册地址；新增 connect/connect_ex 拒绝和 listener 关闭后拒绝回归。最新 `exact_startup_cpu_47e9ee42ebda` 已实际通过 26 项、零跳过，报告 SHA `bd53b2d59d124632c5974359001b89063f94e8d765a1240e307fb3e36ea762fd`；独立复核中。先前 bfc 的 17 项网络隔离证据已独立复核。
3. CPU pytest 临时目录纳入冻结阶段，保留实际请求、响应、失败工件，避免超时只留下摘要。
4. 新的 D16 模型进程采集接线已加入来源前置门：没有 SHA 固定的独立 source review、执行依赖、原生命周期和 CPU 报告则在建目录/启动前拒绝。CPU fixture 分支必须同时具备实际 socket 拦截函数身份及显式夹具客户端。该生产来源包及独立放行仍待交付，不授予 D16 GPU 执行资格。

## 恢复执行

R035 完整副本位于 `/data2/FreeToken/runs/dev_D16/r035_failure_snapshot_20261005_202252/snapshot/E2-R035`，32,153 个文件、33,442,424,331 bytes，receipt SHA `343cbfcb0a9f740aaa127ff5c38e62262d6226a3f7d92acc10f216f11adbfe33`。R 初核指出中间目录 `snapshot/` 仍为 775；root 仅将该新副本的中间目录改为 555，receipt 字节不变，整棵快照不再可写，原 R035 未修改。D04 事故克隆封存仍待完成。

R036 / batch65 已用原封存 51ec 包、原 source/launcher 独立 IR、R032 前提和精确 90015 输入重新进行 fresh launch 检查，RC0。控制 PID/PGID3851074、出生 ticks129813658 已核实，第一组 warm 服务正在加载。新轮次跑全部 28 组和规定的四组普通冷包络，不沿用失败轮次作为验收。不把 CPU guard 说成 R036 GPU 源的一部分：它隔离的是后续 CPU fixture 客户端。

既有 7/9/101/102 项 CPU 包维持各自已核实的有限范围。本事故不能用这些历史通过结果抵消。
