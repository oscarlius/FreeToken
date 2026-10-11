# D06 客户端阅读说明

脚本：development/e2d06/scripts/multisession_probe.py，源码候选03692633df48456fb0baa78de7b64e5628a12ab1，准确SHA见d06_candidate_server.json。公共参数和四个子命令沿用D06卡。选定Qwen标准chat-template模型；tokenizer路径可配置，不能用它绕过非标准编码器限制。

| 命令 | 主要输出 |
|---|---|
| two-decode | reps[].per_way 的ttft_s/decode_tps/completion_tokens/t_first/t_last/token_timestamps；共同窗口秒数、实际ACK token总数、总吞吐；每路提示SHA、前缀重合数和实际前端长度 |
| stall | max_gap_s为解码全序列最长ACK间隔；max_gap_during_interference_s为跨干扰窗口的最长间隔；interference_tps窗口为预填请求发出至首次实际内容；prefill_ttft_s/new_tokens；两个完整request记录及前端证据 |
| pair-short | 两TTFT、实际perf发送skew、D02 reqs UID证据推导same_prefill_batch；缺证据时null和原因，不能从相同提交时间猜同批 |
| h1 | 每rep none/idle/prefill的事件实际起止与H步时和；执行顺序prefill→等时长idle→none，delta_H=prefill-idle；事件内counter、事件后counter分别保存；event_extra_h2d_bytes/miss_total为事件内实际差 |

所有stream计数来自ft_dev_stream/v1 sampled-token ACK；首TTFT取首次实际content。共享perf原点及墙钟锚点用于并发/干扰测量。用D0 step开始时间属于[event_start,event_end)的记录求事件计数；先有事件两侧实际UID数据才允许空区间为0。每条D0计数必须是明确非负整数；step允许从0开始。H步timing通过同UID/step/t对齐，未完整覆盖为失败，不写假零。

--ctx及--prefill-target用于精确实际前端ID数。文本种子放在共享说明之前，不同提示只共享模板级前缀；冷prefill每rep使用新文本种子并记录SHA，不能将后续热命中混作冷样本。agent_turn保持实际trace及cache证据。

请求总超时通过关闭真实socket中断心跳/慢headers，失败取消同伴、join owned线程并非0写独占error JSON。pause还将客户端timeout上限传给服务端入队deadline；dev端点实际timeout上限10秒、idle上限60秒。超限/失败/不完整证据都明确停止。

T05服务端设置FT_DEV_PAUSE_ENDPOINT=1、FT_DEV_D0=1、FT_DEV_D0_PATH、FT_DEV_D0_TIMELINE=1及显式20000时间线步上限；客户端同样设置FT_DEV_D0_PATH。T16默认门不开开发开关。当前69项Linux CPU与实际tokenizer等值通过；GPU门和正式T05待执行，参见d06_progress.md。
