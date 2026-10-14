# 发布 e3 P1 CPU 准备报告（op-hak）

- 执行者：op-hak；服务器时间 2026-10-12（时间戳见协调日志对应条目）。
- 依据：`plan/OPHAK_RELEASE_E3_20261012.md`（a52388caee321e59c26d24e0f71e584e9659bee97c560cb532699e76d0aeb137，0444）；
  补充 1 `plan/OPHAK_RELEASE_E3_ADDENDUM1_20261012.md`（7fee5a520ad22a3651b72dec69697625064dc0a16625fe910ca4be226a51799c，0444，用户已确认）；
  预登记 `PREREG_RELEASE_E3.json`（ee70f1ff45fd604890f85aa7e34491137d29d10268d345f2462d2065506db52c）。

## 结论

**P1 就绪。** §2.1–§2.6 与补充 1 全部实施并验证，f 项三态演练通过。请主会话确认 §8 的三项（其中两项是实现上的偏差）。
开窗仍须主会话在协调日志写"发布 e3 放行"。

## 1. 分支与工作树（§2.1）

| 项 | 结果 |
|---|---|
| 分支 `release/e3` | 9db0ee776c25afa8d2719ab700b2de7ccc606142（父提交 481d3a70 即 release/e2） |
| `git status --porcelain --untracked-files=no` | 空 |
| `_cpu_moe…so` | 10a2bd8311b9…，普通文件，非符号链接 |
| `_pinned_tensor…so` | 07701be28030…，普通文件，非符号链接 |
| `validate_worktree`（release、rollback、r067_cold） | 三个均 ok |

## 2. 运维存档（§2.2）

- 路径：`runs/dev_release/release_e3_ops_v1_20261012/`。CPU 套件 **68 passed**（test_cpu、test_e3_release、test_redeploy_cpu、test_worktree_checks）。
  `test_smoke_live.py` 是显式冒烟，按设计不在 CPU 套件中；若直接跑它，会因缺少 `RELEASE_SMOKE_*` 环境变量而失败，这是预期行为。
- 与 v8 的差异（不含 evidence/）：`binary_manifest.json`、`release_config.py`、`run_smoke.py`、`test_redeploy_cpu.py`、`test_smoke_live.py`，
  以及新增的 `test_e3_release.py`。全部在 §2.2 允许的范围内。
  release_config.py 的改动：`MODES['release']` 指向 `wt/release-e3` 与 9db0ee77；`serve_argv('release')` 在 `--mamba-host-slots 0` 后追加
  `--prefill-anchor-cut-min-tokens 32768`。
- `d07_g3g4_prepare.py` 与 v8 逐字节相同（SHA256 c4a28aaa…）。
- evidence/（release_argv.json、release_SERVE_CMD.txt、release_vs_R056.diff、source_manifest.json、CPU_pytest.txt、CPU.junit.xml）为构建时生成，本次未改动；
  其中 68 项与本次重跑结果一致。

## 3. 恢复包 restore14（§2.3；补充 1 §4 要求保持原样）

- 由 restore13 复制。相对 restore13 的差异只有：-13→-14 的替换（approval、rollback、run_dir），`observation_until` 改为
  `2026-10-13T09:00:00+08:00`，以及由此派生的 README、ROOT_FINAL_REVIEW、SOURCE_MANIFEST、测试文件与 observe_overnight.py 中的同类文字。
- 独立审查 SHA 保持 a52388…（补充 1 §4 规定不改）。
- 测试 **7 passed**。门链：`GATE_CHAIN_PASS RESTORE481-MORNING-20261011-14 2026-10-13T09:00:00+08:00`。
- 16 个文件，全部 0444。`stop_approved_restore.py` 与 restore13 逐字节相同。
- 链：SOURCE_MANIFEST 093f2204…，DEPLOYMENT_APPROVAL 3bea7f40…，ROOT_FINAL_REVIEW c83b9127…。

