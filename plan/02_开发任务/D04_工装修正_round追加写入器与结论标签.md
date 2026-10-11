# D04 工装修正：`round.json` 追加式写入器、轮次收尾脚本、比对结论行按比较对象生成标签

| 项 | 值 |
|---|---|
| 优先级 | **P0**（规则 §3.2 的执行工具；没有它，已关闭轮次的判定无法合规追加） |
| 估计 | 1–1.5 人日 |
| 位置 | 只改 `freetoken/scripts/`（本地）与 `/data2/FreeToken/scripts/`（远端）；**不涉及 FreeToken 源码** |
| 依赖 | 无 |
| 01 验证 | 不需要 GPU 卡；由 01 在下一张收尾的卡（T01 之后任意一张）中按新流程使用，并在结果文件「执行记录」写明工具版本（md5） |
| 论文依据 | v3.2 §6.8 工装备注「batch19 日志结尾那行『bank 恢复与整段重算在状态层一致』，实际比较的是 B 对 B2……标签有误」；§9.3「结论行的标签要与比较对象一致」；规则 §1.4、§3 |

## 目标

1. 让「只追加」成为工具强制，而不是靠自觉。
2. 让比对工具的结论行永远写出「谁对谁」，不再出现固定文案。

## 范围

### A. `scripts/round_json_append.py`（远端运行）

```
round_json_append.py <轮次目录> verdict  --new <值> --reason <文本> --evidence <路径或轮次ID>... --by <角色>
round_json_append.py <轮次目录> retract  --target <SC id 或文本> --reason <文本> --evidence ... --by <角色>
round_json_append.py <轮次目录> add      --json <补丁.json>     # 只允许新增键 / 向列表末尾追加
round_json_append.py <轮次目录> check                           # 只校验历史链，不写
```

行为：

- 读当前 `round.json` 与 `round_history/` 最新版本，二者必须逐字节相同，否则拒绝（说明有人绕过工具改过）。
- 生成新版本后做**子集校验**：旧版本每个键值在新版本中原样存在（字典递归；列表只能变长且前缀不变）；唯一例外：`verdict`（必须等于新追加的 `verdict_history[-1].new`）与 `sub_conclusions[i].status`（必须有对应 `retractions` 条目或 `verdict_history` 理由）。
- 写入：临时 `chmod u+w` 轮次目录内的 `round.json` 与 `round_history/`；写 `round.json`、`round_history/round.v<NNN>.json`；更新 `round_history/SHA256SUMS`；恢复 `chmod a-w`。
- 时间戳自动生成（CST）；`--by` 必填。
- 对没有 `round_history/` 的历史轮次（E1-R000…E1-R004）：首次使用时先把当前文件存为 `round.v000.json`（标注 `legacy_snapshot`），再追加。**不改动历史文件内容。**

### B. `scripts/round_close.sh <轮次ID>`（远端运行）

把规则 §1.4 的收尾 5 步做成一个命令：检查必备文件（`round.json`、每臂 `SERVE_CMD.txt`/`serve.log`/`serve_args.txt`/`ENV.txt`、`batch.sh`）→ JSON 合法 → `round_history/round.v001.json` → `MANIFEST.sha256` → `chmod -R a-w` → 打印 `MANIFEST.sha256` 自身的 sha256。缺任何必备文件则报错退出，不关闭。

### C. 比对工具结论行按比较对象生成标签

- `scripts/state_eq.py`：结论行改为 `结论（<ref 标签> 对 <test 标签>）：…`。标签默认取目录路径的最后两级（如 `E1-R003-stateeq/dump_B`），可用 `--label-ref`、`--label-test` 覆盖；只有当 `test` 目录含 `resume` 记录时，才允许出现「恢复」字样，否则文案用「两侧状态逐位一致 / 有 N 个长度不一致」。
- 同样处理 `agent_trace.py compare` 与 `serve_args_diff.py` 的汇总行（若有固定文案）。**注意：规划阶段只读核实，`agent_trace.py` 本地（md5 `eec0806b…`）与远端（`f81acb79…`）不同；`state_eq.py`、`serve_args_diff.py`、`cold_eq.py`、`ft_probe_ckpt_tax.py` 两边相同。先 diff 两份 `agent_trace.py`，以远端（实际被所有批次使用的版本）为准合并后再改，并在交付记录写明差异内容。**
- 历史批次日志（batch19.log 等）**不改**；论文 §6.8 已登记该标签错误。

## 非目标

- 不重写 `RESULTS_E1` 里的历史修订脚本（`_shared/dev_d0/rev_*.py`），它们直接改远端 `round.json`；本卡交付后，这类脚本停止使用（在 `freetoken/README.md` 写明）。

## 设计约束

- 纯标准库 Python（远端 venv `/data2/FreeToken/venv`），不新增依赖。
- 任何校验失败：非 0 退出、打印第一处不符的 JSON 路径，不写任何文件。

## 验收门

| 门 | 条件 |
|---|---|
| G1 | 单测：合法追加通过；改旧数值、删键、改列表中间元素、`verdict` 与 `verdict_history` 不一致——全部被拒 |
| G2 | 在 `/tmp` 下的轮次目录副本上演练：`round_close.sh` 关闭 → `verdict` 追加 → `retract` 追加 → `check` 通过；`MANIFEST.sha256` 不受 `round.json` 追加影响 |
| G3 | `state_eq.py` 在 `E1-R003-stateeq/dump_B` 对 `dump_B2` 上的结论行不再出现「bank 恢复」；在 `dump_B` 对 `dump_A` 上出现「恢复」且注明标签；逐长度行与旧版输出逐字相同 |

## 需要的测试

`freetoken/scripts/tests/test_round_json_append.py`、`test_state_eq_label.py`（离线，用合成目录）。

## 交付物

- 三个脚本的本地与远端副本（md5 相同）；`freetoken/README.md` scripts 一节补三条，并写明 `rev_*.py` 停用。
- 交付记录给出 01 收尾的新命令（替换 01 README §7 第 2–4 步的写法；01 README 由总负责人更新）。

## 风险

低。唯一风险是权限：若远端轮次目录属主不是 `dell`，`chmod` 会失败——工具应在写入前检查属主并报错。

## 交付记录（02 执行者填写）

```
- 脚本与 md5：
- 测试：
- G2 演练记录：
- 01 收尾新命令：
- 已知限制：
```
