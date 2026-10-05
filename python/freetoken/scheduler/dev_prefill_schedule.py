"""Strict opt-in development schedule for one cold Qwen prefill.

This module deliberately has no scheduler or CUDA imports so malformed JSON can
be rejected before it changes a request's cache ownership.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass


ENV_NAME = "FT_DEV_PREFILL_SCHEDULE"
_MODES = frozenset(("ordinary", "layer_major"))


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    mode: str
    subchunks: tuple[int, ...]


@dataclass(frozen=True)
class PrefillSchedule:
    segments: tuple[Segment, ...]


def _positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def parse(value: str) -> PrefillSchedule:
    """Parse the complete JSON value; unknown fields and implicit repairs fail."""
    try:
        rows = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("FT_DEV_PREFILL_SCHEDULE must be JSON") from error
    if not isinstance(rows, list) or not rows:
        raise ValueError("FT_DEV_PREFILL_SCHEDULE must be a nonempty list")
    segments = []
    previous_end = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"start", "end", "mode", "subchunks"}:
            raise ValueError(f"schedule segment {index} must contain exactly start,end,mode,subchunks")
        if type(row["start"]) is not int or row["start"] < 0:
            raise ValueError(f"segment {index}.start must be a nonnegative integer")
        start = row["start"]
        end = _positive(row["end"], f"segment {index}.end")
        mode = row["mode"]
        chunks = row["subchunks"]
        if type(mode) is not str or mode not in _MODES:
            raise ValueError(f"segment {index}.mode is unsupported")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError(f"segment {index}.subchunks must be a nonempty list")
        subchunks = tuple(_positive(item, f"segment {index}.subchunks") for item in chunks)
        if start >= end or sum(subchunks) != end - start:
            raise ValueError(f"segment {index} geometry differs from subchunks")
        if mode == "ordinary" and len(subchunks) != 1:
            raise ValueError(f"segment {index}.ordinary mode requires one model-call subchunk")
        if previous_end is None:
            if start != 0: raise ValueError("schedule must start at absolute token zero")
        elif start not in (previous_end, previous_end - 1):
            raise ValueError(f"segment {index} is not contiguous or a one-token rewind")
        segments.append(Segment(start, end, mode, subchunks)); previous_end = end
    return PrefillSchedule(tuple(segments))


def from_env(environ: dict[str, str] | None = None) -> PrefillSchedule | None:
    value = (os.environ if environ is None else environ).get(ENV_NAME)
    if value in (None, ""):
        return None
    path = os.fspath(value)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return parse(stream.read())
    except OSError as error:
        raise ValueError("FT_DEV_PREFILL_SCHEDULE must name a readable JSON file") from error


def grid_alignment(page_size: int, fla_chunk_size: int, qsa_index_ratio: int) -> int:
    return math.lcm(_positive(page_size, "page_size"), _positive(fla_chunk_size, "fla_chunk_size"), _positive(qsa_index_ratio, "qsa_index_ratio"))


def admit(schedule: PrefillSchedule, *, prompt_len: int, cached_len: int, device_len: int,
          request_count: int, first_generation: bool, has_multimodal: bool,
          disk_ple: bool, rewind_alignment: int, fla_chunk_size: int = 64) -> tuple[Segment, ...]:
    """Validate the only supported request geometry; never fall back silently."""
    if request_count != 1 or not first_generation or cached_len != 0 or device_len != prompt_len:
        raise ValueError("development schedule requires one first-generation cold request")
    if has_multimodal or disk_ple:
        raise ValueError("development schedule rejects multimodal and disk-PLE requests")
    if type(prompt_len) is not int or prompt_len <= 0 or schedule.segments[-1].end != prompt_len:
        raise ValueError("development schedule prompt geometry differs")
    alignment = _positive(rewind_alignment, "rewind_alignment")
    fla = _positive(fla_chunk_size, "fla_chunk_size")
    for previous, current in zip(schedule.segments, schedule.segments[1:]):
        if current.start == previous.end - 1:
            if current.start % alignment:
                raise ValueError("development schedule rewind is not grid aligned")
            # Ordinary forwards also write the FLA/GDN/PLE checkpoint. Preserve
            # their actual call geometry, but require an interior track row.
            if current.start <= previous.start:
                raise ValueError("development schedule rewind lacks an interior FLA checkpoint")
            offset = previous.start
            for length in previous.subchunks:
                end = offset + length
                if offset < current.start < end and (current.start - offset) % fla:
                    raise ValueError("development schedule grid would split an interior FLA track")
                offset = end
    return schedule.segments
