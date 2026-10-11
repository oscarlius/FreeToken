# D03 普通分块诊断元数据修复（CPU 验证记录）

2026-10-04，主线负责人记录。状态：本地修复及 CPU 验证完成；尚未冻结新的 GPU 候选、执行新 T16 或完成 T04 业务验收。

## 已确认的问题与修复

T04 E2-R015 的恢复请求需要多个普通 prefill 分段。原代码生成下一段 Req 时，没有传递请求首次恢复的 `_dev_restore_proof` 和 `_dev_prompt_cached_len`，导致最后一段 logits index 记录为空 proof、把最后分段的 cached_len 当成初始恢复长度。

本地工作树 `development/e2d03-continuation/`，分支 `exp/e2d03-continuation`，父提交 `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`。修复只在新 Req 存在时传递旧 Req 已有的两个诊断属性，保留同一个 proof 对象。没有诊断属性的普通请求继续保持属性缺席；实际 segment_cached_len 和缓存恢复/分配路径保持原口径。

变更文件：

- `python/freetoken/scheduler/prefill.py`：6 行新增、1 行替换；SHA256 `71f93be121edd17235654cfb2cc731c81ac8600396283fee892eb6345d6f12ce`。
- `tests/scheduler/test_scheduler_chunked_prefill.py`：保留原测试，新增 93 行，覆盖 host/device 诊断属性跨两段传播和冷请求属性缺席；SHA256 `5190f4936a4208f80dfe163fa91c239195a6429aa92e7f492aaf09666aca1c91`。

独立 01 已复核此修复与测试，结论 PASS，仅限 CPU 诊断传播范围。后续已生成提交f5067bb并建立独立服务器候选；其新的默认GPU门及业务测量尚待，详见末节。

## Linux 实际验证

隔离 CPU 验证工作树：`/data2/FreeToken/runs/dev_D03/continuation_cpu_71f93be/repo`。使用服务器现有 Python/Torch，`CUDA_VISIBLE_DEVICES=''`，未启动模型服务或使用 GPU，活动候选 `/data2/FreeToken/wt/e1r003st` 保持原 c30。

| 验证 | 实际结果 | 日志 SHA256 |
|---|---|---|
| 原 c30 + 新回归用例（RED） | 2 failed / 1 passed / 7 deselected；host/device 两例确实缺少 _dev_restore_proof | `4ca229bacde7bddc059fea1156ecd71d82f49c0a1909aebc841d2c0b289f6604` |
| 修复后分块、锚点开关、边界落盘、dev logits 四模块（GREEN） | 26 passed | `6e296f43c41d315d084f1c9024610477bad8d426b301c511acc5c3824e0f85cd` |
| 同口径扩大 G1 回归 | 447 passed / 2 known failed / 6 skipped / 1 warning；没有新增失败 | `2c0d8634273a3e29c9ef06b6394ae80e5c2adb45ac7cddac33478e14b0819b2e` |

两个既有失败均在 `tests/scheduler/test_abort_inflight_prefill.py`：`test_prefix_commit_sentinel_guard`、`test_post_terminal_overlap_step_is_dropped`，与 c30 基线相同的 `SimpleNamespace.d3_extra_anchor_ids` 缺失。扩大回归不称全绿。

执行命令与结果核验保存在 [continuation_cpu_verify.sh](continuation_cpu_verify.sh) 和 [continuation_cpu_regression.sh](continuation_cpu_regression.sh)。服务器日志为该隔离目录下 `red.log`、`green.log`、`regression.log`；已执行脚本不得覆盖原日志重跑。

## T04 的另一个问题及下一步

E2-R015 实际 seed 的归档长度是 448、4544、8640、12416，实际 host 恢复到 12416；任务要求的是 12672。上述诊断属性修复不会把实际恢复长度变成 12672，不能据此让失败轮次通过。

早期 ServerArgs 显示 page_size=1，但实际初始化日志明确 qsa_sparse 将页大小覆盖为 64。证据：[t04_r015_geometry.json](t04_r015_geometry.json)，SHA256 `dddee68b5b3a8e308ac7f2446cce71f381b14a21d1ea83366b033578a2a27549`。原始 CPU 输入摘要：[t04_r015_boundary_inputs.json](t04_r015_boundary_inputs.json)，SHA256 `69e77aafa80b49a0f6a6e4898a2ce1e7265a58e4066860df71901762da93474d`。

