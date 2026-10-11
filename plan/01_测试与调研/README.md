# 01 测试与调研：执行手册

> **版本声明（2026-10-03 用户决定）**：后续测试与开发统一在**第 2 代基线 `E2-base`** 上进行。E2-base = `40fd5d4` + #578 + #577 + 状态落盘钩子 + D01 + D02，新增功能默认关闭或保持现状；构建见 `02_开发任务/D00`，立项测量见 `01_测试与调研/T00`。
> - E2-base 过门之前，只有不依赖它的卡可以开工：T01、T02、T12–T15（不占 GPU），以及只读复核。
> - 各卡中写的第 1 代树（40fd5d4 / 80943fd / c721c74 / 97bc62c）只用于复现第 1 代历史数据。新轮次一律以 E2-base 为父树，轮次 ID 用 `E2-R<序号>`，由总负责人分配。
> - 每个新轮次的 `round.json` 必须写 `base.code_version = "E2-base@<短提交号>"`。

> 执行者：低成本模型。**只测与调研，不改代码。** 规则全文见 `../00_规则_测试存储与数据版本.md`，本手册只给可照抄的操作。
> 远端：`172.16.108.9`。所有远端命令都经本地 `ssh_exec.py` 执行；上传用 `ssh_upload.py`。

---

## 1. 开工前必读（每次）

1. 读本卡全文，确认「依赖」一节的开发卡状态为「完成」（看 `../README.md` 的当前状态表）。依赖未完成 → 不执行，结果文件写「阻塞」。
2. 读 `../00_规则_测试存储与数据版本.md` 第 6 节（执行纪律）。
3. 工作时间（08:00–17:30）不做任何下载；需要下载的卡会单独写限速命令。

## 2. 本地命令写法

在 Git Bash 里：

```bash
SSH="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_exec.py"
UP="python D:/00.开发/2026/03-模型实验/freetoken/_shared/ssh_upload.py"
$SSH 'ls /data2/_shared/runs/ft_rounds/ | tail -5'
$UP <本地路径> <远端路径>
```

- 远端命令用单引号整体包住；命令内部需要单引号时，改为先上传脚本再执行，不要拼复杂转义。
- `ssh_exec.py` 的退出码就是远端命令的退出码；非 0 一律记录。

## 3. 卡片清单与状态

| 卡号 | 任务 ID | 内容 | GPU | 依赖（02 卡） | 优先级 |
|---|---|---|---|---|---|
| T00 | E2-R000 | **第 2 代基线立项测量**：S1-lite + 64K + 开关四格复测（之后第 2 代所有轮次的父轮） | 是 | D00（+ T16 gate-D00） | P0（E2-base 过门后第一个跑） |
| T01 | FTD-20261003-1 | 服务器侧数据发布落地 | 否 | 无 | P0 |
| T02 | S-001 | 地板归因补核（recomputed=1 的每遍 H2D）+ T1 第 5 轮 3.50 s 残差 | 否 | 无 | P0 |
| T03 | E1-R008（在 E2-base 上执行时由总负责人改发 E2 轮次号） | 只关切段、保留快照的冷热四格；父轮改为 T00 | 是 | D00、D01（+ T16） | P0（依赖就绪后第一个跑） |
| T04 | E1-R003-tolcal | 状态层容差独立标定（合法重排包络） | 是 | 阶段 1 无；阶段 2 依赖 D03 | P0 |
| T05 | E1-R005 | 两路不同内容多会话基线（H1、停顿、时间线） | 是 | D06、D02 | P1 |
| T06 | E1-R007 | 路由轨迹与真实后缀分布 | 是 | D07 | P1 |
| T07 | E1-R009 | 同树 D0 开关对照 + 冷预填留出点 8K/16K/48K | 是 | 无 | P1 |
| T08 | E1-R010 | 生产口径 S1 重测（taskset 1,3-47，不开 D0） | 是 | 两路并发子项依赖 D06 | P2 |
| T09 | E1-R002b | hybrid 诊断（变体 A/B/C） | 是 | 端到端无；服务时间分解依赖 D08 | P2 |
| T10 | E1-R003-nondet | 跨进程输出不确定性定位（200 token 口径） | 是 | 阶段 1 无；阶段 2 依赖 D03 | P1 |
| T11 | S-006 / E1-R003-uid8 | uid=8 缺 donate 记录归类（阶段 1 只读）与复现（阶段 2） | 阶段 1 否，阶段 2 是 | 无 | P1 |
| T12 | S-002 | G0：TP2/TP4 每卡显存账（分析型） | 否 | 无 | P2 |
| T13 | S-003 | 上游 #577/#578/#505 状态跟踪（周期性） | 否 | 无 | P2 |
| T14 | S-004 | Layered Prefill / SLOWeave 与 D6 差异核对 | 否 | 无 | P3 |
| T15 | S-005 | 4090 多卡 P2P / NCCL 经主存中转公开资料 | 否 | 无 | P3 |
| T16 | `<父轮>-gate-<卡号>` | 开发卡交付验收：默认路径逐位门（通用） | 是 | 被验收的 02 卡已交付 | 随被验收卡 |

