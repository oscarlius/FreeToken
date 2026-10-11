"""Strict parser for AIPerf 0.11 raw per-request records used by D10 V7."""
from __future__ import annotations

import json
import math
from pathlib import Path


def _metric(metrics: dict, name: str) -> float:
    value = metrics.get(name)
    if not isinstance(value, dict) or not isinstance(value.get("value"), (int, float)):
        raise RuntimeError(f"missing AIPerf 0.11 metric: {name}")
    number = float(value["value"])
    if not math.isfinite(number):
        raise RuntimeError(f"non-finite AIPerf 0.11 metric: {name}")
    return number


def parse_profile(directory: Path) -> list[dict]:
    records: list[dict] = []
    for source in sorted(directory.rglob("profile_export.jsonl")):
        for line in source.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            metadata, metrics = raw.get("metadata"), raw.get("metrics")
            request_id = metadata.get("x_request_id") if isinstance(metadata, dict) else None
            if not isinstance(request_id, str) or not request_id.strip() or not isinstance(metrics, dict):
                raise RuntimeError("invalid AIPerf 0.11 per-request record")
            completion = _metric(metrics, "usage_completion_tokens")
            output = _metric(metrics, "output_token_count")
            ttft = _metric(metrics, "time_to_first_token")
            speed = _metric(metrics, "output_token_throughput_per_user")
            if completion != int(completion) or completion <= 0 or completion != output:
                raise RuntimeError("invalid positive completion count")
            if ttft <= 0 or speed <= 0:
                raise RuntimeError("TTFT and decode throughput must be positive")
            records.append({"request_id": request_id, "completion_tokens": int(completion),
                            "ttft_ms": ttft, "decode_tokens_per_second": speed})
    if len(records) != 2 or len({row["request_id"] for row in records}) != 2:
        raise RuntimeError("each group needs exactly two non-empty unique request IDs")
    return records


def _speed_gate(rows: list[dict]) -> list[dict]:
    if any(row["decode_tokens_per_second"] <= 30 for row in rows):
        raise RuntimeError("per-request decode speed must be > 30")
    return rows


def original_gate(directory: Path) -> list[dict]:
    return _speed_gate(parse_profile(directory))


def fixed_gate(directory: Path) -> list[dict]:
    rows = parse_profile(directory)
    if [row["completion_tokens"] for row in rows] != [256, 256]:
        raise RuntimeError("ignore-EOS fixed group must complete exactly [256, 256]")
    return _speed_gate(rows)
