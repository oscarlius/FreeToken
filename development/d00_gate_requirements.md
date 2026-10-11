# D00 T16 默认路径：三场景专用要求（只读规划）

## 比较对象与启动前共同门

- `OLD`：80943fd；`NEW`：最终合齐 D01/D02 的 `E2-base@<commit>`（候选来源为 23f2e2c）。每个服务必须独立进程、独立输出目录，按单写者锁、端口、显存、clean worktree、正确 import path 检查。
- 同一场景的 OLD/NEW 必须使用完全相同的 prompt/cold-id、temp=0、输出 token 数、模型、窗口和既有服务参数。业务 Prefill 序列门单独排除就绪 `say ok`；D0 JSONL 对齐必须保留该全量事件，不能混用两种基数。
- 不显式传 `--mamba-host-slots`、不传 `--no-prefill-anchor-cut`，以验证新增字段的默认值；不设 `FT_DEV_STATE_DUMP`、`FT_DEV_D0`、`FT_DEV_D0_PATH`、`FT_DEV_D0_TIMELINE`，D0-off 臂不得创建 D0 文件。

## Parsed arguments：唯一预声明允许差异

相对 80943fd，23f2e2c 的 `server/args.py` 只新增：

1. `prefill_anchor_cut=True`（`--no-prefill-anchor-cut` 未传时）；
2. `mamba_host_slots=0`（`--mamba-host-slots` 未传时）。

`pid` 为每进程固有差异。除此三项外，归一化后的 Parsed arguments 必须相同。`FT_DEV_D0*` 是环境变量，不是 Parsed arguments 差异；D0-on 与 D0-off 的 `SERVE_CMD.txt` 差别只能是该环境前缀及路径。

## 三场景：两套配置、共 8 个独立服务

运行两套配置各四个独立服务：OLD-D0off、NEW-D0off、OLD-D0on、NEW-D0on。不得用同一驻留服务改变 layer-major 或 chunk 参数。L 独占 layer-major 配置；S 与 C 在同一 non-layer-major 配置服务内按顺序使用不同的新 cold-id，各树对应输入相同且每个业务请求的 `cached_tokens=0`。

| 场景 | 输入 | 公共 flags | 必须证明 |
|---|---|---|---|
| L：冷 32K layer-major | `cold_eq.py <stable-id-L> ... 32052 128` | `--prefill-layer-major --max-prefill-length 4096 --enable-special-token-ckpt` | layer-major 长提示的 temp0 全文、Prefill 序列、D0 前缀字节完全一致 |
| S：短提示默认调度路径 | `cold_eq.py <stable-id-S> ... 2000 128`（batch26实际执行；non-LM 服务内先执行） | `--max-prefill-length 4096 --enable-special-token-ckpt`（不传 layer-major） | 非 layer-major 的短路径全文和 Prefill 序列一致；D00卡未固定输出数 |
| C：32K 4096 分块默认路径 | `cold_eq.py <stable-id-C> ... 32052 128`（同一 non-LM 服务内、S 后执行） | `--max-prefill-length 4096 --enable-special-token-ckpt`（不传 layer-major） | 多个 4096 分块执行的完整 Prefill 序列与逐段 H2D/D2D 一致 |

D0-off 验收（每场景）：全文逐字节相同；`Prefill batch` 中 `#new-token/#cached-token` 序列逐行相同；无 `GDN bank:`、状态 dump、`D0 prefill` 或 `D0 seg:` 输出；无 D0 产物。`mamba_host_slots=0` 时 bank 的 runtime 行不得出现（debug 行若日志级别被改为可见亦作为失败处理）。

D0-on 验收（每场景）：全文和 Prefill 序列仍相同；两边非末段的 H2D/D2D 整数字节严格相同。时间或吞吐只记录，不参与无损门。

## D02 即时末段：不可用 zip 掩盖的严格校验

对每个 D0-on 服务，解析**全** `serve.log` 的 `Prefill batch` 行（包含 `say ok`）为 `P_all[]`，解析所有 `d0_prefill.jsonl` 行为 `J[]`；业务序列另为去除首个就绪事件的 `P_business[]`。

1. OLD（80943fd）必须满足 `len(J_old) == len(P_all_old)-1`；NEW 必须满足 `len(J_new) == len(P_all_new)`；同时 `P_all_old == P_all_new`（逐行 `(new,cached)`）。业务 `P_business` 只用于业务 SEQ 门，不参与本行计数。任一不符即停止。
2. 对 `i in [0, len(J_old))`（包含 say-ok 对应的首条）强制 `J_old[i].h2d_bytes == J_new[i].h2d_bytes` 且 `d2d_bytes` 相等，不能以浮点 GiB 显示值代替整数。
3. NEW 的每条 `J_new[i]` 必须按顺序对齐 `P_all_new[i]`：`sum(reqs[].new_tokens)` 与 `sum(reqs[].cached_tokens)` 分别等于该 `Prefill batch` 的 `(new,cached)`；最后一条也必须满足，且其索引是 `len(P_all_new)-1`。
4. 最后一条 NEW 记录必须真实存在于服务仍存活时；停止服务后不得把 shutdown 输出作为补写证据。缺字段、重复/跳号、无法一一对齐或任一字节不等均停止并上报。

## 为什么通用 T16 不足

通用 T16 的四臂只覆盖一组共同 flags（模板默认 layer-major+4096），其 `cold_eq` 与多消息 tax 探针不能独立证明短提示非 layer-major 路径和 32K 非 layer-major 4096 分块路径。模板 H2D 比较使用 `zip()`；即使它检查 `n_new=n_parent+1`，也没有逐条证明新增记录恰为最后 Prefill 事件，亦没有验证 D0-off 的 bank/dump/原因日志沉默。因此 gate-D00 应保留通用 T16 的四项门，并增加本说明的三场景检查。

## 停止

任一 gate、服务未就绪、非零业务 rc、参数差异超出预声明 allowlist、全文/Prefill/整数 H2D-D2D 不一致、D0-off 泄漏、缺失/错位末段记录即停止；不改参数重跑。正式轮次 ID、E2-base commit、工件目录与 verdict 由总负责人填写。