GPU 卡一律串行（单写者）。同一时刻只能有一张 GPU 卡在跑。

---


### 2026-10-05 新增与改动（详见 `../PLAN_20261005_重新规划.md` §5；GPU 队列以该文为准）

| 卡号 | 内容 | GPU | 依赖 | 优先级 |
|---|---|---|---|---|
| T17（判据修订） | 命中续算等价门：状态交接逐位 + 同结构冷参照 + 合法重排包络 | 是 | 卡D14 的 `FT_DEV_PREFILL_SCHEDULE`、卡D16 | P0 |
| **T20（新）** | E2-base.1 立项测量（含卡D16 套件、规范判卷器 60 题） | 是 | 卡D17、T16 | P0 |
| T10 / T05 / T06 / T03b | 改在 E2-base.1 上执行（E2-R044 / R045 / R046 / R047） | 是 | T20；T05 另需卡D06 G3/G4（E2-R042），T06 另需卡D07 G3/G4（E2-R043） | P1 |
| T09（改） | hybrid 诊断与修复验证，加变体 S（Strata 线程池移植后） | 是 | 卡D08 | P1 |
| **T21（新）** | 自适应专家缓存验证（留出负载） | 是 | 卡D15、T06 | P1 |
| **T19（新）** | Strata 本机基线（同模型 GGUF，空档执行） | 是 | GPU 空档 | P2 |

## 4. 批次脚本模板（GPU 卡共用，逐字复制）

生成方法：

1. 把下面整段复制到 `plan/01_测试与调研/batches/batchNN_<轮次ID>.sh`（`NN` 按规则 §1.3 取号）。
2. **只改**「参数区」与「主体区」，内容逐字取自卡片。固定区一个字符都不改。
3. 文件必须是 LF 换行。上传后在远端检查：`$SSH 'grep -c $'"'"'\r'"'"' /data2/FreeToken/runs/plan_batches/batchNN_<轮次ID>.sh'` 应输出 `0`；不为 0 时执行 `$SSH "sed -i 's/\r$//' /data2/FreeToken/runs/plan_batches/batchNN_<轮次ID>.sh"`。
4. 先做语法检查：`$SSH 'bash -n /data2/FreeToken/runs/plan_batches/batchNN_<轮次ID>.sh && echo SYNTAX-OK'`。

