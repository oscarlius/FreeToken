# T11 E1-R003-uid8：uid=8 缺完成捐赠记录的复现与归类

> **10-06 21:05 改写（总负责人；取代下文所有更新块与正文中冲突的内容）**
>
> - **已知**：S-006 与 E2-R011（E2-base）已复现：11 次恢复，目标请求（历史编号 uid=8）命中 13,376、重算 56；完成捐赠是否写回 radix 树未证明（H-hook 与 H-bug 未分）。
> - **第 2 阶段改为行为判定，轮次 E2-R052，基线 E2-base.1@0aa23431，1 个进程**，不需要新钩子：
>   1. 按 E2-R011 的同一轨迹重放到目标请求（uid=8 对应轮）结束。
>   2. 紧接着发一个「续问」请求：目标请求的完整提示 + 输出 + 1 条新的短用户消息。
>   3. 记录续问的 `cached_tokens`。命中长度 ≥ 目标请求完整长度向下取整到 64 的倍数 → 完成捐赠已写回，判 **H-hook**（只是落盘钩子覆盖面）；命中停在 13,376 或更短 → 判 **H-bug**。
> - 同时记录 E2-base.1 的 D0 段记录与 `anchor_snapshots_taken`，因卡D14 改动了快照计划，问题可能已被顺带修复，需如实记录。
> - 批次脚本由 02 泳道照 E2-R011 的批次改写（只加第 2 步续问），经泳道 R 启动前复核后执行。GPU 队列第 8 位（PLAN §8.8）。
> - 结果文件：`results/T11-E2-R052_<YYYYMMDD>.md`。结论直接决定卡D05 的分支。

> **2026-10-05 重新规划更新（优先于下文）**　T11 的基点改为 E2-base.1（原 97bc62c 作废），依赖卡D17，阶段 B / P2。**卡面正文尚未按 E2-base.1 改写，轮次号待总负责人分配；分配并更新本卡前不得执行。** 详见 `../PLAN_20261005_重新规划.md` §5。

| 项 | 值 |
|---|---|
| 轮次 ID | 阶段 1：`S-006`（只读分析，不占 GPU）；阶段 2：`E1-R003-uid8`（GPU） |
| 结果文件 | `results/T11-S-006_<YYYYMMDD>.md`；阶段 2 另写 `results/T11-E1-R003-uid8_<YYYYMMDD>.md` |
| 优先级 | P1（D05 的前置：先归类，再决定修不修） |
| 依赖 | 无（树 `exp/e1r003-statedump` @ 97bc62c） |
| 预计耗时 | 阶段 1 约 30 分钟；阶段 2 约 20 分钟 |
| 论文依据 | v3.2 §6.8 状态层表「缺陷线索：uid=8（round 7）在恢复臂没有产生完成捐赠记录，参照臂有——待单独归因」；「uid=8 缺少完成捐赠记录，作为独立缺陷归因，不与无损性判定混在一起」 |

## 规划阶段读码得到的待检假设（执行者只需验证，不需理解代码）

e1r003sd 树上，落盘钩子的 `donate` 点只挂在「预填段提交」路径（`python/freetoken/scheduler/cache.py:481-483`），请求**完成时**的捐赠（`cache_req` 的 `finished=True` 分支，`cache.py:415-461`）**没有**挂钩子。uid=8 在恢复臂只续算了 56 个 token（`cached=13376、recomputed=56`），而 GDN 分块大小是 64（`kernel/fla/chunk.py:28`）。参照臂对 uid=8 整段重算 13,432 token，必然经过预填段提交。

**假设 H-hook**：「缺 donate 记录」只是钩子覆盖面问题（短续算没有触发预填段提交的落盘），**不是**状态没有写回树。
**假设 H-bug**：恢复后完成捐赠确实没有发生（状态没写回 radix 树）——这才是需要 D05 修的缺陷。

## 阶段 1：只读归类（S-006）

```bash
SSH="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_exec.py"
$SSH 'cd /data2/_shared/runs/ft_rounds/E1-R003-stateeq && /data2/FreeToken/venv/bin/python - <<"EOF"
import json, collections
def idx(p):
    return [json.loads(l) for l in open(p)]
A, B = idx("dump_A/index.jsonl"), idx("dump_B/index.jsonl")
print("A kinds", collections.Counter(r["kind"] for r in A), "B kinds", collections.Counter(r["kind"] for r in B))
for name, X in (("A", A), ("B", B)):
    by = collections.defaultdict(list)
    for r in X:
        by[r.get("uid")].append((r["kind"], r["length"]))
    print(name, {k: by[k] for k in sorted(by, key=lambda u: (u is None, u))})
R = json.load(open("S_A_coldfirst.json"))["rounds"]
for i, r in enumerate(R):
    print("A round", i, "prompt", r["prompt_tokens"], "cached", r["cached_tokens"], "recomputed", r["recomputed_tokens"])
EOF'
$SSH 'cd /data2/_shared/runs/ft_rounds/E1-R003-stateeq && sed "s/\x1b\[[0-9;]*m//g" S_A/serve.log | grep -nE "Prefill batch|GDN bank: resuming" | sed "s/, token usage.*//" | head -80'
```

把输出整理成表（结果文件第 4 节）：

| uid | 轮 | prompt | cached | recomputed | A 侧记录（kind:length） | B 侧记录 | recomputed 是否 < 64 |
|---|---|---|---|---|---|---|---|

