Long offloaded prefills revisit the decoder stack for every token chunk, streaming the same expert layers repeatedly. This adds **`--prefill-layer-major`**, disabled by default: each decoder layer processes all internal chunks before the next layer starts, allowing streamed experts to be reused. In the bounded 32K comparison below, first-text latency fell from 21.913 s to 11.030 s with the same quantized kernel.

### Scope and state handling

- Qwen3.8/Qwen4Exp, TP=1, NVFP4 experts, GPU `offload`, **pinned PLE**, one pending text request, and new-token length greater than the existing prefill budget and at most 32,768. Unsupported configurations retain ordinary chunked execution, including the default disk PLE backend.
- `--max-prefill-length` remains the internal chunk size. The outer request owns checkpoint planning; internal chunks preserve absolute cached positions and project that plan. Conv, recurrent and PLE state advance in chunk order within each layer; the outer batch context is restored on success and exceptions.
- An eligible long prefill occupies one scheduling turn. This does not interleave other requests' decoding between internal chunks. The 32K cap bounds retained activations, but does not guarantee every configuration fits every GPU.

Related problem: #579. The loop ordering is informed by [Layered Prefill](https://arxiv.org/abs/2510.08055); this does not implement its full stall-free scheduler. #578's kernel optimization and #577's host checkpoint bank are separate contributions and are not included.

### Target-model comparison

Tested candidate: `63858faa584ddd623d5ea1728e26270e0c7f649b`; frozen upstream baseline: `9c635a157798da4aa43e6d051e92620521ed1858`. Three services ran sequentially: baseline, candidate flag off, candidate flag on. All used the same environment, model files, synthetic prompts, 4K internal chunks, 2,700 expert slots, pinned PLE and upstream Triton NVFP4 kernel. Client concurrency was 1.

| Arm | Median cold first-text latency | Median full-response time | Median output tokens / full-response second |
| --- | ---: | ---: | ---: |
| Frozen main | 21.913 s | 27.604 s | 4.64 |
| Candidate, flag off | 21.617 s | 27.308 s | 4.69 |
| Candidate, flag on | 11.030 s | 16.719 s | 7.66 |

Each median contains **two scored 32,012-token cold requests**, each generating 128 tokens. First-text latency is measured from immediately before HTTP to the first nonempty completion-text SSE event. The last column includes prefill and is **not steady-state decode throughput**. Baseline-to-enabled latency reduction is 49.67% (1.987x latency ratio). These synthetic samples establish a bounded result, not a statistical confidence estimate or a general workload claim. H2D bytes and peak VRAM were not measured.

Nine generation calls ran per arm: two unscored 512-token warmups, one short functional check, then three cold/continuation pairs. The first long pair warmed up long-shape JIT and was excluded from performance scoring in advance. The remaining two cold requests supplied the table. Every request used `temperature=0`, `max_tokens=128`, `ignore_eos=true`, and ended with `length`.

All nine corresponding **native 128-token ID sequences** matched across the three arms, including flag off against baseline. Cold requests admitted zero cached tokens. Each 32,077-token continuation reused 32,000 tokens and prefetched the remaining 77. IDs and cache counts were observed at the scheduler's existing CPU reply seam, without adding GPU synchronization. Logs confirmed enabled cold prefills used a single 32,012-token outer prefill; baseline/off used seven 4,096-token chunks plus a 3,340-token tail. This is limited target-model coverage, not an exhaustive equivalence, cancellation or concurrent-serving gate.

**Run lifecycle caveat:** all three timed arms and all 27 requests completed before a post-run GPU-idle cleanup check recorded `failed_harness`. That terminal status is retained. A subsequent read-only check found the GPU idle; production was restored and two official-SDK smoke requests passed against its frozen reference, without measurement reruns. The table reports completed timed arms, not a claim that the entire control harness passed. Independent review found no remaining blocker in those measured-arm results.

Upstream subsequently merged #670 and #685; submission-time main is `f02fbb16a213f5c81094e4017c988d41f0164141`. Git's merge-tree check is clean. This branch preserves the exact tested commit; the merged result with those two newer CPU/hybrid changes has not been GPU-tested.

### Environment and reproduction

