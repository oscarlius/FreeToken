# 晚间窗口执行结果（EVENING_RESULT）

- 执行者：KIMI（本地会话，ssh 9 → dell@172.16.108.9）
- 指令：`plan/KIMI_EVENING_WINDOW_20261011.md`（SHA256 `dd89778a31525ebfed975a459c9bc5031c495837136c7074d2dfe03599e7decb`，两侧一致）
- 补充指令 1：`plan/KIMI_EVENING_WINDOW_20261011_ADDENDUM1.md`（SHA256 `30a1e2ff4a68077b82fc93da86d6b3d046c738dd623b68b3ed39a04b9a3f1490`，两侧一致；E0 完成后立即开窗）
- 窗口实际时间：2026-10-11 10:55（A2 结束观察器）→ 13:31（E5 恢复完成）
- 红线遵守：未推送、未启动 Ollama、未改论文、未动旧证据、未手动删 GPU 锁、全程零重试。冻结区 `t16_d05/`、`t16_d09fix/`、`runs/dev_T16/reviews/` 未改动。

## 各步终态

| 步 | 内容 | 终态 |
|---|---|---|
| A2 | 提前结束 -08 观察器 | 完成。进程组 1219625 身份复核后单次 TERM 退出（未用 KILL）。91 采样全部健康（eligible() 逐项复核），首 09:24:54 末 10:54:58。terminal.json 按设计缺席。记录 `evening/OBSERVER_EARLY_STOP.json` |
| E1 | 开窗检查 + 停 481 | 通过。无 STOP 文件（两侧）、env 检查=0、E0-4 已过。stop_approved_restore.py 退出码 0；stopped.json 在位；gpu.lock 释放；GPU 计算进程 0 |
| E2 | T16 D09fix | **kept**（batch167，rid E2-D09FIX-T16-20261011，10:58–11:47） |
| E3 | T16 D05 | **kept**（batch168，rid E2-D05-T16-20261011，11:51–12:41） |
| E4 | hybrid 验证 window02 | overall=**complete**（12:41:57–13:19:51，2274s，未触 9000s 上限） |
| E5 | 恢复 481（restore09） | 完成。启动+冒烟+观察器三步全过（见下） |
| E6 | 本文件 | 完成 |

## T16 判定（机械判据：所有臂 sequence+h2d 全 SAME = kept）

两次运行判据相同：layer_major 与 non_layer_major 下 D0/PROD 的 sequence 全 **SAME**；prefill h2d 全 **SAME**（layer_major 13/13 行、non_layer_major 23/23 行，tail_aligned 与 parent_tail_aligned 均 true）。`proposed_verdict` 均为 **kept**。两侧编译扩展（_cpu_moe、_pinned_tensor）SHA 逐对一致。

