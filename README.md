<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/FlashML-org/FreeToken/main/assets/freetoken-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/FlashML-org/FreeToken/main/assets/freetoken-logo-light.svg">
    <img alt="FreeToken" src="https://raw.githubusercontent.com/FlashML-org/FreeToken/main/assets/freetoken-logo.svg" width=65%>
  </picture>
</div>

<p align="center">
| <a href="https://www.flashml.ai/"><b>Download</b></a> | <a href="https://arxiv.org/abs/2608.16157"><b>Paper</b></a> | <a href="https://join.slack.com/t/flashml/shared_invite/zt-3zpdh5j10-9dwTXrgLiqpVxizhA9KVbA"><b>Developer Slack</b></a> | <a href="https://discord.gg/MsA277cJzZ"><b>Community Discord</b></a> | <a href="https://github.com/FlashML-org/FreeToken/issues/482"><b>Community WeChat</b></a> |
</p>


Unlock datacenter-class intelligence on the hardware you already own — Run 290B+ frontier MoE models locally on your gaming PC at blistering interactive speeds.

## About

FreeToken is an edge-native Mixture-of-Experts (MoE) serving engine designed for running frontier-scale open-weight models on personal and consumer hardware. It treats heterogeneous edge resources—GPUs, CPUs, host memory, and interconnects—as a unified, elastic inference platform. Its core features include:  

- **Fast Edge-Native Runtime**: Provides efficient MoE serving with bandwidth-adaptive CPU–GPU co-execution ($q^\star$ policy), full-layer double-buffered prefill streaming, global LRU expert caching, graph-compatible execution, and the FTW fast weight format.  
- **Semantic-Aware Caching**: Features semantic anchor checkpoints for recurrent state and KV caches, allowing agentic context edits (e.g., tool calls, thinking blocks) to avoid redundant context recomputation.  
- **Elastic Memory Management**: Supports dynamic, runtime VRAM re-allocation between expert caches and KV memory without engine restarts or weight reloading.  
- **Broad MoE & Ecosystem Support**: Supports frontier open-weight MoE models (e.g., DeepSeek-V4-Flash, Qwen3.6-35B-A3B, GLM-5.2) across various parameter scales and quantization formats (e.g., MXFP4, NVFP4, FP8, BF16), with Anthropic/OpenAI-compatible APIs for seamless integration with real-world coding and tool-calling agents (e.g., Codex, Claude Code, OpenCode, OpenClaw, DeepSeek Harness). 
- **Diverse Consumer Hardware**: Scales across consumer laptops, gaming desktops, and workstation GPUs, with native support for NVIDIA RTX 30, RTX 40, and RTX 50 series GPUs.  

## Getting Started

### Desktop app

