# D03 状态层工具：参照臂中间边界落盘 + 逐层包络 + 固定后续 token 的 logits 比对（第 3 层门）

> **10-06 21:05 改写（总负责人；取代下文所有更新块与正文中冲突的内容）**
>
> - **状态**：三样工具（中间边界落盘、逐层包络、logits 比对）已交付，默认门 E2-R002-gate-D03、E2-R018-gate-D03 kept，并已用于 T10 与 T17 诊断。本卡视为完成。
> - **剩余一项（按需）**：T04 改为只读分析 S-007 后，若 `state_envelope.py` 不能直接读取 T17 普通冷参照臂（E2-R036、E2-R038）的落盘格式，补一个只读读取器（CPU，约 0.5 人日），不改引擎、不需要 T16 门。由 T04 执行者在结果文件中上报后再启动。

> **2026-10-05 重新规划更新（优先于下文）**　卡D03 的基点改为 E2-base.1（原 97bc62c 作废），依赖卡D17，阶段 B / P2。**卡面正文尚未按 E2-base.1 改写，轮次号待总负责人分配；分配并更新本卡前不得执行。** 详见 `../PLAN_20261005_重新规划.md` §5。

| 项 | 值 |
|---|---|
| 优先级 | **P0**（#577 能否放行的唯一判定路径；也服务跨进程不确定性定位） |
| 估计 | 3–5 人日 |
| 基点 | `exp/e1r003-statedump` @ `97bc62c`（已含 `FT_DEV_STATE_DUMP` 落盘钩子） |
| 新分支 / worktree | `exp/e1r003-statetools` / `/data2/FreeToken/wt/e1r003st` |
| 依赖 | 无（T04 阶段 1 的合法重排落盘可并行采集） |
| 01 验证 | **T16**（`E1-R003-gate-D03`，父树 97bc62c；不设任何新环境变量时逐位一致）→ **T04 阶段 2**、**T10 阶段 2** |
| 论文依据 | v3.2 §3.5 四层准入（第 3 层「用相同的后续 token 序列，比较恢复路径与参考路径的 state 和 logits，定位首个差异层」）与「容差必须独立标定」；§6.8 判定与下一步；`RESULTS_E1` 第二、三刀的 `next_discriminator`（「参照臂同一边界补一个落盘点 + 一趟重算」） |

## 目标

交付三样工具，让 01 能机械地完成：(a) 合法重排包络 vs 恢复路径的逐层比较；(b) 边界态本身的比较；(c) 第 3 层：固定后续 token 的 logits 判定。

## 范围

### A. 参照臂中间边界落盘：`FT_DEV_STATE_DUMP_AT=<长度列表>`

在 `--mamba-host-slots 0` 的整段重算里，当某个 ×64 边界长度 L ∈ 列表落在本次前向的扩展区间内时，额外落盘 L 处的完整续算状态（`conv_states`、`recurrent_states`、`slot:ple_conv`、`slot:ple_ngram_ctx`，与现有钩子同格式），`kind="boundary"`。

- **优先方案**（不改变计算顺序）：在 GDN 分块扫描的边界选择处（上游 `attention/linear.py:116-128`：`c = (r.extend_len - 1) // CHUNK_SIZE`，每请求每次前向只取 1 个最深的 ×64 边界；`CHUNK_SIZE=64` 定义于 `kernel/fla/chunk.py:28`）**额外**取 L 处的边界态，而不是通过多切一段来制造边界（多切一段本身就是一次重排）。
- conv 窗口与 PLE 状态在 L 处的值，按现有落盘钩子取同口径（`kvcache/linear_state_pool.py:301` `dump_state`）。
- A 侧归档长度（448、4544、8640、12672、14144、18240、21504，均为 64 的倍数；RESULTS_E1 第三刀）必须能全部落盘。

### B. 逐层包络：`scripts/state_envelope.py`

```
state_envelope.py --ref <dir> --test <dir> [--legal <dirA>:<dirB> ...] --out <csv> [--kinds donate,boundary,archive]
```

