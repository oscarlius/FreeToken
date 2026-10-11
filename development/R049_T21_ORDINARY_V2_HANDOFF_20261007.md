# R049 T21 ordinary 工装：CPU交付状态

更新：2026-10-07 17:22。最新只读 CPU 源为 `/data2/FreeToken/runs/dev_T21/ordinary_runtime_cpu_v3_20261007_170945`，入口 `r049_t21_ordinary_prepare_v2.py`，SHA `dadb4e424e21662005699aae0323fd8cff20239d3279e85d79149a50895a01e3`。候选仍为 `988c9e183c8dca4415fd9b5d02318b26664da619`，父树 `effb996`；98304/.88，trace、暂停均关闭。这里没有GPU测量结论或启动签。

## 本次已交付

- 普通 SSE 请求绑定 payload SHA、原始 SSE 与 event-clock SHA、API UID/usage/terminal、Worker UserMsg 全输入 ID 与进程 birth、Detokenize 逐 token 序列；不调用暂停 ACK。
- 两份留出轨迹采用 R046c 封存的 messages，按原顺序回放；每条输入 ID 对照原 worker 证据，不重新生成工具会话，不截短 seed_real。两个角色分别写独立目录。
- 冷请求保留 frozen build_text 的 32052 正文目标、128 输出、关闭 thinking；实际 candidate TokenizeManager 验证渲染后为 32064，且与前端重建逐 ID 相同。
- 两路沿用 candidate make_messages 的不同内容 32000 输入，普通请求经 barrier 同时发出，每路绑定512实际输出 token，并校验首非空输出至终态的共同时间窗。SSE分片数不充当token数。
- 六个生产进程与三个D0诊断进程按卡面顺序隔离。速度来自普通流的首非空输出/终态单调时钟和API实际completion数量；D0只用于UID绑定的miss/H2D/swap成本。
- 比较使用实际输入、token ID、正文、reasoning、工具名称及参数。API随机 tool_call.id 保留在完整原始响应中，排除在模型等价比较之外（候选 openai_api.py::_tool_call_id 使用uuid）；PID/UID/路径/时间戳不参与数值比较。
- 实际 Parsed arguments 和环境差异全部保留；政策是分层比较中的唯一科学变量，端口/PID/诊断输出路径作为过程记录。分配API/TCPStore成对端口，生产wrapper只接收serve参数，D0wrapper保留可导入spawn目标和正常SIGTERM退出。

## 新鲜验证证据

| 证据 | 结果 | SHA256 |
|---|---|---|
| Linux实际CPU suite | 22 PASS，CVD空/socket guard；真实spawn及SIGTERM、入参/返回值保持 | 353293fd9946e366e89d0bf65fce7e05bfcd5abf9062da6cc35dff3cb9e81b1d |
| actual_candidate_cpu.json | 目标Tokenizer/FrontendManager一致，512专家画像builder/reader CPU样例通过，CUDA未初始化 | 02ebadf6f4405cc4b105f5ee9cacdf1009bfb6c5393aadebd6179db3d2cf8f5b |
| nine_arm_cpu_rehearsal.json | 九臂文件写入通过；CPU fixture训练源、不同正式路径，明确**不是正式FILEDRY** | 3dc63c8742f79fc96157b9c99965f389f5e0ce71cdb3b41d8640a7b6cb3dcf10 |

Linux suite日志 SHA：`3ba21bca49ef5f8e107713122ff9151d0e57e0cb613ec6b31698aa5539fbc626`。三份报告及22项实际依赖SHA详见 [本地证据指针](R049_RUNTIME_CPU_V3_20261007.json)。独立R只读预审PASS、无P0；这项预审不签GPU启动。

## 尚待

R046c measured与训练路由尚未产出，正式profile只允许取其G_seed12k/route。之后必须在同入口/同用户/正式执行路径完成真实FILEDRY，再取独立R启动签；CPU fixture画像不得用于正式测量。R059原v1 NOT_MET与纠正依据均原样保留，等用户裁定，当前后续GPU未启动。
