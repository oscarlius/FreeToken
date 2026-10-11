# T10 E1-R003-nondet：跨进程输出不确定性定位（200 token 口径）

> **2026-10-05 重新规划更新（优先于下文）**　详见 `../PLAN_20261005_重新规划.md`。

> 基线改为 **E2-base.1**，在 T20 之后执行，轮次 **E2-R044**；启动参数分两组，普通预填组不加 `--prefill-layer-major`，层优先组加上。按 `development/T10_RETEST_PROTOCOL_20261004.md` 分两组：普通预填、层优先预填，各 3 个进程 × 12 轮。
>
> - 报告冷对冷、热对热、冷对热的计数，与旧 33/36（普通预填，E2-base）比较。
> - 分叉点继续按 top-2 logit 差分类（同 R013 的口径）。
> - 不预先断言分歧会消失：确定性的路径差异（近乎平局处翻转）可能仍然存在。

>
> **本段取代下文中与之冲突的基点、优先级、估计、依赖与轮次号**（下文原表格保留作历史记录）。轮次号见 PLAN §5.3。

| 项 | 值 |
|---|---|
| 轮次 ID | `E1-R003-nondet`（结果文件 `results/T10-E1-R003-nondet_<YYYYMMDD>.md`） |
| 类型 | 定位，GPU |
| 优先级 | P1 |
| 依赖 | **阶段 1：无**（树 `exp/e1r003-pr577` @ c721c74，与 E1-R003-v5 的 B/B2 同树同配置）。**阶段 2：D03**（固定后续 token 的 logits 工具） |
| 预计耗时 | 阶段 1 约 60 分钟（3 个进程） |
| 论文依据 | v3.2 §6.8 输出层表与「v5 中 200 token 口径的自比不一致，可能出现在更晚的解码步……成因尚未定位」；§12 第 6 条；`REPLY_GPT6_V3_REVIEW` R6「不确定性来源在命中、恢复路径或缓存状态相关的执行顺序上，不能当噪声放过」 |

## 已知事实（不需重测）

| 比较 | 口径 | 不一致轮数 |
|---|---|---|
| B 对 B2（v5，整段重算，跨进程） | 正文前 32 token（回放上限 200） | 4/12（第 5、8、9、10 轮） |
| A 对 A2（v5，bank 恢复，跨进程） | 同上 | 3/12（第 5、8、10 轮） |
| B 对 B2（stateeq，带落盘钩子的树） | 输出前 32 token（上限 32） | 0/12 |
| E1-R001 冷 32K | 全文 | 跨进程逐位一致 |

## 要回答的问题

1. 同树同配置、整段重算、跨进程时，200 token 回放的输出在**第几个 token** 开始分叉？分叉是否总在同几轮？
2. 同一进程内，同一轮在「冷（倒序首趟）」与「热（升序重放）」两种缓存状态下输出是否相同？（区分「跨进程」与「缓存状态」）
3. （阶段 2）分叉位置上，两边的 logits 是否逐位相同；top-1 与 top-2 的差有多大（近平局放大，还是数值路径不同）？

## 阶段 1（现在可执行）

### 前置检查

```bash
SSH="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_exec.py"
$SSH 'git -C /data2/FreeToken/wt/e1r003 rev-parse --short=7 HEAD; ls /data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json /data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/tokenizer.json; ls -d /data2/_shared/runs/ft_rounds/E1-R003-nondet 2>/dev/null; ls -la /data2/_shared/gpu.lock 2>&1'
#   期望：c721c74；文件存在（tokenizer.json 不存在时改为记录 ls 结果并在步骤「定位」用 AutoTokenizer 目录加载）；无目录；锁文件不存在
```

### 批次脚本（01 README §4 模板）

**参数区**：

```bash
RID=E1-R003-nondet
CARD=T10
WT=/data2/FreeToken/wt/e1r003
EXP_COMMIT=c721c74
PORT=8095
WIN=49152
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"
```

**主体区**：

```bash
REV=/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json
TR=/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json
FLAGS="--enable-special-token-ckpt --max-prefill-length 4096 --mamba-host-slots 0"
export FT_REPLAY_MAX_TOKENS=200
proc() { local ARM=$1; local O=$D/$ARM
  ok || exit 7
  start $O "" $FLAGS
  [ $READY = 1 ] || { echo "$ARM NOT-READY"; stop; exit 6; }
  $PY $SCR/agent_trace.py replay --trace $REV --out $O/coldfirst.json --fresh-note "$RID-$ARM-cold" > $O/coldfirst.log 2>&1; echo "$ARM cold rc=$?"
  $PY $SCR/agent_trace.py replay --trace $TR  --out $O/warm.json      --fresh-note "$RID-$ARM-warm" > $O/warm.log 2>&1; echo "$ARM warm rc=$?"
  stop
}
proc B1; proc B2; proc B3
for p in "B1 B2" "B1 B3" "B2 B3"; do set -- $p
  $PY $SCR/agent_trace.py compare --a $D/$1/coldfirst.json --b $D/$2/coldfirst.json --trace $REV --tokens 200 --out $D/cmp_cold_$1_$2.json > $D/cmp_cold_$1_$2.log 2>&1; echo "cmp $1 $2 rc=$?"
done
for p in B1 B2 B3; do $PY $SCR/serve_args_diff.py $D/B1/serve.log $D/$p/serve.log > $D/args_diff_B1_$p.txt 2>&1; done; cat $D/args_diff_B1_B2.txt $D/args_diff_B1_B3.txt
```

