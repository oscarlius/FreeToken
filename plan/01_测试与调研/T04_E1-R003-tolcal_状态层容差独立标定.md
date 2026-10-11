# T04 E1-R003-tolcal：状态层容差独立标定（合法重排包络）

> **10-06 21:05 改写（总负责人；取代下文所有更新块与正文中冲突的内容，现可执行）**
>
> - **定位变化**：T17 已在 28 组上证明「同结构冷参照」与续算逐位相等，放行不再依赖容差。T04 现在只为论文 §9「合法重排包络」和 PLAN §4.1 第 3 层记录提供标定数据，优先级降为 P2。
> - **改为只读分析，轮次 S-007，不占 GPU**。数据已经存在，不再采集：
>   1. `E2-R002`（T04，待复核）：同一输入在 B、R4096、R8192、RLM 四种合法分块下的状态落盘，36 条可比记录。先完成它的独立复核。
>   2. `E2-R036`、`E2-R038` 中带普通冷参照臂的 4 组（`prefix-8192-tail-65`、`prefix-12416-tail-4097`、`prefix-12736-tail-8193`、`prefix-18944-tail-4097`）：普通全冷对同结构参照的状态与 128 token 差异。
> - **工具**：卡D03 已交付的 `scripts/state_envelope.py` 与 logits 比对工具；只读运行，不改工具。工具不能读取上述某类数据时停止上报，由卡D03 补读取器。
> - **输出**：按四类状态（GDN conv、GDN recurrent、PLE conv、PLE ngram）逐层给出最大绝对差与相对差的分布，标明来自哪种合法重排；不下「容差」的放行结论，只给分布。
> - **时间约束**：避开 T20 第 1、2、3、7 项性能测量时段运行（PLAN §8.8 第 3 条）。
> - 结果文件：`results/T04-S-007_<YYYYMMDD>.md`。若分析表明需要新的 GPU 落盘，预留 E2-R053，另行申请。

> **2026-10-05 重新规划更新（优先于下文）**　T04 的基点改为 E2-base.1（原 97bc62c 作废），依赖卡D17，阶段 B / P2。**卡面正文尚未按 E2-base.1 改写，轮次号待总负责人分配；分配并更新本卡前不得执行。** 详见 `../PLAN_20261005_重新规划.md` §5。

| 项 | 值 |
|---|---|
| 轮次 ID | `E1-R003-tolcal`（结果文件 `results/T04-E1-R003-tolcal_<YYYYMMDD>.md`；阶段 2 另写 `_r2`） |
| 类型 | 标定，GPU |
| 优先级 | P0 |
| 依赖 | **阶段 1：无**（用现有带钩子的树 `exp/e1r003-statedump` @ 97bc62c）。**阶段 2：D03**（逐层包络工具、参照臂中间边界落盘、固定后续 token 的 logits 比对） |
| 预计耗时 | 阶段 1 约 50 分钟（3 个进程 × 约 15 分钟）；阶段 2 视 D03 交付 |
| 磁盘 | 每臂落盘约 1.5–2 GB（参照 batch18/19：A+B+B2 共 8.6 GB），三臂约 6 GB |
| 论文依据 | v3.2 §3.5「容差必须独立标定」、§6.8「判定与下一步」；`REPLY_V31_MERGED_REVIEW` §2；**v3.2 不接受 `RESULTS_E1` 第四刀「本次实测到的偏离量级就是容差标定的起点」** |

## 要回答的问题

#577 恢复路径的状态与整段重算不逐位相等（11 个可比长度 10 个不等；论文 §6.8）。这些差异是否落在「一次**已知合法**的计算顺序变化」应有的范围内？容差必须来自独立的合法重排，**不能**用恢复路径自己的偏差。

