# 阶段 1 交付汇总（KIMI，2026-10-11 上午）

按 `plan/KIMI_RUNBOOK_PHASE2_20261011.md` 第 1 节执行，全程只用 CPU，未碰 GPU，未停 481，未推送，未启动 Ollama，未改论文，未动旧证据目录。所有产出已同步服务器 `/data2/FreeToken/` 同名路径。**阶段 1 到此为止，停下等主会话审核；审核通过且 09:00 后才进入阶段 2。**

## 1. 各步状态

| 步骤 | 状态 | 产出（本地 freetoken/ 下） | SHA256 |
|---|---|---|---|
| 1.1 交接现状核对 | 完成（3/3 判据符合） | development/kimi_phase2_20261011/00_HANDOVER_STATE.md | `4acf5626…68ed55` |
| 1.2 版本登记表 | 完成（63 工作树 + 7 bundle；0.5 节 4 版本核对一致） | development/VERSION_REGISTRY_20261011.md / .json | `3ef6f9c4…a0b08` / `93462693…a9b8c` |
| 1.3 T16 工装 D05 套 | **完成但带阻断项**（见 2.1） | development/kimi_phase2_20261011/t16_d05/CPU_READINESS.md；diff_d05.txt | `4b2aa783…b828f` / `93c511e1…9f2d14` |
| 1.3 T16 工装 D09fix 套 | 完成（CPU 演练通过；回执待阶段 2 停 481 后补，属正确性保护） | development/kimi_phase2_20261011/t16_d09fix/CPU_READINESS.md；diff_d09fix.txt | `1948ade2…272b3` / `7d6d5f33…e50a6d` |
| 1.4 hybrid 验证工装 | 完成（两项待裁定，见 2.2/2.3；服务器 pytest 26 过、quality60 README 命令 18 过） | development/kimi_phase2_20261011/hybrid_verify/CPU_READINESS.md；ROOT_ADMISSION.json（服务器 0444 封存） | `f2a1b8b5…176eed` / `becc648e…3c93f3c` |
| 1.4b 停止/恢复 481（restore08） | 完成（修复后两侧 pytest 7 过 + GATE_CHAIN_PASS；文件 0444 封存） | development/kimi_phase2_20261011/restore08/CPU_READINESS.md；diff_restore08.txt | `3ef5846d…c5136` / `94f97402…5fb10b` |
| 1.5 WSL2 客户端说明 | 完成（验证记录见文档第 7 节） | evaluation/toolchain/WSL2_CLIENT_SETUP.md | `fa5dcc42…a546d2` |
| 1.6 本汇总 | 完成 | development/kimi_phase2_20261011/STAGE1_SUMMARY.md | 见协调日志 |

无失败、无跳过步骤。

## 2. 遇到的问题与待主会话裁定项

1. **D05 T16 阻断（裁定前不得执行 2.2）**：D05 候选没有 CLI 旗标，默认关闭开关是环境变量 `D05_ALIGNED_DECODE_STATE`；而钉住协议 `assert_default_off_args` 要求 serve.log 解析参数中必须存在 `message_boundary_ckpt=False`，缺键即抛错。真跑会在 compare 步骤必然判 failed_harness，白耗约 1 小时 GPU 窗口。修改判定逻辑属协议修改，手册禁止，未做。另：D05 候选工作树 `d05-decode-align-481-20261011`（730b58c9）的系谱在 1.2 登记表中标为"待核"。
2. **hybrid LC2 路 2 负载未冻结**：手册"从 LC1 截 32K 片段"的规则在真实负载上不可行——LC1 第 1 条消息单独就有 87,100 token，超过 32,000 上限。已在 hybrid_verify/CPU_READINESS.md 记录并附提案（前缀 129,101 字符 → 31,999 token），准入暂不包含 LC2。路 1（12,905 token）与 LC1（87,328 token，与生产实报逐字一致）已冻结。
3. **hybrid host/port 两处表述矛盾**：手册 1.4 判据与 2.4 节不一致，已按 2.4 默认 `127.0.0.1:8123` 构建准入。若裁定 1.4 优先，改 `prepare_root_admission.py` 的 HOST/PORT 为 `172.16.108.9/8095` 并重建准入即可。
4. **restore08 的 observation_until 新设为 2026-10-12T09:00:00+08:00**（-07 原为当天 09:00），属身份/策略值，待审核。若不批准：只改 DEPLOYMENT_APPROVAL.json 该字段并重签 approval_sha256 与 ROOT_FINAL_REVIEW.json（SOURCE_MANIFEST 不含 json，不受影响）。
5. **restore08 构建返工一次**：observe_overnight.py / test_cpu_orchestration.py 曾因 Windows 写文件被转成 CRLF，已改回 LF（diff 复核仅剩身份行）并按门链重签全链，两侧复验通过。细节见 restore08/CPU_READINESS.md 第 5 节修复 2。
6. **hybrid 质量 60 估计耗时（35–65 分钟）可能顶到 115 分钟窗口上限**，已在 CPU_READINESS 标注；是否调 `window_limit_seconds` 留待审核决定。