> `agent_trace.py compare` 是失败关闭的判定器，`rc≠0` 表示有不一致，**这里是预期的，不是失败**；读数以输出文件为准。若 `--tokens` 参数不被接受（看 `cmp_*.log`），去掉它重跑这三条 compare（compare 不占 GPU，可在批次后手工执行）。

### 定位分叉点（批次结束后，只读，不占 GPU）

```bash
$SSH 'cd /data2/_shared/runs/ft_rounds/E1-R003-nondet && /data2/FreeToken/venv/bin/python - <<"EOF" | tee locate.txt
import json, itertools
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay", trust_remote_code=True)
def rounds(p):
    return {r["round"]: r for r in json.load(open(p))["rounds"]}
def full(r):
    return (r.get("text") or "")
runs = {a: {k: rounds(f"{a}/{k}.json") for k in ("coldfirst", "warm")} for a in ("B1", "B2", "B3")}
def first_div(x, y):
    n = min(len(x), len(y)); i = next((k for k in range(n) if x[k] != y[k]), n)
    return i, (i == n and len(x) == len(y))
print("== 跨进程（coldfirst）")
for a, b in itertools.combinations(runs, 2):
    for rd in sorted(runs[a]["coldfirst"]):
        x, y = full(runs[a]["coldfirst"][rd]), full(runs[b]["coldfirst"][rd])
        i, same = first_div(x, y)
        ti = len(tok(x[:i])["input_ids"]) if not same else -1
        print(f"{a}-{b} round={rd} same={same} first_char={i} first_token~{ti} len={len(x)}/{len(y)} prompt={runs[a]['coldfirst'][rd].get('prompt_tokens')} cached={runs[a]['coldfirst'][rd].get('cached_tokens')}/{runs[b]['coldfirst'][rd].get('cached_tokens')}")
print("== 同进程冷 vs 热")
for a in runs:
    for rd in sorted(runs[a]["coldfirst"]):
        if rd not in runs[a]["warm"]:
            continue
        x, y = full(runs[a]["coldfirst"][rd]), full(runs[a]["warm"][rd])
        i, same = first_div(x, y)
        print(f"{a} round={rd} cold_vs_warm same={same} first_char={i} cached={runs[a]['coldfirst'][rd].get('cached_tokens')}/{runs[a]['warm'][rd].get('cached_tokens')}")
EOF'
```

- 若报 `KeyError: 'text'` 或 `'round'`：执行 `$SSH 'head -c 2000 /data2/_shared/runs/ft_rounds/E1-R003-nondet/B1/coldfirst.json'`，把实际键名记入结果文件，**停**并上报（不要自行改脚本键名以外的逻辑）。
- 「text」字段含思考段与正文段的拼接方式以 `agent_trace.py` 为准；结果文件注明本卡比较的是 `text` 全文。

### 阶段 1 判据

| 观察 | 记为 |
|---|---|
| 三进程两两全部 `same=True` | 「本次未复现跨进程不一致」——与 v5 的 4/12 矛盾，上报（可能与时段、负载有关） |
| 分叉轮次集中在固定几轮，且 `first_token` 落在 33–200 之间 | 「分叉发生在较晚的解码步」（支持论文 §6.8 的推测） |
| 同进程冷 vs 热出现 `same=False` | 「缓存状态影响输出」：记下轮次与 `cached` 差 |
| 分叉轮的 `cached` 在进程间不同 | 「命中量不同导致」：这不是纯跨进程不确定性，上报 |

`proposed_verdict = measured`。

### `round.json` 骨架要点

同 T03 结构；`title`「跨进程输出不确定性定位（200 token）」；`parent` `E1-R003-v5`；`results` 含每对进程的不一致轮次列表、每轮 `first_token`、冷热同进程比较结果。

## 阶段 2（依赖 D03）

对阶段 1 每个分叉点（轮次 r、分叉 token 位置 k）：用 D03 的 logits 工具，在两个新进程中分别以「第 r 轮提示 + 两边共同的前 k−1 个输出 token」为输入，取最后位置 logits，比较：逐位是否相同、top-1/top-2 差、两边 argmax。命令以 D03 交付记录为准；轮次 ID 由总负责人分配（建议 `E1-R003-nondet2`）。

判据框架：

| 结果 | 记为 |
|---|---|
| 两进程 logits 逐位相同 | 预填路径确定；分叉来自解码路径（如解码 GEMV、缓存命中与否走不同计算顺序） |
| logits 不同但 top-2 差 < 1e-2（相对 logit 量级） | 近平局放大 |
| logits 不同且 top-2 差大 | 数值路径不确定，上报为高优先级缺陷 |

## 停止条件

门失败；`NOT-READY`；replay `rc` 非 0；`serve_args_diff` 出现 `pid` 以外的键。

## 上报

规则 §8。「需要总负责人决定」：阶段 2 轮次 ID；是否据阶段 1 改写论文 §6.8 / §12 第 6 条。
