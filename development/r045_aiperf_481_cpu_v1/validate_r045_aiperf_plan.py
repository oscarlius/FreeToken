#!/usr/bin/env python3
"""Offline validator for the R045 AIPerf planning-only packet.

It reads local JSON/JSONL only.  It neither starts a process nor opens a
network connection, so passing it does not authorize or simulate a benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "r045_aiperf_plan.json"
INPUTS_PATH = ROOT / "inputs.jsonl"
CANDIDATE = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("every input record must be an object")
    return records


def validate(plan: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    if plan.get("schema") != "ft_r045_aiperf_cpu_plan/v1":
        raise ValueError("unexpected schema")
    if plan.get("state") != "planning_only" or plan.get("execution_proposal", {}).get("not_authorized_to_execute") is not True:
        raise ValueError("packet must remain planning_only and execution-blocked")
    if plan.get("candidate_commit") != CANDIDATE:
        raise ValueError("candidate is not the frozen 481d3a7 identity")
    tool = plan.get("tool", {})
    if tool.get("name") != "aiperf" or tool.get("version") != "0.11.0":
        raise ValueError("tool must remain AIPerf 0.11.0")
    scope = plan.get("execution_proposal", {})
    expected_scope = {"service_count": 2, "profiles_per_service": 1, "concurrency": 2,
                      "generation_calls_per_service": 2, "total_generation_calls": 4,
                      "aiperf_readiness_calls": 0, "scheduling": "concurrency_burst"}
    if {key: scope.get(key) for key in expected_scope} != expected_scope:
        raise ValueError("two-service / four-generation-call proposal changed")
    options = plan.get("aiperf_options", {})
    expected_options = {"endpoint_type": "chat", "streaming": True, "request_count": 2,
                        "concurrency": 2, "wait_for_model_timeout": 0, "no_server_metrics": True,
                        "no_gpu_telemetry": True, "ui": "none", "request_timeout_seconds": 300}
    if {key: options.get(key) for key in expected_options} != expected_options:
        raise ValueError("AIPerf option freeze changed")
    if plan.get("legacy_dependency_policy", {}).get("prerequisites") != []:
        raise ValueError("legacy prerequisites must remain empty")
    if len(records) != 2 or any(not isinstance(record.get("text"), str) for record in records):
        raise ValueError("inputs must be two single-turn text records")
    if any(record.get("output_length") != 128 for record in records):
        raise ValueError("each request must retain output_length=128")
    if any(record.get("extra") != {"temperature": 0, "top_p": 1, "ignore_eos": False} for record in records):
        raise ValueError("each request must retain the frozen sampling values")
    input_spec = plan.get("inputs", {})
    actual_sha = sha256(INPUTS_PATH)
    if input_spec.get("sha256") not in {"TO_BE_FILLED_BY_VALIDATE", actual_sha}:
        raise ValueError("inputs SHA-256 does not bind this packet")
    return {"candidate_commit": CANDIDATE, "inputs_sha256": actual_sha, "records": len(records),
            "status": "CPU_PLAN_VALID_NO_EXECUTION"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate R045 AIPerf plan without network or GPU activity")
    parser.add_argument("--write-input-sha", action="store_true", help="bind the current local inputs SHA-256 into the plan")
    args = parser.parse_args()
    plan = load_json(PLAN_PATH)
    records = load_jsonl(INPUTS_PATH)
    result = validate(plan, records)
    if args.write_input_sha:
        plan["inputs"]["sha256"] = result["inputs_sha256"]
        PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["input_sha_written"] = True
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
