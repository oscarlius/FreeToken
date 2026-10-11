# hybrid_verify 工装 CPU 就绪报告（手册 1.4）

构建时间：2026-10-11 上午（阶段 1，纯 CPU）。目录：`/data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify/`（本地同名镜像）。源工装 `development/d08_d10_gpu_retry2_20261011/` 未改动；继承的 retry2 证据文件已隔离到本目录 `_inherited_retry2/`，`d0_service.py` 已删，`__pycache__` 已清。

---

## 0. 两项待主会话裁定

### 0.1 LC2 第二路：手册截取规则在真实负载上不可行（阻断 LC2 两路）

手册 1.4 规则："从 LC1 截取，按顺序逐条加入 messages，不超过 32,000 token，保留尽可能多的完整消息"。实际 LC1（`G_seed_real/round-01.payload.json`）只有 3 条消息，第 1 条 user 消息单独渲染即 **87,100 token**（连同 tools 模板 87,328），一条都放不下，规则产出为空。已按规则原样执行并记录（`payloads/PAYLOADS.json` 的 `LC2_lane2` 节，含逐条累计 token 数）。

已生成一份**明确标注"未冻结"的提案**供裁定：token 级前缀截取 LC1 第 1 条消息的前 129,101 / 345,089 字符，渲染后 **31,999 token**（保留 tools 渲染；尾部中文提问随截断丢失，内容为真实仓库代码文本）。

- 提案负载：`payloads/lc2b_proposal_prefix32k.payload.json`，SHA `2147f5cecc51efe3e2e9dd85a62d4c8925c8986bc0a98157ce265ebbc86f6c69`
- 提案 AIPerf 输入（路1=G_seed12k 12,905 + 路2=提案 31,999）：`payloads/inputs_LC2.proposal.jsonl`，SHA `5ee260c65f3be5c7f278f67ccae8bcd79cad7b908ecb6faddd9434c277d9ebe4`

**当前准入不含 LC2**（`lc2_status: excluded_pending_main_session_adjudication`），2.4 的 LC2 两路两行与 J5 的 lc2 比值相应空缺。若批准提案（或另指定来源）：重跑 `payload_freeze.py --out payloads_v2`（把提案路径写入清单）后重跑 `prepare_root_admission.py` 重建准入即可，代码零改动。若裁定放弃 LC2：当前准入直接可用。

### 0.2 手册内部矛盾：1.4 判据"argv 只有两处差异" vs 2.4"每个服务只监听 127.0.0.1 测试端口"

retry2 原工装把 hybrid 服务绑在生产地址 172.16.108.9:8095 上（当时 481 已停）。本轮 2.4 要求测试服务只听 127.0.0.1。我的处理：**host/port 做成准入参数，默认 `127.0.0.1:8123`**。因此最终 argv 与生产的逐项差异为：

- O1/O2（offload 参照）：2 处——`--host`、`--port`；
- H1/H2（hybrid）：4 处——0.5 节两处（绑核前缀、`--moe-strategy hybrid`）+ `--host`、`--port`。

机制对比不受 host/port 影响：O 与 H 的 host/port 完全相同，两者之间的差异仍然恰好是 0.5 节的两处。若审定 1.4 判据优先（严格两处）：把 `prepare_root_admission.py` 中 `HOST='127.0.0.1'`、`PORT=8123` 改为 `'172.16.108.9'`、`8095`，重跑该脚本重建准入即可，其余代码零改动（注意：此时测试服务占用生产地址，481 必须先停，与 retry2 相同）。

---

## 1. 负载清单与 SHA（冻结完成，服务器侧计数与生产实报完全一致）

| 负载 | 来源 | 内容 | 渲染 token 数 | 生产实报核对 | AIPerf 输入 SHA256 |
|---|---|---|---|---|---|
| X | `development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl` | 两条不同 ~1.2K 提示 | — | SHA 与冻结钉 `f63b3623…a1162` 一致 | 同左（原文件直接用） |
| LC1 | `ft_rounds/E2-R046g/G_seed_real/round-01.payload.json` | 真实 agent 对话（3 消息+3 tools） | **87,328** | 87,328 ✅ 逐字一致 | `7c46dbb7…297e1e` |
| LC2 路1 | `ft_rounds/E2-R046g/G_seed12k/round-01.payload.json` | 另一真实会话（3 消息+3 tools） | **12,905** | 12,905 ✅ | （含在提案文件中） |
| LC2 路2 | 从 LC1 截取 | **规则不可行，见 0.1** | — | — | 未冻结 |

