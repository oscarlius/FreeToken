# T16 工装（D05 修复候选）CPU 就绪报告 —— **附一条阻断项，待主会话裁定**

- 轮次标识：`E2-D05-T16-20261011`
- 候选：`730b58c96527fe5bf117d1f3c2430e405173d28b` @ `/data2/FreeToken/wt/d05-decode-align-481-20261011`（基于 481）
- 父版本：`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` @ `/data2/FreeToken/wt/release-e2`（未改）
- 工装来源：复制自 `/data2/FreeToken/development/d09_gpu_reapplication_20261010/protocol_t16/`，原目录未改。

## 0. 阻断项（先读）

**这套工装的正式判定逻辑与 D05 候选不匹配，阶段 2 不能直接执行。**

- 钉住协议要求候选 serve.log 的解析参数中**必须存在** `message_boundary_ckpt=False`（runner.py `assert_default_off_args`：缺键即 `ValueError`，且 `strict_args` 的候选唯一允许增量就是这一项）。
- 但 D05 候选**没有新增任何 CLI 参数**：它对 481 的 diff 仅 6 个文件（README.md、core.py、env.py、scheduler/cache.py、scheduler/scheduler.py、tests/…），不含 server/args.py。它的默认关闭开关是**环境变量** `D05_ALIGNED_DECODE_STATE = EnvBool(False)`（env.py 实测 diff），不进入 serve.log 的解析参数表。
- 因此阶段 2 真跑时，8 臂测量会全部完成，但在 compare 步骤必然抛 "missing its parsed default-off message-boundary flag"，整轮判 failed_harness，白白消耗约 1 小时 GPU 窗口。
- 把默认关闭断言改成接受"无此字段"或改认环境变量，属于**判定逻辑/协议修改**，手册明文禁止，未做。
- 请主会话裁定（示例方向，非建议擅自执行）：为 D05 修订协议的允许增量集并重新独审；或 D05 的 T16 改走别的已批准工装。

## 1. 适配内容（只允许的位置，与 D09fix 套相同）

1. 轮次标识 → `E2-D05-T16-20261011`（卡名 `D05`）。
2. 候选提交号与工作树 → `730b58c9…` / `d05-decode-align-481-20261011`。
3. `required_rounds` → `(("E2-D09-T16-reapply-bd57-20261010", "kept"),)`（batch163 kept 已实测：round.json verdict=kept、pin 0444、MANIFEST 齐备）。
4. 原生扩展绑定：候选工作树新建两个符号链接指向已批准 c17 源 `.so`（`_cpu_moe` / `_pinned_tensor`）；链接前候选树无 `.so`，链接后 git 跟踪态仍干净；c17 与 release-e2 的 `.so` SHA256 实测相同（10a2bd83…/07701be2…）。新清单 `d05_native_provenance_730b58c9.json`（SHA256 `e1c2af2fd03d99a8f2e0a8b4f5a2ce8e7deffcf774879758b6ed9eb79d9bc808`），`candidate_changed_paths` 6 项、非 Python/docs 改动实测为 []。导入探测（`CUDA_VISIBLE_DEVICES=`）前后 `torch.cuda.is_initialized()` 均 false。
5. **未改**：父版本/父工作树、协议、判定逻辑、GPU 锁与清理逻辑、钉住基底、冻结 helpers、`D09_QUEUE_PREDECESSORS`。

## 2. diff 核验结论

`diff -ru` 原目录 vs 本副本：仅 `owned_launch.py`、`runner.py`、`test_native_candidate_binding.py` 有差异，外加新增 1 个清单 JSON；全文见 `diff_d05.txt`（SHA256 见 STAGE1_SUMMARY），逐项属于允许位置。副本内 `evidence_cpu_filedry_retry1/` 为原 bd57 CPU 证据的原样副本。

## 3. CPU 测试结果（全部 `CUDA_VISIBLE_DEVICES=`、venv python -B）

```
$ pytest test_native_candidate_binding.py -q
..                                                                       [100%]
2 passed in 4.03s

$ runner.py --self-test
D09 RETRY1 ADAPTER SELFTEST PASS: dynamic PID accepted; business argument delta rejected
```

