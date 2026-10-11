# D08 v2 / D10 η：本轮结果与恢复

真实写入：2026-10-11T00:57:36.057768+08:00。候选 481d3a7。独审结论 **SUPPORTED_FAILURES_AND_RESTORED**。

| 项目 | 本轮终态 / 结果 |
|---|---|
| offload 单路 X lane0 | 1 调用，1179 输入 / 256 输出，length；AIPerf ITL 33.1444148745 ms，即 **30.1709957405 tok/s**。原始输入首行逐字节一致。 |
| D10 η | **failed_harness**：脚本追加的 `--moe-collect-stats` 不在 481 的 CLI 参数表，模型加载前退出。无图回放、拷贝、T_comp/T_copy/T_both 或 η 数值。 |
| D08 hybrid | **failed_harness**：1 服务、0 生成调用；240 秒 readiness 限时在 PLE/专家加载未完成时触发。无单路/两路速度，不能判断 H1/H0 或预测区间偏差。 |
| 原清理载体 | failed，OSError(98)。原 PID/组已退出，GPU 4 MiB/无计算进程；TIME_WAIT 使 bind 检查暂时失败。载体保持原样。 |
| root 追加恢复 | 等端口可绑定后，重验死进程/组、GPU、端口，精确核对锁 token/inode/device 后释放。Restore06 恢复成功，未回滚。 |
| 481 验收 | 98,304 窗口 / **2700 槽**；官方 SDK 512/8257 输入，各128 length。与首次冷基准 df77cb14… 的 **15 个稳定字段逐项一致**。当前三进程身份、锁、serving 健康状态已核对。 |

**D08 v2 已冻结：** 没有第二个分流配置点；预测每路19–27不作判据；H1仍须两路≥19.6，H0仍须两路≤17.0，且后续若满足H0，只能写“关闭当前执行器（含固定开销）的两路收益”。本轮未测得两路，不关闭当前执行器或 hybrid 机制。控制器去除 FT_DEV_* 环境变量；启动 ServerArgs 明示 moe_collect_stats=False；未启动 D0/trace 性能采集。

**max-fetch 记录：** argv 未显式覆盖，实际启动 ServerArgs 为 `moe_hybrid_max_fetch=-1`。481 Git blob 核对一致：`server/args.py:759–765` 定义 CLI，`engine/config.py:67` 默认−1；`engine/engine.py:758–787` 按带宽画像选择比例，画像不可用时回退 cap=1；`moe/offload_cache.py:152–161,1216–1231` 为每层每解码步的搬运上限/比例，剩余失误由CPU计算。启动未到达自动解析阶段，**生效比例/固定cap及 hybrid 槽数未取得**；不拿R048b的cap=3代填。证据为 evidence/window02/ROOT_SOURCE_SEMANTICS.json。

**时间和预算：** window01 是 CRLF 输入复制导致的 pre_gpu_failed，0服务0调用、未停481，原件保留；仅二进制首行复制修复后启动window02。实际窗口 **00:41:01→00:53:31，共750.646秒（12分31秒）**，含恢复，小于2100秒。新hybrid服务1个，测速生成仅offload参照1调用；恢复SDK2调用另属已批恢复门。计时前已结束CPU开发/独审，offload和η入口已记录uptime/R线程；hybrid未发测量请求。

**观察与纪律：** Restore05观察23:20:44→00:41:18已标“截断”，不是隔夜通过。Restore06从00:53:31重开观察至09:00，目前观察中。Ollama保持停止；未推送，未改论文，原始终态均保留。跨20:35的旧批次速度比较须标“环境不同”；本轮无hybrid速度可比较。

**工装缺口：** CPU准入没有解析η最终实际引擎argv，漏掉不支持的CLI选项；未来应按冻结基线解析后设置受审查的配置字段，并加入精确入口CPU用例。D08的冷启动预算和TIME_WAIT清理检查也需在新工装中核对。以上仅记录原因，本轮不追加GPU，不将工装失败登记为机制负结果。

**独审与证据：** 最终独审JSON SHA256 `199410a807d05ef07596ea480d1cbeae2cec1df78abd3b7fe5298c2668634a8a`；原始测速、失败、清理、恢复证据在 `evidence/window02/`，SDK和逐项比较在 `../morning_restore06_20261011/`。D05/D09 CPU一页结论见 `../d05_d09_tail_cpu_20261010/ONE_PAGE_CONCLUSION.md`：13,376/20,160精确复现，按不同拒绝条件判**不同源**；修复仅方案，节省128/122个续算重算token，不是解码提速。
