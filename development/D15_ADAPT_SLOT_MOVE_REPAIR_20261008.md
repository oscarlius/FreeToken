# D15 槽提升映射修复与验证

候选825655305d69df94d3d2f79c3f416234bfe890e6，基于T21实际候选988c9e1，产品修改481aa4d。独立本地分支exp/e2d15-adapt-slot-move；未合并显存快照guard，未替换正式轮次源码，未启动新GPU轮次。

## 确认的问题与修复

prefill overlap开启时，profile+adapt可以把前2E临时槽中的专家提升到稳定槽。旧实现只重写新槽的正反向map，遗留临时槽id_of_slot；后续_invalidate_prefill_buffer读这个旧owner，清掉新stable mapping，造成假miss/驻留丢失。实际R049c的OFFLOAD与overlap=True并存，二者并非互斥选项。

修复在同一all-bank/maps事务内先核对原owner并清临时槽反向map，再发布新stable owner。错误走既有rollback；任何部分写入都不作为成功发布。

## CPU证据

- 17项profile/boundary基础验证通过，补映射中途/发布后异常回滚后19项全部通过，日志SHA b299c6236ef0c1a593106c2c0a665c98bfb35cdea630d9865aa34c9f02b06c43。
- 严格对照采用完全相同的最终测试文件SHA5e121a9dd6cda4cd87cecc45b27ddbd0f24d4162ea64510181ab8a6558cb2e3b：原988c的最终stable mapping被buffer invalidation清为-1（应8），修复481aa4d通过。
- 原源对照日志SHA eb85b71f4dc06c9ac4fa37c00ffe557ba9ac7ba1d41e4af62f73977f687614fb；修复同测试日志f61b21844284d9ed389d66f65f651a0036ef6aad2870ec3a0dbc62b727a32a3b。
- 初始red提交b489641用了不同profile fixture，提前失败的结果保留但不作为缺陷对照证明；最终测试与原产品源码的v2对照消除此混淆。
- 回滚测试同时核对全部bank、slot_for_id、id_of_slot、usage、近期路由与swap字节；包括清victim映射后发现old owner不一致，以及map全部发布后故障两个位置。
- CVD为空并使用已有CPU guard；以上不是CUDA执行证据。

## 限制与下一步

该缺陷证明驻留映射丢失，没有证明错误权重被命中，也没有证明R049c的输出分叉已解决。T21 canonical verdict仍not_met。应先完成新候选默认路径门及针对分叉输入的真实验证，再讨论完整T21重跑；新GPU范围尚未提交裁定。复用现有T16/T21工具，保留旧raw/判词和全部失败轮。

## 2026-10-08 后续源码定位

独立只读核对 actual Triton NVFP4 decode 路径后，未发现“仅更换缓存槽号就改变解码归约顺序”的源码机制：`layers/quantization/moe/nvfp4.py:70` 分派至 `moe/fused_nvfp4.py` 的 decode 实现，launch geometry 由 M、TOP_K、N、K 决定；`kernel/triton/nvfp4_fused_moe.py:190` 按原 route index 计算，各路写入独立输出切片后归约。slot ID 用来选择 packed/scale/global bank 的行，不用来排序 decode routes。

该观察只缩小假设范围，不证明 CUDA 实际结果。前提是两边 hidden states、route IDs/weights、六类 bank 被选中行和运行参数相同。prefill 是另一条契约：raw expert IDs 对应 position==expert-ID 的整层缓冲，不能把 decode 的 slot IDs 直接套入。

后续定向验证应复用现有 T21 失败输入及已有 route/state 取证，在第8 token之前核对上述输入、映射与真实 bank 身份；若全部相同，再定位流同步和更早的状态差异。现有 promotion→invalidation、全 bank/maps 回滚 CPU 测试已覆盖已知映射缺陷，不为同一行为重复建立工装或测试。新 GPU 诊断尚未获批，本次没有执行。
