# T06 去掉暂停开关的 CPU 源码审计

记录时间：2026-10-07 13:44（ssh9 date）。依据交接书第十三节。只查当前代码；没有读取旧轮次原始数据、连接模型端口、启动服务或 GPU。

UID 绑定可以脱离暂停开关：openai_api.py 的普通聊天 SSE/非流式回执均为 chatcmpl-{uid}；prefill.py 的 seg_reqs 保存同一 req.uid 为 rid、new_tokens 与 cached_tokens；D0 prefill JSONL 持久化该 reqs。第一段记录缓存命中，续段 cached_tokens=0；所有段累计 new_tokens+首次 cached_tokens 应等于实际 API prompt_tokens。不能只按 chunk 全局编号或 seg_reason 推断是哪次请求。

但当前 T06 客户端不能直接关暂停。scripts/agent_trace.py 的 route-evidence 模式严格要求 ft_dev ACK，route_analyze.py 也要求 ft_route_ack/v1 的连续 request_seq 与 completion_tokens_cumulative。generation.py:705–715 仅在 DEV_PAUSE_ENABLED 时输出 DevStreamAck。D0 的 UID 字段解决请求关联，不能替代逐 token ACK 或用 SSE chunk 数充当 token 数。

后续 R046c 可把客户端改为普通 SSE id + 实际 usage + D0/route 同 UID 绑定；如仍沿用旧 ACK 验收，就由新版本外部观察器记录真实后端 ACK/DetokenizeMsg，保留连续序列/累计输出计数，再与 API usage 和 route 文件交叉核对。不得伪造 ACK、改旧冻结文件或直接放宽旧 reader。G3 的 trace ON/OFF 暂停均关，其他配置完全一致。该改造属于本轮必需工装，CPU 回归后须新真实空跑与 R 启动复核；尚未实现或获得 GPU 结论。

当前更直接的结论：T06 不必为了 UID 打开暂停；删除暂停依赖需要同时迁移 ACK 工装，单改环境变量会确定性失败。
