#!/usr/bin/env python3
"""Fail-closed summary for D0 decode CUDA-event timeline JSONL files."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


_LAYER_TIMES = (
    "copy_start_ms",
    "copy_end_ms",
    "compute_start_ms",
    "compute_end_ms",
)


class TimelineError(ValueError):
    pass


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimelineError(f"{name} must be a finite non-negative number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise TimelineError(f"{name} must be a finite non-negative number")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TimelineError(f"{name} must be a non-negative integer")
    return value


def _interval_union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _interval_length(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _intersection_length(
    first: list[tuple[float, float]], second: list[tuple[float, float]]
) -> float:
    total = 0.0
    first_index = second_index = 0
    while first_index < len(first) and second_index < len(second):
        first_start, first_end = first[first_index]
        second_start, second_end = second[second_index]
        total += max(0.0, min(first_end, second_end) - max(first_start, second_start))
        if first_end <= second_end:
            first_index += 1
        else:
            second_index += 1
    return total


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _validate_record(record: Any, line_number: int, expected_layers: set[int] | None) -> dict:
    prefix = f"line {line_number}"
    if not isinstance(record, dict):
        raise TimelineError(f"{prefix}: record must be an object")
    for name in ("step", "t", "bs", "rids", "step_ms", "layers"):
        if name not in record:
            raise TimelineError(f"{prefix}: missing {name}")
    step = _integer(record["step"], f"{prefix}.step")
    t = _number(record["t"], f"{prefix}.t")
    bs = _integer(record["bs"], f"{prefix}.bs")
    step_ms = _number(record["step_ms"], f"{prefix}.step_ms")
    rids = record["rids"]
    if not isinstance(rids, list) or len(rids) != bs:
        raise TimelineError(f"{prefix}.rids length must equal bs")
    for index, rid in enumerate(rids):
        _integer(rid, f"{prefix}.rids[{index}]")
    layers = record["layers"]
    if not isinstance(layers, list) or not layers:
        raise TimelineError(f"{prefix}.layers must be a non-empty list")

    layer_ids: set[int] = set()
    normalized_layers = []
    for index, layer in enumerate(layers):
        layer_prefix = f"{prefix}.layers[{index}]"
        if not isinstance(layer, dict):
            raise TimelineError(f"{layer_prefix} must be an object")
        if "layer" not in layer:
            raise TimelineError(f"{layer_prefix}: missing layer")
        layer_id = _integer(layer["layer"], f"{layer_prefix}.layer")
        if layer_id in layer_ids:
            raise TimelineError(f"{prefix}: duplicate layer {layer_id}")
        layer_ids.add(layer_id)
        times = {}
        for name in _LAYER_TIMES:
            if name not in layer:
                raise TimelineError(f"{layer_prefix}: missing {name}")
            times[name] = _number(layer[name], f"{layer_prefix}.{name}")
        if times["copy_start_ms"] > times["copy_end_ms"]:
            raise TimelineError(f"{layer_prefix}: copy start exceeds end")
        if times["compute_start_ms"] > times["compute_end_ms"]:
            raise TimelineError(f"{layer_prefix}: compute start exceeds end")
        if times["copy_end_ms"] > step_ms or times["compute_end_ms"] > step_ms:
            raise TimelineError(f"{layer_prefix}: event ends after step_ms")
        normalized_layers.append({"layer": layer_id, **times})
    if expected_layers is not None and layer_ids != expected_layers:
        raise TimelineError(f"{prefix}: layer set differs from earlier steps")
    return {
        "step": step,
        "t": t,
        "bs": bs,
        "rids": rids,
        "step_ms": step_ms,
        "layers": normalized_layers,
    }


def load_timeline(path: str | Path) -> list[dict]:
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise TimelineError(f"cannot read {path}: {exc}") from exc
    if not lines:
        raise TimelineError(f"{path}: input is empty")

    records = []
    previous_step: int | None = None
    expected_layers: set[int] | None = None
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TimelineError(f"line {line_number}: empty line")
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TimelineError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        record = _validate_record(raw, line_number, expected_layers)
        if previous_step is not None and record["step"] <= previous_step:
            raise TimelineError(f"line {line_number}: step must strictly increase")
        previous_step = record["step"]
        expected_layers = {layer["layer"] for layer in record["layers"]}
        records.append(record)
    return records


def summarize(records: list[dict]) -> dict:
    if not records:
        raise TimelineError("input is empty")
    by_layer: dict[int, dict[str, list[float]]] = {}
    steps = []
    for record in records:
        copy_intervals = []
        compute_intervals = []
        for layer in record["layers"]:
            layer_stats = by_layer.setdefault(layer["layer"], {"copy_ms": [], "compute_ms": []})
            copy_ms = layer["copy_end_ms"] - layer["copy_start_ms"]
            compute_ms = layer["compute_end_ms"] - layer["compute_start_ms"]
            layer_stats["copy_ms"].append(copy_ms)
            layer_stats["compute_ms"].append(compute_ms)
            copy_intervals.append((layer["copy_start_ms"], layer["copy_end_ms"]))
            compute_intervals.append((layer["compute_start_ms"], layer["compute_end_ms"]))
        copy_union = _interval_union(copy_intervals)
        compute_union = _interval_union(compute_intervals)
        covered = _interval_length(_interval_union(copy_intervals + compute_intervals))
        overlap = _intersection_length(copy_union, compute_union)
        step_ms = record["step_ms"]
        steps.append(
            {
                "step": record["step"],
                "overlap_ms": overlap,
                "overlap_ratio": overlap / step_ms if step_ms else 0.0,
                "bubble_ms": step_ms - covered,
            }
        )
    layers = {
        str(layer): {
            "copy_ms": {"median": _percentile(values["copy_ms"], 0.5), "p90": _percentile(values["copy_ms"], 0.9)},
            "compute_ms": {"median": _percentile(values["compute_ms"], 0.5), "p90": _percentile(values["compute_ms"], 0.9)},
        }
        for layer, values in sorted(by_layer.items())
    }
    overlap_ratios = [step["overlap_ratio"] for step in steps]
    bubbles = [step["bubble_ms"] for step in steps]
    return {
        "steps": steps,
        "layers": layers,
        "overall": {
            "overlap_ratio": {"median": _percentile(overlap_ratios, 0.5), "p90": _percentile(overlap_ratios, 0.9)},
            "bubble_ms": {"median": _percentile(bubbles, 0.5), "p90": _percentile(bubbles, 0.9)},
        },
    }


def _print_text(summary: dict) -> None:
    print("Per-layer durations (ms; percentile uses linear interpolation)")
    for layer, values in summary["layers"].items():
        print(
            f"layer {layer}: copy median={values['copy_ms']['median']:.3f} p90={values['copy_ms']['p90']:.3f}; "
            f"compute median={values['compute_ms']['median']:.3f} p90={values['compute_ms']['p90']:.3f}"
        )
    overall = summary["overall"]
    print(
        "Overall: overlap_ratio "
        f"median={overall['overlap_ratio']['median']:.3f} p90={overall['overlap_ratio']['p90']:.3f}; "
        f"bubble_ms median={overall['bubble_ms']['median']:.3f} p90={overall['bubble_ms']['p90']:.3f}"
    )
    print("Per-step: overlap is copy/compute interval-union intersection divided by step_ms; "
          "bubble is uncovered by those expert events and may include attention or routing.")
    for step in summary["steps"]:
        print(
            f"step {step['step']}: overlap_ms={step['overlap_ms']:.3f} "
            f"overlap_ratio={step['overlap_ratio']:.3f} bubble_ms={step['bubble_ms']:.3f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="D0 decode timeline JSONL file")
    parser.add_argument("--json", action="store_true", help="write structured JSON")
    args = parser.parse_args(argv)
    try:
        summary = summarize(load_timeline(args.jsonl))
    except TimelineError as exc:
        print(f"d0_timeline_summary: error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        _print_text(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
