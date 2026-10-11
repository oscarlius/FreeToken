# D16 剩余项的 openai-python SDK 采集范围（01:30 夜间预授权）

## 当前夜间授权范围（取代下方 8/12 历史提案）

**当前已获夜间预授权的范围为 interleave 6 服务 / 8 调用；不含 warm，也没有 primer。** R040h 已进入 canonical pending-review 且“48 resident/hits 0”判词为待定；它不提供 warm hit 证明。请求清单在 `evaluation/d16_api/scope_payloads.json`，每条均复用固定 `/v1/completions` schema：mapped text prompt、`max_tokens=128`、`temperature=0`、`top_p=1`、`ignore_eos=true`、streamed usage。两个 batch 服务各并发两个请求，四个 single 服务各一个请求；四个 `pair_0..3` 分别比较 batch 与 single 的完整投影。标准 SDK 薄适配器封存 request、HTTP status/headers、每一 decoded chunk 及相对到达时间，再严格要求 `length`、128 completion tokens、全文和 usage 相等。

原 interleave 不是同一输入重复：冻结运行体实际传入 `ids[0]` 的 512-token tail 和同一 source case 的完整 8,257-token long query。`evaluation/d16_api/interleave_input_binding.json` 已在 FT venv、local-files-only tokenizer 下封存两套原 IDs、decode text SHA、retokenized IDs/SHA；二者当前各自 round-trip 相同，仍只构成获批的文本映射，不构成 worker 内部输入证明。

**warm_0/1 当前 deferred，不计入服务或调用。** 普通 `ft serve` 不使用已退役的 `FT_D16_CACHE_INIT`/capture wrapper；候选 `--enable-cache-report` 只能在 OpenAI usage 报告 prefix `cached_tokens`，不是 expert cache initial residency 或 actual prefill hit。R040h 的待定记录含 warm 初始 48/48、`prefill_hit_rows=0`，仍不能构成命中证明。没有只读的既有 cache report/stats/log/D0 count 同时证明 actual expert hit 时，早晨只报告该缺口，不启动 warm 服务；不得新增 collector、hook、primer 或修复原采集器。

R040h/b116 的 `failed_harness` D04 已封存（round pin `96e68909…`，review pin `48e15054…`）。当前 scope 只复用 root 负责的既有 D04 service lifecycle，不实现新的 D04 adapter，也不创建正式轮次或启动 GPU。

## 历史提案 — **SUPERSEDED：不得按 8 服务 / 12 调用执行**

**状态：仅报批，未分配轮次号，未启动 GPU。** R040h/b116 的独立 `failed_harness` 复核与 D04 封存已完成（round pin `96e68909…`，review pin `48e15054…`）：`warm_0` 的初始 48/48 层驻留与 `prefill_hit_rows=0` 不一致，模型功能仍未定；不得修复或重试原生采集器。本提案只把尚未完成的 `warm_0/1 + interleave_0..5` 改为标准 OpenAI API 的 SSE 观测，并不把 API 结果称为原 D16 的 cache-hit、物理批处理或 worker-state 证据。

## 冻结身份与输入边界

| 项目 | 原 R040h | 拟议 SDK 范围 |
| --- | --- | --- |
| 候选 / 工作树 | `effb9969706922ddad9e59b96377e46469ebe97f` / `/data2/FreeToken/wt/e2base1-p1` | 相同；不改候选、模型、权重或服务端代码 |
| 服务配置 | `E2-R040h/.../warm_0/SERVE_CMD.txt`：`numactl --cpunodebind=0,1 --interleave=all`，私有 loopback，`--memory-ratio 0.88`、`--max-running-requests 4`、`--cuda-graph-max-bs 4`、`--kv-reserve-tokens 98304`、`--max-seq-len-override 98304`，以及相同的模型/量化/MoE 参数 | **非同一 argv/environment。** 使用候选普通 `/data2/FreeToken/venv/bin/ft serve`，保留上述 NUMA、模型路径/名称、量化/MoE、4/4、98304/.88 参数；不使用 `d16_native_capture_shutdown_v3.py`，也不设置 `FT_D16_CACHE_INIT`、`FT_D16_EXECUTION_ID`、`FT_D16_SERVICE_CAPTURE_*`、`FT_DEV_STATE_DUMP`、`FT_T17_INPUT_RECEIPTS`、`FT_T17_OBSERVATIONS`。每臂仍由既有 D04/已审 lifecycle 管理。 |
| 原始输入 | `/data2/_shared/runs/ft_rounds/E2-R040/source_tools/realinput_28.json` 的 `cases[*].query` 为 token-id 列表；原生 `/internal/t17/exact-ids` 直接接收 `input_ids_exact` | 保留原 512 IDs、原 `input_ids_sha256` 与选择规则；**不能**直接传给 OpenAI endpoint |
| API 映射 | 无 | 已在 FT venv、仅本地 tokenizer 文件完成预备映射：R040h `warm_0/cache_input.json` 的 512 IDs SHA `d5a436…bfe9e5` decode 后文本 SHA `e319a7…c8b2df`，再 tokenize 得 512 IDs 和同一 SHA；完整 IDs、文本及结果在 `evaluation/d16_api/input_binding.json`。这只是在当前 tokenizer 的 CPU 结果，仍须作为映射批准项，不能自动扩展成原生 worker 输入证明。 |

