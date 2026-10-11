# T16 工装（D09 修复候选）CPU 就绪报告

- 轮次标识：`E2-D09FIX-T16-20261011`
- 候选：`7d8d389ee5d85de7e4f8e533f35c27f4c4c02690` @ `/data2/FreeToken/wt/d09_fix_20261011`（含 bd57）
- 父版本：`481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` @ `/data2/FreeToken/wt/release-e2`（未改）
- 工装来源：复制自 `/data2/FreeToken/development/d09_gpu_reapplication_20261010/protocol_t16/`（batch163 验证过的工装），原目录未改。
- 执行时间：2026-10-11 凌晨（协调日志有准确时间戳）

## 1. 适配内容（只允许的位置）

1. 轮次标识 → `E2-D09FIX-T16-20261011`（owned_launch.SPECS、runner.ASSIGNED_RID、CASES/自检测/测试文件的卡名 `D09FIX`）。
2. 候选提交号与工作树 → `7d8d389e…` / `d09_fix_20261011`。
3. `required_rounds` → `(("E2-D09-T16-reapply-bd57-20261010", "kept"),)`（要求 batch163 已封存 kept；已实测其 round.json verdict=kept、pin 0444、MANIFEST 与 round_json_append.py 齐备，`require_closed_round` 支持此检查）。
4. 原生扩展绑定：仿照 bd57 做法，在候选工作树建立指向上批批准的 c17 源文件的符号链接：
   - 新建：`wt/d09_fix_20261011/python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so` → `wt/d09-message-boundary-v1/.../_cpu_moe...so`
   - 新建：同目录 `_pinned_tensor.cpython-310-x86_64-linux-gnu.so` → 同款链接
   - 链接前候选工作树无 `.so`（未删除任何已有文件）；链接后 `git status --porcelain --untracked-files=no` 仍为 0（干净）。
   - c17 源 `.so` 与 release-e2 的 `.so` SHA256 实测逐字节相同（`_cpu_moe` 10a2bd83…、`_pinned_tensor` 07701be2…，与工装内 EXTENSION_SHA256 常量一致）。
   - 新清单 `d09fix_native_provenance_7d8d389e.json`（SHA256 `6d9de3232c799777caaa6f4ec9104911f64740a5653ead894c5c811f96500f7c`），结构沿用 bd57 清单，改动字段：candidate_commit / candidate_worktree / candidate_changed_paths（16 个文件，`candidate_diff_non_python_or_docs` 实测为 []：docs/cli.md + 15 个 .py）。
   - 导入探测（实测，`CUDA_VISIBLE_DEVICES=` + 候选 PYTHONPATH）：`import freetoken.kernel._cpu_moe/_pinned_tensor` 前后 `torch.cuda.is_initialized()` 均为 false。
5. **未改**：父版本/父工作树、协议（8 服务 100 调用、臂结构、冻结输入）、判定逻辑（`assert_default_off_args`、`strict_args`、sequence/h2d SAME 判定）、GPU 锁与清理逻辑、`t16_private_port_dryrun_r062_v1.py`（哈希钉住）、`t16_frozen_helpers_v1/`、`D09_QUEUE_PREDECESSORS`。
   - 候选人默认关闭字段保持 `message_boundary_ckpt=False` 不变——D09 修复树含 bd57，具备 `--enable-message-boundary-ckpt`（server/args.py diff 已核实），原有判定逻辑对新候选原生适用。

## 2. diff 核验结论

`diff -ru` 原目录 vs 本副本：仅 `owned_launch.py`、`runner.py`、`test_native_candidate_binding.py` 三个文件有差异，外加新增 1 个清单 JSON。全部差异见第 6 节全文，逐项属于第 1 节的允许位置。副本中的 `evidence_cpu_filedry_retry1/` 为原 bd57 CPU 证据的原样副本（未动）。

## 3. CPU 测试结果（全部 `CUDA_VISIBLE_DEVICES=`、venv python -B）

```
$ pytest test_native_candidate_binding.py -q
..                                                                       [100%]
2 passed in 4.03s

$ runner.py --self-test
D09 RETRY1 ADAPTER SELFTEST PASS: dynamic PID accepted; business argument delta rejected
```

（自检测通过信息中的 "D09 RETRY1" 字样为原工装标签，未改；卡名绑定已改为 D09FIX 并由自检测断言核对。）

## 4. 文件演练（file dry-run）结果

- `--dry-run --card D09FIX`：**按预期拒绝** `RuntimeError: dry run remains queued while a GPU batch holds the lock`（生产 481 持锁）。
- `--dry-run-injected --card D09FIX`：注入模式通过锁与 GPU 空闲查询后，依次实际通过：batch163 kept 前置轮次检查 → 候选身份/洁净/祖先核对 → 原生来源清单 SHA 绑定 → 原生扩展布局核对 → 源文件只读冻结核对 → 父目录写入探测 → 演练树与 wrapper 创建；随后被钉住基底的**进程竞争扫描**（base 第 214–219 行，注入模式明确不覆盖的一项）拒绝：`competing GPU/test process: 97256 ft serve …`（生产 481 在跑）。
- **回执未生成**（无 `E2-D09FIX-T16-20261011_file_dry_run_v2.json`）。原因是正确性保护而非工装缺陷：注入模式的设计注释明示 ps 扫描保持原样；481 停服后该门即通过。阶段 2 在停 481 之后、正式执行之前用 `--dry-run`（无需注入）补生成回执，再由独审封存启动复核。
- 演练遗留物已清理：两个 `.dryrun_E2-*` 临时树（仅含未执行的 wrapper）已删除；`runs/dev_T16/reviews/` 无新 rid 的任何回执。

## 5. 阶段 2 实际要执行的命令（写全，现在不执行）

```bash
# 前提 0：481 已按手册 2.6 停止（gpu.lock 释放、nvidia-smi 无计算进程、production.active.json 已清除）
# 前提 1：生成演练回执（停 481 后 ps 门通过，无需注入）：
cd /data2/FreeToken && CUDA_VISIBLE_DEVICES= /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/owned_launch.py --dry-run --card D09FIX
# 前提 2：独审封存 runs/dev_T16/reviews/E2-D09FIX-T16-20261011_startup_review_v2.json
#         （PASS，绑定 9 个源文件 SHA256 与前提 1 回执 SHA；既有治理流程，非本工装产出）
# 前提 3：用户批准 runs/dev_T16/reviews/E2-D09FIX-T16-20261011_user_scope_approval_v1.json
#         （绑定 arms=8、planned_generation_calls=100、queue_predecessors=["E2-R047","Strata","E2-R052a","E2-R044"]）
# 正式执行（controller，自动分配批次号并独占 GPU 锁）：
cd /data2/FreeToken && /data2/FreeToken/venv/bin/python -B \
  /data2/FreeToken/development/kimi_phase2_20261011/t16_d09fix/owned_launch.py --run --card D09FIX
```

## 6. diff 全文

见同目录 `diff_d09fix.txt`（SHA256 见 STAGE1_SUMMARY），与 `diff -ru` 原始输出逐字节一致。
