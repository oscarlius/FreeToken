# D05/D09 尾部续算状态：一页 CPU 结论

写入：2026-10-11T00:31:38.348227+08:00。源码 bd57cfd；仅 CPU，未开服务、未用 GPU、未实施修复、未推送。

**结论：两数已复现；按预登记“同代码且同拒绝条件”判据，不同源。** 非作者在隐藏 CUDA 的服务器上重跑 D05 v6 / D09 v7，均 exit 0，独审为 ACCEPTED_CPU_SCOPE。

| 问题 | 已验证结果 |
|---|---|
| 复現门 | D05 follow-up=13,376（finish=13,554）；D09 UID1 match=20,160。真实 LinearStatePool、CacheManager、Scheduler._forward 与 Req.complete_one；bd57 源码与 Git blob 一致。 |
| Q1/Q2 | 20,282 carrier 已原生保存（idx=1），到达完成捐赠；_commit_d09_exact 确实调用一次，old_cached=20,160、非 D09 handle，原函数返回 False，拒绝条件为 cache.py:655 的非零旧 hybrid handle。 |
| Q3 | 原生 attention/linear.py:127–139 在 0→20,224 前填产生 ((20,224−1)//64)*64=20,160；raw 也记载 donate@20,160。20,224 是段结束点，不是该段的 track，故少一页。 |
| Q4 | D05：cache.py:568–577，align_down(13,554)=13,504 不等于完成长度，且 decode 未形成对应 track，保留 13,376。D09：cache.py:655 拒绝已有非零 hybrid handle 的 exact commit。拒绝条件不同，不能合并为一个缺陷。 |

**Q5（仅方案，分别默认关闭）：** D05 在 decode 到达 P=13,504 时保存真实 P 状态并晋升，不能把 13,554 的状态标成 P（约 **2 人日**）。D09 保留旧 prefix 的页/状态所有权，为 P=20,282 增设受控 exact pointer，末页私有/COW；失败回落现有 guard（约 **3 人日**）。详见 SUPPLEMENT_Q1_Q5.md。

两案 CPU 必测 **conv、recurrent、PLE** 在 P 的状态，以及页/槽/引用守恒、恢复、淘汰和双 reader。实现后须分别申请 T16 默认关闭门：相同发布参数和冻结输入，现有 T16 协议完整执行，基线与候选默认关闭的输出逐 token/逐位一致；CPU 通过不替代 T16，启用路径另行验收。

**天花板仅是续算少重算的 token：** 此例 D05 对齐提升空间 128 token；D09 exact 边界提升空间 122 token。均不能推断解码 tok/s 收益。D05 沿用获准的合成 prefix 几何 fixture，未声称真实 R052a token 内容；D09 则绑定原始 token、开关、切分与 round SHA a6655b59…。

证据：V7_ASSERTION_RECEIPT.md、FINAL_PINNED_RECEIPT.md；独审 JSON SHA **4384de8ae9f4a64c1a7212c696ab2bb0c0a5ce61dc1d611c61104a70c8e23e6f**。原始证据、既有终态和修复源码均未改。