```bash
#!/bin/bash
# batchNN_<轮次ID>.sh —— 由 plan/01_测试与调研/README.md §4 模板生成
set -u
# ================= 参数区（按卡片填写）=================
RID=__轮次ID__                 # 例 E1-R008
CARD=__卡号__                  # 例 T03
WT=/data2/FreeToken/wt/__worktree__
EXP_COMMIT=__7位commit__
PORT=8095
WIN=49152                      # 窗口：--kv-reserve-tokens 与 --max-seq-len-override
LAUNCH="numactl --cpunodebind=0,1 --interleave=all"   # 卡片可改为 taskset 版本
# ================= 固定区（不得修改）=================
URL=http://127.0.0.1:$PORT/v1/chat/completions
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64:${LD_LIBRARY_PATH:-}
export VIRTUAL_ENV=/data2/FreeToken/venv PYTHONUNBUFFERED=1
PY=/data2/FreeToken/venv/bin/python
SCR=/data2/FreeToken/scripts
D=/data2/_shared/runs/ft_rounds/$RID
LOCK=/data2/_shared/gpu.lock
SELF=$(basename "$0")
[ -e "$D" ] && { echo "GATE-FAIL-RID-EXISTS $D"; exit 9; }
mkdir -p "$D" && cp "$0" "$D/batch.sh"
export PYTHONPATH=$WT/python
EXP=$WT/python/freetoken/__init__.py
MODEL=/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay
BASE="--model-path $MODEL --served-model-name Qwen3.8-Flash-Next-NVFP4 --host 0.0.0.0 --port $PORT --memory-ratio 0.88 --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned --moe-strategy offload --quant-backend moe.nvfp4=triton --max-running-requests 2 --cuda-graph-max-bs 2 --kv-reserve-tokens $WIN --max-seq-len-override $WIN --enable-cache-report --tool-call-parser qwen3_coder --reasoning-parser qwen3"
SPID=""
lock_take() { if [ -e $LOCK ] && ! grep -q "\"owner\":\"$RID\"" $LOCK; then echo "GATE-FAIL-LOCK $(cat $LOCK)"; return 1; fi
  echo "{\"owner\":\"$RID\",\"card\":\"$CARD\",\"since\":\"$(date '+%F %T')\",\"pid\":$$}" > $LOCK; }
lock_release() { grep -q "\"owner\":\"$RID\"" $LOCK 2>/dev/null && rm -f $LOCK; }
cleanup() { [ -n "$SPID" ] && kill -- -$SPID 2>/dev/null; lock_release; }
trap cleanup EXIT
ok() {
  local R=$($PY -c "import freetoken;print(freetoken.__file__)" 2>/dev/null)
  local C=$(git -C $WT rev-parse --short=7 HEAD 2>/dev/null)
  local DIRTY=$(git -C $WT status --porcelain --untracked-files=no 2>/dev/null | wc -l)
  local B=$(ps -eo args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace\.py (replay|generate)|ft_probe|probe_ft_cold32k|cold_eq\.py|batch[0-9]+_/ && !/awk/' | wc -l)
  local L=$(ss -ltn | grep -c ":$PORT ")
  local G=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  local K=0; $PY -c "import freetoken.kernel._pinned_tensor, freetoken.kernel._cpu_moe" 2>/dev/null || K=1
  echo "GATE import=$R expect=$EXP commit=$C expect_commit=$EXP_COMMIT dirty=$DIRTY busy=$B listener=$L gpu_mib=$G kernels_missing=$K"
  [ "$R" = "$EXP" ] || { echo GATE-FAIL-IMPORT; return 1; }
  [ "$C" = "$EXP_COMMIT" ] || { echo GATE-FAIL-COMMIT; return 1; }
  [ "$DIRTY" = 0 ] || { echo GATE-FAIL-DIRTY-TREE; return 1; }
  [ "$K" = 0 ] || { echo GATE-FAIL-KERNELS; return 1; }
  [ "$L" = 0 ] || { echo GATE-FAIL-LISTENER; return 1; }
  [ "$G" -lt 1000 ] || { echo GATE-FAIL-VRAM; return 1; }
  [ "$B" = 0 ] || { echo GATE-FAIL-SINGLE-WRITER; ps -eo pid,args | awk -v self="$SELF" 'index($0,self)==0 && /ft serve|agent_trace|ft_probe|probe_ft|cold_eq|batch[0-9]+_/ && !/awk/'; return 1; }
  lock_take || return 1
}
snap() { { date '+%F %T %Z'; echo "RID=$RID CARD=$CARD WT=$WT"; git -C $WT log -1 --format='%H %s';
  $PY -c "import freetoken,torch;print(freetoken.__file__, torch.__version__, torch.version.cuda)";
  nvidia-smi --query-gpu=name,driver_version,memory.used,clocks.sm,temperature.gpu --format=csv;
  numactl -H | grep -E 'size|free'; uptime; ps -eo pid,psr,pcpu,args --sort=-pcpu | head -8 | cut -c1-160; } > "$1/ENV.txt" 2>&1; }
# 用法：start <臂目录> "<额外环境变量，空格分隔，可为空>" <额外 ft serve 参数...>
start() { local OUT=$1 AENV=$2; shift 2; mkdir -p $OUT; snap $OUT; local T0=$(date +%s)
  echo "env $AENV $LAUNCH ft serve $BASE $*" > $OUT/SERVE_CMD.txt
  env $AENV setsid $LAUNCH ft serve $BASE "$@" > $OUT/serve.log 2>&1 &
  SPID=$!; READY=0; echo "SPID=$SPID"
  for i in $(seq 1 40); do sleep 15
    if kill -0 $SPID 2>/dev/null; then
      if curl -s -m 25 $URL -H 'Content-Type: application/json' -d '{"model":"Qwen3.8-Flash-Next-NVFP4","messages":[{"role":"user","content":"say ok"}],"max_tokens":2,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' | grep -q '"content"'; then READY=1; echo "READY $(( $(date +%s)-T0 ))s"; break; fi
    else echo SERVER_DIED; tail -20 $OUT/serve.log; break; fi
  done
  grep -m1 -A1 'Parsed arguments' $OUT/serve.log > $OUT/serve_args.txt
  echo "taskset: $(taskset -cp $SPID 2>/dev/null)"; }
stop() { kill -- -$SPID 2>/dev/null || kill $SPID 2>/dev/null; sleep 25; kill -9 -- -$SPID 2>/dev/null; sleep 10; SPID=""
  local G=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1); echo "gpu-after=${G}MiB"
  [ "$G" -lt 1000 ] || { echo "GATE-FAIL-VRAM-NOT-RELEASED"; exit 8; }
  lock_release; }
# ================= 主体区（逐字取自卡片）=================
echo "### $RID $CARD start $(date '+%F %T')"
# <卡片主体>
echo "### $RID $CARD done $(date '+%F %T')"
```