（通过信息中的 "D09 RETRY1" 为原工装标签，未改；卡名绑定断言已指向 D05。）

## 4. 文件演练结果

- `--dry-run --card D05`：按预期拒绝（生产 481 持锁）。
- `--dry-run-injected --card D05`：注入后实际通过 batch163 kept 前置检查、候选身份/洁净/祖先、原生清单与扩展布局、源文件冻结、父目录写入探测；随后被钉住基底的进程竞争扫描拒绝（`competing GPU/test process: 97256 ft serve`）——生产在跑时的正确保护行为。
- **回执未生成**；481 停服后用 `--dry-run` 补生成（见第 5 节）。演练临时树已清理，reviews/ 下无本 rid 回执。

## 5. 阶段 2 命令（**阻断项未解除前不得执行**）

```bash
# 前提 0：481 已停止；前提 1：补 dry-run 回执；前提 2：独审封存 startup_review_v2；前提 3：用户批准 user_scope_approval_v1
# （命令形式与 t16_d09fix/CPU_READINESS.md 第 5 节相同，--card D05，目录换为 t16_d05）
cd /data2/FreeToken && /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d05/owned_launch.py --run --card D05
```

**注意：即使补齐前提 1–3，正式执行也会在 compare 步骤因第 0 节阻断项判 failed_harness。执行前必须先有主会话对判定逻辑的书面裁定。**

## 7. 修订 v2（2026-10-11 上午，按主会话审核 `plan/KIMI_STAGE1_REVIEW_20261011.md` 第 2.1 节授权修改）

**阻断项已由主会话书面裁定解除**：默认关闭检查改为"参数零差异 + 环境变量清除"（比原检查更严格），SAME 判定本身（sequence、h2d）不变。第 0 节的阻断描述自此作废；第 5 节命令可按 S4 前提执行。

只改了 `runner.py`（owned_launch.py、钉住基底、check_det、sequence/h2d 比较、锁与清理均未动）：

1. `DEFAULT_OFF_CANDIDATE_ARGS = {}`；新增 `DEFAULT_OFF_ENV = 'FREETOKEN_D05_ALIGNED_DECODE_STATE'`；删除 `PUBLIC_DEFAULT_OFF_FLAG`、`PARSED_DEFAULT_OFF_ARG` 及其全部引用。
2. `environment()`：在 `super().environment(...)` 之后删除所有 `FREETOKEN_D05_` 开头的键（两臂同函数，均清除）。
3. `assert_default_off_args()`：只保留 `base['strict_args'](parent, candidate, DEFAULT_OFF_CANDIDATE_ARGS)` 一行（除 _unique_suffix PID 外拒绝一切差异）。
4. 回执字段 `'default_off_public_flag': {...}` 改为 `'default_off_env': {DEFAULT_OFF_ENV: 'absent'}`。
5. `adapter_self_test()` 改为裁定的 5 条断言（PID 接受 / message_boundary_ckpt 拒绝 / server_port 拒绝 / env 清除验证 / 身份绑定），通过打印 `D05 ADAPTER SELFTEST PASS`。

验证（服务器，CUDA_VISIBLE_DEVICES=）：

- `runner.py --self-test` → **D05 ADAPTER SELFTEST PASS**
- `pytest test_native_candidate_binding.py -q` → **2 passed in 3.77s**
- `owned_launch.py --dry-run-injected --card D05` → 通过全部绑定检查（身份/洁净/祖先/原生清单/扩展布局/源文件冻结/父目录写入探测）后，仍只在钉住基底的进程扫描处被拒绝：`competing GPU/test process: 97256 ft serve …`（生产 481 在跑，正确保护）。与修订前行为一致。

新 SHA256：

- `runner.py`：`859b0a1c0d02c977dedfb794687b1e8225a591a7a7018209d24c7799c315e173`（0444 封存）
- `diff_d05.txt`（v2，相对 protocol_t16 全文）：`f7afdc2048257066a08155d2347d59ec84340ce9ab37681e79089724ebb93442`，改动行复核：仅 1.3 允许位置 + 本次 2.1 授权位置。排除项为运行时产物与本文档（__pycache__、.pytest_cache、evidence_cpu_filedry_retry1、CPU_READINESS.md）。
