# Codex 对第二轮交接的回报

截至 2026-10-04 23:07 CST；后续 GPU 结果以轮次封存为准。

相对坐标问题影响实际初始状态。非零前缀命中、剩余预填进入层优先分块时，
首子块的 `cached_len=0` 会触发 GDN recurrent 清零、conv fresh 路径以及 PLE
初始上下文替换。它不限于 n-gram 或快照元数据。详见
[源码证据链](D14_initial_state_impact.md)。修复后输出是否与全冷计算一致，
R023 已给出首个冷/热不等价反例；完整 T17/T10 接受尚未完成。

| 项目 | 结果与边界 |
|---|---|
| 共用 T16 | 一个测量实现：`t16_candidate_runner_full_tail.py` + `t16_full_tail_base_runner.py`；事件数取父树实际事件及显式尾段覆盖，不再按卡写死。R019/R021 真实夹具保留；规则第6节已添加同步修复要求。共享启动/冻结入口 Linux CPU 55PASS，历史副本不改。 |
| R021 | `failed_harness` 封存；43个原始工件哈希保持。 |
| D14 T16 | R022/batch50 四臂完成、独立复核PASS、D04封存。D0/默认路径128 token全文一致；13/13预填事件及搬运计数一致；74个原始工件校验通过。 |
| T17 | R023/batch51 为 `not_met`，已独立复核、D04只读封存，76个原始工件未变。8192边界短尾段：同一8257输入、两臂128token，首分叉index36。D2D恢复四角色通过，续算后GDN conv/recurrent及PLE conv不同，ngram相同。其余边界未完成比较。 |
| T10 | 尚未重跑。实际历史R006/R017均为普通预填；旧33/36不能直接与层优先重跑作修复归因。后续同一统一树分普通和层优先两项实验，详见[协议](T10_RETEST_PROTOCOL_20261004.md)。 |
| D07默认门 | R024/batch52已用55PASS冻结共用入口启动，准确D06父树与D07候选通过预检；GPU结果待测量与独立复核。 |
| E2-base.1 | 尚未创建/接受；T17失败维持接受阻塞。D06 R020默认门已过，D07 R024验证中。 |

数据版本已发布并只读封存。本地与服务器字节一致：

| 清单 | 服务器路径 | SHA256 |
|---|---|---|
| FTD-20261004-1 | `/data2/_shared/runs/ft_releases/FTD-20261004-1/manifest.json` | `836217380206fef106aa71dd6713cab0f18222932b9f884ba36d5ac4130ef014` |
| 不可变勘误1 | `/data2/_shared/runs/ft_releases/FTD-20261004-1-erratum-1/erratum.json` | `c360bb0de7fc9575f9edf6ca800803ffa0de5e72e735a5307e9d84d19f9fc8f8` |

本地副本在 `plan/data_releases/`。初版清单已有缺陷说明，但逐项输出层标签
不完整，所以保持初版封存并补勘误。勘误将 R006/R017 命中续算和冷热输出、
R008/R009/R009-p64k 暖回放输出，以及实际含60题证据的 R009 多轮质量，共
八条子结论明确标为 `hypothesis`。冷请求时延和冷输出、原始工件与测量判定
保留。发布不等于 D14 接受，不等于科学归因或质量复测完成。

R022 证据：round SHA `976ac037e235dbb230dd9dcdee4a0ef3ea7dbe77c8e98e117ec339f0104f9d1f`；
MANIFEST SHA `91778cbcdc41ff9ad491758c39c382826cd0587706a87a62eaf23e9af59f81f0`；
独立review SHA `87bf64185a6897493a20a0ab92905494a4e626cb0ee876ca7c36e173105ad2bb`。
冻结reviewer源码随轮次归档，已只读重放并复现PASS。

R023 证据：round SHA `92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d`；
MANIFEST SHA `ef2d98846aa8a23c8168596d641e0c2614e0a2dac47f88e07d099b27c0391cfa`；
review SHA `86bebc276f56c47299dfd7e5da0385f1c4c9bb0166381c80c917d5c5551d5384`。
独立复算、D04历史检查和全部MANIFEST校验通过，判定为实测反例而非工装失败。
详见[反例及归因边界](T17_R023_COUNTEREXAMPLE_20261004.md)。

后续先隔离捐赠状态与预填分块路径的影响，保留原T17严格门及失败证据。
D07默认门可独立验证，但不解除T17阻塞；通过前不合成接受版E2-base.1，
不启动接受性T10、60题或多会话/路由基线。D08–D13及TP继续冻结。
论文v4.1仍由总负责人编辑；本回报没有改论文。
