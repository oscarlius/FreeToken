"""STRP expert-profile IO shared by the D15 offline tool and cache policy.

The binary layout is deliberately byte-compatible with Strata's MIT-licensed
``tools/make_profile.py``: ``STRP`` + five little-endian u32 values, ranked
u16 (layer, expert) pairs, then an i32 frequency table.  This module contains
no kernels and never touches model weights.

Format reference: Strata, Copyright (c) Strata contributors, MIT License.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MAGIC = b"STRP"
VERSION = 1
_HEADER = struct.Struct("<5I")


@dataclass(frozen=True)
class ExpertProfile:
    num_layers: int
    num_experts: int
    ranked: tuple[tuple[int, int], ...]
    frequencies: tuple[int, ...]

    def for_capacity(self, capacity: int) -> tuple[tuple[int, int], ...]:
        return self.ranked[:max(0, capacity)]


def rank_frequencies(num_layers: int, num_experts: int, frequencies: Iterable[int]) -> ExpertProfile:
    values = tuple(int(value) for value in frequencies)
    if num_layers <= 0 or num_experts <= 0 or num_layers > 65535 or num_experts > 65535:
        raise ValueError("STRP dimensions must be within [1, 65535]")
    if len(values) != num_layers * num_experts or any(value < 0 for value in values):
        raise ValueError("frequency table shape or values are invalid")
    ranked = tuple(sorted(
        ((layer, expert) for layer in range(num_layers) for expert in range(num_experts)),
        key=lambda pair: (-values[pair[0] * num_experts + pair[1]], pair[0], pair[1]),
    ))
    return ExpertProfile(num_layers, num_experts, ranked, values)


def write_profile(path: str | Path, profile: ExpertProfile) -> None:
    if len(profile.ranked) > 0xFFFFFFFF or any(value > 0x7FFFFFFF for value in profile.frequencies):
        raise ValueError("STRP values exceed their on-disk integer range")
    expected = profile.num_layers * profile.num_experts
    if len(profile.frequencies) != expected or len(set(profile.ranked)) != len(profile.ranked):
        raise ValueError("profile has invalid frequency table or duplicate ranks")
    if any(not (0 <= layer < profile.num_layers and 0 <= expert < profile.num_experts) for layer, expert in profile.ranked):
        raise ValueError("profile rank is out of range")
    ranks = [-1] * expected
    for rank, (layer, expert) in enumerate(profile.ranked):
        ranks[layer * profile.num_experts + expert] = rank
    payload = bytearray(MAGIC + _HEADER.pack(VERSION, profile.num_layers, profile.num_experts, len(profile.ranked), len(profile.ranked)))
    payload.extend(b"".join(struct.pack("<HH", layer, expert) for layer, expert in profile.ranked))
    payload.extend(struct.pack(f"<{expected}i", *ranks))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)


def read_profile(path: str | Path, *, num_layers: int | None = None, num_experts: int | None = None) -> ExpertProfile:
    blob = Path(path).read_bytes()
    if len(blob) < 24 or blob[:4] != MAGIC:
        raise ValueError("not a complete STRP profile")
    version, layers, experts, slots, ranked_count = _HEADER.unpack_from(blob, 4)
    if version != VERSION or ranked_count > slots or layers == 0 or experts == 0:
        raise ValueError("unsupported or invalid STRP header")
    if num_layers is not None and layers != num_layers or num_experts is not None and experts != num_experts:
        raise ValueError(f"STRP geometry {layers}x{experts} does not match cache geometry")
    expected = 24 + 4 * ranked_count + 4 * layers * experts
    if len(blob) != expected:
        raise ValueError("STRP profile is truncated or has trailing data")
    ranked = tuple(struct.unpack_from("<HH", blob, 24 + 4 * index) for index in range(ranked_count))
    if len(set(ranked)) != len(ranked) or any(layer >= layers or expert >= experts for layer, expert in ranked):
        raise ValueError("STRP ranking contains invalid pairs")
    ranks = struct.unpack_from(f"<{layers * experts}i", blob, 24 + 4 * ranked_count)
    frequencies = tuple(0 if rank < 0 else ranked_count - rank for rank in ranks)
    return ExpertProfile(layers, experts, ranked, frequencies)
