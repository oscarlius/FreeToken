# 测试任务：FreeToken 冷 32K 首 token

只做这一件事。不要重测 ExLlama，不要扫新参数，不要动四张卡方案。

## 要回答的问题

ExLlamaV3 冷 32K（32052 token 进、128 token 出）首 token **48.7 秒**，解码 **30.24 / 30.41 tok/s**。FreeToken 在 33202 token 上的解码是 **35.10 tok/s**，但那次没有同一口径的冷首 token。

测出 FreeToken 在同样冷提示上的首 token 秒数，以及 128 token 的解码速度。

## 判据

- 首 token **明显短于 48.7 秒**：生产锁定 FreeToken，ExLlama 归档。任务结束。
- 首 token 也在几十秒：把秒数写进报告后停止。不要当场改 ExLlama。是否做一次 ExLlama 预填实验，等结论回来再定。那次实验的解码必须仍然 ≥30 tok/s。

解码数字一并记下，用来和 35.10、30.3 放在一起。本任务不以「解码超过 35.10」为通过条件。

## 环境

- 机器：`172.16.108.9`
- 只占用 **8095**。测前确认没有别的推理服务占这个端口。ExLlama 的结果已经在 `exllamav3/RESULTS_20261002.md` 和 `/data2/exllamav3/runs/tune_20261002/RESULTS.md`，不要为了再确认 30.3 而重启它。
- Python：`/data2/FreeToken/venv`。不要用 ExLlama 或 KTransformers 的 venv。
- 模型：`/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay`（没有该目录时用 `/data2/model/Qwen3.8-Flash-Next-NVFP4`）。权重只软链接，不复制。
- 不停 ollama。不要绑死核 0 和 2。

## 启动

与产出 **35.10 tok/s** 的那次命令相同，只保证窗口装得下 32052+128。仓库里的 `freetoken/scripts/launch_qwen38_test.sh` 把 `--max-seq-len-override` 和 `--kv-reserve-tokens` 写成了 32768，**不能原样用于本任务**。找不到当时的 49152 命令时，用下面这一条：

```bash
export PATH=/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export VIRTUAL_ENV=/data2/FreeToken/venv
export PYTHONUNBUFFERED=1

numactl --cpunodebind=0,1 --interleave=all \
  /data2/FreeToken/venv/bin/ft serve \
  --model-path /data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay \
  --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 0.0.0.0 \
  --port 8095 \
  --memory-ratio 0.88 \
  --moe-cache-auto \
  --moe-prefill-hit-d2d \
  --ple-backend pinned \
  --moe-strategy offload \
  --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 \
  --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 49152 \
  --max-seq-len-override 49152 \
  --max-prefill-length 4096 \
  --enable-cache-report \
  --enable-special-token-ckpt \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3
```

`--ple-backend` 保持 `pinned`。不要改成 disk。不要开更低比特。加载完成后 `curl -s http://127.0.0.1:8095/v1/models` 必须返回该模型名。把完整命令和日志路径写进结果。

## 提示

文本构造沿用 `exllamav3/scripts/probe_32k_once.py` 的 `build_text`：唯一头 `Cold-prefix-<id>`，重复同一段验收记录，目标长度 **32052** token。分词器与服务端模型一致。不要用 `_shared/speed_probe.py` 的按字符截断。

两轮，id 分别为 `ft-cold-a`、`ft-cold-b`。每轮 `temperature=0`，`max_tokens=128`。两轮提示除了 `Cold-prefix` 头以外相同。不要把第二轮接在第一轮前缀后面。

## 计时

走流式 `POST /v1/chat/completions`，`stream=true`，`stream_options.include_usage=true`。

- **首 token**：从发出请求到第一条带正文的 content 事件。不要用 HTTP 响应头的时间。
- **解码**：`(输出 token 数 - 1) / (最后一条正文事件时刻 - 第一条正文事件时刻)`。输出不足 2 个 token 则解码记为空，本轮作废。
- 服务端若返回 `usage.prompt_tokens_details.cached_tokens`，必须为 **0**。大于 0 的轮次作废，换一个新的 `Cold-prefix` id 重测。
- `prompt_tokens` 应在 32052 附近。差出几千 token，说明窗口被截断或前缀命中，本轮作废。
- 输出不足 128 token 时，解码可以留下，但注明 `finish_reason`，不要拿来和 128 token 的 30.3 比高低。

每轮把 JSON 存到 `/data2/FreeToken/runs/cold32k_20261002/`：

```json
{
  "cold_id": "ft-cold-a",
  "prompt_tokens": 0,
  "cached_tokens": 0,
  "completion_tokens": 0,
  "ttft_s": 0,
  "decode_tps": 0,
  "finish_reason": "length"
}
```

## 交付

在 `freetoken/` 写一份短报告，包含：实际启动命令、两轮 JSON、以及一句话结论（首 token 是多少秒，相对 48.7 秒是短还是同样处于几十秒）。

并用接口写进面板（同一模型加框架只有一格，备注里保留原来的 35.10）：

```bash
curl -sS -X POST http://127.0.0.1:8098/api/benchmarks/record \
  -H 'Content-Type: application/json' \
  -d '{"model_id":"Qwen3.8-Flash-Next-NVFP4","framework":"ft","status":"TESTING","decode_tps":0,"ttft_s":0,"concurrency":"1","author":"task","source":"http_post","notes":"冷32K ft-cold-a/b。首token秒数写在这里。解码口径 (n-1)/(t_last-t_first)。历史 33202 token 解码 35.10。ExLlama 冷32052 首token 48.7s，解码 30.24/30.41。"}'
```

`decode_tps` 和 `ttft_s` 填两轮里有效的那一轮；两轮都有效时，首 token 取较慢的一轮，解码取两轮平均，并在 notes 里写明两轮原始值。

## 不要做

- 不要重跑 ExLlama，不要改 `-mct` / `-ndt` / `-mcs`。
- 不要测 GLM，不要测并发 C2/C4，不要跑 `ft bench bw`。
- 不要换量化，不要把 PLE 改成 disk。
- 不要为了首 token 去调 `--max-prefill-length`。4096 保持不动，本任务只测量。
