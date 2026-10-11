"""Connect SDK capture to the existing shared Phase 3 loop and pinned grader."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import openai

from sdk_capture import capture_chat_stream


def run_phase3_sdk(benchmark, client, model_id, prompt_file):
    """Use the existing question loop; retain failed calls as RUNTIME_ERROR."""
    if client.max_retries != 0:
        raise ValueError("Quality60 requires max_retries=0")
    output = Path(benchmark.RUN_DIR) / f"quality_results_{model_id}.jsonl"
    if output.exists():
        raise FileExistsError(output)
    chunks_dir = Path(benchmark.RUN_DIR) / "sdk_chunks"
    chunks_dir.mkdir(exist_ok=False)
    ordinal = 0
    provenance = {
        "backend": "openai-python",
        "sdk_version": openai.__version__,
        "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "capture_sha256": hashlib.sha256(Path(__file__).with_name("sdk_capture.py").read_bytes()).hexdigest(),
    }

    def capture(messages, *, max_tokens):
        nonlocal ordinal
        ordinal += 1
        path = chunks_dir / f"{ordinal:03d}.jsonl"
        request = {"model": benchmark.MODEL_NAME, "messages": messages,
                   "max_tokens": max_tokens, "temperature": 0.0, "stream": True,
                   "stream_options": {"include_usage": True}}
        metadata = {**provenance, "chunk_log": str(path), "model": benchmark.MODEL_NAME,
                    "request_sha256": hashlib.sha256(json.dumps(request, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        try:
            result = capture_chat_stream(client, request, path)
        except Exception as exc:
            # Partial chunks remain in the exclusive log. Never grade a partial
            # answer, infer stop, or hide a failed request by retrying it.
            result = {"response": "", "thinking": "", "finish_reason": "error",
                      "error": type(exc).__name__}
        else:
            metadata.update({key: result[key] for key in ("usage", "completion_id", "request_id")})
            result["error"] = None
        if path.exists():
            metadata["chunk_log_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return {**result, "metadata": metadata}

    return benchmark.run_phase3_quality(model_id, prompt_file, capture_chat=capture)


def main():
    import argparse
    import httpx

    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("api-base", "model", "prompts", "run-dir"):
        parser.add_argument("--" + option, required=True)
    args = parser.parse_args()
    os.environ.update(FT_API_BASE=args.api_base, FT_MODEL_NAME=args.model, FT_RUN_DIR=args.run_dir)
    source = Path(os.environ.get("FT_QUALITY_BENCHMARK_SOURCE",
                  Path(__file__).resolve().parents[3] / "_shared" / "benchmark_client.py"))
    spec = importlib.util.spec_from_file_location("quality60_shared_benchmark", source)
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    with httpx.Client(trust_env=False) as transport:
        with openai.OpenAI(base_url=args.api_base, api_key=os.environ.get("OPENAI_API_KEY", "local"),
                           max_retries=0, timeout=120.0, http_client=transport) as client:
            summary = run_phase3_sdk(benchmark, client, args.model, args.prompts)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