- 对 `ref` 与 `test` 的共同长度、每个 GDN 层（36 层）、每个张量，计算相对 L2 `‖test−ref‖/‖ref‖` 与逐元素不等比例；
- `--legal` 给出若干「合法重排」目录对，逐点取最大值形成包络；输出 `ratio = 被检 / 包络`，汇总超出点数与最大比值；
- 失败关闭：长度集合、角色集合、形状不一致时报错（沿用 `state_eq.py` 的口径：按**角色名**匹配，不按文件名；bf16 全程 torch）。
- 论文 §6.8 的逐层表（12,416 / 14,080 / 21,568）必须能用本脚本在 `E1-R003-stateeq/dump_A`、`dump_B` 上复现到小数点后两位（作为工具正确性的回归测试）。

### C. 第 3 层：固定后续 token 的 logits 比对：`scripts/logits_probe.py` + 服务端 `FT_DEV_LOGITS_DUMP=<目录>`

- 输入：轨迹某轮的提示 P、固定后续 token 序列 X（token id 列表，两臂逐字节相同；用 `input_ids` 的 sha256 校验）。
- 服务端在 `FT_DEV_LOGITS_DUMP` 设置时，把该请求**预填末尾 K 个位置**（K = len(X)，上限 64）的 fp32 logits（或 top-64 + logsumexp，足够算 KL 与 top-k）与每个 GDN 层在 X 末尾的状态摘要（相对 L2 所需的张量或其 sha）落盘。
- 客户端分别对「恢复臂」（`slots=32`，P 的前缀命中 bank）、「重算臂」（`slots=0`）、「合法重排臂」（`slots=0` + `--max-prefill-length 8192`）发同一请求；输出：逐位置 top-1 一致率、top-1/top-2 间隔、KL(恢复‖重算)、KL(重排‖重算)、首个差异层（若层摘要不同）。
- 也支持 T10 阶段 2 的用法：输入 = 第 r 轮提示 + 两进程共同的前 k−1 个输出 token，比较最后位置 logits 是否逐位相同与 top-2 间隔。
- 发送 token id：优先用服务端已支持的 token id 输入方式（读码确认 `server/` 是否接受 `prompt` 为 id 列表）；不支持时，由服务端在 `FT_DEV_LOGITS_DUMP` 模式下接受一个开发用字段，**仅**在该环境变量设置时生效。

## 非目标

- 不改恢复路径的计算（不去「修」不逐位，那是验收标准问题，由总负责人裁决）。
- 不定义放行阈值（T04 阶段 2 给出框架，阈值由总负责人在看到包络后确认）。

## 代码挂点（路径相对 `python/freetoken/`；e1r003sd 行号为规划阶段只读核实）

| 位置 | 内容 |
|---|---|
| `kvcache/linear_state_pool.py:29` 开关、`:301` `dump_state`、`:357` 写 `index.jsonl`（字段：seq、kind、length、uid、note、dev_slots、host_slots、files、各张量 sha、slot_sha） | 新 kind `boundary`、`logits` 的落点 |
| `scheduler/cache.py:199-200`（archive 钩子）、`:481-483`（donate 钩子，只在预填段提交路径）；`scheduler.py:668-670`（resume 钩子） | 现有三个钩子 |
| 上游 `attention/linear.py:94-137`（关键 116-128） | 中间边界的取法 |
| 上游 `scheduler/cache.py:382-414` `_cache_req_hybrid` 中 ×64 边界冻结 | 参照 |
| `models/qwen4_exp/ple.py:378-404` `commit_ngram_context`、`:622` `_write_track_snapshot`、`:632` `_conv_state_slab` | PLE 状态在 L 处的取法 |
| `freetoken/scripts/state_eq.py`（本地与远端同名） | 匹配口径与失败关闭写法的参照 |

## 设计约束

- 不设 `FT_DEV_STATE_DUMP_AT` / `FT_DEV_LOGITS_DUMP` 时，与 97bc62c 逐位一致（T16）。设了以后，**被检请求的输出也必须与不设时逐位一致**（落盘只读不写）——开发自检用 `cold_eq.py` 验证一次。
- 守卫反例：不设环境变量时不得创建任何目录（参照 batch18 的守卫反例）。
- 落盘体积：每个 boundary 记录与现有 donate 同量级（batch18/19 三臂共 8.6 GB）；`logits` 只存末尾 K 个位置。

## 验收门