Download FreeToken for Windows or Linux at [flashml.ai](https://www.flashml.ai/). It sets the engine up for you and gives you a GUI for running models, chatting, and tuning the engine.

<div align="center">
  <img alt="FreeToken Desktop" src="https://raw.githubusercontent.com/FlashML-org/FreeToken/main/assets/desktop-console.png" width=92%>
</div>

### CLI

Install FreeToken with [uv](https://docs.astral.sh/uv/) (recommended) or pip:

```bash
uv pip install "freetoken[accel]"
```

Or build from source:

```bash
git clone https://github.com/FlashML-org/FreeToken.git && cd FreeToken
uv venv && source .venv/bin/activate
uv pip install -e ".[accel]"
```

For More details:

- [Install FreeToken](https://github.com/FlashML-org/FreeToken/blob/main/docs/install.md)
- [Quick start](https://github.com/FlashML-org/FreeToken/blob/main/docs/quickstart.md)
- [Supported models](https://github.com/FlashML-org/FreeToken/blob/main/docs/models.md)
- [CLI reference](https://github.com/FlashML-org/FreeToken/blob/main/docs/cli.md)
- [Repairing old FTW checkpoints](https://github.com/FlashML-org/FreeToken/blob/main/docs/ftw-hotfix.md)

## Development route tracing

Set `FT_DEV_ROUTE_TRACE=/path/to/routes` before server startup to export one JSON/NPZ
pair per real MoE forward. The NPZ stores raw expert ids before cache-slot rewriting,
with shape `[layer, token, 10]` and dtype `int16`. The JSON names actual MoE layer ids
and each request's unpadded token layout. Default execution creates no collector,
buffer or writer. Trace mode disables CUDA graphs and layer-major prefill, and logs
these changes; its timings are not performance measurements. Enabled/disabled text
equivalence still requires the D07 GPU gate.

Enable the server's sampled-token ACK stream with `FT_DEV_PAUSE_ENDPOINT=1`, then
collect client evidence explicitly:

```bash
python scripts/agent_trace.py --route-evidence generate --rounds 12 --max-tokens 2048 --out trace.json
python scripts/multisession_probe.py two-decode --ctx 8000 --max-tokens 256 --same-prompt 0 --reps 1 --out two_decode.json
python scripts/route_analyze.py ROUTES --traces trace.json --serve-log serve.log --two-decode two_decode.json --out summary.json
```

Use the scripts in the declared candidate worktree; do not replace shared tools used
by historical rounds. Client route evidence is independent of server environment
inheritance and preserves all ACK sequence entries, including zero-token entries.
No ACKs, changed UID/counters, failed requests or completions beyond the actual wire
budget are rejected. Dry-run output cannot substitute for engine measurements.

The analyzer joins complete prefill chunks by UID, checks per-request log totals,
and reports suffix/output distributions, empirical per-layer expert coverage and
its unconditional bounds. Only the declared, distinct-content two-decode UID pairs
and token sidecars enter `R_B = 20 / |expert union|`; absent pair evidence is pending,
and an undeclared B=2 pair is an error. Raw route data includes readiness requests;
business distributions use only the provided trace UIDs. Export size before
compression is 20 bytes per token per MoE layer: 48 layers use 960 bytes/token,
or 96 MB per 100,000 tokens.

## Citation

If you use FreeToken for your research, please cite our [paper](https://arxiv.org/abs/2608.16157):

```bibtex
@article{yang2026freetoken,
  title={FreeToken: Efficient Edge-Native MoE Serving with Bandwidth-Adaptive Execution},
  author={Yang, Shuo and Fan, Xiaoze and Pan, Melissa and Xi, Haocheng and Wang, Zhe and Sun, Shanlin and Keutzer, Kurt and Han, Song and Zaharia, Matei and Xu, Chenfeng and Stoica, Ion},
  journal={arXiv preprint arXiv:2608.16157},
  year={2026}
}
```

## Acknowledgment

FreeToken was deeply inspired by [mini-sglang](https://github.com/sgl-project/mini-sglang), and
learned the design and reused code from the following projects:
[SGLang](https://github.com/sgl-project/sglang),
[vLLM](https://github.com/vllm-project/vllm),
[FlashInfer](https://github.com/flashinfer-ai/flashinfer),
[flash-linear-attention](https://github.com/fla-org/flash-linear-attention),
[LightLLM](https://github.com/ModelTC/lightllm) and [llama.cpp](https://github.com/ggml-org/llama.cpp).

## Layer-major prefix checkpoints

Layer-major prefill projects the scheduler's single checkpoint plan onto one
internal chunk and preserves absolute cached-prefix positions. A boundary at a
chunk start freezes incoming GDN and PLE state per layer before that chunk runs.
CPU contracts are in `tests/engine/test_layer_major_tracks.py`; real-model
prefix-hit continuation requires the separate T16/T17 gates.

## License

[Apache License 2.0](https://github.com/FlashML-org/FreeToken/blob/main/LICENSE).


### Development multisession probe

`scripts/multisession_probe.py` provides the D06 `two-decode`, `stall`,
`pair-short`, and `h1` measurement commands. Run `--help` for the unchanged
task-card interfaces. Requests require the opt-in sampled-token acknowledgement
stream (`FT_DEV_PAUSE_ENDPOINT=1`); this flag also enables the development-only
`POST /dev/pause` endpoint and stays unset for the default-path T16 gate.

The probe targets the selected Qwen checkpoint's standard chat-template frontend,
renders with `enable_thinking=False`, and proves actual input IDs. Tokenizers
selecting the DSV4 encoder are rejected. Configure `FT_DEV_D0_PATH` for UID-bound
D02 records; H1 additionally requires `FT_DEV_D0_TIMELINE=1` and sufficient
`FT_DEV_D0_TIMELINE_STEPS` coverage (the T05 suite uses an explicit 20000-step cap).

H1 first measures each real prefill interval, then pauses for that same duration.
Its event-period counters and post-event H-step timing are distinct. Request
failures cancel owned peers and return nonzero with an exclusive error artifact;
missing evidence is never replaced with a fabricated zero.

## D16 opt-in service sampler capture

`equiv_suite.service_capture.install_from_env(engine)` is a launcher-only, disabled-by-default adapter.  With no `FT_D16_SERVICE_CAPTURE_DIR`, it returns `None` and does not alter the engine.  An opt-in launcher supplies an explicit JSON list of `{uid, generation_index, logical_label}` records and positive capture budgets through `FT_D16_SERVICE_CAPTURE_EXPECTED_JSON`, `FT_D16_SERVICE_CAPTURE_MAX_CAPTURES`, and `FT_D16_SERVICE_CAPTURE_MAX_BYTES`; `FT_D16_EXECUTION_ID` remains required by the sampler's self-derived process identity.

Immediately before the actual scheduler receives a `UserMsg`, the launcher writes an exclusive admission receipt containing real UID, CPU int32 IDs and hash, normalized sampling-fields hash, self-derived process identity, and a monotonic admission sequence.  The physical event identity derives from those receipt fields; the configuration label never supplies it.  It observes each successfully issued `DetokenizeMsg`, including `finished`, and seals only after the entire declared multi-query run drains.  The adapter observes the existing sampler only; it neither projects logits nor samples tokens.  `service_delivery.json` records a physical sample following the same UID's delivered terminal generation as `un_delivered_samples`; it is never output proof.  Missing, duplicate, mismatched, or pre-terminal extra deliveries fail closed.

For the actual scheduler path, run the independent launcher with `PYTHONPATH=python:scripts python scripts/equiv_suite/service_capture_startup.py ...`.  When enabled, it constructs the upstream Scheduler, attaches the sampler after construction, wraps only that instance's `_process_one_msg`, `send_result`, `_schedule_next_batch`, and `shutdown`, and records the real `UserMsg` and successfully issued `DetokenizeMsg` calls.  The batch wrapper observes only the already prepared native return: its phase, physical requests and CUDA-graph padded rows, UID/input-ID hash/table and linear slots, active table rows, and sequence. It is diagnostic (`admitted:false`) and never supplies scheduling input. The same explicit capture count/byte budgets bound retained batch receipts; exhaustion retains one indeterminate error while native later returns remain unchanged. CUDA graph padding is reported separately as padded rows and never treated as a user request. The capture directory must sit below `dev_D16`; the expected-query JSON provides only a logical label for each actual UID.  It seals only at shutdown/EOF, so a donor delivery cannot finalize a later hit/query.  With the capture directory environment unset, the entry delegates to the ordinary launcher without installing any wrapper. The observer records a real phase sequence for later D16 analysis, but it neither creates mixed decode/prefill forwards nor implements a per-request parking/resume protocol.
