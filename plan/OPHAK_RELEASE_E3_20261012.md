# op-hak 发布 e3：阈值切段参数上生产（2026-10-12，主会话 freetoken-06）

> 读者是执行者 op-hak。通用规则沿用 `plan/OPHAK_TASK_A_ANCHOR_CUT_20261011.md` §0 与补充 1：窗口任何终态都必须恢复 481。本文件发出后冻结（0444），更正另发补充。
>
> **用户授权**：2026-10-12 上午，用户："OK，参数上生产"。指的是任务 B 验证过的 `--prefill-anchor-cut-min-tokens 32768`。用户已确认本指令，并已知悉停服约 11–13 分钟、失败时再加约 5 分钟。
>
> **预登记**：`development/release_e3_accounting_20261012/PREREG_RELEASE_E3.json`，SHA256 `ee70f1ff45fd604890f85aa7e34491137d29d10268d345f2462d2065506db52c`，下发前已封存，此前没有任何 e3 数据。

## 1. 为什么不能直接改启动参数

- 生产的启动参数、工作树和提交号写死在冻结运维目录 `runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded` 里（`release_config.py`、`binary_manifest.json`），层层有哈希锁定。所以新参数上线，需要一套新的运维目录和一个新的审批包。
- **冒烟参考值必须重测。** 冒烟的长请求有 8,257 token。现在它按锚点切成 512 + 7,745 两段（-13 的 serve.log 与参考值都是这样）。新参数下它小于 32,768，会变成一段 8,257。冻结参考值逐行比较 `backend_cache_rows`，所以一定判失败。
  - 依据：`segment_sim_v2` 能复现 -13 的实际切段，在 thresh32k 下给出 [8257]（`smoke_thresh_sim_out.txt`）。
- **输出文本会变。** 任务 B 中，C_A1 对 C_B1 有 15/20 轮输出不同（C_A2 对 C_B2 同样 15/20），同臂两服务 0/20 不同。长请求的新哈希无法事先预测，所以要先在窗口里用一个全新的 e3 服务实测一次（Q1）作为参考值，再由正式发布的冒烟去复现它。
- **短请求可以预测。** 512 token 在两种版本下都是一段，冷请求输出必须等于 e2 参考值 `fd11a315…`。这一条用来检验构建与参数是否正确。

## 2. P1：CPU 准备（不停服）

### 2.1 分支与工作树

- 在 `/data2/FreeToken/src/FreeToken` 仓库执行 `git branch release/e3 9db0ee776c25afa8d2719ab700b2de7ccc606142`（它的父提交就是 release/e2 的 481d3a70），然后 `git worktree add /data2/FreeToken/wt/release-e3 release/e3`。
  - **不移动 release/e2，不 push。**
- 把 `wt/release-e2/python/freetoken/kernel/` 下的 `_cpu_moe…so` 与 `_pinned_tensor…so` 用 `cp --preserve=mode` 复制成**普通文件**。不能用符号链接，因为 `worktree_checks._ordinary_path` 拒绝符号链接。复制后 SHA256 必须分别为 `10a2bd83…` 与 `07701be2…`。
- `git status --porcelain --untracked-files=no` 必须为空。
- 主会话已在临时克隆里原样跑过这几步，`validate_worktree` 返回 ok。

### 2.2 运维目录 `runs/dev_release/release_e3_ops_v1_20261012/`

复制 v8 存档的 `source/` 与 `evidence/`，**只改下面几处**：

1. `release_config.py`：
   - `MODES['release']` 改为 `(ROOT / 'wt/release-e3', '9db0ee776c25afa8d2719ab700b2de7ccc606142', 98304, 4096)`；
   - `serve_argv('release')` 在 `'--mamba-host-slots', '0'` 之后追加 `'--prefill-anchor-cut-min-tokens', '32768'`；
   - rollback 模式不动。
