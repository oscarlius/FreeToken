# 主会话审批：GLM NVFP4 单卡窗口的停服与恢复（2026-10-12，freetoken-06）

- **绑定指令**：`plan/OPHAK_GLM_NVFP4_LOAD_20261012.md`（sha256 2e2bd8cc048de471903807fd60306bf270b74040330cda4b8c5502b8fffbd7aa）。
- **用户授权**：方向文件 §11（9a76f610d84b…）与协调日志 2026-10-12T17:03:45 条记录的用户原话"现在就可以，你可以让op-hak去执行。"（op 会话转达）。
- **性质**：条件式预签。下列条件由 op-hak 在 W1 之前逐项机判，全部满足即生效，窗口关键路径上不再需要主会话。
- **主会话保留否决**：P0_READY_GLM.md 出来后主会话会异步复核。若发现问题，会在协调日志写"撤回 GLM 窗口审批"，见 C7。

## 1. 授权范围（各一次，不得重试）

1. **停 e3 一次**：只能用 `development/ophak_release_e3_20261012/release_e3/stop_approved_restore.py`（真实停服脚本）停 RELEASE-E3-20261012-01。
   - 停服前先停它的观察器（当前 pid 992641）：按 pid 加 /proc start_ticks 核对后 kill，不得用 `pkill -f`。
   - 停之前，把观察器最后一条采样复制进窗口记录。
2. **GLM 测试服务**：按指令 §2 启动，argv B 一次；argv C 只在 B 报显存不足时用一次。
3. **恢复 e3 一次**，用新身份 `RELEASE-E3-20261012-02`：
   - 内容：release_e3 包的身份副本；commit 9db0ee776c25afa8d2719ab700b2de7ccc606142；argv 与 `PREREG_RELEASE_E3.json` 的 argv.e3 逐项相同。
   - 冒烟：与 Q1 参考逐字段比较。短请求 fd11a315…，长请求 8a442817…。冷基线沿用 release_e3 包的 first_cold_baseline，路径与 sha256 都不变（021e2ab32f660e8bef7936f3fbc745a017d1f86521fcc84b16fcd457660e752f，与 `q1_real/cold_smoke.json` 相同）。不再做新的 Q1。
   - observation_until 仍为 2026-10-13T09:00:00+08:00。
   - 观察器里硬编码的 approval_id 改为 -02。
4. **恢复失败**：
   - 按 e3 补充 1 的三态路由处理，"已接管"的判定身份换成 -02：先用 -02 包停 -02，再执行 restore14。
   - restore14 = RESTORE481-MORNING-20261011-14，至今未执行，run_dir 不存在；只用一次。
5. **不授权**：
   - push；
   - 修改 e3/e2 的源码、构建或 restore14 包；
   - 重试 -02；
   - 往 `/data2/FreeToken/venv` 安装或卸载任何包（GLM 分支走与发布工装相同的 worktree 路径加载）；
   - 停任何不属于 op-hak 的进程。

## 2. 生效条件（W1 前逐项机判，任一不满足就不开窗，并报告）

| 编号 | 条件 |
|---|---|
| C1 | `P0_READY_GLM.md` 存在，权限 0444，指令 1.1–1.7 全部完成 |
| C2 | 协调日志中有 op 会话的"GLM 窗口放行"条目，时间晚于 P0_READY_GLM.md 的 mtime |
| C3 | -02 包与 release_e3 包逐文件 diff，差异只在身份字段：approval_id、run_dir、recorded_at、观察器硬编码 id、README、ROOT_FINAL_REVIEW 与本审批的绑定、user_authority/scope 文字，以及随上述字段变化的 SOURCE_MANIFEST 与 package_source_manifest_sha256。附 diff 全文。-02 包的 CPU 测试全部通过，项数不少于 release_e3 包 |
| C4 | -02 包 `ROOT_FINAL_REVIEW.json` 的 independent_review_sha256 等于本文件的 sha256 |
| C5 | 指令 1.5 的恢复入口真实演练跑到取 GPU 锁之前。下列三项反向对照都必须被拦下：① 绑定的审批 sha 写错；② approval_id 写错；③ 用 -02 包的停服脚本去停 -01 owner |
| C6 | restore14 三个文件的 sha256 与签发时相同：SOURCE_MANIFEST 093f2204…，DEPLOYMENT_APPROVAL 3bea7f40…，ROOT_FINAL_REVIEW c83b9127…；其 run_dir 仍不存在 |
| C7 | 协调日志中没有主会话的"撤回 GLM 窗口审批"条目 |
| C8 | W1 开始时间不晚于 2026-10-13 07:00（W1 + 120 分钟不越过 e3 观察截止 09:00） |

