# D10 实现状态

`IMPLEMENTATION_INCOMPLETE` — 已完成默认关闭的 CUDA streams/events 原型、两 lane
cache/state slot 别名防护、CPU 合约测试和仅限开发的二请求 fixture；尚未实现以
Qwen3.8-Flash-Next 目标模型为主体的服务级错相位 decode。

不应运行任何 D10 GPU 正式轮次。正式轮次唯一有效的入口仍应是目标 Qwen 模型、R045
AIPerf 0.11、原两条冻结 `128/ignore_eos=false` 提示以及新增 `256/true` 变体。fixture
不能替代其中任一项。

阻塞不是 GPU 可用性，而是代码语义未闭合：现有 Qwen3.8 `Qwen4ExpModel.forward` 在一个
`Batch` 中完成全部层，`OffloadMoeCache` 同时把 LRU copy plan 和 bank slot space 作为
全局可变对象。安全实现还需要 lane-local LRU/cache partition、每层两 lane 模型执行、
KV/GDN/PLE 状态提交和采样异常语义的集成。精确源码边界与顺序见
`night_d10_service_integration_gap.md`。