| 门 | 条件 | 谁验证 |
|---|---|---|
| G1 | 单元测试通过，失败数不多于基线 | 02 |
| G2 | T16 通过 | 01 |
| G3 工具正确性 | `state_envelope.py` 在 `E1-R003-stateeq` 现有落盘上复现论文 §6.8 逐层表（三行，conv/recurrent 首层与末 5 层区间，两位小数） | 02 自检，写交付记录 |
| G4 边界态 | 开发自检：`slots=0` 臂在 12,672 落出 `boundary` 记录；与 A 侧 `archive(12672)` 用 `state_envelope.py` 比较有输出（不要求相等） | 02 自检 |
| G5 logits 自洽 | 同一臂同一请求两次（两个独立进程）的 logits 逐位相同（`slots=0`；若不同，立即上报——这本身就是 T10 要找的不确定性） | 02 自检 |

## 需要的测试

- `tests/kvcache/test_state_dump_at.py`：给定长度列表，边界选择函数返回正确的 ×64 边界；不在扩展区间内的长度被忽略。
- `scripts/` 两个工具的离线单测：合成张量上相对 L2 与包络比值正确；角色集合不等时报错。

## 交付物

- 分支 `exp/e1r003-statetools`；`scripts/state_envelope.py`、`scripts/logits_probe.py`（本地与远端同步，md5 相同）；`freetoken/README.md` scripts 一节补两条。
- 交付记录给出 T04 阶段 2、T10 阶段 2 可直接抄用的完整命令（含环境变量、参数、输出路径约定）。

## 风险

- 中。取中间边界需要触及 GDN 分块扫描内核的调用参数；若必须改内核才能取到非最深边界，改为「对 L 处单独起一次只到 L 的整段重算」（这会改变分块，属于另一种合法重排，必须在交付记录里明说，T04 判读时按「另一合法重排」处理）。
- logits 落盘若需关 CUDA Graph，只影响预填路径（预填本来不走图），解码不受影响。

## 交付记录（02 执行者填写）

2026-10-04：c30原候选开发自检及正式T16已复核封存；T04 R015/b43真实恢复12416非12672且末段诊断proof丢失，失败保留，独立本地分支普通分段诊断修复已独立复核并通过Linux RED/GREEN与447PASS/2原有FAIL/6SKIP回归；尚无新GPU候选门，见[诊断修复记录](../../development/d03_continuation_fix.md)；T10 R017/b44工装已独立复核及Linux28PASS、冻结后启动；业务验收尚未完成。根据统一E2基线决定，本次父树与G2轮次替代上表规划阶段的97bc62c/E1轮次。

- 分支 / commit：`exp/e1r003-statetools` @ `c30ae0d7003c3bbbf56867ce74da797332fa7ed5`。
- worktree：服务器 `/data2/FreeToken/wt/e1r003st`；本地 `development/e2d03/`。两边提交一致，tracked tree干净。
- 开发父树 worktree / commit：`/data2/FreeToken/wt/e2base` / `23f2e2caa3395837c9474735ffc83321f3b9b5a1` (`E2-base@23f2e2c`)。
- 新增开关：开发环境 `FT_DEV_STATE_DUMP_AT`（逗号分隔长度）、`FT_DEV_LOGITS_DUMP`（目录）；全部默认关闭。原有 `FT_DEV_STATE_DUMP` 配合边界采样使用。开发落盘仅支持TP=1，关闭时不限制原TP路径。
- 新增脚本（候选worktree及服务器正式scripts均已同步）：`state_envelope.py` MD5 `f95a58a588161f15b2b1efabd1a7b842`；`logits_probe.py` MD5 `e66328421bb9b8ae82af5595f9da942a`。项目README的scripts条目已补充。
- 目标测试命令：在候选worktree以 `CUDA_VISIBLE_DEVICES='' PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py tests/scripts/test_logits_probe.py scripts/tests/test_state_envelope.py tests/tokenizer/test_tokenize.py tests/scheduler/test_dev_tokens.py` 执行，48 passed；日志SHA `6040252609e7e05f76a8c91887f5bb9163caa644fdb0c068595c77a341b1c30c`。
- 扩大回归444 passed / 2 known failed / 6 skipped，失败数不增加。已有失败为 `test_prefix_commit_sentinel_guard`、`test_post_terminal_overlap_step_is_dropped`。日志SHA `c4ba1cc5bfaeaa660c19f93e2fb7d2326ae4f9844eee61e422457eb03c646125`；整组不称全绿。
- G3复现（数值为相对L2百分比，ref=B/test=A，首层；末五层）：