## 3. 窗口内的附加要求

1. **GPU 锁**：GLM 服务在 W3–W5 全程持有与发布工装同一把 GPU 锁；不手删 gpu.lock。
2. **主存**：W1 之前和 W5 之后各记录一次 `free -g` 与 `ls -la /dev/shm`。进入 W6 前要求：
   - GLM 服务在 /dev/shm 的残留为 0（与 W1 记录逐项比较）；
   - 主存 available ≥ 150 GiB（e3 的专家池约 112 GiB，按 shared 计）。
   - 不满足时，只清理 GLM 服务自己的进程与段，然后再进 W6。
3. **与主会话后台任务重叠（17:30 起）**：下面两项都不是 op-hak 的进程，op-hak 不得停它们。
   - `kt_sep_chain.sh`（下载 wheel 后离线安装 KT 新 venv）：脚本第 27 行把 `CUDA_VISIBLE_DEVICES` 置空，不占 GPU。它会比对 FreeToken venv 的 freeze 指纹（0756260823eb…），这正是第 1 节第 5 项禁止往该 venv 装包的原因。
   - `kt_dsv4_image_pull.sh`（只拉镜像，不运行容器）。
   - 两者占磁盘与网络。GLM 读盘变慢只记录，不作判据。如果 W2 发现它们占用 GPU，按 W2 失败处理，并通知主会话。
4. **观察检查**：18:03 与 09:03 两次检查都要覆盖 -01 的 serve.log（到停服为止）和 -02 的 serve.log。
   - 指针判据接受 -02，前提是 commit 与 argv 都与 e3 相同。
   - 窗口期内的 health 与指针异常标注为窗口，不计入。
   - 续段判据不变：`cut_continuation_check.py`（31a46f4c…）严格档与宽松档中 remain ≤ 32768 的对数为 0。GLM 服务日志不适用这一判据。
5. **恢复后**：用 -02 包的 `post_night_observer.py` 启动观察器。

## 4. 主会话复核记录

- **已核**：
  - 指令文件 sha 与权限 0444；指令 §2 的失败去向逐步可达，最坏情况落到 restore14（e2）。
  - restore14 未用过。
  - Q1 冷基线 sha。
  - 生产指针为 -01 / 9db0ee77。
  - 观察器只读，不会触发停服或恢复。
  - /dev/shm 只用了 69 MB，e3 专家池是进程内共享内存，进程退出即释放。
  - GLM 检查点 config.json 为 e23c5d98…，mtime 09-21 与其他下载文件相同，目录中没有改写痕迹。
  - 磁盘：/data2 余 2.9T，/ 余 2.7T。
- **未核**：
  - op 的显存账逐张量求和：指令把它当预测，由 W3 日志核对，本审批不依赖它。
  - op-hak 的 P0 代码：由 C3、C5 机判，op 核对后放行；主会话异步复核，保留 C7 否决。
- **自检**：
  - 本审批在包建成之前签发，独立性比 e3 弱。弥补方式有两条：差异只允许出现在身份字段（C3），反向对照三项必须拦下（C5）。
  - 风险最大的是 W6：e3 冒烟与 Q1 逐字比较。e3 的 Q1 与正式冒烟是两次独立冷启动，SHA 相同，所以预期一致。若不一致，按既有规则走 restore14，不放宽。