## 4. 发布包 release_e3（§2.4 与补充 1）

- 旧版已备份为 `release_e3_pre_addendum1/`（未删除）。
- 补充 1 的改动：
  - `deploy_conditional.py`：`execute()` 在 start 之前做 W3.5；不通过则返回 5，不启动任何服务，不进入恢复路由。
    `recover_after_restore_failure` 为三分支（已接管 / 确认不存在 / 状态不明），每 2 秒轮询，最长 60 秒。
    状态不明时写 `ROUTING_AMBIGUOUS.json`（附快照）并返回 3。本包从不启动 ROLLBACK184。
  - `e3_probe.py`（新）：只读探测（指针、owner.json、gpu.lock、隔离标记、e3 进程、8095/8096 监听、GPU 计算进程与显存）与 W3.5 条件。
    不通过的快照写到 `runs/production/RELEASE-E3-20261012-01.W35_SNAPSHOT.json`，不创建 run 目录（start_approved_release.py 要求 run 目录不存在）。
  - `test_cpu_orchestration.py`：新用例 13 项（三态路由 6 项、execute 路由 5 项、W3.5 预检 2 项），加上原有的 EntryGuard 2 项与 FinalizeTests 4 项（后者原样保留），共 19 项。
  - `stop_approved_restore.py` 与 `restore14/`：未改动。
- 链：SOURCE_MANIFEST **66e1b136…**，DEPLOYMENT_APPROVAL **a42113f7…**，ROOT_FINAL_REVIEW **085c570d…**
  （independent_review_sha256 = 7fee5a…，verdict PASS）。18 个文件，全部 0444。
- 测试：**19 passed**（在真实包上运行）。门链：`GATE_CHAIN_PASS RELEASE-E3-20261012-01 2026-10-13T09:00:00+08:00`。
- 占位，由窗口内的 finalize 填写：first_cold_baseline 及其 SHA；rollback_approval 为 `NOT_USED_E3_FAILURE_PATH_IS_RESTORE14`。

## 5. Q1 工装（§2.5）

- 文件：`q1_e3.py`（91047aa2…）；`stub_e3_server.py`（fc352fac…，仅供演练）。
- 服务管理沿用 task_b_runner：`wait_ready`、`Handle`、`safe_stop`、`parsed_min_tokens`、`startup_status`、`PROBE_CODE`、`FT_PYTHON`。
  oh_window 的 `idle`、`take_d07_gpu_lock`、`capture_birth`、`cleanup`、`release_d07_gpu_lock` 调用与 RealLauncher 相同；环境取 `release_config.environment('release')`。
- argv = `release_config.serve_argv('release')`，只替换 host/port。与生产 argv 比较，只有两处不同：host 172.16.108.9→127.0.0.1，port 8095→8123。
- 构建门：导入 `/data2/FreeToken/wt/release-e3/python/freetoken/scheduler/prefill.py`，通过。
- 参数门：Parsed arguments 中 `prefill_anchor_cut_min_tokens=32768`，通过。
- 冒烟：不发 warmup，先 short 后 long。断言直接复用 test_smoke_live 的 `validate_cold_rows`、`valid_projection`、`validate_health`；
  请求经 r066 的 `collect_one`。`api_cached_tokens ∈ {None, 0}`，两请求之间无外来 Prefill。
  输出 `cold_smoke.json`，schema `ft_release_cold_smoke/v1`，键与 test_release_smoke 的 payload 相同。
- 局限：**real 模式未在 GPU 上运行**（CPU 上只能验证到构建门与桩）。finalize 不检查 `q1_mode`，窗口内只能使用 real 模式产出的 cold_smoke.json。

## 6. 演练（§2.6，补充 1 之后的最终版本）

报告：`p1_drills_run3/DRILL_E3.json`。`all_expected_pass = true`，`real_artifacts_unchanged = true`，无残留桩进程。

