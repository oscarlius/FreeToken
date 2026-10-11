# T09 E1-R002b：hybrid 诊断（变体 A / B / C）

> **2026-10-05 重新规划更新（优先于下文）**　详见 `../PLAN_20261005_重新规划.md`。

> 基线改为卡D08 候选（基于 E2-base.1），不再用 40fd5d4。轮次 ID 改为 **E2-R048**（取代未启动的 E2-R010）。
>
> - 四个变体（V0、A、B、C）保持不变，**另加变体 S**：卡D08 移植 Strata 线程池后的版本，用变体 A 的亲和设置。
> - 记录卡D08 的每层服务时间分解，以及两路端到端（卡D06 客户端）。
> - 判据：S 对 V0 的每层额外开销、同时运行时的完成率、两路端到端速度。论文中两路每路 30 tok/s 推算所需的 CPU 有效带宽（17.7–34.1 GB/s）**只作参照，不作门**。

>
> **本段取代下文中与之冲突的基点、优先级、估计、依赖与轮次号**（下文原表格保留作历史记录）。轮次号见 PLAN §5.3。

| 项 | 值 |
|---|---|
| 轮次 ID | `E1-R002b`（结果文件 `results/T09-E1-R002b_<YYYYMMDD>.md`） |
| 类型 | 受控诊断支线（不进入核心验收），GPU |
| 优先级 | P2 |
| 依赖 | 端到端解码：无（树 40fd5d4）。**若 D08 已完成，`WT`/`EXP_COMMIT` 改用 D08 交付记录中的树（D08 必须基于 40fd5d4），主体会自动打开 `FT_DEV_HYB_TRACE`**。**每层服务时间分解（CPU 计算 / 交接 / 屏障）与「CPU 与 PCIe 同跑时两路各自完成率」：依赖 D08**；两路端到端：依赖 D06。未交付的部分跳过并记 `pending` |
| 预计耗时 | 约 50 分钟（4 个进程） |
| 父轮 | E1-R002（树 40fd5d4，worktree `/data2/FreeToken/wt/e1r000b`） |
| 论文依据 | v3.2 §9.1「复测 E1-R002b 的设计」与「判定」；§4.4 (3) 说明第 2 条；附录 D hybrid 行；`RESULTS_E1` E1-R002 修订 1（分块大小未对齐） |

## 背景（执行者只需知道这些）

- E1-R002：hybrid 解码 4.84 / 4.86 / 4.86 / 4.75 tok/s，offload 36.61 / 38.15，下降 87%（§9.1）。
- 机理是**假设**：自旋屏障 + 执行器线程绑在 0..22 号核，而 0、2 号核被常驻 ollama `llama-server` 占用（约 119–123% CPU）。
- 已核实（规划阶段只读读码，e1r003 树，与 40fd5d4 同源）：执行器线程绑核**不是写死的**——`moe/cpu_executor.py:119-141` 在进程当前亲和集合（`sched_getaffinity`）内为每个物理核取一个逻辑 CPU，自动模式下把最后一个核留给协调线程；所以用 `taskset` 限制进程亲和就能改变绑核范围。日志行 `CPU MoE executor ready: threads=N (pinned to cores …)` 给出实际绑核。
- 已核实拓扑：超线程兄弟 `0↔24`、`2↔26`；node0 = 偶数号、node1 = 奇数号 CPU。只排除 0、2 而不排除 24、26 时，执行器仍可能选中 24、26，与 ollama 共用物理核。

## 变体

| 臂 | 启动前缀（LAUNCH） | 目的 |
|---|---|---|
| V0 | `numactl --cpunodebind=0,1 --interleave=all` | 复现 E1-R002（但显式 `--max-prefill-length 4096`，修正 E1-R002 的分块不对齐） |
| A | `numactl --interleave=all taskset -c 1,3-23,25,27-47` | 避开 0、2 号物理核（含兄弟 24、26） |
| B | `numactl --interleave=all taskset -c 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47` | 只用 node1 的核 |
| C | `numactl --membind=1 taskset -c 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47` | B + 内存全部绑 node1（专家池与 PLE 约 111 GiB，§9.1 前提） |

所有臂：`--moe-strategy hybrid --max-prefill-length 4096`，不开层优先（与 E1-R002 同），`FT_DEV_D0=1`（与 E1-R002 同，便于比较失误率）。

## 前置检查

```bash
SSH="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_exec.py"
$SSH 'git -C /data2/FreeToken/wt/e1r000b rev-parse --short=7 HEAD; cat /sys/devices/system/cpu/cpu0/topology/thread_siblings_list /sys/devices/system/cpu/cpu2/topology/thread_siblings_list; ps -eo pid,psr,pcpu,comm | grep llama-server | head -3; grep -E "MemFree|FilePages" /sys/devices/system/node/node1/meminfo; ls -d /data2/_shared/runs/ft_rounds/E1-R002b 2>/dev/null; ls -la /data2/_shared/gpu.lock 2>&1'
```

期望：`40fd5d4`；兄弟列表 `0,24` 与 `2,26`（不同 → 停，上报，本卡的 CPU 列表要改）；记录 llama-server 的 CPU 占用；无目录；锁文件不存在。

**变体 C 的前提**：`node1 MemFree + FilePages ≥ 120,586,240 kB`（115 GiB）。不满足 → C 臂跳过，记 `skipped_insufficient_node1_memory` 并上报；其余臂照跑。

## 批次脚本（01 README §4 模板）

参数区（`LAUNCH` 在主体里按臂切换，参数区填 V0 的值）：

