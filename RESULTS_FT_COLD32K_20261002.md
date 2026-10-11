# 测量结果：FreeToken 冷 32K 首 token（20261002）

任务：`TEST_TASK_FT_COLD32K_TTFT_20261002.md`。只做了这一件事，未重测 ExLlama，未扫参数，未动四张卡方案。

## 结论（一句话）

**FreeToken 冷 32K 首 token 21.5 秒（两轮 21.32 / 21.52，取慢轮），明显短于 ExLlama 的 48.7 秒（约为其 44%）；解码 37.13 / 37.91 tok/s（均值 37.52）。按任务判据：生产锁定 FreeToken，ExLlama 归档，不做 ExLlama 预填实验。**

## 判据对照

- 判据一（命中）：首 token 明显短于 48.7 秒 → 生产锁定 FreeToken，ExLlama 归档，任务结束。
- ExLlama 未做任何改动（未重启、未改 `-mct` / `-ndt` / `-mcs`）。

## 两轮 JSON

存放于 `172.16.108.9:/data2/FreeToken/runs/cold32k_20261002/`：

```json
{
  "cold_id": "ft-cold-a2",
  "prompt_tokens": 32064,
  "cached_tokens": 0,
  "completion_tokens": 127,
  "ttft_s": 21.32,
  "decode_tps": 37.13,
  "finish_reason": "length"
}
```

```json
{
  "cold_id": "ft-cold-b2",
  "prompt_tokens": 32064,
  "cached_tokens": 0,
  "completion_tokens": 127,
  "ttft_s": 21.519,
  "decode_tps": 37.91,
  "finish_reason": "length"
}
```

面板提交值：首 token 取较慢轮 **21.52**，解码取两轮平均 **37.52**（口径见下）。

## 面板记录

已通过 `POST http://127.0.0.1:8098/api/benchmarks/record` 写入并回读确认（Qwen3.8-Flash-Next-NVFP4 / ft 格，tested_at 2026-10-02 15:01:02）：`status=PASS, decode_tps=37.52, ttft_s=21.52`，notes 含两轮原始值、口径、历史 35.10、ExLlama 对比与锁定结论。任务模板中 `status` 原为占位 "TESTING"；因结果命中判据一锁定分支，按面板既有惯例（Qwen3.8 ft/kt 验证通过即 PASS）提交 PASS——如需改回 TESTING，重发一次该接口即可覆盖。

## 一个口径偏差（必须知道）

服务端 chat 模板默认开启思考模式（`default_reasoning_effort=xhigh`）。首轮 `ft-cold-a`（思考开启）把 128 token 预算全部耗在 `reasoning_content` 上，正文 content 事件为 0，按任务口径（首 token = 第一条带正文的 content 事件）该轮无法成立，判废，已存档为 `ft-cold-a.thinking-on-invalid.json`。按任务"作废换新 id 重测"规则，有效两轮改用新前缀 id（`ft-cold-a2` / `ft-cold-b2`）并在请求中加 `"chat_template_kwargs": {"enable_thinking": false}`，其余与任务规定完全一致（temperature=0、max_tokens=128、同 `build_text`、流式口径）。关闭思考后 reasoning 事件为 0，TTFT ≈ 纯预填 + 首个生成步，与 ExLlama 48.7 秒（服务端 `time_prefill`，同样不含思考阶段）同台可比。

补充：首轮判废前那次（思考开启、真冷权重）整体 wall 42.07s（含 127 个思考 token 生成约 3.6s），即便按最不利估计，冷态首 token 也在 48.7 秒以内——结论对该偏差不敏感。

## 口径备注

- 提示构造与 `exllamav3/scripts/probe_32k_once.py` 的 `build_text` 逐行一致（唯一头 + 重复验收记录 + 固定尾，按 token id 截断），目标 32052 token，分词器取服务端 overlay 模型。服务端返回 `prompt_tokens=32064`（模板开销 +12），达标。
- 两轮 `cached_tokens=0`（换前缀，无前缀命中），`finish_reason=length`。
- 输出为 127 token（非 128）。按任务规定注明：解码数字不直接与 ExLlama 128 token 的 30.24/30.41 比高低；且本任务解码口径为 `(n-1)/(t_last-t_first)` 流式口径，与 ExLlama 的 `n/generate_s` 及历史 35.10 不同源。数字放在一起看：**37.13 / 37.91** vs 35.10 vs 30.24/30.41。
- PLE 保持 `pinned`（服务启动即钉住 47.7G PLE 表 + 73.4G 专家权重），"冷"仅指前缀缓存为 0。

## 实际启动命令

与任务文件给定命令逐字一致，日志：`/data2/FreeToken/runs/cold32k_20261002/serve.log`，命令存档：同目录 `SERVE_CMD.txt`。

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

启动前停掉了占用 8095 的遗留 ExLlama 实例（pid 140665，结果已在 `exllamav3/RESULTS_20261002.md` 与 `/data2/exllamav3/runs/tune_20261002/RESULTS.md` 归档，未重启）。加载完成后 `curl /v1/models` 返回 `Qwen3.8-Flash-Next-NVFP4`，`max_model_len=49152`。

测后 FreeToken 服务仍运行在 8095（pid 409043），如需释放：`ssh 172.16.108.9 "kill 409043"`。

## 测量脚本

`freetoken/scripts/probe_ft_cold32k.py`（已同步到远端 `/data2/FreeToken/scripts/`）。用法：`python scripts/probe_ft_cold32k.py <cold_id> [target=32052] [max_tokens=128] [nothink]`。