合法重排的定义（本卡采用）：同一棵树、同一倒序轨迹、`--mamba-host-slots 0`（每轮整段重算，不走恢复），只改变预填子块划分：
- `R4096`：分块 4096（= E1-R003-stateeq 的 `S_B`/`S_B2` 配置；本卡复跑一次作为跨日确定性检查）；
- `R8192`：分块 8192（`--max-prefill-length 8192`；E0-R002 生产曾用，已知可运行）；
- `RLM`：层优先（`--prefill-layer-major`，子块 4096）。

## 阶段 1：采集合法重排的状态落盘（现在可执行）

### 前置检查

```bash
SSH="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_exec.py"
$SSH 'ls /data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json /data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_B/index.jsonl /data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_A/index.jsonl /data2/FreeToken/scripts/state_eq.py && git -C /data2/FreeToken/wt/e1r003sd rev-parse --short=7 HEAD && df -h /data2 | tail -1'
#   期望：4 个文件存在；commit 97bc62c；可用空间 > 50G
$SSH 'ls -d /data2/_shared/runs/ft_rounds/E1-R003-tolcal 2>/dev/null; ls -la /data2/_shared/gpu.lock 2>&1; nvidia-smi --query-gpu=memory.used --format=csv,noheader'
#   期望：无目录；锁文件不存在；显存 < 1000 MiB
```

### 批次脚本（01 README §4 模板）

**参数区**：

```bash
RID=E1-R003-tolcal
CARD=T04
WT=/data2/FreeToken/wt/e1r003sd
EXP_COMMIT=97bc62c
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
```

**主体区**：

```bash
TR=/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json
REFB=/data2/_shared/runs/ft_rounds/E1-R003-stateeq/dump_B
FLAGS="--enable-special-token-ckpt --mamba-host-slots 0"
arm() { local ARM=$1; shift; local O=$D/$ARM
  ok || exit 7
  mkdir -p $O/dump
  # 落盘钩子在服务端：FT_DEV_STATE_DUMP 必须给 ft serve，不是给回放客户端
  start $O "FT_DEV_STATE_DUMP=$O/dump" $FLAGS "$@"
  [ $READY = 1 ] || { echo "$ARM NOT-READY"; stop; exit 6; }
  $PY $SCR/agent_trace.py replay --trace $TR --out $O/replay.json --fresh-note "$RID-$ARM" > $O/replay.log 2>&1; echo "$ARM replay rc=$?"
  grep -c 'GDN bank: resuming' $O/serve.log | sed "s/^/$ARM 恢复次数（应为 0）: /"
  if [ -s $O/dump/index.jsonl ]; then wc -l < $O/dump/index.jsonl | sed "s/^/$ARM 落盘记录: /"; else echo "$ARM NODUMP"; fi
  stop
}
arm R4096 --max-prefill-length 4096
arm R8192 --max-prefill-length 8192
arm RLM   --max-prefill-length 4096 --prefill-layer-major
echo "### 比对（state_eq.py；rc=1 表示有差异，对合法重排是预期的，不是失败）"
$PY $SCR/state_eq.py $REFB $D/R4096/dump --tol 0.0 > $D/eq_B_vs_R4096.txt 2>&1; echo "B_vs_R4096 rc=$?"; tail -16 $D/eq_B_vs_R4096.txt
$PY $SCR/state_eq.py $D/R4096/dump $D/R8192/dump --tol 0.0 > $D/eq_R4096_vs_R8192.txt 2>&1; echo "R4096_vs_R8192 rc=$?"; tail -16 $D/eq_R4096_vs_R8192.txt
[ -s $D/RLM/dump/index.jsonl ] && { $PY $SCR/state_eq.py $D/R4096/dump $D/RLM/dump --tol 0.0 > $D/eq_R4096_vs_RLM.txt 2>&1; echo "R4096_vs_RLM rc=$?"; tail -16 $D/eq_R4096_vs_RLM.txt; }
for p in R8192 RLM; do $PY $SCR/serve_args_diff.py $D/R4096/serve.log $D/$p/serve.log > $D/args_diff_R4096_$p.txt 2>&1; cat $D/args_diff_R4096_$p.txt; done
```