| 项 | E2 D09fix | E3 D05 |
|---|---|---|
| batch / rid | 167 / E2-D09FIX-T16-20261011 | 168 / E2-D05-T16-20261011 |
| 候选 commit | `7d8d389ee5d85de7e4f8e533f35c27f4c4c02690`（wt d09_fix_20261011） | `730b58c96527fe5bf117d1f3c2430e405173d28b`（wt d05-decode-align-481-20261011） |
| 基线 commit | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9`（wt release-e2） | 同左 |
| 判定 | kept | kept |
| 证据 | batch167.log=`0a83a87f…6fe2`；launch 回执=`dda51ef2…e692` | batch168.log=`f9b6e596…7ae6`；launch 回执=`de38c9c7…3785` |

## hybrid 验证（window02）机械判定

verdict.json=`b87139d6…be0c`、events.jsonl=`e83ab60e…ee36`、terminal.json=`f818d2d4…c4de`（terminal：error=null、未越截止、工装未碰生产停复、未推送）。abnormal_lanes 为空。

- **J1 两路收益：met**。offload 单路 8 次均值 16.898 tok/s（16.81–16.98）；H1 两路 25.957/26.120/26.111/26.272 tok/s；门槛 19.433（=offload 均值×1.15）。
- **J2 测量漂移：met**。O1 均值 16.882 vs O2 均值 16.915，相对漂移 0.197%。
- **J3 质量等价：no_data**。
- **J4 自身复现性：affected**。三比较组均 differs：H1 x_single 重复间（样本 1179，首异字符 454）、H1 x_two 重复间（1179、1231）、H2×H1 x_single（1179）。
- **J5 长上下文（只记录）：null**。LC1 单路：H1 两次均 finish_reason=stop（93/101 completion tokens），被短车道排除（counted=false）→ no_data；offload 侧无数据。LC2 不在本次准入（not_in_admission）。

注：events.jsonl 中 O1/O2 的 `service_terminal.measured=false`，而 J1/J2 的 offload 数据齐全——O 服务不承担 x_single/x_two 复现阶段，该标志含义以工装实现为准，此处如实转录。

## 恢复冒烟（E5，restore09，审批 RESTORE481-MORNING-20261011-09）

1. `start_approved_release.py` 退出码 0：supervisor pid 1847842、service pid 1847873，GPU 锁归属 `production:release:RESTORE481-MORNING-20261011-09`。
2. `wait_release_and_smoke.py` 退出码 0：classification=**passed**；guarded 冒烟 pytest **1 passed in 31.56s**（smoke_gate.json：1 测 0 败；含 df77cb 基准对比）；serving_ready：model Qwen3.8-Flash-Next-NVFP4、backend_epoch=0、restart_attempts=0。
3. 观察器已脱离运行：post_night_observer pid 1865038 → observe_overnight pid 1865057（--until 2026-10-12T09:00:00+08:00）。首个采样全绿（owner 匹配、三活、watchdog 健康 http 200）。
4. 服务面：172.16.108.9:8095 LISTEN（pid 1847873）；`/data2/FreeToken/run/production.active.json` owner=-09、commit `481d3a70…`。

## 证据 SHA256 索引

| 证据 | 路径 | SHA256（前缀） |
|---|---|---|
| 观察器提前结束记录 | development/kimi_phase2_20261011/evening/OBSERVER_EARLY_STOP.json（两侧一致） | `12062c26…c397` |
| -08 观察采样 | runs/production/RESTORE481-MORNING-20261011-08/overnight_observation/samples.jsonl（91 条） | `a6f5fa00…392e7` |
| E2 测量日志 | /data2/_shared/runs/ft_rounds/batch167.log | `0a83a87f…6fe2` |
| E2 启动回执 | runs/dev_T16/launch_E2-D09FIX-T16-20261011_batch167.json | `dda51ef2…e692` |
| E3 测量日志 | /data2/_shared/runs/ft_rounds/batch168.log | `f9b6e596…7ae6` |
| E3 启动回执 | runs/dev_T16/launch_E2-D05-T16-20261011_batch168.json | `de38c9c7…3785` |
| E4 判定 | runs/dev_hybrid_verify_20261011/window02/verdict.json | `b87139d6…be0c` |
| E4 事件流 | 同目录 events.jsonl | `e83ab60e…ee36` |
| E4 终态 | 同目录 terminal.json | `f818d2d4…c4de` |

E0 各件 SHA 见协调日志 10:53 "E0 完成" 条目与 restore09/CPU_READINESS.md。

## 与指令不一致处 / 勘误

1. **E1 active.json 检查路径笔误**：协调日志 E1 条写 `runs/production/active.json`，真实路径为 `/data2/FreeToken/run/production.active.json`（该文件从不在被检路径，"已移除"系路径不存在）。停服事实由 stopped.json、gpu.lock 释放、0 计算进程及 E4 前置（production_pids_dead、lan_8095_bindable）充分证实。
2. **A2 采样数为 91**：主会话 10:44 日志写"79 个采样"，系更早快照；提前结束时刻的最终数为 91（全部健康）。
3. **主会话补充指令 1 已执行**：取消 19:00 开窗约束，E0 完成后立即开窗（A2→E1）。
4. 其余步骤与指令第 3/4 节逐条一致；失败路由表全程未触发。
