# 饕餮监控修改影响评估（2026-10-06 23:33）

结论：当前监控 UI/采样改动没有修改已冻结 T20 或 R046 开发包。T20 batch71 的缺 delivery 另有独立的 SIGTERM 收尾缺陷；后续 GPU 准入仍受连续两次工装失败的用户确认规则约束。

## 已核对的范围

远端 `/data2/_shared/run_monitor/monitor.py` SHA `7586a0a248f4166ed8116407e7dfe9a4471680217576d0f7e78272a769295950`；HTML `23d7644c0e3953558146089822b66ca857334345b70610382e8984b11d66caa1`；JS `9b40d538339a7a8288abc9c58c9eaaeaed4ac7042267f7e02563b72b4cc70099`。现场文件mtime 23:28，按实际文件而非协调日志中23:55/23:59记录推断时间。

T20 execution_archive 的104个小源码实际SHA全部匹配，依赖清单及capture写端没有run_monitor/development_status/8099引用。没有重读原始tensor或全量哈希前置轮次。R046独立启动前回执列出的15源文件实际SHA全部匹配。候选工作树0aa23431、D08 4a12d7b、远端D15 3d2ef80均无tracked修改。monitor.py AST解析通过，未启动或重启监控，未访问任何服务端口。

监控容器启动脚本将`/app`和`/data2/_shared`只读挂载；当前进程PID20472。源码仅轮询只读GET及宿主元数据，未发现修改round/锁/MANIFEST、发送生成请求的路径。这能证明包与产物写入边界，不证明性能零影响。

## 与GPU锁规则的冲突

`monitor.py:83-95`直接urlopen；`engine_poll`读取`/health`、`/v1/stats`、`/v1/cache/status`、`/v1/requests`；`loop:649-656`每2秒调用，未根据GPU_LOCK提前退出。GPU_LOCK只在lock_snapshot中作展示。监听地址由运行脚本设为127.0.0.1:8095。

因此监控并不符合“有人持gpu.lock时任何进程不得连接8095/监听端口”的原文。只读GET不能自行视为豁免；目前没有证据证明GET改变了结果，不作污染或not_met推断。按§8.1共享所有权，未直接修改共享监控文件。下一GPU批次前应由共享泳道交付持锁期间不请求引擎的模式（继续展示只读round/status、宿主指标及带时间戳的历史值），或由用户明确批准监控轮询例外；不能暗中放宽规则。

## T20首失败与建议续跑范围

冻结`equiv_suite/service_capture_startup.py:98-112`只在Scheduler.shutdown wrapper内adapter.finalize生成capture/service_delivery.json；run_scheduler只在KeyboardInterrupt调用shutdown。owned stop发送SIGTERM，专用worker直接结束，最终文件未写。实际arm已产生admissions、sampler receipts及请求响应，不能用这些替代缺失delivery。

修复应只新增冻结版本：专用worker将SIGTERM转受控退出，保留/恢复原handler，确保shutdown/finalize一次执行，并增加真实子进程SIGTERM CPU回归。不得改batch71已冻结来源，不能补造缺失capture。4/4续算独立原始复算CORE_PASS_PENDING_CLOSURE；7性能臂已完成但尚非完整T20接受。用户批准后仅补未完成native矩阵，沿用经R复算干净的项，不整轮重测；续跑轮次/批次须按用户批准登记，不擅自新增。

R040原地55439路径只读，GPU锁已释放，控制器及日志记录的服务进程组均退出。canonical D04仍待处理。结果详见plan/01_测试与调研/results/T20-E2-R040_20261006.md。

后续只读准备：R已核验R049 v3新解释器CPU38PASS、13项真实依赖、候选关键6文件Gitblob匹配；固定startup review尚未签发，不称可启动。

更正：停车四阶段PT实际由既有parking_roundtrip保存，此前“producer无四角色raw”的判断有误；缺口在collector/map绑定，R040a将复用这些raw补清单，不新增未来采集路径。23:40用户已裁定继续；监控锁guard已部署，当前SHA98a49307e05fd1f47f660a6de16749cd7a5f1dbc5889473d3ac6b743b58a533e，run-monitor于23:44:58重启，持锁不轮询模型端口。
