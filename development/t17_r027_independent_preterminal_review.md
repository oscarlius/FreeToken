# R027 首层共享前缀诊断的独立预终态审查

同类历史比较：R023 原 4096 分块输出 index36 分叉；R025 改为 7680 分块的诊断逐位相同。R027 仍在测量，不存在可用于替代原 T17 判定的新终态比较。

独立 verifier 只读核验 `prefix_numeric_65b32b3fc54a` 的 18 份冻结来源、CPU 报告 SHA `85cf811e1d0d91c8c6e6e0dbd826edfc80a9793f7061b3cb7e4f653a8148ec7c` 和实际 warm 工件；没有操作 GPU、锁、服务或封存目录。

warm donor device8193 的共同绝对区间 `[512,8192)` 被实际子块拆为 `[512,4608)` 与 `[4608,8192)`，每段包含 conv_in、q、k、v、g、beta。h 的目标行由 `(8192-4608)/64=56` 计算；cold device8257 的实际 track 边界8256/h57与目标8192/h56分列。包装函数把原参数及返回对象原样传递，缺少实际 `(output,h)` 返回时拒绝结论。

终态审查须加载全部 warm/cold 原始张量，逐项核对保存 SHA、shape、dtype、绝对区间与不同字节数；GPU runner 本身只保存证据，没有做张量比较。

证据限制：runtime receipt 未记录显式 decoder index/layer_id，安装器选择首个 `_is_linear` 层；应表述为“首个线性 GDN”，不能称该 receipt 独立证明 decoder0。receipt 证明原 kernel 实际返回 h，但不记录原 kwargs 的 `return_h=True`，不能夸大为 flag 来源已逐项绑定。

张量写入使用 `exists()` 后 `torch.save(path)`，没有独占发布或并发覆盖回归。不同服务的私有目录降低碰撞机会，但不能据此声称写入原子；这是本轮工装的证据发布限制。原始工件及冻结来源保持不变，后续工装修正应另存新来源，不能回改已执行来源。

本审查是终态比较的前置检查，不授予 kept、T17 接受、E2-base.1、T10 或性能结论。