| 项 | 做法 | 结果 |
|---|---|---|
| W0 只读 | owner、gpu.lock、observer、8123、残留进程、e3 run 目录 | 通过。"发布 e3 放行"行未出现（之前匹配到的是流程说明行，已排除） |
| W2 Q1（桩） | 两条冷冒烟 | passed；rows [512] 与 [8257]；usage 512/128/640 与 8257/128/8385；finish length |
| W3 finalize | 夹具：短请求 SHA 换成 e2 参考值（标注 FIXTURE，不是测量） | rc 0，`q1_check: passed` |
| W4 取锁前 | 干净探测（模拟 W3 之后的主机），录制 runner | 通过 W3.5，停在 start_approved_release.py |
| (a) 短请求 SHA 不符 | 桩的短请求输出不同 | finalize rc 2，拒绝；参考值未写入 |
| (b) 长请求 [512,7745] | 桩的长请求段数 | finalize rc 2，拒绝（行结构不符） |
| (c) argv 漏参数 | 去掉两个参数 | param_gate_refused；未发请求 |
| (d) PYTHONPATH 指向 release-e2 | 构建门 | build_gate_refused；未启动桩 |
| (e) 冒烟与 Q1 参考值不一致 | `compare_expected_reference` 判失败（代替正式冒烟，正式冒烟需要生产 owner） | calls：start、wait、stop、restore14；rc 0；无 ROLLBACK |
| (f) 三态六场景 | 见下 | 全部通过 |

（f）详情：

- 确认不存在（连续两次）：calls `[restore14]`，rc 0，t = 2 秒，未调用 stop。
- 第 25 秒接管：calls `[stop, restore14]`，rc 0，t = 26 秒，stopped.json 存在。
- 守护进程存活但无 owner：calls `[]`，rc 3，t = 60 秒，写出 ROUTING_AMBIGUOUS.json。
- 指针属于他人：calls `[]`，rc 3，t = 0。
- 指针部分匹配（approval 相同、commit 不同）：calls `[]`，rc 3，t = 0。
- 接管后 stop 失败：calls `[stop]`，rc 3，不启动 restore14。

每个场景都在封印包的副本中运行**真实的** stop_approved_restore.py（只替换指针路径、run 目录、ops 目录）。controller 为测试替身，见 §7。

W3.5 的只读结果（当前，481 运行中，预期不通过）：compute_processes（3909216）；gpu_memory 22454 MiB；监听 8095/8096；gpu.lock 存在；production.active.json 存在。
W3.5 在 W1 之后运行。

## 7. 命名空间可行性（补充 1 §5.2）

报告：`ns_feasibility_20261012T095502/NS_STOP_FEASIBILITY.json`。护栏检查全部通过：

- 护栏 1：stop 链上的绝对路径已列出（stop 脚本 2 处，e3_probe 3 处，release_config 1 处，d07 4 处；release_control 通过 ROOT 常量访问）。
  会被写入的路径已在命名空间内 bind 到临时目录：`/data2/FreeToken/run`、`/data2/FreeToken/runs/production`、`/data2/_shared`。
- 护栏 2：进入命名空间后，三个标记文件（内容为本次随机令牌）逐一确认；真实 gpu.lock 不可见。
- 护栏 3：伪造 owner 只引用 `sleep 3600`（pid 884742，start_ticks 186459104），其 pid 不属于生产集合。
- 护栏 4：宿主侧前后比对——真实 production.active.json 的 SHA 不变；gpu.lock 的 inode 与内容不变；481 health 为 200、serving，不变；
  GPU 计算进程与生产进程集合不变。
- 其它：stop 脚本与审批的 SHA 不变；只有哑进程收到 SIGTERM（退出码 -15）。
- 结果：stop 返回 1，耗时 220.4 秒。release_control 抛出 `Stop exceeded 220s; inspect cleanup/alerts; do not start rollback`。