候选的 `python/freetoken/server/openai_api.py` 虽提供 `/v1/completions`，但对 `prompt: list[int]` / `list[list[int]]` 明确拒绝（“token-id prompt inputs are not supported”）。因此 `OpenAI(...).completions.create(prompt=原 IDs, stream=True)` 不可行；没有获批的输入映射或服务端改动，本范围必须 fail-closed，禁止 decode 后默认为同一实验。

## 已作废的调用矩阵：8 个服务、12 个 API 调用

| 臂 | 服务 | API 调用 | 执行与比较 |
| --- | ---: | ---: | --- |
| warm | `warm_0`、`warm_1` | 每服务 `primer` + `measure`，共 **4** | 每个新服务先向同一已批准映射 prompt 发一条 primer，再发 measurement；primer 是 API 层前序请求，替代已退役的原生 `FT_D16_CACHE_INIT=warm` hook，不声称缓存命中。比较两条 `measure` 的完整 SSE 结果。 |
| interleave batch | `interleave_0`、`interleave_1` | 各 2 条，共 **4** | 每服务用 barrier 同时发两条原配对 prompt；记录两请求的客户端启动、首/末 chunk 与结束时间。只证明 API 调用重叠。 |
| interleave single | `interleave_2` 至 `interleave_5` | 各 1 条，共 **4** | 四个独立服务各发原配对的一条 prompt；与相应 batch prompt 比较。 |
| **总计** | **8** | **12** | 原原生范围是 8 服务/10 次 generation；为使 “warm” 有明确前序请求，SDK 范围增加 2 条 primer。若不接受 primer，范围只能称为 8/10 的普通 API 请求，不能称 warm。 |

唯一的 SDK 请求 schema 为 `/v1/completions`：`model=<现有服务模型标识>`、`prompt=<已批准映射文本>`、`max_tokens=128`、`temperature=0`、`top_p=1`、`stream=true`、`stream_options={"include_usage":true}`，并通过 SDK 的 `extra_body={"ignore_eos":true}` 发送 `ignore_eos=true`。候选 `CompletionRequest` 明确接受这些字段，且 `stream_completion_chunks` 的结束顺序为 `choices[0].text` 增量、带 `finish_reason` 的空 text 终止 choice、随后空 choices 的 usage chunk、`[DONE]`。每臂启动前把实际 request JSON 及其 SHA 写入 receipt；字段若被服务拒绝即失败，不得静默丢弃。服务地址只绑定 `127.0.0.1`，每臂停服并保存 stdout/stderr 后才进入下一臂。

## 工具、采集物与判据

原 8/12 提案当时使用冻结 `/data2/FreeToken/evaluation/toolchain`：`openai==2.54.0`、`pytest==9.1.1`（同时记录 `aiperf==0.11.0` 的 freeze，**本范围不调用 AIPerf**），不新增专有 collector。当时的 `sdk_completions.py`/静态清单均没有 benchmark loop、服务 controller、D04 adapter 或 CLI；该段只保留其 CPU contract 的历史依据，不描述现行 payload。当前实际 CPU receipt 见 `evaluation/d16_api/cpu_receipt_20261009.json`。

每一调用封存扁平化后的实际 request JSON、SDK raw-response 的 HTTP status/headers、SDK 解码的完整 chunk 序列及相对到达时间、服务 argv/环境/源码哈希。pytest 对可比的同一映射 prompt 断言：拼接的 completion `choices.text`、终止 `finish_reason=length`、以及 `usage.prompt_tokens/completion_tokens/total_tokens` 相等，且每条均为 `completion_tokens=128`；缺 usage、finish 或因截断而不能同时提供二者即失败，任何提前 `stop` 也失败。OpenAI SDK 不把 `[DONE]` 暴露为 chunk，因此该 library-only 范围不独立证明 wire-level `[DONE]`；它不应被表述为原始 SSE 字节捕获。`/v1/completions` 不产生 chat 的 `delta.content` 或 `reasoning_content`，所以本范围不比较思考字段。batch 对还断言两条请求在客户端时间窗有重叠。D04 仅复用其既有封存/汇合和失败保留规则：新 API 产物独立追加，不能覆盖 R040h failed_harness 或把其改判为 kept。

## 能证明与不能证明的事项

该范围可证明：指定候选及**新的普通 FT serve** argv 下的 API 可达性、确定性采样下两侧的 completion SSE 全文/finish/usage 一致性、以及客户端观测到的 batch API 并发。它**不能**证明：原始 512 token IDs 实际进入模型（尽管当前 CPU retokenize 相同）、expert 初始驻留/actual hit、`prefill_hit_rows`、worker admission、物理 scheduler 同批、GPU 内部 cache/tensor 状态，或原生 interleave 的强制批调度等价。所有结论必须标为 “SDK API 行为等价（已批准文本映射下）”，不得替代原 D16 的内部状态判据。

本节仅保留原 8/12 方案的审计历史，不构成批准或执行请求；其 primer、warm 服务和相关 8/12 结论均被当前 6/8 scope 覆盖。当前批准对象仅为文首的输入映射、interleave 6 服务/8 调用和 API-only 判据；获批后由执行方完成既有 source review/输出目录等常规 fail-closed 准入，不另设范围批准。
