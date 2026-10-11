"""CPU-only D10 command planner; runtime is deliberately disabled by default."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
R045 = ROOT.parent / "r045_production_aiperf_20261009"
MODEL = "Qwen3.8-Flash-Next-NVFP4"
URL = "http://172.16.108.9:8095"
TOKENIZER = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
AIPERF = "/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf"


def argv(input_file: str, output_dir: str) -> list[str]:
    return [AIPERF, "profile", "--model", MODEL, "--endpoint-type", "chat",
            "--streaming", "--url", URL, "--input-file", input_file,
            "--custom-dataset-type", "single_turn", "--dataset-sampling-strategy", "sequential",
            "--request-count", "2", "--concurrency", "2", "--wait-for-model-timeout", "0",
            "--request-timeout-seconds", "300", "--no-server-metrics", "--no-gpu-telemetry",
            "--ui", "none", "--tokenizer", "builtin", "--use-server-token-count",
            "--use-legacy-max-tokens", "--export-level", "raw",
            "--output-artifact-dir", output_dir]


def verify_prediction_seal() -> str:
    seal = json.loads((ROOT / "PREDICTION_SEAL.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((ROOT / "prediction_manifest.json").read_bytes()).hexdigest()
    assert digest == seal["sha256"], (digest, seal["sha256"])
    return digest


def validate_inputs(base: Path = ROOT, manifest: dict | None = None) -> dict:
    original = R045 / "inputs.jsonl" if base == ROOT else base / "inputs.jsonl"
    variant = ROOT / "inputs_ignore_eos256.jsonl" if base == ROOT else base / "inputs_ignore_eos256.jsonl"
    expected = "9ac31867b8d9303b2b00109828e3e66ecd66699ce6d109dc7b11e994c8ce1cc3"
    expected_variant = "a1fcedff4ec4d70ca8ecdebf2e704fc30475600ff668177f3715f11d569e64a5"
    actual = hashlib.sha256(original.read_bytes()).hexdigest()
    assert actual == expected, (actual, expected)
    records = [json.loads(line) for line in original.read_text(encoding="utf-8").splitlines()]
    variants = [json.loads(line) for line in variant.read_text(encoding="utf-8").splitlines()]
    variant_digest = hashlib.sha256(variant.read_bytes()).hexdigest()
    assert variant_digest == expected_variant, (variant_digest, expected_variant)
    assert len(records) == len(variants) == 2
    for source, candidate in zip(records, variants):
        assert source["text"] == candidate["text"]
        assert source["extra"]["temperature"] == candidate["extra"]["temperature"] == 0
        assert source["extra"]["top_p"] == candidate["extra"]["top_p"] == 1
        assert source["extra"]["ignore_eos"] is False and source["output_length"] == 128
        assert candidate["extra"]["ignore_eos"] is True and candidate["output_length"] == 256
    if manifest is not None:
        assert actual == manifest["inputs"]["original"]["sha256"]
        assert variant_digest == manifest["inputs"]["variant"]["sha256"]
    return {"original_sha256": actual, "variant_sha256": variant_digest, "prompt_identity": True}


def plan() -> dict:
    seal_sha = verify_prediction_seal()
    manifest = json.loads((ROOT / "prediction_manifest.json").read_text(encoding="utf-8"))
    inputs = validate_inputs(manifest=manifest)
    return {
        "status": "CPU_PREPARED_PENDING_RUNTIME",
        "runtime_enabled": False,
        "gpu_launch_allowed": False,
        "aiperf": {"version": "0.11.0", "concurrency": 2, "request_count": 2,
                   "original_waves": [argv("/data2/FreeToken/d10_staggered_20261009/inputs.jsonl", "<original-wave-1>"), argv("/data2/FreeToken/d10_staggered_20261009/inputs.jsonl", "<original-wave-2>")],
                   "variant_wave": argv("/data2/FreeToken/d10_staggered_20261009/inputs_ignore_eos256.jsonl", "<ignore-eos-256-wave>"),
                   "tokenizer_preflight_path": TOKENIZER, "aiperf_dataset_tokenizer": "builtin",
                   "local_staging": {"original": str(R045 / "inputs.jsonl"), "variant": str(ROOT / "inputs_ignore_eos256.jsonl")},
                   "remote_deployment_map": {"original": "/data2/FreeToken/d10_staggered_20261009/inputs.jsonl", "variant": "/data2/FreeToken/d10_staggered_20261009/inputs_ignore_eos256.jsonl"},
                   "input_validation": inputs},
        "prediction": manifest["prediction"],
        "prediction_seal_sha256": seal_sha,
        "hooks": ["AIPerf raw per-request decode rate", "T05/D02 per-layer transfer/compute timeline when available", "T16 gate artifact"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--enable-runtime", action="store_true", help="refused: formal admission is required")
    args = parser.parse_args()
    if args.enable_runtime:
        raise SystemExit("REFUSED: D10 runtime requires formal admission; CPU preparation only")
    if args.plan:
        print(json.dumps(plan(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
