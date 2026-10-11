# D09 T17 GPU 工装独立启动审查

- 审查时间：2026-10-09T23:44:33+08:00
- RID：`E2-D09-T17-night-20261009`
- 方法：本地与远端只读源码/哈希/既有 CPU FILEdry 收据；未运行 GPU、服务、HTTP、编译或下载。
- 结论：**P0 / REQUEST CHANGES；禁止 GPU 启动。**

## 已核对且正确的静态事实

- 本地与 `/data2/FreeToken/development/d09_t17_night_v1` 的 8 个执行源完全同字节；`D09_T17_EXACT_INPUTS.json` SHA-256 为 `b21a29e47d6dc5fb5be9d32e98bc446ed8a1f5d625efd7774aad31d2afdde6f9`。
- 输入有两个 cell：`20282/1020` 与 `22558/197`。每个 donor 与 target 等长，恰好一个 ID 在 `boundary+1` 处不同（分别为 20283、22559）；其余前缀相同。
- 配置静态预算是 6 个服务、8 次调用，全部带 `--enable-message-boundary-ckpt`；既有 CPU FILEdry 收据确为 6/8、`product_acceptance=false`，因此没有被误读为 GPU 结果。
- 远端当前 `ROOT_ADMISSION.json` 不存在且 `/data2/_shared/gpu.lock` 存在；当前尚不会因 admission 缺失直接启动，但这不能修复下列绕锁缺陷。

## P0 / HIGH 问题

### 1. Root admission 与 R047 锁均未被真实消费

位置：`d09_t17_runner.py:111-113`，以及全文没有 `/data2/_shared/gpu.lock` 的取得或核验。

`--run` 只检查 `ROOT_ADMISSION.json` 是否是普通文件，不校验其 SHA、RID、candidate commit、输入/源码 hash、root 身份或一次性消费状态。运行器也完全不检查、更不原子取得共享 GPU lock；因此 R047 已持锁时，任意人放置任意同名文件即可尝试 GPU 启动。

修复：在所有 GPU 前置动作之前，解析并严格比对不可写 admission 的 RID、candidate、输入 SHA、执行源 manifest SHA、R047 predecessor/owner；用原子 `O_EXCL` 取得已验证的本轮 GPU lock，保存 PID/start-ticks/lock inode。遇 foreign lock 必须非零退出且绝不启动服务。

### 2. 实际服务无法导入已复制的工装模块

位置：`tooling/t17_startup.py:3-4`、`d09_t17_runner.py:49-54,79-81`。

启动脚本导入 `t17_d14_exact_ids`、`t17_d14_observe`，但 runner 只复制为 `t17_exact_ids.py`、`t17_observe.py`。它覆盖的 `PYTHONPATH` 仅含 service arm 与 candidate `python/`，不含 `/data2/FreeToken/development`；前者也不存在于这些路径。真实 `--run` 会在服务启动前 `ModuleNotFoundError`，而 FILEdry 从不导入启动脚本，未覆盖此缺陷。

修复：统一 copied filenames 与 import names，并在 CPU startup probe 中从实际 service arm/import path 导入这三个已复制文件；不要依赖未声明的全局 `PYTHONPATH`。

### 3. 产品比较必然取不到 sampled IDs，且未核验产品实际收到的输入

位置：`tooling/t17_startup.py:23`、`d09_t17_runner.py:92-102`、`tooling/t17_observe.py:64-75`。

真实 endpoint 返回 `input_ids_sha256`、文本和 usage，却不返回 `sampled_token_ids`；runner 在 cell 比较时无条件读取 `raw['sampled_token_ids']`。因此八个真实调用后会 `KeyError`，没有 T17 terminal。更严重的是 runner 从未比较 endpoint 的 `input_ids_sha256` 或 `FT_T17_INPUT_RECEIPTS` 与每条冻结 SHA；FILEdry 在 `d09_t17_runner.py:96` 人工注入 `[0]*32`，所以可 PASS 而不能证明真实产品路径。

修复：将 response UID 绑定到 immutable input receipt，断言 receipt/endpoint SHA 等于冻结 request SHA；从 `observations.jsonl` 读取同 UID 的有序 sampled token events，检查 32 token、完成状态、无 error，再把实际 IDs/文本用于 coldA–coldB 和 hot target–cold 比较。FILEdry 必须模拟同一 receipt/observation contract，不能只塞字段。

### 4. 启动、停止和失败清理没有可审计的 fail-closed 生命周期

位置：`d09_t17_runner.py:68-106`。

runner 没有记录 Popen PID/start ticks、health receipt、每次请求的错误状态、清理结果或 lock owner。任一 health/request/assertion/比较异常只通过 `finally` 尝试 SIGTERM，随后抛出；没有原子 terminal failure receipt，不能证明服务已停或让后续轮安全判定。正常停止也没有检查退出、进程组存活或 port 释放。

修复：为每个 arm 以 append-only lifecycle receipt 记录 PID birth、argv/hash、health、request UID/结果、SIGTERM/wait、group-dead/port-free 证据；任何失败先写 `failed_harness` terminal，再仅在确认无 owned process 后释放本轮锁。清理失败应保留锁并阻止后续 GPU 轮。

### 5. candidate/provenance 仅记录字符串，未验证实际 GPU worktree

位置：`d09_t17_runner.py:43-47,36-40,75`。

config 中的 `c17b69a...`、provenance hash 与 `--enable-message-boundary-ckpt` 只是记录/argv 断言；未核验 `/data2/FreeToken/wt/d09-message-boundary-v1` 的 HEAD、源 manifest、实际解析 flag 或 state dump。`sha(PROVENANCE)` 只证明文件非空，不能绑定其预期内容。错误 worktree 或未生效开关仍可能被归因为 c17。

修复：GPU admission 前验证实际 worktree HEAD 和 immutable provenance digest；启动后保存已解析配置/feature state 的产品 receipt，并将其与 c17、inputs、tooling hash 绑定。任何不符必须在请求前停止。

## FILEdry 结论

`evidence_cpu_filedry_local_v3/.../terminal.json` 的 `PASS` 仅验证 fake process/transport 下的配置循环和 synthetic comparison，且明确 `product_acceptance=false`。它不是实际 runner 成功，也不能替代 GPU startup、产品输入回执、sampled token、比较或 cleanup 证据。

在所有 P0 修复、源码重新冻结、CPU 真实 arm-import/receipt 回归和独立复审前，不得创建 root admission 或尝试 GPU run；R047 lock 必须保持优先。
