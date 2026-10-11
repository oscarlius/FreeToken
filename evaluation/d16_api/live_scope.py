"""Run one approved D16 API-only service arm through openai-python.

This is intentionally a client/artifact adapter: it never launches a service,
allocates a GPU, reads native worker state, or interprets API concurrency as a
physical batch.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import httpx
from openai import OpenAI

from sdk_completions import CompletionCollectionError, collect_completion, compare_completion


HERE = Path(__file__).resolve().parent


def write_once(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def scope_inputs() -> tuple[dict, dict[str, tuple[str, int]]]:
    scope = json.loads((HERE / "scope_payloads.json").read_text(encoding="utf-8"))
    binding = json.loads((HERE / "interleave_input_binding.json").read_text(encoding="utf-8"))
    prompts = {row["label"]: (row["decoded_prompt"], len(row["original_input_ids"])) for row in binding["inputs"]}
    if scope.get("services") != 6 or len(scope.get("calls", [])) != 8 or set(prompts) != {
        "slot_0_short_512", "slot_1_long_query"} or sorted(count for _, count in prompts.values()) != [512, 8257]:
        raise RuntimeError("D16 scope/input binding differs")
    return scope, prompts


def request(prompt: str, model: str) -> dict:
    return {"model": model, "prompt": prompt, "max_tokens": 128, "temperature": 0,
            "top_p": 1, "stream": True, "stream_options": {"include_usage": True},
            "extra_body": {"ignore_eos": True}}


def collect_one(base_url: str, model: str, item: dict, prompt: str, expected_prompt_tokens: int, output: Path,
                barrier: threading.Barrier | None = None) -> dict:
    http_client = httpx.Client(trust_env=False)
    client = OpenAI(base_url=base_url + "/v1", api_key="d16-api-only", max_retries=0, timeout=900.0,
                    http_client=http_client)
    try:
        if barrier is not None:
            barrier.wait()
        started = time.monotonic()
        artifact = collect_completion(client, request(prompt, model))
        artifact["client"] = {"started_seconds": started, "completed_seconds": time.monotonic(),
                              "service": item["service"], "label": item["label"], "input": item["input"]}
        actual = artifact["projection"]["usage"]["prompt_tokens"]
        if actual != expected_prompt_tokens:
            artifact["contract_error"] = f"prompt_tokens={actual}, expected={expected_prompt_tokens}"
            write_once(output, artifact)
            raise ValueError(artifact["contract_error"])
        write_once(output, artifact)
        return artifact
    except CompletionCollectionError as exc:
        artifact = exc.artifact
        artifact["client"] = {"started_seconds": started, "completed_seconds": time.monotonic(),
                              "service": item["service"], "label": item["label"], "input": item["input"]}
        write_once(output, artifact)
        raise
    finally:
        client.close()


def run_service(base_url: str, model: str, service: str, output: Path) -> dict:
    scope, prompts = scope_inputs()
    calls = [item for item in scope["calls"] if item["service"] == service]
    if not calls or service not in {f"interleave_{index}" for index in range(6)}:
        raise RuntimeError("unapproved D16 service")
    output.mkdir(parents=False, exist_ok=False)
    started = time.monotonic()
    if len(calls) == 2:
        barrier = threading.Barrier(2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(collect_one, base_url, model, item, *prompts[item["input"]], output / f"{item['label']}.json", barrier) for item in calls]
            records = [future.result() for future in futures]
        windows = [(record["client"]["started_seconds"], record["client"]["completed_seconds"]) for record in records]
        if max(start for start, _ in windows) > min(end for _, end in windows):
            raise RuntimeError("batch API client windows do not overlap")
    else:
        records = [collect_one(base_url, model, calls[0], *prompts[calls[0]["input"]], output / "single.json")]
    write_once(output / "service_result.json", {"schema": "ft_d16_api_service/v1", "service": service,
        "calls": len(records), "elapsed_seconds": time.monotonic() - started,
        "api_concurrency_only": len(records) == 2,
        "does_not_prove": ["physical_batch", "worker_admission", "native_token_input", "expert_cache_hit"]})
    return {item["compare"]: record["projection"] for item, record in zip(calls, records)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_service(args.base_url.rstrip("/"), args.model, args.service, args.output)
    print(json.dumps({"projection_sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
