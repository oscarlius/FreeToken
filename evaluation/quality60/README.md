# Quality60 SDK 采集适配

此目录归 FreeToken。`sdk_capture.py` 是 OpenAI SDK 的薄采集适配，不包含服务启动、测试循环、轮次记账或评分规则，也不解析 SSE。`phase3_sdk.py` 将采集结果交给现有 `_shared/benchmark_client.py::run_phase3_quality` 的可选回调；题目循环、768-token预算和 canonical grader 均复用原实现。FreeToken 新评测使用下面的 SDK 入口；旧共享命令仍兼容原调用方，已冻结轮次不迁移或重跑。

## FreeToken 调用入口

先按对应轮次取得真实模型/GPU验证范围，再执行；本命令不启动服务、不等待或探测服务健康、不申请GPU锁，也不代替正式轮次准入。

```bash
/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python \
  /data2/FreeToken/evaluation/quality60/phase3_sdk.py \
  --api-base http://127.0.0.1:8095/v1 \
  --model Qwen3.8-Flash-Next-NVFP4 \
  --prompts /data2/_shared/test_prompts_60.json \
  --run-dir /data2/FreeToken/runs/NEW_APPROVED_QUALITY_RUN
```

输出目录必须是本次独占使用的新目录。逐题结果沿用 `quality_results_<model>.jsonl`，每条引用 `sdk_chunks/<序号>.jsonl` 及SHA；增加 SDK/适配源码版本、请求SHA、真实usage、completion/request ID。SDK分支的旧TTFT/latency和正文/思考拆分token字段显式为null；性能由AIPerf负责，不用chunk数补token。网络/解析/契约失败记为 `RUNTIME_ERROR`，原日志保留，禁止隐式重试。已有结果与chunk目录拒绝覆盖。

`FT_QUALITY_BENCHMARK_SOURCE` 仅供隔离源码验证覆盖共享客户端路径；不设置时加载固定框架相邻的 `_shared/benchmark_client.py`，评分器仍须匹配规范SHA。

## 已修复的采集边界

旧采集器会忽略无法解码的 JSON，并将缺失的 `finish_reason` 默认成 `stop`。本模块交给 SDK 解析流，将每个 SDK 解码后的 chunk 原样 JSON 序列化到独占创建的 JSONL 文件，再独立投影正文、thinking、结束原因和 usage。SDK chunk 日志不是 HTTP 原始字节记录。

解析、传输和契约错误均保留已采集内容及错误类型；缺失结束原因、缺失或冲突 usage、结束后继续出现 choice 数据等直接拒绝，不推测成功。调用方必须提供 `max_retries=0`、有限 timeout、单 choice 流式请求和 `stream_options.include_usage=true`。

固定 quality60 的 structured_tool 题使用文本 JSON 回答；这里拒绝原生 tool-call 流，不把它隐式改写为评分正文。该限制只适用于这套固定题库，不定义产品整体工具调用能力。

现有调用方接入方式为：

```python
capture = capture_chat_stream(client, original_request, new_chunk_log_path)
status, detail = canonical_grade_question(
    question, capture["response"], finish_reason=capture["finish_reason"]
)
```

调用方沿用原来的模型、prompt、768-token预算、temperature和规范判分器；评分器加载及 SHA 校验复用既有质量评测代码。性能统计交给 AIPerf，不在本模块增加时序断言。

## 验证与边界

- 本地 15PASS/1skip：skip 是目标服务器的冻结输入回放；无本地副本时不猜测结果。
- Linux 16PASS：依赖使用 `/data2/FreeToken/evaluation/toolchain/venv-eval`，禁用 CUDA，未调用真实模型端口。
- 真实 SDK 的 MockTransport 测试覆盖正常 SSE、JSON 损坏、reasoning/usage/length 保留；失败日志保留、禁止重试和不覆盖历史文件均有回归。
- 对封存 E0 的 60 条原始答案，验证 grader、corpus、answers、expected 四份 SHA 前后不变，经真实 SDK 解析后逐题核对 response/thinking/finish_reason，再调用冻结 grader，精确复现 47 PASS、11 TRUNCATED、2 ANSWER_FAIL。
- 回放的 SSE envelope 和 usage=1/1/2 为明确构造的协议夹具；它证明字段/判分语义保持，不证明历史 HTTP 字节、真实 token 用量、目标模型生成或性能。
- 独立只读复核已核对远端回执、日志、源文件 SHA 及测试范围，通过范围限于 CPU/冻结回放。

18:32接线增量：Linux **23PASS**（含原共享客户端5项回归），本地22PASS/1skip。新测试经真实 `main` 验证请求与输出model身份一致；经现有题循环将封存60题逐题回放，再次得到47 PASS、11 TRUNCATED、2 ANSWER_FAIL，逐题response/thinking/finish_reason、评分状态及chunk日志SHA一致。另覆盖缺失finish和损坏JSON归为RUNTIME_ERROR、失败不重试、历史输出不覆盖。无真实目标模型调用，CUDA未初始化。

本次源码、日志及可回读的pytest产物：`/data2/FreeToken/runs/dev_quality60/phase3_sdk_20261008_1833/`。本地 `receipt-phase3-20261008T183218.json` SHA `711442cf7b5054713f0de3f53a5f79448c70e589889fee7574f6b8d3ff7df65f`；先前16PASS回执保留。

准确回执 `receipt-20261008T180552.json`，SHA256 `fd008f888f1b2c30112e8565cc6bf3d15a88462c60ba35a089eec3976d2b8c17`；日志 `pytest-20261008T180552.log`。

重跑目标服务器 CPU 验证：

```bash
cd /data2/FreeToken/evaluation/quality60
CUDA_VISIBLE_DEVICES= PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
FT_QUALITY60_FROZEN_ROUNDS=/data2/_shared/runs/ft_rounds \
/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python -m pytest \
  -q -p no:cacheprovider test_sdk_capture.py test_phase3_sdk.py test_frozen_replay.py
```

lm-eval 0.4.13 的聊天适配器仅将正文传给评分器，丢弃 finish_reason/reasoning_content/usage，因此不接管此 canonical quality60。它在独立工具环境中用于适合文本结果的其他基准。