2. `binary_manifest.json`：只改 `worktrees.release` 的 `path` 与 `commit`；`extensions`、`rollback`、`r067_cold` 不动。
3. 冒烟参考值：新建 `development/release_e3_reference_20261012/expected_reference.json`。它在窗口内由 finalize 脚本写入（见 2.4）。`test_smoke_live.compare_expected_reference` 与 `run_smoke.py` 中的参考值路径改指向它；e2 的参考值文件原样保留在副本里，不再被引用。
4. 测试：只改钉死 e2 提交号、argv 或参考值的断言。新增至少 3 项：
   - `serve_argv('release') == e2 生产 argv + 两个参数`（逐项相等）；
   - `validate_owner` 拒绝 e2 的 argv；
   - 参考值比较接受 [8257]、拒绝 [512, 7745]。
5. `evidence/`：重新生成 `release_argv.json`、`release_SERVE_CMD.txt`、`release_vs_R056.diff`、`source_manifest.json` 与 pytest 记录。

交付 `diff -r`（v8 对 e3，`evidence/` 除外），只允许出现上述文件；出现任何别的差异，即判为未就绪。`d07_g3g4_prepare.py` 必须逐字节相同，因为 `release_control.helpers()` 钉了它的 SHA `c4a28aaa…`。

**存档内部的目录名一律不改**（`source/development/release_e2_ops_v2/`、`r066_*`、`redeploy_smoke_fix_20261009/` 等），只改存档根目录名。原因是 `start_approved_release.py` 用 `ops.parents[2]` 定位存档根目录，其他代码按名字引用同级目录。

### 2.3 恢复包 restore14

- 以 restore13 为模板复制，不复制 `EXECUTION_TIME_PREFLIGHT.json` 与 `__pycache__`。
- 只做三类替换：
  - `-13 → -14` 精确字符串（approval_id、rollback 号、run_dir）；
  - `observation_until` 改为 `2026-10-13T09:00:00+08:00`，因为 restore13 的截止时间已过，`observe_overnight.py` 第 34 行会拒绝过去的时间；
  - `independent_review_sha256` 填本指令的 SHA。
- 恢复的仍是 release-e2 481d3a7，冒烟仍对 df77cb 基准。
- 要求 pytest 7 passed，门链通过。

### 2.4 发布包 `development/ophak_release_e3_20261012/release_e3/`

以 restore13 为模板，改为：

- `approval_id` `RELEASE-E3-20261012-01`，`run_dir` `runs/production/RELEASE-E3-20261012-01`；
- `frozen_ops` 指向 2.2 的目录，带两个清单的 SHA；
- `restore_commit` 为 9db0ee77…；
- `observation_until` 为 `2026-10-13T09:00:00+08:00`；
- `user_authority` 写明用户原话、本指令与预登记的 SHA，以及"无 push"。

**失败路径改写**：`deploy_conditional.recover_after_restore_failure` 改为先运行本包的 `stop_approved_restore.py`，再执行 `restore14/deploy_conditional.py --execute`。本包不得直接启动 ROLLBACK184。

**finalize 脚本**（窗口内机械执行，≤ 2 分钟），输入是 Q1 的 `cold_smoke.json`：

1. 逐项核对预登记 `q1_cold_smoke`：
   - 短请求：行结构 [512]、usage 512/128/640、`finish_reason` 为 length、SHA 为 `fd11a315…`；
   - 长请求：行结构 [8257]、usage 8257/128/8385、`finish_reason` 为 length；
   - 任何一项不符即退出码非 0。
2. 写入 e3 参考值文件，以及 `first_cold_baseline`（`cold_baseline.json` 格式，`mode/window/chunk/running/graph` 为 release/98304/4096/2/2）。
3. 重新生成存档的 `source_manifest.json`，再生成审批 JSON、包的 `SOURCE_MANIFEST.json`，以及绑定这些 SHA 的 `ROOT_FINAL_REVIEW.json`。
4. 自检 `require_root_final_review` 通过。

### 2.5 Q1 工装

