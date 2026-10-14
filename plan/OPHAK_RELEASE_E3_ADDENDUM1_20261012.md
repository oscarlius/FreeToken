# 发布 e3 补充 1：W4 启动失败时的路由（2026-10-12，主会话 freetoken-06）

> 针对 op-hak 报告的阻塞：e3 在发布 owner.json 之前失败时，`recover_after_restore_failure` 先调用 `stop_approved_restore.py`。该脚本在既没有 owner、也没有 stopped.json 时抛出异常，于是 restore14 不会运行，481 停着无人恢复。原测试用的是返回 0 的桩，没有覆盖这一点。本补充修订 `OPHAK_RELEASE_E3_20261012.md`（a52388ca…）§2.4 与 §3，其余不变。用户已确认本补充。

## 裁定：方案 A 加强版（只改 e3 发布包，restore14 与 stop 脚本保持原样）

### 1. `release_e3/deploy_conditional.recover_after_restore_failure` 改为三分支

先轮询，最长 60 秒，每 2 秒一次，判断 e3 处于哪种状态：

- **e3 已接管**：run 目录有 `owner.json`，或者 `production.active.json` 的 approval_id 是 e3 的。处理：照原路径运行本包的 `stop_approved_restore.py`；它返回 0 后，执行 `restore14/deploy_conditional.py --execute`。stop 返回非 0 时，生产状态不明，**不启动 restore14**，按"状态不明"分支写快照并报告。
- **e3 确认不存在**：以下条件同时成立，并且连续两次轮询都成立：
  - 没有命令行含 `release_control.py` 且含 `RELEASE-E3-20261012-01` 的进程；
  - 8095/8096 没有监听；
  - `nvidia-smi` 没有计算进程；
  - `/data2/_shared/gpu.lock` 与 `production.active.json` 都不存在。

  处理：跳过 stop，直接执行 `restore14/deploy_conditional.py --execute`。
- **状态不明**：60 秒内既没有接管，也不能确认不存在（例如守护进程还活着，但一直没有发布 owner）。处理：**不启动 restore14**，以免两个服务同时抢 GPU。写 `ROUTING_AMBIGUOUS.json`（附进程、端口、锁、显存快照），返回非 0，立即在协调日志记录并发消息给主会话。

这样也覆盖了 op-hak 提到的 20 秒竞态：守护进程如果在 20 秒后才发布 owner，会落入"已接管"分支，走正常的 stop。

### 2. 新增 W3.5：W4 之前的只读预检

在 W4 之前，用与 `start_approved_release.py` 相同的条件，只读检查一遍，最长等 60 秒：

- 无计算进程，每张卡显存 < 1000 MiB；
- 8095/8096 没有监听；
- gpu.lock、`production.active.json`、`production.cleanup_failed.json` 都不存在；
- e3 的 run 目录不存在。

结果处理：

- 通过：进入 W4。
- 不通过：说明 Q1 没有清理干净，此时 e3 和 restore14 的启动都会被同样的断言拒绝。处理：不启动任何服务，写快照，立即报告主会话。这是唯一一种由人工处理的停服状态。

### 3. 测试（不准用返回 0 的 stop 桩代替真实语义）

- 用**真实的** `stop_approved_restore.py`（只替换 owner 路径和 run 目录到临时位置），覆盖三种情形：
  - 无 owner 且确认不存在：调用序列为 `['restore14']`，没有 stop；
  - owner 在第 25 秒出现：调用序列为 `['stop', 'restore14']`；
  - 守护进程存活但始终没有 owner：不调用 restore14，写出 `ROUTING_AMBIGUOUS.json`，返回非 0。
- 原有的 smoke 失败测试保留，并补一条断言：失败路径上从未调用 ROLLBACK184。
- 改完后重新封印 SOURCE_MANIFEST → DEPLOYMENT_APPROVAL → ROOT_FINAL_REVIEW 链；`independent_review_sha256` 填本补充的 SHA。

### 4. restore14 保持原样

restore14 自己在 owner 发布之前启动失败时，同样会停在"先检查再回滚"。这是 restore 包原有的冻结语义，restore13 在多个窗口里都按这个语义用过。本补充不改它。若出现这种情况：停止一切 GPU 工作，立即报告主会话（481 处于停服状态，需要人工处理）。在 `RESULT_E3.md` 里如实记录这一点，作为已知限制。

## 5. 对 op-hak 两点询问的答复（下发前补入）

1. **"已接管"的判据**：
   - e3 的 run 目录存在 `owner.json`；或者
   - `production.active.json` 的 `approval_id` 等于 `RELEASE-E3-20261012-01`，**并且** `commit` 等于 `9db0ee776c25afa8d2719ab700b2de7ccc606142`。

   指针属于其他 owner，或者两项只对上一项，一律归"状态不明"。
2. **真实 stop 脚本的测试方法**：同意在私有挂载命名空间（`unshare -rm`）里原样运行未修改的 stop 脚本，并且先做一次可行性验证。必须同时满足以下护栏，任何一条做不到，就改回"内存中替换路径"的测试，并在报告里注明：
   - 先 grep stop 脚本及其导入的所有模块，列出全部写死的绝对路径。凡是会被写入或删除的路径，在命名空间内都要用临时目录 bind 覆盖。至少包括 `/data2/FreeToken/run`、`/data2/FreeToken/runs/production`、`/data2/_shared`（GPU 锁所在目录）。
   - 运行 stop 之前，在命名空间内检查每个被覆盖路径里的标记文件，确认看到的是临时目录。
   - 伪造的 owner 只能引用测试自己启动的哑进程（如 `sleep`），并记录 pid 与 start_ticks。进入命名空间之前，先在宿主侧读取真实的 `production.active.json`，断言哑进程的 pid 与其中任何 pid 都不同。
   - 测试前后在宿主侧各记录一次：真实 `production.active.json` 的 SHA256、`/data2/_shared/gpu.lock` 的 inode 与内容、481 的 health。三项必须前后一致，否则立即停止并报告。
   - 这项验证只在命名空间内进行，不改任何文件，不触碰生产指针。

## 自检

| # | 项 | 情况 |
|---|---|---|
| 1 | 为什么不选 B | 改 stop 脚本会同时改变 restore14 的语义，影响面更大，而且 restore14 是已审过的恢复包的副本 |
| 2 | 为什么不选 C | 窗口的关键路径上不能有人工步骤（清单第三次教训）。现在只有两种"确实无法自动"的状态（W3.5 不通过、状态不明）才交给人工，并且两者都有快照 |
| 3 | 单纯 A 方案的漏洞 | 守护进程超过 20 秒才发布 owner 时，A 会在 e3 起来的同时启动 restore14。加强版先确认 e3 不存在，否则不启动 |
| 4 | 测试是否覆盖真实语义 | 三种情形都用真实的 stop 脚本；不允许用返回 0 的桩 |
| 5 | stop 本身失败 | 生产状态不明，不启动 restore14，按"状态不明"处理（自检时补上） |
| 6 | 命名空间测试会不会伤到生产 | stop 会删锁、给进程发信号。护栏：覆盖全部被写路径并用标记文件确认；只用哑进程，且断言其 pid 与生产 pid 不同；宿主侧前后比对指针、锁和 health |
