# D15 W98K/W128K window A/B package

`window_runner.py --prepare` is CPU-only and default-inert. `--run --approval` is Linux-only and requires a root-sealed approval binding the kept formal T16 record, terminal T17/R067e formal rounds and manifests, the exact prepared packet, and runtime source/native pins. No production service or model weights are changed.

Exactly two task-owned services run sequentially: W98K A1–A8, then W128K A1–A8 plus B9–B12 (at most four continuation rounds) and one cold request. The first native token ID difference stops the round and suppresses B/cold. B9 must render 100,223 canonical input tokens; later continuation reaching the capacity limit stops before dispatch and records the boundary. Cold is approximately 126 Ki tokens with max_tokens=256; canonical frontend, Worker and API inputs must agree and cached_tokens must be zero.

Both services use the authoritative 481 production recipe with D0 off, private loopback/API/master ports, window-only geometry changes, and the same native-token/async stream observer. W98K must resolve 2,700 slots. W128K actual slots come from the unique engine auto-cache log, not the expected 2,401 value.

Timing uses the network monotonic dispatch/first-output/terminal receipts. The pooled eight-round decode rate is sum(completion_tokens−1)/sum(first-output-to-terminal interval). Prefill receipts use asynchronous CUDA events spanning Engine.forward_batch, including sampling/copy enqueue and CPU waits; this is not a sum of kernel times or TTFT. Each request records uptime, R-thread count, total duration, decode fraction and telemetry memory headroom. `window_runtime.py` samples raw GPU memory and host environment nominally at 1Hz.

The measurement deadline is 1,800 seconds; owned service termination and verified idle checks have a bounded cleanup allowance. Cleanup checks the owned process group, both API/master ports, and GPU idle. An unsafe cleanup or surviving stream thread preserves the owner lock and writes evidence; a safely cleaned product or harness failure can release the lock. OOM preserves original serve-log hashes and the original exception. No automatic GPU retries are added.

`ROOT_PREREGISTRATION.md` defines the user-approved 4% prediction and 6%/12% decision bands. All comparisons with batches before ollama stopped at 20:35:15 are labelled 环境不同. CPU tests exercise the actual frozen v9 input/native-token binding, immediate equality failure, two-service budget, master-port rejection, unsafe start/cleanup and a stream that remains active at the deadline. `source_bundle/` reuses frozen ordinary client helpers; `test_binding_fixtures.py` copies receipt fixture builders from the existing ordinary-client CPU tests and does not authorize runtime effects.

## 剩余服务接续

2026-10-10T22:25:26.782393+08:00：`window_resume.py` 仅启动尚未运行的W128K，逐字复用只读封存的W98K八轮计时与原生token证据。独审与root新准入必须绑定全原始hash清单、source、既有生产配方、剩余一次服务、累计21调用和原22:41:56绝对测量上限。原failed_harness载体保持原判；清理异常先记详情，再以服务组、API/master端口与GPU空闲证明恢复。没有独审和新准入不运行。