- 计数/渲染用的是 release-e2（481d3a7）自己的 `TokenizeManager`，路径与 `server/generation.py::count_prompt_tokens` 完全一致（`render_messages` + tools + 无 chat_template_kwargs）；工作树干净、HEAD=481d3a7 已在清单中存证。
- AIPerf 发送格式：与 X 相同的 single_turn JSONL（CRLF 行尾），`text` 为 481 聊天模板渲染后的完整提示串，`output_length=256`，`extra={temperature:0, top_p:1, ignore_eos:false}`。服务端会再套一层聊天模板（与全部既有 X 测量同一路径），实测 prompt_tokens 会比上表多约 10 个 token 的外壳。
- 清单：`payloads/PAYLOADS.json`，SHA `c015ab1abb41b2e65d0e5d896e3cc4f2bf0f045e0125a4fd4c49377bdb227b99`。
- 未使用合成 32K 文本（probe_cold32k / R048b dec32k），符合手册禁令。

## 2. 启动参数对比（准入内置门，启动前逐项校验）

基线：`BASELINE_OWNER_FREEZE.json`（生产 -07 实时回读，SHA `d849e302…664ed6`）。完整 diff 由工装在启动时写入每个服务的 `argv_diff.json`（含逐位置对照）。

- O1/O2 argv = 生产 argv，仅 `--host 172.16.108.9→127.0.0.1`、`--port 8095→8123`。
- H1/H2 argv = O argv + 0.5 节两处：`taskset -c 1,3-47` → `numactl --interleave=all taskset -c 1,3-23,25,27-47`；`--moe-strategy offload` → `hybrid`。
- 两条 argv 均已通过 **481（release-e2）自己的参数解析器 dry-run**（`freetoken.server.args.parse_args`，输出 `ServerArgs(...)` 确认；见 `ADMISSION_BUILD.json` 的 `parser_dry_runs`）。

## 3. 测量编排（2.4 节实现）

- 顺序 O1→H1→H2→O2，每个服务独立持 GPU 锁、独立清理证明；某服务测量失败继续下一个，清理失败则整个窗口中止。
- 矩阵（当前准入）：O1/H1 = X单路×2、X两路×2、LC1单路×2、quality60×1；H2 = 冷启不预热、X单路×1；O2 = X单路×2、X两路×2、LC1单路×2。LC2 两路待 0.1 裁定。
- 预热：除 H2 外每个服务 2 条不计成绩 SDK 请求（短 512 / 长 8257 token，各 128 token 完成），与恢复 481 的 SDK 冒烟同源（r065 适配器，SHA 钉住）。
- 通用设置 temperature=0、max_tokens=256、ignore_eos=false；速度=1000/ITL；<128 token 的路不计入并标注；任一路 <7.8 tok/s 记 abnormal。
- J1–J5 由 `gpu_window.compute_verdicts` 机械计算写入 `verdict.json`；J4 文本比较用收编的 `output_compare.py`（与 `development/d08_hybrid_review_20261011/output_compare.py` 逐字节相同，SHA `8968ca4d…d36870`，收编原因：该评审目录服务器上不存在）。
- 本工装不停/不恢复 481：启动前硬性前置检查（生产 -07 三个 pid 均不活、8095 可绑定、无 ft serve 进程、观察进程已自行退出、GPU 锁文件不存在），任一不满足拒绝启动。
- quality60：`venv-eval` 的 `phase3_sdk.py`，脚本与题库 SHA 均已钉入准入；输出目录为各服务下新建独占目录。

## 4. 测试输出

| 项 | 结果 |
|---|---|
| 本地 pytest（工装目录） | 25 passed, 1 skipped（跳过=服务器专属 dry-run） |
| 服务器 pytest（venv，CUDA 关，准入构建内执行） | **26 passed in 7.80s** |
| quality60 README 命令（3 个测试文件，venv-eval） | **18 passed in 2.64s** |
| 准入回读校验（封存文件 pins + argv 门重放） | PIN_AND_ARGV_GATE_PASS |

测试覆盖：4 控制器文件钉集、准入封存/异 schema 拒绝、offload/hybrid argv 构造（含非法前缀/模式拒绝）、PID 出生证明、清理端口探测、预热契约（测试端口+512/8257）、LC2 截取规则（含首消息超大不可行用例）、前缀提案二分、J1/J2/J3/J4/J5 判定（met/not_met/短路排除/异常标记）、release-e2 解析器 dry-run（仅服务器）。

