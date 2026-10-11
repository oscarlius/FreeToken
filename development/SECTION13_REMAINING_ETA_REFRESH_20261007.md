# §13 剩余工期刷新（2026-10-07 16:38）

## 结论与口径

此前 `43–72h` 已撤回：它没有逐卡请求循环、token 预算或服务启动证据支持。本刷新只计算尚未实际 GPU 测量的 `R040a、R046c、R049、R048、R045、R052、R044、R047`；`R057a`、`R058` 已完成，不重计。R058 的 D04 root 实际完成于 **15:29**，独立闭合在后，不能写作 15:40。

R059 的 4 个 128 臂已完成；v1 因交接误写为 256 而只读 `NOT_MET`。按权威 128 纠正时只复核、封存已有 metadata/raw，**新增 GPU=0、不得新开轮次**；仍须用户裁定，且不作为任何后续 GPU 已获准的依据。

下表中的「completion 上限」是脚本的 `max_tokens`/reps 算术上限，不是已生成 token，更不是性能预测。速率锚点只采用 R056 同窗口、同 0.88 发布配置的 34.33–38.24 tok/s（32K 后续 cold 至 short）；87K 的 30.30 tok/s 为 different any-delta 口径，不能直接混入本表。所有服务串行持有同一 GPU；CPU 准备可与前一批 GPU 测量并行。

## 静态执行账本

| 卡 / 入口（源码行） | 实际服务启动数 | 已声明 completion 上限（推导） | 已知纯 decode 上界 @34.33–38.24 tok/s | 不能由源码量化的时间 |
|---|---:|---:|---:|---|
| R040a D16 + anchor（`r040a_d16_supplement_prepare_v6.py:232–277` → base:192–252；D16 v2 `440–512`；anchor v4 `400–458`） | **36**（真实 Popen：slots2=6、slots4=10、parking=4、cache=4、interleave6=30；anchor=6） | 5,360 = D16 `40×128` + anchor `60×4` | 2.3–2.6 min | 36 次启动、预填、native capture、停服。36 是正式 Popen 数，非 FILEDRY scope。 |
| R046c G3/G4+T06（`r046c_d07_t06_prepare.py:592–605,634–675`） | 6（G3 off/on 2 + seed12k/45k/real/two 4） | **74,496** = `3×12×2048 + 2×256 + 2×128`；冻结 D07 helper 已明确 G3 cold max=128 | 0.54–0.60 h | 三个 heldout seed 的逐轮 prompt 增长/自然触窗；v2 MANIFEST `c0293911`、Linux 25 PASS；尚待 R059 裁定后 FILEDRY 与独立 R。 |
| R049 T21（`r049_t21_ordinary_prepare_v2.py:28,68,350–358`） | 9 | **453,888** = `9×[2×128+2×12×2048+2×512]` | **3.30–3.67 h** | 18 个 seed session 的逐轮长提示预填、SSE/分析、停服；Linux22 PASS（runtime CPU v3 `3ba21bca`）；32052→32064 TokenizeManager、512-expert profile 与九臂 filewriter rehearsal 已通过。它不是 formal FILEDRY；独立 R 静态预审中。 |
| R048 T09（`r048_t09_prepare.py:191–214,237–259`） | 5 | 9,280 = `5×[(64+128+128+512)+2×512]` | 0.067–0.075 h | 每臂 prefill、hybrid trace、node1 C 臂可能 skip。 |
| R045 T05+D06（`r045_section12_draft_v6/source/r045_d06_t05_prepare.py:64–99,136–145,247–288`；probe `e2d06/scripts/multisession_probe.py:504–510,714–721,746–925`） | 3（G3/G4 1 + P1/P2 2） | **40,643** = P1/P2 各 `128+3072+1024+4503+4503+1200+4611`，再加 G3 two `1024` 与 G4 H1 `1537` | 0.30–0.33 h | pause-chain 的实际停顿、所有 32K/trace prefill、D0 采集与分析。latest v6 `serve_argv` 与 self-test 均为 98,304/.88（:99,288）；撤回旧 73,728 复制路径风险。 |
| R052 T11（`r052_t11_replay.py:118–150`；`r052_t11_followup_prepare.py:82–108`） | 1 | 1,664 = replay `8×200` + follow-up 64 | 0.012–0.013 h | 8 次回放的实际上下文长度/预填；单个服务。 |
| R044 T10（`t10_e2_r044_prepare.py:12,114–123,233–254`） | 6（ordinary/layer-major × B1/B2/B3） | 28,800 = `2 modes×3 arms×24 UIDs×200` | 0.21–0.23 h | cold/warm replay 的 prompt 长度、sampler capture I/O 与 top-2 FP32 采集。 |
| R047 T03b（`t03b_e2_r047_prepare.py:260–267,437–469`） | 6 | 37,248 = `6×(3×2048+64)` | 0.27–0.30 h | thinking 提前终止、每回合上下文增长、snapshot/serve-log 处理。 |

