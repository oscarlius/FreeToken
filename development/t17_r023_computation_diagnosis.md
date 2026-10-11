# R023 计算态差异诊断

R023 已只读封存 `not_met`，实际结果见 [T17 报告](../plan/01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md)。本文件记录下一诊断的依据；没有新 GPU 结果。

四角色 donor→恢复源→目的复制按 uint8 完全相同，短续算实际命中 8192，长续算首子块 has_initial_state=true。相同 8257 输入的 cold/hit 仍在第 37 个采样 token 分叉，8256 计算态三个浮点角色不等，且第 0 层已经有差。

| 原始观察 | 路径 |
|---|---|
| Cold | cached=0 → anchor 512 → layer-major outer 7745 → children 512→4608→8257 |
| Hit | cached=8192 → 四角色 D2D 恢复 → 普通 prefill 65 → 8257 |
| 共同约束 | 同一候选 e4f3202、精确 IDs、模型、compiled extensions、温度 0、128 token、device-only state |

候选与服务器同提交 Git blobs 已核对。`scheduler/prefill.py:175` 允许 layer-major 一次准入整个剩余 prompt；`engine/engine.py:1081` 按 `FT_LM_CHUNK`（默认 max_extend=4096）切内部块。`models/qwen4_exp/model.py:148` 按层处理各块；`gdn.py:158` 将每块长度交给 causal_conv 与 FLA prefill，FLA 的逻辑 chunk 为 64。PLE 和专家矩阵也按块处理。

这证明两臂执行分块不同，构成可检验的数值路径解释。最终张量不等不能单独证明恢复错误或非因果计算；也不能仅凭源码将差异归为合法舍入。需要边界状态定位。

下一新轮使用 `FT_LM_CHUNK=7680`，保留 anchor 设置与实际输入，将 cold/供体公共前缀的内部块统一到 `512→8192`，之后分别为 cold 的 65 尾块和 hit 恢复后的 65-token 续算。纯测试观察器在 8192 捕获各实际层状态，避免后续尾块覆盖；并比较 8256 的正式捐赠状态、完整 token IDs 和文本。

- 8192 已不等：定位到前缀计算/块投影阶段。
- 8192 相同，8256 不等：定位到后缀计算或恢复后的元数据/内核阶段。
- 两边界和输出都相同：支持原 R023 分块/数值路径解释，原协议的 `not_met` 仍保留；此诊断不能替代原门。

观察器只调用原方法一次，保存实际层/UID/slot/坐标及即时 CPU 副本，不修改请求、状态池或生产源码。缺层、重复或坐标冲突均停止结论。CPU、正常 spawn 与独立源码审查完成后才冻结并分配新 RID/batch；GPU 全局锁、源码/扩展绑定和所属进程停止仍沿用已验证协议。
