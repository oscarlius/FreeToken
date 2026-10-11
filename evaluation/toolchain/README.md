# FreeToken evaluation toolchain

This directory owns standalone validation clients for later FreeToken acceptance. It does not alter `/data2/FreeToken/venv`, start a model server, acquire GPU resources, download weights/datasets, or replace existing collection/verdict tooling.

## Installed environments

2026-10-09 append-only update: `anthropic==0.125.0` was installed in `venv-eval` for the official public-route restart CPU regression. The resolved package set is in `freeze-20261008T173559Z.txt` (SHA-256 `f8f5e60da4d931b95a90df76b19ed4525a2f54b811125934c476d3bd3581ed10`). Dependency checks passed; the model venv was not changed by this installation. The eight loopback SDK tests cover OpenAI chat/completions/responses and Anthropic messages, each streaming and non-streaming, on candidate `481d3a7`; they prove restart admission and epoch completion with a CPU fake backend, not GPU recovery.

`venv-aiperf` contains `aiperf==0.11.0`, the newest AIPerf wheel currently published on PyPI for the deployment host. `venv-eval` contains `openai==2.54.0`, `pytest==9.1.1`, and `lm-eval==0.4.13`. Exact transitive resolutions are saved after installation as `venv-*.freeze.txt`.

On the remote host, after synchronizing this directory into `/data2/FreeToken/evaluation/toolchain`, run:

```bash
cd /data2/FreeToken/evaluation/toolchain
./bootstrap_remote.sh
./verify_remote.sh
```

The verification writes a timestamped receipt with source SHA-256 values and command output. It checks dependency consistency, the AIPerf and lm-eval CLIs, package versions, and an owned loopback OpenAI JSON/SSE fixture. The fixture constructs the client with `max_retries=0` and `timeout=5.0`; it is protocol-only evidence and is shut down by the test.

After the first successful install, `venv-*.freeze.txt` is the exact transitive lock receipt. To reconcile either environment to that recorded set, run `./bootstrap_remote.sh --locked`; the installer refuses this mode if the receipt is absent. The default mode refreshes the pinned direct requirements and rewrites the receipts.

AIPerf 0.11.0 contains the `aiperf validate` CLI but does not ship the later `aiperf-mock-server` executable. `verify_remote.sh` therefore runs a two-request `aiperf profile` smoke against this directory's owned loopback streaming fixture, with the built-in tokenizer, empty GPU visibility, offline HuggingFace variables, disabled proxy inheritance, and disabled GPU/server metrics. Each run permanently retains official AIPerf artifacts, stdout, stderr, and `receipt.json` under `smoke-runs/<unique-run-id>/`; `aiperf-smoke-latest.json` points to the latest receipt. The prior top-level `aiperf-smoke-receipt.json` remains a first-round hash summary whose raw artifacts were temporary and are unavailable. These are CLI/protocol evidence, never model performance evidence.

## Metric and scope boundary

AIPerf 0.11.0 includes `time_to_first_output_token` (TTFO): its source defines it as the first non-reasoning output token. TTFT is the first token of either reasoning or final content. Record both fields in any later acceptance report; do not rename TTFO to TTFT.

`lm-eval` is installed only as an independent text-benchmark tool. It does **not** own or replace the canonical quality-60 grader. It is also not approved for FreeToken multiple-choice/local-completions scoring: that adapter needs completion `logprobs` and `echo`, while the current FreeToken OpenAI API rejects both. The current permitted quality route remains generation-only quality-60 with per-item semantic-equivalence review, without changing scoring thresholds. This deployment neither proves target-model generation nor model-server compatibility.

Locust and Toxiproxy are deliberately absent. They remain optional, separately approved tools for later load/network-fault work.
