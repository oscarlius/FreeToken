# R062：D12 默认关闭路径门

待执行候选 `8f6a912ea6066f192c37dc74435efc9da0c7591c`，对照父版本 `effb9969706922ddad9e59b96377e46469ebe97f`。使用实际 Qwen3.8-Flash-Next-NVFP4、98,304/.88、4 个独立服务、48 次生成请求，按 T16 原判据比较 token、全文、prefill 分段和 D0 搬运统计。

本轮仅测试 `moe_prefill_routed_only_max_tokens=0` 的默认关闭行为。开启按需搬运后的 D16 数值和短后缀性能属于后续验收。

实际执行入口：`/data2/FreeToken/runs/dev_T16/d12_default_gate_v2_20261008_1638/d12_default_gate_runtime_v2/r062_owned_launch.py`。v1 的参数名错误由独立审查拦截，原 denied 记录保留；v2 对实际 parser 的字符串 `"0"` 做每臂与终态比较，缺键、非零或其他参数变化均拒绝。

- 产品 Linux CPU：60 PASS / 3 skip；实际 native 来源与 candidate/parent SHA 已绑定。
- v2 入口 Linux CPU：33 PASS，report SHA `14a0026aab2013e58d0396c96ff037d5fe769ae7addc82625e30032f189abeb0`。
- 同入口 FILEdry：`E2-R062-gate-D12_file_dry_run_v2.json`，SHA `cead8f032b24eebee84990997f6073ce818955785363ef1d1544bfe6b5cbf81e`。
- 独立启动签：`E2-R062-gate-D12_startup_review_v2.json`，SHA `f6dacecf2bd17866f736d16588d9f91a8f8cfcba41ea41316f1409eecacffa6f`。

FILEdry 与启动签均在 `/data2/FreeToken/runs/dev_T16/reviews/`，已封存。未分配 batch、未建正式轮次、未启动 GPU/服务。新增数字轮次按 `plan/CODEX_HANDOFF_20261006.md` 第八节第4条，在执行前单独批准此具体范围；D12 开发工作已按第十七节授权完成上述准备。