结论：命名空间隔离与原样运行 stop 脚本已验证。但在 481 仍占用 8095/8096 与 GPU 的情况下，**真实 release_control 的 stop 无法完成**
（`resource_snapshot` 检查的是宿主机的端口与计算进程）。因此，"接管且 stop 成功"的分支不能用真实 controller 在本机验证。
测试中该分支的 controller 为测试替身，只替代 `release_control.py --stop`（写 stopped.json、删除指针）。
stop 脚本、路由判定与审批检查都是真实运行的。

## 8. 偏差与需主会话确认的事项

1. **controller 替身。** 见 §7。请确认接受。若必须用真实 controller 验证，只能在 W1 之后的窗口中进行，而窗口中不做测试。
2. **W3.5 放在 execute() 内。** start 之前等待最多 60 秒；不通过则写快照、返回 5，不启动任何服务，也不进入恢复路由。
   这样 W4 无论从哪条路径进入都不会跳过 W3.5。W4 在后台运行时，操作者需要查看返回码与快照文件。
3. **§3 表 W5 的人工路线。** e3 观察器（observe_overnight）不会因服务停止而退出，会一直记录 issues 直到 2026-10-13 09:00。
   人工停服后，需要按身份核对后用 TERM 结束它（不用 KILL）。指令未覆盖这一步，请确认。

## 9. 已知限制与待定事项

- restore14 自身在 owner 发布之前启动失败：沿用 restore 包的冻结语义（先检查再回滚），不会自动恢复，需人工处理，并在 RESULT_E3.md 中如实记录（补充 1 §4）。
- restore14 的 user_authority 仍是任务 B 的文字。指令要求只做三类替换，因此按指令保持。
- DEPLOYMENT_APPROVAL 的 first_cold_baseline 为占位，窗口内由 finalize 写入。
- W1 之后需确认 -13 的 monitor_health（pid 3908999，在 -13 的指针中登记）已随停服退出。
- e2 的原始短请求文本未归档，因此正向只能用夹具验证 finalize 的机制，无法复现 fd11a315… 对应的文本。
- Q1 的 real 模式未在 GPU 上运行（见 §5）。

## 10. 修正与透明记录

- 第一次复现（沙箱副本改了 stop 脚本，触发了源清单校验）无效，已作废，保留为 `p1_repro_stop_route/repro_attempt1_INVALID_integrity_tripped.json`。
  重做改为在内存中替换路径，结果有效（`repro_valid.json`）。
- 第一次 W0 把协调日志第 2452 行的流程说明误判为放行，已改为行首格式匹配（`- 时间 主会话 … 发布 e3 放行`）。
- 演练 run1、run2 为补充 1 之前的版本；run3 为最终版本。

## 11. 文件与哈希（SHA256 前 16 位）

| 文件 | 哈希 |
|---|---|
| release_e3/deploy_conditional.py | eb5c2ba95450d671 |
| release_e3/e3_probe.py | abadf51e2bbfad32 |
| release_e3/test_cpu_orchestration.py | b9ad85e5c810a8f3 |
| release_e3/stop_approved_restore.py（与旧版相同） | 6d52d64590ec0a94 |
| q1_e3.py | 91047aa2eb10e066 |
| stub_e3_server.py | fc352facc63504f1 |
| drill_e3.py（最终版） | c1e26e7319f960ed |
| ns_stop_feasibility.py | ae09060f84763ca1 |
| seal_e3_addendum1.py | 89137698194c6e7a |

开发目录：`/data2/FreeToken/development/ophak_release_e3_20261012/`。
报告：`p1_drills_run3/DRILL_E3.json`；`ns_feasibility_20261012T095502/NS_STOP_FEASIBILITY.json`。

## 12. 请求

请主会话：

1. 确认 §8 的三项；
2. 若接受，按 P1 放行流程在协调日志写"发布 e3 放行"。开窗前，op-hak 会按 §3 表重新做 W0，并在 W4 之前确认 W3.5 通过。
