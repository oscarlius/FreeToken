# R052 T11 cache evidence CPU fixture repair

本次只更新 `r052_t11_replay.py`、`r052_t11_followup_prepare.py` 及其定向测试；候选引擎、已冻结轮次、卡面和正式目录均未改动。

- API `usage` 仍强制真实 `prompt_tokens` 与 `completion_tokens`；缺失的 `prompt_tokens_details.cached_tokens` 记录为 JSON `null`，不把它伪造成 `0`。
- 每次请求从原始 SSE `id=chatcmpl-{uid}` 提取唯一 UID；存在 `ft_dev.uid` 时必须一致。目标与续问都在服务退出后按同轮 `d0_prefill.jsonl` 的全局 `chunk` 顺序，以同 RID 首条记录作为 admission；之后每条必须 `cached_tokens=0`，且 `admission.cached_tokens + all new_tokens == API prompt_tokens`。这覆盖 `token_budget`、`anchor_cap` 与末段 `continuation` 的真实形状，不依赖 `seg_reason` 猜测。缺 D0、错误 RID、非零后续、UID 不一致、prompt 合计或 API/D0 不一致均拒绝。
- target/follow-up SSE UID 必须不同。续问实际 response（含 payload、usage、stream events 与 UID）在 D0/分类前先写入 `followup_raw.json`；故边界、D0 或 mismatch 拒绝仍保留已收到的 raw。不会以 `0` 回退。D0 证据随后才触发 H-hook/H-bug 分类。
- dry-run、startup review、owned launch 和 raw measurement 升至 v4；既有远端 v3 冻结与 dry receipt 保留，不能满足 v4 启动门。
- 对已有 T11 卡面的重叠/空档加入可判定性守卫：`floor <= 13376` 或 `13376 < cached < floor` 时保留原始事件和 D0 证据后报 `hypothesis bounds do not distinguish observed result`，不输出 H-hook/H-bug。目标阈值使用该次 API 的真实 prompt 和 completion；历史 56 是重算量，不作为输出预算。

本地定向回归：`python -m pytest development/tests/test_r052_t11_replay.py development/tests/test_r052_t11_followup_prepare.py -q`，35 passed，py_compile通过。Linux同组定向回归35 PASS，CVD为空、socket guard生效、torch未加载、五份源码compile通过；小报告 `/data2/FreeToken/runs/dev_R052/cache_evidence_cpu_20261007_130907/report.json`，SHA256 `0d07bdf1db9abcfa5e6b6e8fde6f9d50c73eb9c5495233c837d4a2b7defddb9e`，本地指针 `R052_CACHE_CPU_LINUX_20261007.json`。实际动态端口真实 file-dry v4 以及独立 R 启动复核尚未完成；未启动服务、拿锁、分配 batch 或创建正式 R052 轮次。

独立R已读取小报告并核源码SHA，复核PASS（仅CPU语义修复），未发现具体缺陷，见[R052 CPU复核](R052_CACHE_CPU_REVIEW_20261007.md)。该结论不代替真实FILEDRY、正式R启动签字或T11 GPU判定。