真实 CPU 构造门现已通过，详见下节。修复候选冻结并重新过默认路径门后，使用新 RID 重测，保留 R014/R015 失败原件及既有 814 点 / 199 超出 / 最大比值 5.489091417 的科学结果。

## 真实 Linux CPU 边界构造门（已通过）

在隔离 CPU 树上，调用实际 `PrefillAdder._add_one_req` 和 `attention.linear._build_track_metadata`，按真实 page_size=64、max_extend_tokens=4096、last-anchor、普通 prefill 验证 branch seed。Linux 10 passed / 1 warning，独立源码复核 PASS；测试没有模型、权重或 GPU，也没有把 stub 状态值当张量测量。

| seed | 最后一个非最终分段的实际内部 track | 最终分段 track（不作 archive） |
|---|---:|---:|
| 原 Y96，长度12768 | 12416 | 12736 |
| Y122，长度12794 | 12608 | 12736 |
| Y129，长度12801 | 12672 | 12800 |

Y129 的非最终分段结束位置是12736，内部 track 是12672；分段结束12672的Y122并不会产生12672 archive。因此后续新工装选择Y129，并继续严格要求实际 restore proof/cached_len 都为12672。

- 预测文件：[t04_boundary_cpu_prediction.json](t04_boundary_cpu_prediction.json)，SHA256 `57bf608c7cc752e061dd3dbdd5010dba2af84103529f498a35ba035275699610`。
- 最终 CPU gate SHA256 `666bdb5a8a86a247b4c401e722edfc911f348d915d60eaa6d81543a12d68e1f7`；测试 SHA256 `66f632525992fb8a78bbdde8ef1bf370f9fbfaaf8dcfc6bfe29789de36f8008b`。
- 真实 Linux 日志 SHA256 `2abffb86f4a393650fe1845c1fb8f2d2b9946d9f5c7bb485ddff0434e04fde1b`；只读包 `/data2/FreeToken/runs/dev_D03/t04_boundary_cpu_666bdb5/`。
- canonical Linux linear.py SHA256 `34a4ad296724659825fb31afa6ea857034d3fb24127e82dd653896e638d9c4a1`，与 c30 Git blob 字节一致。此前 Windows CRLF pin 不适用于 Linux，已纠正 pin 后重新验证；未改 linear 计算语义。

这只证明调度和内部 track 的 CPU 预测，尚不证明 GPU 真正归档12672、host恢复12672、状态包络或 logits 通过。下一步是冻结诊断修复候选、重新跑默认GPU门，再用新RID完成四臂测量。R015失败状态和旧输入保持原记录。

## 修复候选已提交并在 Linux 复验

- 新提交：`f5067bbe05da51d5f78185213435a8be095a684a`，父提交c30；只含prefill诊断传播与对应回归测试两个文件，tracked tree干净。
- 本地：`development/e2d03-continuation/`，分支exp/e2d03-continuation；服务器独立候选：`/data2/FreeToken/wt/e2d03-continuation`。R013仍使用原c30的e1r003st，未切换活动源树或重启模型。
- Git对Windows混合行尾作正常LF归一化，实际代码与此前已复核/实测版本逐字节归一化后相同。新commit/Linux源码prefill SHA256 `765b346fa732070a0d301b0562c50f774ed1dd18d52e620f9887740ea20f0533`；测试 SHA256 `b275602ff1a3c2f3242e509d383791049b1097a1ce02811c17bd11a3c8e27a19`。上文71f9/5190是原验证工作树字节，不冒充新Git blob。
- 新准确commit在Linux重新运行四个针对性模块，26 passed / 6.00s；日志 `/data2/FreeToken/runs/dev_D03/continuation_f5067bb/targeted.log`，SHA256 `dede3d42298580c5f7f2f3ec850cebe8f750957a068ae1c94f33607b03180eba`。
- 2,078字节Git增量bundle SHA256 `2d2a005b9e366edf51530eb2d7448756bf9ebccaff03a25054fe20d9d48b45b2`；仅代码增量，没有权重/tensor/大日志。
- [服务器候选记录](d03_continuation_candidate.json)。

提交、候选建立与CPU复验不等于GPU门或部署完成。下一步在R013释放GPU后，验证f506默认冷输出及T16，再为T04 Y129四臂分配新RID；不能复用c30的T16证明替代修复候选的新门。