退出码约定：`9` 轮次目录已存在；`8` 停服后显存未释放；`7` 门失败；`6` 服务未就绪；`5` 工件缺失。**任何非 0 退出 → 不重跑，按 §6 上报。**

## 5. 运行与监视

```bash
# 1) 建远端批次目录（只需一次）
$SSH 'mkdir -p /data2/FreeToken/runs/plan_batches'
# 2) 上传、检查换行与语法（见 §4）
$UP plan/01_测试与调研/batches/batchNN_<轮次ID>.sh /data2/FreeToken/runs/plan_batches/batchNN_<轮次ID>.sh
# 3) 后台启动，日志到 ft_rounds 根目录
$SSH 'cd /data2/FreeToken/runs/plan_batches && nohup bash batchNN_<轮次ID>.sh > /data2/_shared/runs/ft_rounds/batchNN.log 2>&1 < /dev/null & echo started'
# 4) 监视（每 3–5 分钟一次，只读）
$SSH 'tail -15 /data2/_shared/runs/ft_rounds/batchNN.log'
```

- 看到 `GATE-FAIL-*`、`SERVER_DIED`、`NOT-READY`、`rc=` 非 0 → 立即按 §6 处理。
- 批次正常结束的标志：最后一行 `### <轮次ID> <卡号> done …`，且 `$SSH 'ls /data2/_shared/gpu.lock'` 报「No such file」（锁已删除）。

## 6. 异常处理（唯一允许的动作）

1. 不重跑、不改参数。
2. 若服务仍在：从批次日志取本批次最后一个 `SPID=<数字>`（`$SSH 'grep -o "SPID=[0-9]*" /data2/_shared/runs/ft_rounds/batchNN.log | tail -1'`），确认该进程仍是 `ft serve`（`$SSH 'ps -o pid,lstart,args -p <SPID>'`），然后按进程组停止：`$SSH 'kill -- -<SPID>; sleep 30; kill -9 -- -<SPID> 2>/dev/null; nvidia-smi --query-gpu=memory.used --format=csv'`。**不得用 `pkill -f "ft serve"`**（会杀掉执行它的远端 shell，也会误杀不是本卡起的服务）；不是本卡起的进程**不得杀**。
3. 若 `gpu.lock` 仍属本轮（`owner` 为本轮次 ID）：`$SSH 'rm -f /data2/_shared/gpu.lock'`。属于别人：不动。
4. 写结果文件「异常」节：现象、批次日志末 20 行、已产生的工件路径。
5. 上报（规则 §8 格式），状态写「异常停止」。轮次目录**不删除**；它保持未关闭状态，由总负责人决定作废或续用。

## 7. 收尾（每张 GPU 卡与需要落盘的分析卡）

