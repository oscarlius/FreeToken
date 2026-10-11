# T17 R023 实测反例

R023/batch51 已独立复核并按 D04 封存为 `not_met`。这是命中续算与全冷
重算不等价的实际测量；D14 T16 通过不能替代 T17，E2-base.1 尚未接受。

运行树为 `e4f32022a5aa4d8734d87d9f6eb15e98c1edde42`。
轮次目录：`/data2/_shared/runs/ft_rounds/E2-R023-gate-T17`。
原始76个工件留在服务器且哈希未变，历史为 pending_review → not_met。

| 检查 | 原始证据得出的结果 |
|---|---|
| 输入 | 两臂相同8257个输入ID，实际命中8192；temperature=0、max_tokens=128 |
| 恢复 | GDN conv/recurrent、PLE conv/ngram四角色D2D复制均逐位一致 |
| ngram | 捐赠及恢复均为 `[11994,984]` |
| 输出 | 两臂均正常产生128个采样token；首个不同位置index36，即第37个token，warm=4625、cold=2404；全文不同 |
| 续算状态 | 8256处GDN conv/recurrent和PLE conv不同；PLE ngram相同 |
| 长尾观察 | 暖臂首子块cached=8192、device=12288、has_initial_state=true；后块cached=12288、device=12353、has_initial_state=true |
| 覆盖限制 | 仅8192短尾段完成冷/热比较；长尾冷臂及其余三个边界未完成，不计为通过 |

冷臂执行普通 anchor 0→512，再执行层优先512→8257。
命中短尾臂从8192开始进行普通短预填。因此失败本身成立，但该实验未
隔离快照保存、后续预填路径及浮点累积差异，不能把分叉直接归因于
D14修复仍然错误，也不能仅凭恢复复制通过判D14正确。

下一步诊断需要独立比较8192处捐赠/重算状态，并控制两臂的续算路径。
诊断结果与原接受门分列；没有放宽逐位要求或用容差制造PASS。

| 封存文件 | SHA256 |
|---|---|
| round.json | `92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d` |
| MANIFEST.sha256 | `ef2d98846aa8a23c8168596d641e0c2614e0a2dac47f88e07d099b27c0391cfa` |
| review_batch51.json | `86bebc276f56c47299dfd7e5da0385f1c4c9bb0166381c80c917d5c5551d5384` |
| 首短尾比较 | `28d9685b4d775a903b05c293c3c317c183128c884d69d9af570a32daaf44fd13` |

独立复核重放真实回执、实际采样ID和原始张量，D04历史检查与全部
MANIFEST SHA校验通过。所属batch和两个服务进程已终止；停止回执记录
GPU回到4MiB，R023锁已释放。后续R024 D07锁属于独立验证轮次。

FTD-20261004-1及其不可变勘误保持原样；本反例不重写历史发布。
T10历史33/36实际来自普通预填路径，后续比较见
[T10重跑协议](T10_RETEST_PROTOCOL_20261004.md)。