| 长度 | conv_states | recurrent_states |
|---|---|---|
| 12416 | 0.24；11.77,14.59,11.69,10.89,8.50 | 0.40；3.18,14.23,3.62,8.21,9.71 |
| 14080 | 0.00；9.89,11.05,15.58,9.68,8.40 | 0.18；4.98,14.22,6.91,14.04,12.29 |
| 21568 | 0.12；15.07,16.76,17.83,14.04,11.18 | 0.39；15.54,20.78,13.74,24.49,17.42 |

- G3实际工件：`/data2/FreeToken/runs/dev_D03/g3_envelope_refB.csv`，三行均复现至两位小数；长度集合不同的默认命令实际拒绝。
- G4/G5开发自检：`/data2/FreeToken/runs/dev_D03/gpu_selfcheck_c30ae0d_urlfix/`；manifest SHA `4e8d18429ecaef5b8f856f73a4c913c1a08068f9f433acce73091a4cb27764c3`，独立只读复核通过。七边界完整，同输入12672比较输出74层/角色；parent OFF/candidate OFF/ON冷输出逐位一致，OFF不建诊断目录。两个独立进程K=64、完整FP32词表logits64/64逐位一致、top1=1、KL=0。全部进程已退出，端口/GPU锁释放。历史12672没有合法包络，不能据此作阈值放行。
- 首轮自检因为客户端重复`/v1`拼接HTTP404而中止；原失败目录/manifest保留，不算数值比较失败。修正测试调用地址后使用全新输出，不改候选模型计算。
- G2正式门：`E2-R002-gate-D03` / batch38 已完成，四臂全文、13事件、搬运字节、参数及默认惰性均通过，独立01复核PASS，D04封存及只读清单校验通过。MANIFEST SHA256 `2bc41220885af37386e0f365ef2fba3be97c39e96ec585b4a4cf9ed7dbd8526f`；初版round SHA256 `77bfb5d0cf57950fdbea4b02550a18fdc0acd5373affa17163257238e7cdfeb4`。隔离T16 runner MD5 `00661195a6df1a6f6456fc938c489381`；正式verdict仍pending_review。T04 R014/b39/PID2493982已启动，T04/T10业务验收仍待。
- 01完整可执行命令、环境变量、输出目录、真实token与恢复证据要求见 [D03阶段2执行说明](../../development/d03_phase2_commands.md)。三个消费者轮次固定为T04 `E2-R014`、T10P1 `E2-R012`、T10P2 `E2-R013`；启动器在真实T16独立复核并封存之前拒绝启动。
- 已知限制：边界取自同次scan，不通过切段改变参照；历史无层名映射时标明按索引对齐；非64对齐cached偏移拒绝不准确取样；logits开发原始IDs仅随环境开启，包含added tokens；固定同一P+X，不从文本重编码推导实际引擎分叉。T04已测CPU合法包络814点中199点超出，最大比值5.489091417；不修改计算或放宽科学阈值。

最新消费者状态：T11 R011/b40已独立复核并于12:19:49 CST封存，11次真实恢复及历史11长度44张量逐位一致；写回归因仍待。T04 R014只完成boundary capture、恢复为空失败，原工件保留；R015/b43/PID2749339通过独立复核及Linux20PASS后已启动，修改测试请求历史，不改c30模型计算或数值阈值。T10 R012/b41启动环境失败；R016/b42完成12/72条后因tool_calls/stop映射校验错误失败，两轮原工件保留；R017修复验证中未启动。旧命令是历史记录，不能用已有RID重跑。

详尽源位置、哈希和失败保留记录见 [开发验证记录](../../development/d03_design_notes.md)。

后续诊断修复候选：f5067bbe05da51d5f78185213435a8be095a684a，独立服务器树e2d03-continuation已建立，准确Git blob在Linux26PASS；新GPU默认门待测。T10 R017实际72记录已复核封存，R013/b45阶段2运行中；Y129构造CPU10PASS，T04新四臂尚待，不使用本卡早期启动观察作为当前状态。