1. 按卡片「读数提取」一节的命令取数，填结果文件。
2. 按卡片给出的 `round.json` 骨架（schema `ft_round/v2`，规则 §3.1）写第一版：在本地写好 → 上传到 `<轮次目录>/round.json`。
   - 先校验 JSON 合法：`$SSH '/data2/FreeToken/venv/bin/python -m json.tool /data2/_shared/runs/ft_rounds/<轮次ID>/round.json > /dev/null && echo JSON-OK'`。
3. 用D04收尾工具首次关闭（重复关闭会拒绝），由工具生成 `round_history/round.v001.json`、`MANIFEST.sha256` 并将整个目录恢复只读；不得手工替代历史链或修改已关闭工件：

   ```bash
   $SSH 'FT_ROUND_PYTHON=/data2/FreeToken/venv/bin/python bash /data2/FreeToken/scripts/round_close.sh <轮次ID>'
   $SSH '/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py /data2/_shared/runs/ft_rounds/<轮次ID> check'
   ```

4. 将工具打印的manifest自身SHA写进结果文件，并核对：`$SSH 'sha256sum /data2/_shared/runs/ft_rounds/<轮次ID>/MANIFEST.sha256'`。登记实际工具MD5（T10/E2-R006已首次使用并验证）：

   ```bash
   $SSH 'md5sum /data2/FreeToken/scripts/round_json_append.py /data2/FreeToken/scripts/round_close.py /data2/FreeToken/scripts/round_close.sh'
   ```
5. 改 `../README.md` 当前状态表中本卡的状态与结果链接。
6. 上报。

关闭后的裁决由总负责人按规则追加，01执行者不自行裁决；旧工件及manifest保持不变，直接改写 `round.json` 的 `rev_*.py` 停用。追加器的命令如下，角色、理由和证据均填写实际值：

```bash
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py <轮次目录> verdict --new <判定> --reason <理由> --evidence <工件路径> --by <角色>
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py <轮次目录> retract --target <SC编号> --reason <理由> --evidence <工件路径> --by <角色>
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py <轮次目录> add --json <新增键或列表尾部的补丁.json>
/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/round_json_append.py <轮次目录> check
```

## 8. 常用读数命令（只读）

```bash
# 预填段（执行事件）：每行一段；看 #new-token 与 #cached-token
$SSH 'grep -n "Prefill batch" <臂目录>/serve.log'
# A/B 参数差异（对照出数前必须跑）
$SSH '/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/serve_args_diff.py <臂A>/serve.log <臂B>/serve.log'
# 状态层比对
$SSH '/data2/FreeToken/venv/bin/python /data2/FreeToken/scripts/state_eq.py <参照dump目录> <被检dump目录> --tol 0.0'
# 专家槽数（--moe-cache-auto 解析结果；49,152 窗口为 3149，73,728 窗口为 2924）
$SSH 'sed "s/\x1b\[[0-9;]*m//g" <臂目录>/serve.log | grep -oE "moe-cache-auto resolved moe_cache_size=[0-9]+ num_pages=[0-9]+"'
# hybrid 执行器实际绑核
$SSH 'sed "s/\x1b\[[0-9;]*m//g" <臂目录>/serve.log | grep -oE "CPU MoE executor ready: threads=[0-9]+ \(pinned to cores [0-9.,]+\)"'
# D0 预填记录条数与每条 H2D
$SSH '/data2/FreeToken/venv/bin/python -c "import json,sys;[print(i,round(json.loads(l)[\"h2d_gib\"],3),round(json.loads(l)[\"wall_s\"],3)) for i,l in enumerate(open(sys.argv[1]))]" <d0_prefill.jsonl>'
```

D0 预填记录（`d0_prefill.jsonl`）现有字段：`chunk, wall_s, h2d_bytes, d2d_bytes, h2d_gib, d2d_gib, layers[{layer, copy_ms, compute_ms, d2d_ms}]`；**没有**请求编号、切段原因、token 数（这些由开发卡 D02 补）。`serve.log` 的 `Prefill batch` 行也没有请求编号。已核实的已知现象：未修复 D0 的树上（含 D01 的 `exp/e1r008-anchorcut`），每个进程 D0 记录数 = `Prefill batch` 行数 − 1（最后一段未落盘），此时按顺序对齐前 n−1 条；D01/D02 交付后优先用 `D0 seg:` 行或 `reqs[].rid` 对齐。除「少 1」外的任何条数差异 → 不得对齐，停并上报。