- 沿用 `task_b_runner.py` 的服务管理（127.0.0.1:8123，取 GPU 锁，worker 退出即时识别，只关我方进程）。新增构建 `release_e3` = `wt/release-e3/python`。
- **argv 取自新存档的 `release_config.serve_argv('release')`**，只替换 `--host/--port`。构建门：导入路径落在 `wt/release-e3`。参数门：serve.log 的 "Parsed arguments" 中 `prefill_anchor_cut_min_tokens=32768`。
- **服务起来后的前两个请求就是冒烟**：先短请求、后长请求，不发 warmup。
  - 用新存档里的 `r066_d16_discriminate_v2/sdk_adapter.py` 的 `inputs()` 与 `collect_one`，以及 `r066b_canary_v2/sdk_adapter.py` 的 `cached_rows`；
  - 断言与 `test_smoke_live.test_release_smoke` 完全相同：`validate_cold_rows`、`valid_projection`、`api_cached_tokens ∈ {None, 0}`、两请求之间无外来 Prefill；产出 `cold_smoke.json`，格式与 `cold_baseline.json` 的 payload 相同。
- 完成后关掉 Q1 服务。

### 2.6 真实入口演练与反向对照（桩服务，不取 GPU 锁，不碰 8095）

正向演练：从 W0 一直走到 W4"即将取 GPU 锁"之前。

反向对照，每项都要能被抓住：

- (a) 桩的短请求 SHA ≠ `fd11a315…`：finalize 拒绝，走 restore14；
- (b) 桩的长请求行结构为 [512, 7745]：finalize 拒绝；
- (c) 新存档的 `serve_argv` 漏掉参数：参数门拒绝；
- (d) Q1 的 `PYTHONPATH` 指向 release-e2：构建门拒绝；
- (e) 发布冒烟与 Q1 不一致（桩）：发布包先停 e3，再走 restore14，ROLLBACK184 没有被调用。

### 2.7 就绪

- 写 `CPU_READINESS_E3.md`（0444），包含 2.1–2.6 的证据、diff 清单、pytest 与演练结果。
- 在协调日志写"op-hak：发布 e3 P1 就绪"，发消息给 freetoken-06。
- **等主会话在协调日志写"发布 e3 放行"之后再开窗。**

## 3. P2：停服窗口（放行后立即执行，总时限 45 分钟）

| 步 | 内容 | 失败时 |
|---|---|---|
| W0 | 确认 481 为 -13 且在服务、无其他 GPU 进程、无残留 8123；确认 -13 观察器已在 09:00 退出（若仍在运行，按任务 B 的 W2 做法停掉，只停观察器） | 不停服，报告，结束 |
| W1 | 用 restore13 的 `stop_approved_restore.py` 停 481 | 按其冻结语义处理并报告，不再继续 |
| W2 | 起 Q1（全新 e3 服务），跑冷冒烟，关掉 Q1 | 关 Q1 → restore14 → 结束（未上线） |
| W3 | finalize（预登记核对 + 生成参考值与审批） | restore14 → 结束（未上线） |
| W4 | `release_e3/deploy_conditional.py --execute`：启动 → 冒烟（对 Q1 参考值逐项比较）→ 观察器 | 包内路径：停 e3 → restore14；smoke_invalid 同样按失败处理 |
| W5 | 核对 serve.log 中参数为 32768；`production.active.json` 的 commit 为 9db0ee77…，argv 等于预登记的 `argv.e3`；health 正常 | 用发布包的 stop 停 e3 → restore14 |

- **W4 与 restore14 都要后台运行**（`setsid`）。`deploy_conditional --execute` 的最后一步是观察器，要运行到 `observation_until`（次日 09:00）才返回，所以冒烟结果以 run_dir 内的 `smoke_execution_result.json` 为准。也可以像任务 B 的 W5 那样把 start、wait+smoke、observer 拆成三步执行，但失败路由必须与上表一致，并由演练 (e) 证明。
- 若 restore14 自身的冒烟失败，按它的冻结路径处理（停服 → ROLLBACK184），之后停止一切 GPU 工作，报告。
- 预计停服时间：服务加载约 3.7 分钟（任务 B 实测 01:37:58→01:41:37），整个窗口 11–13 分钟；走 restore14 再加约 5 分钟。

## 4. 上线后（只报告，不判优劣）