> 注意：`state_eq.py` 结尾的「结论：bank 恢复与整段重算在状态层一致」是**固定文案**，与比较对象无关（论文 §6.8 工装备注；D04 修正）。**不得引用这一行**，只读逐长度行。

### 阶段 1 判据

| 检查 | 期望 | 不满足时 |
|---|---|---|
| 三臂 `恢复次数` | 0 | 停，上报（说明 slots=0 未生效） |
| `B_vs_R4096`（跨日同配置） | 所有可比长度「逐位一致」，`max|Δ|=0` | **停**，上报为重大异常：跨进程确定性前提失效，后续标定无意义 |
| `R4096_vs_R8192` 可比长度数 | ≥ 6 | 少于 6：记录并上报，阶段 2 需 D03 的中间边界落盘才能补 |
| `RLM` 落盘 | 有 `index.jsonl` | `NODUMP`：**本卡允许继续**（钩子可能不覆盖层优先提交路径），记为异常项，上报 |
| `serve_args_diff` | `R8192`：只差 `pid`、`max_extend_tokens`；`RLM`：只差 `pid`、`prefill_layer_major` | 多出键：该对比作废，上报 |

把 `R4096_vs_R8192`（以及 `R4096_vs_RLM`）的逐长度 `max|Δ|` 与 `E1-R003-stateeq/state_eq.txt` 中恢复对重算（A 对 B）的逐长度 `max|Δ|` 并排列表（结果文件第 4 节）：

```bash
$SSH 'cd /data2/_shared/runs/ft_rounds && grep "^len=" E1-R003-stateeq/state_eq.txt; echo ---; grep "^len=" E1-R003-tolcal/eq_R4096_vs_R8192.txt; echo ---; grep "^len=" E1-R003-tolcal/eq_R4096_vs_RLM.txt 2>/dev/null'
```

**阶段 1 不下「合法/不合法」结论**：`max|Δ|` 是逐元素最大值，不是论文用的逐层相对 L2；只列表，`proposed_verdict = pending_review`，子结论 `E1-R003-stateeq SC8` 保持 `hypothesis`。

### 阶段 1 `round.json` 骨架

```json
{
  "schema": "ft_round/v2", "round_id": "E1-R003-tolcal", "epoch": 1, "card": "T04",
  "title": "状态层容差独立标定：合法重排（子块 4096/8192/层优先）落盘", "parent": "E1-R003-stateeq",
  "created_at": "", "closed_at": "", "executor": "",
  "base": {"repo": "fork/FreeToken", "branch": "exp/e1r003-statedump", "commit": "97bc62c", "worktree": "/data2/FreeToken/wt/e1r003sd", "freetoken_file": "/data2/FreeToken/wt/e1r003sd/python/freetoken/__init__.py", "upstream_base": "d3512b4"},
  "serve": {"arms": {"R4096": {"serve_cmd": "R4096/SERVE_CMD.txt", "serve_args": "R4096/serve_args.txt", "env": {"FT_DEV_STATE_DUMP": "R4096/dump"}},
                     "R8192": {"serve_cmd": "R8192/SERVE_CMD.txt", "serve_args": "R8192/serve_args.txt", "env": {"FT_DEV_STATE_DUMP": "R8192/dump"}},
                     "RLM": {"serve_cmd": "RLM/SERVE_CMD.txt", "serve_args": "RLM/serve_args.txt", "env": {"FT_DEV_STATE_DUMP": "RLM/dump"}}}},
  "serve_args_diff": [],
  "design": {"trace": "E1-R003-v2/trace_rev.json（倒序）", "reference_existing": "E1-R003-stateeq/dump_B", "legal_reorders": ["4096→8192 子块", "分块→层优先"]},
  "projection": {"text": "无数值推算；R4096 与 E1-R003-stateeq/dump_B 应逐位一致（B 对 B2 先例）", "source": "论文 v3.2 §6.8"},
  "results": {"B_vs_R4096_bitwise_lengths": null, "R4096_vs_R8192_maxabs_by_len": {}, "R4096_vs_RLM_maxabs_by_len": {}, "restore_vs_recompute_maxabs_by_len_ref": "E1-R003-stateeq/state_eq.txt"},
  "first_shots": [],
  "sub_conclusions": [{"id": "SC1", "text": "跨日同配置整段重算仍逐位一致", "status": "pending", "evidence": ["eq_B_vs_R4096.txt"]},
                      {"id": "SC2", "text": "合法重排的逐长度最大绝对差（待阶段 2 换成逐层相对 L2）", "status": "pending", "evidence": ["eq_R4096_vs_R8192.txt"]}],
  "proposed_verdict": "pending_review", "verdict": "pending_review", "verdict_history": [], "retractions": [], "anomalies": [],
  "batch_logs": [{"path": "/data2/_shared/runs/ft_rounds/batchNN.log", "sha256": ""}],
  "manifest": "MANIFEST.sha256"
}
```