（uid 与轮的对应：dump 记录里的 `uid` 与回放轮次按出现顺序对应；RESULTS_E1 记录 uid=1 是轨迹第一条、uid=8 是 round 7。对应不上时如实写「无法对应」。）

**规划阶段只读预检的输出（供核对，执行者仍须自己跑一遍并贴原文）**：A 侧 uid=2…12 中只有 uid=8 无 `donate`；其余恢复轮 `recomputed` 为 92、3098、1139、1903、760、1431、600、75、65、3803，均 ≥ 64 且都有 `donate`；uid=8 为 `cached=13376、recomputed=56`。B 侧 uid=8 的 `donate` 长度是 13,376（= ⌊13,432/64⌋×64），也就是说该点的状态在 A 侧早已由 uid=7 以 `archive(13376)` 写入。执行者的输出与此不一致 → 停，上报。

### 阶段 1 判据

| 观察 | 结论（建议） |
|---|---|
| A 侧**所有** `recomputed < 64` 的恢复轮都没有 `donate` 记录，所有 `recomputed ≥ 64` 的恢复轮都有 | 支持 H-hook：建议子结论 `E1-R003-stateeq SC7` 改写为「钩子覆盖面造成的记录缺失（待阶段 2 确认）」 |
| 存在 `recomputed ≥ 64` 的恢复轮也没有 `donate` | 不支持 H-hook，倾向 H-bug，进入阶段 2 |
| uid=8 是唯一 `recomputed < 64` 的恢复轮 | 证据不足以区分，进入阶段 2 |

## 阶段 2：带捐赠追踪的复现（E1-R003-uid8，GPU）

用同树、同轨迹、同 `S_A` 配置（`slots=32`）重跑一次，打开 `FT_D3_TRACE=1`（该树祖先提交 3c8f224 引入：每次 GDN 捐赠打印边界与捐赠后的树）与 `FT_DEV_STATE_DUMP`，看 uid=8 完成时是否有捐赠事件。

### 前置检查

```bash
$SSH 'git -C /data2/FreeToken/wt/e1r003sd rev-parse --short=7 HEAD; grep -rn "FT_D3_TRACE" /data2/FreeToken/wt/e1r003sd/python/freetoken/ | head -3; ls -d /data2/_shared/runs/ft_rounds/E1-R003-uid8 2>/dev/null; ls -la /data2/_shared/gpu.lock 2>&1'
#   期望：97bc62c；至少 1 行（没有 → 阶段 2 不执行，上报）；无目录；锁文件不存在
```

### 批次脚本（01 README §4 模板）

**参数区**：

```bash
RID=E1-R003-uid8
CARD=T11
WT=/data2/FreeToken/wt/e1r003sd
EXP_COMMIT=97bc62c
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
```

**主体区**：

```bash
TR=/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json
FLAGS="--enable-special-token-ckpt --max-prefill-length 4096 --mamba-host-slots 32"
O=$D/S_A_trace; ok || exit 7; mkdir -p $O/dump
start $O "FT_DEV_STATE_DUMP=$O/dump FT_D3_TRACE=1" $FLAGS
[ $READY = 1 ] || { echo "NOT-READY"; stop; exit 6; }
$PY $SCR/agent_trace.py replay --trace $TR --out $O/coldfirst.json --fresh-note "$RID" > $O/coldfirst.log 2>&1; echo "replay rc=$?"
grep -c 'GDN bank: resuming' $O/serve.log | sed 's/^/恢复次数（E1-R003-stateeq 为 11）: /'
[ -s $O/dump/index.jsonl ] || { echo "GATE-FAIL-NODUMP"; stop; exit 5; }
stop
$PY $SCR/state_eq.py /data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_A $O/dump --tol 0.0 > $D/eq_prevA_vs_new.txt 2>&1; echo "prevA_vs_new rc=$?"; grep "^len=" $D/eq_prevA_vs_new.txt
```

### 读数

```bash
$SSH 'cd /data2/_shared/runs/ft_rounds/E1-R003-uid8/S_A_trace && sed "s/\x1b\[[0-9;]*m//g" serve.log | grep -nE "Prefill batch|GDN bank: resuming|donat|D3" | sed "s/, token usage.*//" | head -150'
```

找到 round 7（cached 13376、recomputed 56）前后的事件，记录：是否有捐赠追踪行、捐赠的边界长度、捐赠后树里是否出现 13,376 或 13,432 的节点。

### 阶段 2 判据

| 观察 | 结论（建议） |
|---|---|
| 恢复次数仍为 11，`eq_prevA_vs_new` 全部逐位一致，round 7 完成时有捐赠追踪行 | 「可复现、状态已写回、仅落盘钩子未覆盖」→ H-hook 成立；D05 改为「补钩子覆盖面」（工装），不是状态缺陷 |
| round 7 完成时**没有**捐赠追踪行 | H-bug：「恢复后完成捐赠未发生」→ D05 按缺陷修复立项，附本轮工件 |
| 恢复次数或落盘与 E1-R003-stateeq 不同 | 「不可复现」→ 上报，不下结论 |

`proposed_verdict = measured`。

## 停止条件

阶段 1：文件缺失、JSON 解析失败。阶段 2：门失败；`NOT-READY`；replay `rc` 非 0；`GATE-FAIL-NODUMP`；捐赠追踪开关不存在。

## 上报

规则 §8。「需要总负责人决定」：D05 的立项形式（补钩子 / 修缺陷）。