```bash
RID=E1-R002b
CARD=T09
WT=/data2/FreeToken/wt/e1r000b
EXP_COMMIT=40fd5d4
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
```

主体区：

```bash
FLAGS="--moe-strategy hybrid --max-prefill-length 4096 --enable-special-token-ckpt"
NODE1="1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47"
HYB_ENV="FT_DEV_D0=1"
[ -f $WT/python/freetoken/moe/cpu_executor.py ] && grep -q "FT_DEV_HYB_TRACE" $WT/python/freetoken/moe/cpu_executor.py && HYB_ENV="$HYB_ENV FT_DEV_HYB_TRACE=1"
arm() { local ARM=$1; LAUNCH="$2"; local O=$D/$ARM
  ok || exit 7
  start $O "$HYB_ENV FT_DEV_D0_PATH=$O/d0" $FLAGS
  [ $READY = 1 ] || { echo "$ARM NOT-READY"; stop; return 0; }
  sed "s/\x1b\[[0-9;]*m//g" $O/serve.log | grep -oE "CPU MoE executor ready: threads=[0-9]+ \(pinned to cores [0-9.,]+\)" | tee $O/executor_pin.txt
  $PY $SCR/cold_eq.py "$RID-first-$ARM" $O/first_shot.json 2000 64 2> $O/first_shot.err; echo "$ARM first rc=$?"
  for c in s3A s3B; do $PY $SCR/cold_eq.py $c $O/dec32k_$c.json 32052 128 2> $O/dec32k_$c.err; echo "$ARM $c rc=$?"; done
  $PY $SCR/cold_eq.py "$RID-short-$ARM" $O/short.json 2000 512 2> $O/short.err; echo "$ARM short rc=$?"
  if [ -f $SCR/multisession_probe.py ]; then $PY $SCR/multisession_probe.py two-decode --ctx 16000 --max-tokens 256 --same-prompt 0 --reps 1 --out $O/two_decode.json > $O/two_decode.log 2>&1; echo "$ARM two-decode rc=$?"; fi
  stop
}
arm V0 "numactl --cpunodebind=0,1 --interleave=all"
arm A  "numactl --interleave=all taskset -c 1,3-23,25,27-47"
arm B  "numactl --interleave=all taskset -c $NODE1"
M=$(awk '/MemFree|FilePages/ {s+=$4} END {print s}' /sys/devices/system/node/node1/meminfo)
if [ "$M" -ge 120586240 ]; then arm C "numactl --membind=1 taskset -c $NODE1"; else echo "C SKIPPED node1_kB=$M"; fi
for a in A B C; do [ -f $D/$a/serve.log ] && { $PY $SCR/serve_args_diff.py $D/V0/serve.log $D/$a/serve.log > $D/args_diff_V0_$a.txt 2>&1; cat $D/args_diff_V0_$a.txt; }; done
```

> 本卡对单臂 `NOT-READY` 的处理与模板默认不同：**记录后继续下一臂**（`return 0`），因为变体 C 有内存不足导致起不来的已知风险；但 V0 起不来 → 结果全部作废，上报。

## 读数提取

| 指标 | 来源 |
|---|---|
| 实际绑核 | `<臂>/executor_pin.txt` |
| 32K 解码 tok/s（2 个样本） | `<臂>/dec32k_s3A.json`、`dec32k_s3B.json` 的 `record` |
| 短上下文解码 tok/s | `<臂>/short.json` |
| 失误率、每层每步 CPU 专家数 | `<臂>/d0_decode.json`（`miss_rate`、`cpu_per_layer` 等，E1-R002 同口径：失误 30.47%、CPU 2.429） |
| 服务时间分解 | D08 交付记录给出的命令（未交付 → `pending`） |
| 参数差异 | `args_diff_V0_*.txt`：只允许 `pid` |

## 判据（诊断，只给事实判断）

`proposed_verdict = measured`。子结论（状态 `pending`）：

| 子结论 | 写法 |
|---|---|
| SC1 复现 | V0 32K 解码是否仍约 4.8 tok/s（与 E1-R002 差 ≤ 20% → 「复现」） |
| SC2 绑核 | A 相对 V0 的 32K 解码倍数；若 A ≥ 3×V0 → 「抢占核是主因之一」；若 A 在 V0 ±20% 内 → 「避开 0、2 号物理核无效」 |
| SC3 NUMA | B、C 相对 A 的倍数（C 跳过则写 pending） |
| SC4 是否够用 | 任一变体 32K 解码是否 ≥ offload 父轮 36.61 tok/s（只陈述，不建议采用；论文 §9.1：hybrid 没有质量维度的实测，重提前须补质量门） |

论文 §9.1 的「判定」要求三样东西（同跑完成率、服务时间分解、两路端到端），本卡在 D08、D06 未交付时只能给端到端单路数；结果文件必须写明哪几样缺失。

## 停止条件

门失败；V0 `NOT-READY`；`args_diff` 出现 `pid` 以外的键；任一臂 `SERVER_DIED` 伴随 OOM（`dmesg` 不可读，只看 `serve.log` 末 20 行是否含 `out of memory`/`Killed`）。

## `round.json` 骨架要点

同 T03 结构；`title`「hybrid 诊断：绑核与 NUMA 变体」；`parent` `E1-R002`；`serve.arms.<臂>.serve_cmd` 显示各自 LAUNCH；`results` 含 `decode32k_tps`、`short_tps`、`miss_rate`、`cpu_per_layer`、`executor_pin`；`proposed_verdict` `measured`。

## 上报

规则 §8。「需要总负责人决定」：是否立项修执行器（D08 后续；附录 D 估计修复 5–10 人日）。