收尾：01 README §7。**注意**：阶段 2 要读本轮落盘，收尾后只读即可，不需要写。

## 阶段 2：逐层包络与第 3 层 logits 判定（依赖 D03）

D03 交付三样东西（名称以 D03 交付记录为准）：

1. `scripts/state_envelope.py`：对两个落盘目录按长度、按 GDN 层（36 层）、按张量（`conv_states`、`recurrent_states`、`slot:ple_conv`、`slot:ple_ngram_ctx`）计算相对 L2 `‖x−y‖/‖y‖`，输出 CSV；并对「被检曲线」和「参照包络（若干合法重排对的逐点最大值）」给出逐点比值。
2. 参照臂中间边界落盘（例如环境变量 `FT_DEV_STATE_DUMP_AT=<长度列表>`）：让 `slots=0` 的整段重算在 A 归档的边界长度（448、4544、8640、12672、14144、18240、21504；论文 §6.8 / RESULTS_E1 第三刀）落盘，用来比较「边界态本身」。
3. `scripts/logits_probe.py`（或服务端开关）：同一前缀 + 固定的后续 token 序列，分别经「bank 恢复」与「整段重算」（以及合法重排）得到逐位置 logits，输出 top-1 一致率、top-2 间隔、KL、首个不一致位置。

阶段 2 开工时由总负责人分配新轮次 ID（建议 `E1-R003-tolcal2`）并在本卡补「阶段 2 批次主体」。在此之前，阶段 2 的**判据框架**先定如下（数值阈值由 D03 交付后总负责人确认）：

| 层（论文 §3.5） | 检查 | 通过条件（框架） |
|---|---|---|
| 第 2 层 | 恢复对重算（`E1-R003-stateeq` A 对 B）的逐层相对 L2 曲线 vs 合法重排包络 | 所有（长度, 层, 张量）点的比值 ≤ 1；超出点数与最大比值如实报告 |
| 第 2 层（边界态） | A 的 archive(L) vs 参照臂同长度中间边界态 | 与合法重排同量级；若逐位相等，记「边界态等价」 |
| 第 3 层 | 固定后续 token：恢复 vs 重算的 logits 差，对照「合法重排 vs 重算」的 logits 差 | 恢复路径的 top-1 一致率、KL 不劣于合法重排参照 |

阶段 2 的结论只给建议；`#577 是否放行`属于**验收标准变更**（论文 §3.5 先例 E0-R007），由总负责人裁决。

## 停止条件

门失败；任何 `NOT-READY`/`SERVER_DIED`；`B_vs_R4096` 不逐位一致；`R4096` 或 `R8192` 无落盘；参数差异多出键；磁盘可用 < 20G。

## 上报

规则 §8。「关键读数」：B_vs_R4096 是否逐位；R4096_vs_R8192 可比长度数与 max|Δ| 区间；RLM 是否有落盘。「需要总负责人决定」：阶段 2 轮次 ID 与阈值确认。
