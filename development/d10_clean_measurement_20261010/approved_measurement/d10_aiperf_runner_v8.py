"""Self-contained D10 V7 AIPerf command and raw-result contract."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE / "inputs_r045_v7.jsonl"
FIXED = HERE / "inputs_ignore_eos256_v7.jsonl"
AIPERF = "/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf"


def parser():
    spec = importlib.util.spec_from_file_location("d10_parse_v7", HERE / "d10_aiperf_parse_v7.py")
    module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module)
    return module


def argv(endpoint: str, output: str, input_file: Path) -> list[str]:
    return [AIPERF, "profile", "--model", "Qwen3.8-Flash-Next-NVFP4", "--endpoint-type", "chat", "--streaming",
            "--url", endpoint, "--input-file", str(input_file), "--custom-dataset-type", "single_turn",
            "--dataset-sampling-strategy", "sequential", "--request-count", "2", "--concurrency", "2",
            "--wait-for-model-timeout", "0", "--request-timeout-seconds", "300", "--no-server-metrics",
            "--no-gpu-telemetry", "--ui", "none", "--tokenizer", "builtin", "--use-server-token-count",
            "--use-legacy-max-tokens", "--export-level", "raw", "--output-artifact-dir", output]


def require_raw_profiles(root: Path) -> dict[int, list[dict]]:
    p = parser()
    return {0: p.original_gate(root / "profile0"), 1: p.original_gate(root / "profile1"),
            2: p.fixed_gate(root / "profile2"), 3: p.fixed_gate(root / "profile3")}


def source_hashes() -> dict[str, str]:
    names = ("d10_aiperf_runner_v8.py", "d10_aiperf_parse_v7.py", "inputs_r045_v7.jsonl", "inputs_ignore_eos256_v7.jsonl")
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in names}