- 观察器运行到 2026-10-13 09:00。
- 在 12:00、18:00 和次日 09:00 各查一次，报告以下几项：
  - serve.log 中 OOM 与 worker 退出的次数；
  - 请求数；
  - 热轮（cached > 0）的 Prefill 行数分布，只统计 `#new-seq: 1` 的行，因为并发时一行可能含两个请求。`remain ≤ 32768` 的热轮应只有 1 行；出现多行即报告。
- **任一次检查发现 481 不在服务，且原因是 OOM 或 worker 退出**：先用发布包的 `stop_approved_restore.py` 清理（锁与 `production.active.json`），再用 restore14 恢复 e2（若已用过，就按同样规则复制出 restore15），然后报告。
- 不从真实流量推断首 token 收益，收益以任务 B 为准。
- 上线成功后更新 `/data2/FreeToken/README.md` 的"当前生产"段：release/e3 9db0ee77，加参数 `--prefill-anchor-cut-min-tokens 32768`，审批 `RELEASE-E3-20261012-01`。

## 5. 报告

`RESULT_E3.md`（0444），包含：
- 分支与工作树记录；
- 存档 diff；
- Q1 的逐项核对（含长请求哈希是否等于 e2 的 `9845c386…`，只报告）；
- finalize 输出、发布冒烟、W5 核对；
- 停服起止时间；
- 失败时的路由记录。

完成后发消息给 freetoken-06。

## 6. 主会话下发前自检

| # | 清单项 | 本指令的情况 |
|---|---|---|
| 1 | 终点 | 上线即目标：参数生效，冒烟可复现。性能收益已由任务 B 测定，本次不再测 |
| 2 | 预测是否事先写死 | 短请求的行结构与 SHA、长请求的行结构、W5 各项，都写在预登记 ee70f1ff… 中；长请求哈希不预测，明确只报告 |
| 3 | 冒烟会不会误判 | 模拟器先复现 -13 的实际行（[512]、[512, 7745]），再给出 thresh 的 [8257]；旧参考值必然失败，所以改用 Q1 实测作为参考值 |
| 4 | 短请求预测依据 | 切段相同（[512]）；T16-lite 默认路径逐位相同；任务 B 冷且切段不变的 seed_real/00 两臂输出相同 |
| 5 | 输出会变（如实告知用户） | 任务 B 跨臂 15/20 轮不同，同臂 0/20 不同；原因是缓存状态的数值差异，不是近似；同版本可逐位复现 |
| 6 | 构建能过门 | `.so` 必须是普通文件（worktree_checks 拒绝符号链接）；`start_approved_release` 逐字节对比 e2oom-protocol-restart 的 `.so`，复制件 SHA 相同。主会话已在临时克隆中跑通 |
| 7 | 观察器截止时间 | restore13 的截止时间已过，restore14 与发布包都用 2026-10-13T09:00 |
| 8 | 失败去向逐步推导 | 见 §3 表。只有 W0 与 W1 不调用 restore14；W2–W5 一律回到 e2；ROLLBACK184 只可能由 restore14 自身的失败触发 |
| 9 | 窗口时长 | 两次服务加载约 7.4 分钟，加停服、冒烟和 finalize，约 11–13 分钟，不是压力测试 |
| 10 | 人工转达 | 放行在开窗前；窗口内全部是机械判据，不等主会话回复 |
| 11 | E1 风险 | 根因未证。阈值臂 2 个服务 × 20 轮（含 87–95K）都没有 OOM；95K 冷请求未测。上线后按 §4 检查，发现 OOM 停服即恢复 e2 |
| 12 | 不越权 | 不 push，不动 release/e2，不改 v8 存档与 restore13；ROLLBACK184 不在本包的直接路径上 |
| 13 | 自检后补上的五处 | ① W0 核实 -13 观察器已退出；② `--execute` 被观察器阻塞到次日 09:00，W4 与 restore14 必须后台运行，并以 `smoke_execution_result.json` 判定；③ 存档内部目录名不改（`parents[2]` 定位）；④ Q1 断言与 `test_release_smoke` 完全相同；⑤ 上线后 OOM 停服时，先 stop 清理，再 restore14，并且只统计 `#new-seq: 1` 的行 |
