# R045 AIPerf / 481d3a7 CPU planning packet v1

This is a CPU-only, static planning packet for a replacement R045 proposal. It
does not start a service, contact an endpoint, acquire GPU resources, reserve a
batch, or authorize a benchmark. The old `r045_section14_draft_v18` evidence
remains the separate pre-reservation block record and is deliberately untouched.

## Frozen proposal, pending a new authorization

| item | frozen value |
| --- | --- |
| candidate | `481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9` |
| tool | NVIDIA AIPerf `0.11.0`, isolated at `/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf` |
| services | 2 fresh, owned service lifecycles, strictly serial (`S1`, then `S2`) |
| AIPerf profile per service | 1 |
| generation requests | 2 concurrent streaming requests per service, 4 total |
| AIPerf readiness requests | 0 (`--wait-for-model-timeout 0`) |
| input | two ordered `single_turn` JSONL records, `output_length=128`, `temperature=0`, `top_p=1`, `ignore_eos=false` |
| endpoint / model identity | deliberately absent until the deployed service receipt is bound by root |

`--concurrency 2` without `--request-rate` is AIPerf's burst concurrency mode.
`--request-count 2` sets the exact two generation requests in each service
profile. This is a proposed ceiling, not a permission to run it.

The planned command below is only reviewable text. `ADMITTED_URL`, `MODEL`, and
the owned service lifecycle are supplied after deployment and admission; the
command must not be executed from this packet.

```bash
export CUDA_VISIBLE_DEVICES=""
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
AIPERF=/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf
"$AIPERF" profile \
  --model "$MODEL_FROM_DEPLOYMENT_RECEIPT" \
  --endpoint-type chat --streaming --url "$ADMITTED_URL" \
  --input-file inputs.jsonl --custom-dataset-type single_turn \
  --dataset-sampling-strategy sequential \
  --request-count 2 --concurrency 2 --wait-for-model-timeout 0 \
  --request-timeout-seconds 300 --no-server-metrics --no-gpu-telemetry \
  --ui none --output-artifact-dir "$OWNED_ARTIFACT_DIR"
```

The deployed execution packet must bind the command argument vector, input
SHA-256, AIPerf `--version`, candidate/working-tree identity, root-owned URL,
and per-service process/lock/port receipts. It must retain stdout, stderr,
return code, AIPerf JSON/CSV exports, and record export when the pinned version
emits it. No credentials belong in this packet or its artifacts.

## CPU validation

From this directory, the validator only reads this directory and hashes the
JSONL. It makes no subprocess, endpoint, or GPU call.

```powershell
python .\validate_r045_aiperf_plan.py --write-input-sha
python .\validate_r045_aiperf_plan.py
python -m pytest -q .\tests\test_validate_r045_aiperf_plan.py
```

`--write-input-sha` is a local packet-finalization operation; it does not alter
any candidate source or remote tree.

## What AIPerf can and cannot establish

| original T05 concern | AIPerf evidence in this proposal | required separate evidence |
| --- | --- | --- |
| two active API generations | client-observed request count, streaming TTFT, TTFO, ITL, request latency, output-token throughput, and aggregate throughput | root-owned service/process identity and raw API correctness review |
| client timing overlap | `concurrency=2` launch policy and per-request export timestamps | physical server batch membership or scheduler overlap |
| prefill/decode interference | comparative client latency distributions across S1/S2 | worker-clock timeline, scheduler state, and native phase marks |
| cache/warm state | none | explicit cache/native collector evidence |
| token identity/equivalence | none | official SDK sidecar and semantic/token review, if separately approved |
| D06 pause/resume chain | none | a separately frozen pause sidecar with its own calls, clocks, and verdict rules |

For AIPerf 0.11.0, TTFT is the first streamed token and TTFO is the first
non-reasoning output token. They are distinct fields. AIPerf does not naturally
establish token IDs, worker clocks, physical batch membership, cache hits, or
product correctness.

## Removed legacy dependency and queue gate

The replacement plan has an empty execution prerequisite list. It does not
consume `E2-R040g`, the `effb996` T05 entry, or the old R045 v18 entry. The
historical v18 block is retained as evidence only, without changing its verdict.

It remains blocked until all of these are newly evidenced: deployment approval
and deployed `481d3a7` identity; a root-issued queue position; fresh CPU
FILEdry; independent startup review; root actual admission; no conflicting
formal RID or GPU lock; and the normal GPU lifecycle reservation. A product
`not_met` stops the whole proposal. A harness failure is classified and retained
before any bounded tool retry; it is never treated as a product retry.

## Tooling evidence and official references

The local default PATH has no `aiperf`. The existing isolated FreeToken
toolchain records `aiperf==0.11.0`; its local smoke fixture uses `profile`,
streaming, `--request-count`, `--concurrency`, `--no-server-metrics`, and
`--no-gpu-telemetry` against an owned loopback fixture only. A read-only remote
CLI inspection on 2026-10-09 returned `0.11.0` and confirmed the proposed flags.
No package was installed or updated for this packet.

NVIDIA's primary documentation confirms the `profile` concurrency/request-count
semantics, JSONL `single_turn` custom input, streaming timing metrics, output
artifact directory, and the telemetry/UI flags:

- https://docs.nvidia.com/aiperf/reference/command-line-options
- https://docs.nvidia.com/aiperf/benchmark-modes/load-generator-options-reference
- https://docs.nvidia.com/aiperf/tutorials/datasets-inputs/custom-dataset-guide
- https://docs.nvidia.com/aiperf/tutorials/model-endpoint-guides/profile-open-ai-compatible-text-ap-is-using-ai-perf