已声明 completion 合计（不含 R040a）为 **646,019**；含 R040a 为 **651,379**。因此仅以已知上界做速率除法为 **4.73–5.27h**，不是完整 GPU 墙钟。

## 启动、冷预填与可复算公式

令 `S` 为一次新模型服务从 Popen 到可发正式业务请求的实测墙钟，`P_unknown` 为未在上述源码声明 token 数的长提示/trace/hybrid/D0/pause/teardown总时间，`G` 为每轮独立原始复算、D04 追加与封存时间。

- 总正式服务启动数：`36+6+9+5+3+1+6+6 = 72`，故启动项为 `72×S`。没有当前逐服务 S 的实测值，使用 `S=1/3/5 min` 只能得到 **1.2/3.6/6.0h 的情景假设**，不是测量。
- R056 给出 32K 首枪 25.087s、后续 cold32 中位 6.465s（`results/T20-E2-R056_20261007.md:1–4,32–43`）。R049 的 18 个及 R048 的 10 个显式 cold32 若按每服务首/后一次映射，预填观察项为 `14×25.087 + 14×6.465 = 441.7s = 7.36min`；R045 的两条 first-shot 另为 `2×25.087=50.2s`。它们属于不同候选/测量目的，只可作 **8.2min 的类比观察**，不能覆盖 seed、87K、agent trace 或 H1 的预填。
- 可审计总式：`T_GPU = 651379/r + 72×S + P_unknown + G`，其中 `r∈[34.33,38.24]`；所有实际 prompt 预填、分析/停服及封存复核仍没有可合法替代的静态 token 值。

R056 的 87K 两次 only 228 token、TTFT 18.771/18.132s、any-delta 30.296/30.317 tok/s。它证明该形状曾完成，**不**能把 18.45s 乘到 R049 的 seed 回放，也不能将其 API 口径当作 T21 completion 速率。

## 规划用粗估（条件化，不是承诺）

以下只用于排班，明确依赖：`S=1–5min`、未预算业务开销 `P_unknown=1.5–4h`、每卡独立复核/封存 `G=5–20min×8=0.67–2.67h`。其中后两项尚无同入口实测，故是人为规划假设。

- **无失败、所有当前 CPU 缺口及时完成时的串行 GPU 墙钟：约 8–18h**。算式为已知 decode `4.73–5.27h` + `72×S` 的 `1.2–6.0h` + 8.2min 类比冷项 + 假设 `P_unknown` + 假设 `G`；实际早停和未预算预填仍会改变该条件范围，不能证明落在其内。
- **剩余 CPU 开发/验证工作：约 8–20 工程小时（规划假设）**。R046c v2 已冻结并有 25 PASS，余 FILEDRY/R；R049 runtime v3 已 Linux22 PASS，余独立 R 静态预审、formal FILEDRY 和启动复核；R040a 新 CPU89 PASS+17 inventory/schema，02 正在真实 FILEDRY。其余卡虽已有 26/35/48/53 等 CPU PASS，仍各需当前源冻结、同入口 FILEDRY、R review。准备 PASS 不等于 GPU 通过。
- **总关键路径：约 8–22h 的工程开发加测试墙钟（条件化）**，为 `max(T_CPU, T_GPU)` 再加 0–2h 的前置对齐余量，不是把 CPU 工程小时与 GPU 串行时间相加。R046c 在 R059 纠正裁定后才可上 GPU，R049 的 CPU 完整性又是其前置；这两个依赖可使可并行部分失效。
- **一次失败修复情景不适合给固定承诺**：每一次新 fail 至少增加该卡的诊断/源冻结/FILEDRY/R 复核 CPU 工作（规划量 2–8 工程小时）和其重跑的 `decode_i + startup_i×S + prefill_i + G_i`；正式 raw 保留，不能借 CPU/FILEDRY 结果跳过 GPU 或封存。若失败位于 R049，单次重跑的已声明 decode 上界单独为 3.30–3.67h。

这不是用户等待、GPU 排队、裁定等待、发布确认或 deploy/push 时间。前述等待均为零工程工时但可无限拉长日历完工日；特别是 R059 128 更正尚待用户裁定。全链完成后仍须用户最后确认才发布。

## 关键路径与不可替代门

发布前顺序为 `R059 metadata 纠正 kept → R046c → R049 → R048 → R045 → R052 → R044 → R047`；R040a 也占同一 GPU 串行资源，已由独立 R 按其正式 Popen 数跟踪。每卡均须当前源的真实 FILEDRY、独立 R 启动复核、正式 raw 测量、独立原始复算和只读封存。5 分钟若出现在门禁目标中，只能作为目标，不能统一折算为 1–2 小时或已通过。

来源：`development/SECTION13_EXECUTION_STATUS_20261007.md:7–9,60,65–67`（队列与现态）；`plan/01_测试与调研/results/T20-E2-R056_20261007.md:1–4,32–43`（性能锚点）；以及本表逐行源码路径。未读取旧原始 payload、未开端口/模型/GPU、未创建 round。


