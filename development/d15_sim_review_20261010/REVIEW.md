# D15 阶段 0 独立复核（2026-10-10）

## 判定

KIMI 的 LRU 四组校准可由独立 CPU 回放复现后，才可作为 D15 离线研究的基础。
先前版本错误地把 `plan_profile_adaptation()` 的旧 docstring 当成运行时事实；该判断已撤回。
候选 `825655305d69df94d3d2f79c3f416234bfe890e6` 的实际调用链为 scheduler →
`AdaptationBoundary.run()` → `_register_adaptation_boundary()` → `issue_proof()` →
`plan_profile_adaptation()` → `apply_profile_adaptation()`。在已排空已注册流且完成事件可查询时，
`RuntimeAdaptationCoordinator.issue_proof()` 会签发 proof。因此 PA 是**已实现但未 GPU 验收的候选策略**。
离线 PA 数值可以指导阶段 1 的候选臂，却不能替代逐 token 等价性、D0 对齐和 T21 验收。

静态 `P` 画像预置的收益仍须以独立校准为前提。PA-lag1、Belady 和 NOINV 是变体/上界假设，
不能作为当前实现收益。

## 复算范围

`verify_lru.py` 直接读取 E2-R046g 的 `route/*.json`、`route/*.npz` 与
`d0_decode.json`。它没有读取 KIMI 的 `stream_*.pkl`、`calibration.json` 或
`results.*`。模拟的仅是当前可执行基线 LRU：全局槽、raw route 去重、命中先更新
usage、`(usage, slot)` 受害者排序，以及每个 prefill 的 `[0,1024)` 清空。

G_two 保持 D0 快照的口径：79 个完整 decode 步，再加第 80 个记录步的层 0--10。
脚本输出的 `independent_lru_calibration.json` 是本次复核的数值证据。

## 原始输入绑定与结果

远端只读输入树（四组 `route/route-*` 和 `d0_decode.json`，共 16,840 个文件）的
聚合 SHA-256 是
`6750c3367e2744fd5c4134c99ca6040503b8312535c7aaa6db90c0a599b9794a`。
候选 worktree 的 HEAD 是
`825655305d69df94d3d2f79c3f416234bfe890e6`；其两份判断语义的源文件 SHA-256 分别为
`offload_cache.py=9c910f4ffad723ac4da837cc53d2806dd1e566a409b28ea454f22bd3308251f7` 和
`offload_kernels.py=1646d7b8b6f1a0d58c4538eb4cd6579d3d02134bee1e9bd11b555d4f033ba518`。

独立回放的 miss_rate / 相对 D0 偏差为：

| 组 | miss_rate | 偏差 |
| --- | ---: | ---: |
| G_seed12k | 0.375286709 | +0.000000 pp |
| G_seed_45k | 0.355428120 | +0.000000 pp |
| G_seed_real | 0.385862963 | +0.000000 pp |
| G_two | 0.426173702 | +0.000000 pp |

所以 1 pp 的 LRU 校准门通过。该结果不解除 PA 的 live-runtime 阻断。

## 运行边界

只使用远端 FreeToken venv 的 CPU 进程（`CUDA_VISIBLE_DEVICES=''`、OMP/MKL=1、
`nice -n 19`）。不访问 GPU 服务，不改 E2-R046g/R049 原件，不修改 KIMI 目录。
