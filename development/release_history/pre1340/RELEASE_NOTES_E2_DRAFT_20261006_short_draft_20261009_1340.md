# E2 发布说明草案

E2 候选为 `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`。分支已创建；部署、推送和生产服务未批准。OPSv2 的服务器 CPU 归档为 39 passed、0 skipped，不能替代生产验收。

回滚保留 `184c965…` 的普通 8192 / 49,152。H2 已验证 HEAD、argv 和历史 Prefill 正则，但 ignored 工作树内容非空，当前阻断且不自动清理。历史日志没有 API usage 三字段，不能替代 SDK 收据。

R056、R058 约 378 MiB、R061f chat OOM 注入及 128/900 默认值均为有限历史边界。R045 新 `481` AIPerf CPU 计划为 2 服务 / 4 generation calls，部署后等新 admission；旧 v18 停止。R067 已批准待实际：4 格 `P8192/P8256 × T1/T64`、最多 10 服务 / 14 调用，hot=481、cold=D20 d50 one-shot 8 fresh；≤64 等四格 ALLPASS，not_met 为已知缺陷且 E2 发布继续。

E3 禁用 8095/8096；Strata 22/345 未批准。所有部署、推送、停服、回滚及 GPU 执行都仍需独立实际批准。