- One RTX 4090 (24 GiB), driver 580.178.04; two Xeon Silver 4310 CPUs; Ubuntu 22.04.5.
- Python 3.10.12, Torch 2.14.1+cu130, CUDA 13.0 build tools, flashlib 0.4.0, Transformers 5.16.1, Triton 3.8.0. Dependencies and all three native extensions were installed/built in a separate environment; `uv pip check` and native imports passed.
- Existing [nvidia/Qwen3.8-Flash-Next-NVFP4 checkpoint at fc694b5](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4/tree/fc694b54fb0174e0913e6adf86691ef85a4ead47), with the local FreeToken `qwen4_exp` configuration. No MTP enabled. The same files were used for all arms.

Use the same dependency-conformant environment and native build for both worktrees. Measured serve arguments follow; `TREE` selects the frozen baseline or candidate source. Add `--prefill-layer-major` only for the enabled candidate. CPU affinity is specific to this host.

```sh
CUDA_VISIBLE_DEVICES=0 MASTER_PORT=8096 PYTHONPATH="$TREE/python" \
taskset -c 1,3-47 "$VENV/bin/python" -m freetoken.cli serve \
  --model-path "$MODEL_PATH" --served-model-name Qwen3.8-Flash-Next-NVFP4 \
  --host 127.0.0.1 --port 8095 --memory-ratio 0.88 \
  --moe-cache-auto --moe-prefill-hit-d2d --ple-backend pinned \
  --moe-strategy offload --quant-backend moe.nvfp4=triton \
  --max-running-requests 2 --cuda-graph-max-bs 2 \
  --kv-reserve-tokens 98304 --max-seq-len-override 98304 \
  --max-prefill-length 4096 --enable-cache-report
```

<details>
<summary>Exact synthetic prompt construction and request/timing protocol</summary>

Generate text using the same checkpoint tokenizer; no chat template is applied:

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

def exact(text, length):
    ids = tokenizer.encode(text, add_special_tokens=False)[:length]
    assert len(ids) == length
    text = tokenizer.decode(ids, skip_special_tokens=False,
                            clean_up_tokenization_spaces=False)
    assert tokenizer.encode(text, add_special_tokens=False) == ids
    return text

short = exact("Arithmetic exercises: add two small integers and explain the answer.\n" * 100, 512)
paragraphs = [
    "Astronomy records describe distant stars, spectral lines, orbital periods and careful observations.\n",
    "Botanical notes describe leaves, roots, flowering seasons, soil moisture and seed dispersal.\n",
    "Cartography exercises describe rivers, mountain contours, compass bearings and geographic coordinates.\n",
]
pairs = []
for paragraph in paragraphs:
    continuation = exact(paragraph * 3500, 32077)
    cold = exact(continuation, 32012)
    assert continuation.startswith(cold)
    pairs.append((cold, continuation))
```

On a fresh service, send `short` three times, then each `(cold, continuation)` pair in order, sequentially. Score only the botanical and cartography cold requests. POST `/v1/completions` using this payload for each text:

```json
{
  "model": "Qwen3.8-Flash-Next-NVFP4",
  "prompt": "<text>",
  "temperature": 0,
  "max_tokens": 128,
  "ignore_eos": true,
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

Use a monotonic clock immediately before HTTP; save SSE through its end. Record the first nonempty `choices[].text` event and full-response duration. Require `[DONE]`, `finish_reason=length`, and `usage.completion_tokens=128`; verify prompt counts and cache reuse. Compare corresponding native token IDs in addition to API text. The measurement client used Python's `urllib.request` on the same host. A separate read-only observer captured IDs from `DetokenizeMsg` and counts from `PromptAdmittedMsg`; that experiment instrumentation is not part of this runtime patch.

</details>

### CPU validation

On the exact candidate in the isolated Linux environment, with CUDA hidden: **50 passed** (pytest 9.1.1):

```sh
CUDA_VISIBLE_DEVICES='' python -m pytest -q \
  tests/engine/test_layer_major_tracks.py \
  tests/scheduler/test_scheduler_chunked_prefill.py \
  tests/scheduler/test_cost_accounting_core.py \
  tests/scheduler/test_abort_inflight_prefill.py
```

Coverage includes default-off and unsupported-mode fallback (including disk/missing PLE configuration), the 32K eligibility boundary, absolute cached offsets, outer checkpoint projection, incoming conv/recurrent/PLE state, one prefill-cache initialization, and context restoration after exceptions. CLI help and the three freshly built native extension imports also passed. Source and measurement evidence received independent review.