## 5. 准入与封存

- `ROOT_ADMISSION.json`：SHA256 `becc648e59bc0fbe4367da5ef3bd0b961d154cd23b43359923e07febb3c93f3c`，模式 0444，schema `ft_hybrid_verify_20261011/v1`。
- 窗口上限 6900 秒；`output_root=/data2/FreeToken/runs/dev_hybrid_verify_20261011/window01`（必须不存在，工装自建）。
- `ADMISSION_BUILD.json`：SHA `8d900a0a8d4def19ed877e704c052448916e5f53140f1ba46a2c0cdc21e35619`（含 pytest 输出与 dry-run 记录）。
- 服务器侧全部源码、负载、清单、准入均已 `chmod a-w` 冻结。

## 6. 预计时间表（窗口 6900 秒 = 115 分钟）

| 段 | 估计 |
|---|---|
| 4 次服务加载（每次 ≤10 分钟 readiness 预算） | 约 25–40 分钟 |
| 预热 ×3 服务 | 约 3 分钟 |
| X/LC1 AIPerf（LC1 冷预填 87K 为主要开销，单路超时上限 900 秒） | 约 10–20 分钟 |
| quality60 ×2（O1、H1；60 题 ×768 token 预算，串行） | 约 35–65 分钟 |
| 服务间清理/取证 | 约 5 分钟 |
| **合计** | **约 80–130 分钟，上限情形会顶到 115 分钟窗口** |

quality60 是主要不确定性。若实际超出窗口，工装会在 deadline 处按失败处理（不截断写入判据）；如审核希望放宽，把准入 `window_limit_seconds` 调到 9000 即可（需重建准入）。

## 7. 阶段 2 实际要执行的命令（2.4，审核通过且满足前置后）

```bash
ssh 9 'cd /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify && \
  CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 \
  /data2/FreeToken/venv/bin/python -B gpu_window.py --execute \
  --admission /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify/ROOT_ADMISSION.json'
```

前置（工装自检，不满足即拒绝）：481 已经 restore08 停止、观察进程已自行退出、T16 两套已结束且 GPU 锁已释放、`window01` 不存在。本窗口不负责停/恢复 481。

## 8. 失败处理

- 工装报错（failed_harness）：不重试；该服务 terminal.json 与事件日志定位后交主会话。清理失败会保留 GPU 锁并中止窗口（与 retry2 相同）。
- 判据不通过（not_met/drift/affected）：不重试、不改判据，verdict.json 原样交付。
- 遇到手册没写的情况：停下，在协调日志写明，等主会话。

## 7. 修订 v2（2026-10-11 09:07，按主会话审核 `plan/KIMI_STAGE1_REVIEW_20261011.md` 第 2.5 节）

- 旧准入保留为 `ROOT_ADMISSION.v1_window6900.json`（0444，SHA 即第 5 节的 `becc648e…`），其构建回执改名 `ADMISSION_BUILD.v1_window6900.json`。
- `prepare_root_admission.py` 唯一改动：`WINDOW_LIMIT_SECONDS = 6900 → 9000`（150 分钟上限，只是余量，不代表计划用满）。新 SHA256：`375cec25882698d2d68f195345c3466a9d81351eb4296e27a9be3672929b0ad1`（0444）。
- **新准入 `ROOT_ADMISSION.json`：SHA256 `f874501c52eea0c179dfacbf4ffa4fac5227db3b09d89a0a7026dbda7a3ecb0c`（0444）**，`window_limit_seconds=9000`，其余字段与 v1 一致（schema、host/port、矩阵、pins 不变；构建回执 `ADMISSION_BUILD.json` SHA `61776f59…d6e5`）。
- LC2 状态字段：`lc2_status` 在构建器中无参数入口（非常量注入项），按审核 2.2 保持原值 `excluded_pending_main_session_adjudication`；本窗口不跑 LC2，以审核文件为准。J5 只报告 LC1 单路比值，并按审核附注写明发送方式（渲染后整条作 user 消息，服务端再套模板，两臂相同，比值可比但不代表真实 agent 绝对速度）。
- 重建后复核：构建内 pytest **26 passed in 8.22s**；重建后独立重跑 pytest **26 passed in 7.75s**；准入回读校验（封存 pins + 两模式 argv 门重放）**PIN_AND_ARGV_GATE_PASS**。
- 阶段 2 执行命令不变，`--admission` 指向新 `ROOT_ADMISSION.json`。