## 3. 阶段 2 完整命令清单（审核通过且 ≥09:00 才执行；顺序不可变）

### 3.0 前提
- 主会话书面放行；当前时间 ≥ 09:00 且 481 观察窗口已结束（观察进程已自行退出；若在，不 kill，等它或请示）。
- 协调日志追加阶段 2 开始行。

### 3.1 停 481（用原 restore07 包；restore08 的 stop 会因 owner 不符被拒绝）
```bash
ssh 9 'cd /data2/FreeToken/development/morning_restore07_20261011 && \
  /data2/FreeToken/venv/bin/python stop_approved_restore.py'
```
成功判据：退出码 0；`runs/production/RESTORE481-MORNING-20261011-07/stopped.json` 存在；`production.active.json` 已移除；GPU 锁释放。失败不重试，停下记录。

### 3.2 T16（D05）——**阻断项未裁定前跳过**
```bash
# 前提 1：补 dry-run 回执
ssh 9 'cd /data2/FreeToken && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d05/owned_launch.py --dry-run --card D05'
# 前提 2：独审封存 E2-D05-T16-20261011_startup_review_v2.json；前提 3：用户批准 user_scope_approval_v1
# 正式执行：
ssh 9 'cd /data2/FreeToken && /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d05/owned_launch.py --run --card D05'
```
判据：与 481d3a7 相比，开关关闭时所有臂 sequence 与 h2d 全 SAME。not_met → 继续 3.3；failed_harness → 跳过 3.3 直接 3.4。

### 3.3 T16（D09fix）
```bash
# 前提 1：补 dry-run 回执（停 481 后 ps 门即通过，无需注入）
ssh 9 'cd /data2/FreeToken && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/owned_launch.py --dry-run --card D09FIX'
# 前提 2：独审封存 runs/dev_T16/reviews/E2-D09FIX-T16-20261011_startup_review_v2.json
# 前提 3：用户批准 runs/dev_T16/reviews/E2-D09FIX-T16-20261011_user_scope_approval_v1.json
# 正式执行：
ssh 9 'cd /data2/FreeToken && /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/owned_launch.py --run --card D09FIX'
```
判据同 3.2。not_met → 继续 3.4；failed_harness → 仍执行 3.4（hybrid 是另一套工装）。

### 3.4 hybrid 验证（O1→H1→H2→O2；J1–J5 机械判定）
```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify && \
  CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python -B \
  gpu_window.py --execute --admission /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify/ROOT_ADMISSION.json'
```
判据 J1–J5 已预先写死在工装与 CPU_READINESS.md。窗口上限 6900 秒。任一判据不通过即记 not_met，不重试。

### 3.5 恢复 481（用 restore08 包，分三步；不要用 deploy_conditional.py --execute）
```bash
# 1) 启动（内含全部 preflight）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  /data2/FreeToken/venv/bin/python start_approved_release.py'
# 2) 等待 serving 并 SDK 冒烟（df77cb 基准 15 字段+启动参数逐项对比）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -u wait_release_and_smoke.py'
# 3) 冒烟通过后启动任务观察器（后台脱离）
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  setsid -f /data2/FreeToken/venv/bin/python post_night_observer.py \
  > /data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-08/observer_outer.log 2>&1'
```
任一步失败时的回滚（先记失败回执 → 停 -08 → 起 ROLLBACK184 → 回滚冒烟）：
```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/restore08 && \
  /data2/FreeToken/venv/bin/python -c "import subprocess; from deploy_conditional import recover_after_restore_failure; raise SystemExit(recover_after_restore_failure(subprocess.run))"'
```

### 3.6 失败处理总表（手册第 2 节）
工装报错/判据不通过/清理失败/恢复失败/手册未覆盖的情况：均**不重试**，按对应类别停下、记录、必要时回滚；拿不准就停，问主会话。

## 4. 阶段 1 红线自检

未推送 git；未启动 Ollama；未改论文；未动旧证据目录；未删 GPU 锁；全程未碰 GPU（481 仍在跑，观察窗口未动）；无失败重试；测速类命令未与其他 CPU 任务并发（阶段 1 无测速）。协调日志 1.1–1.6 每步均已追加。
