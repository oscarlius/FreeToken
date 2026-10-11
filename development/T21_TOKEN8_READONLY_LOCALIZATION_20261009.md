# T21 第 8 token 分叉：既有证据只读定位

2026-10-09。范围遵循 01:00 指令第 13 条：只读已有 route/state、普通输入与 token 记录、服务日志和候选源码；未新建采集工装、未运行模型、未修改封存轮次或候选。

结论：分叉已定位到 R049c 的 PA1 第二条冷请求（UID 1）第 8 个输出 token；现有证据不足以把它归因于某一次专家置换。旧候选存在一个已经单独修复的反向槽位归属缺陷，但没有该请求的运行时映射和 bank 快照来证明它导致这次分叉。R049c 的 `not_met` 保持不变。

## 已确认的请求与运行条件

- 轮次 `/data2/_shared/runs/ft_rounds/E2-R049c`，候选 `988c9e183c8dca4415fd9b5d02318b26664da619`；远端 `/data2/FreeToken/wt/e2d15` 本次读取得到同一 HEAD，tracked clean。
- PA1 为 `profile+adapt`，`adapt_every=1`、`swaps=1`；实际 OFFLOAD、layer-major、98,304 / 0.88、图上限 2，D0 关闭。日志确认 1,676 个画像专家预装到稳定槽 `[1024,2700)`，没有记录每一步实际置换是否发生。
- 画像由 `E2-R046g/G_seed12k/route` 生成，画像 SHA `8fd705d5556c43d94d9a74b963b7942332b2ae05d3e02bc7b3292dca457c206e`。这是训练画像的路由，不是本次 cold32k_2 的路由，不能用它填补分叉时的状态。
- cold32k_2 与保留 L1/P1 输入相同：32,064 token，输入 ID SHA `f6fc1b4fd7446ceadb0ab713d45c47bc5259bc9a611728c8c1bfafbd2e37d790`；均输出 128 token、finish=`length`。独立复核记录前 7 个输出相同，第 8 个对照为 `103988`，PA1 为 `103781`，完整文本也不同。
- PA1 原始普通 token 记录的 UID 1 前 8 项是 `103715,103853,103725,104003,98151,97320,3709,103781`。第 8 项时间为 `1791440730278312747 ns`；这是输出观察时间，不等于内部专家置换时刻。

## 源码路径与归因边界

`python/freetoken/moe/adaptation_boundary.py` 的边界顺序为关闭新 launch、drain 前一 forward、同步 engine/scheduler/prefill streams、取得 proof，再 plan/apply。`offload_cache.py:952` 规划替换；`:997` 的事务复制全部 bank、更新映射并同步发布事件，失败时回滚。该执行结构本身不能证明此次运行已经执行了某次替换，也不能证明某层的数值保持一致。

旧候选 `offload_cache.py:1040` 更新提升专家的新稳定槽时没有清除其原 volatile 槽的反向归属。独立修复 `481aa4d` 清除旧归属并检查双向映射一致性；R050a/b118 已完成含该修复及回滚回归测试的 `8256553` 默认关闭路径门，并于2026-10-09 01:59封存kept。该缺陷可以静态解释潜在映射被后续失效操作误清的风险，**尚不能证明它就是 R049c 第 8 token 分叉的原因**。R050a 默认门通过也只证明默认关闭行为，不证明 PA1 开启行为修复。

本轮文件清单没有模型 `.pt`、逐步 expert route、slot map、bank row、adaptation receipt 或 logits 产物。普通 observer 只有输入、token、服务/worker 出生标识；serve.log 只有初始化和批次摘要。因此只读定位在此形成明确证据边界，不能继续推导首个数值分叉层、置换提交点或 CUDA 数值误差。未为此新建工装或 GPU 范围。

## 绑定与后续约束

| 既有证据 | SHA-256 |
| --- | --- |
| `round.json` | `ae796848a05c992392d26ef375463e8968188214f1999f2697797a518e0f8ca8` |
| `MANIFEST.sha256` | `ad9f5467655162d3f618901ad8ae7f3e775cbb3f1d4db3a49e7adf3dfb878498` |
| `independent_terminal_review.json` | `a34a8ec7a7108d17e0e0140bd43cee2eeae5e0c223406d047c94f7eb94b91ce2` |
| `PA1/ordinary_observer/tokens.jsonl` | `c4ec13df671baffb7528b05c219dd69490da986b224b31f064dae3c5427cb197` |
| `PA1/serve.log` | `3b7a5c2a430104a84a7ffcd1bea01ad577a66a6c2b47cc213eed3edf4ba1ca35` |
| 候选 `offload_cache.py` | `5d7a9b6267baff692f58597dcbad0aceaae2eedad21b44e8b929f6c1f2865df0` |
| 候选 `adaptation_boundary.py` | `9fe26a0268d6a38131f1fbe9f26f18b3a0167636a53854a437c957a14081231d` |

只读调查已完成到现有证据所支持的边界，根因仍未确定。D15 的 Strata 延迟置换/辅助线程与画像持久化开发须等 R050a 完成，并在独立分支默认关闭；T21 后续开启臂仍需具体范围审批。该 E3 工作不阻塞当前发布门。
