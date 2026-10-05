#!/usr/bin/env python3
"""Build a STRP-compatible D15 profile from D07 route-*.npz trace files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from freetoken.moe.expert_profile import rank_frequencies, write_profile  # noqa: E402


def build(route_dir: Path, output: Path, num_experts: int) -> dict:
    files = sorted(route_dir.glob("route-*.npz"))
    if not files:
        raise ValueError(f"no D07 route-*.npz files in {route_dir}")
    frequencies = None
    records = 0
    for path in files:
        ids = np.load(path)["expert_ids"]
        if ids.ndim != 3 or ids.shape[2] != 10 or np.any(ids < 0):
            raise ValueError(f"{path}: expected non-negative [layer, token, 10] expert_ids")
        if frequencies is None:
            frequencies = np.zeros((ids.shape[0], num_experts), dtype=np.int64)
        if ids.shape[0] != frequencies.shape[0] or int(ids.max()) >= num_experts:
            raise ValueError(f"{path}: route geometry differs from the first trace")
        np.add.at(frequencies, (np.repeat(np.arange(ids.shape[0]), ids.shape[1] * ids.shape[2]), ids.reshape(-1)), 1)
        records += 1
    assert frequencies is not None
    profile = rank_frequencies(frequencies.shape[0], frequencies.shape[1], frequencies.reshape(-1).tolist())
    write_profile(output, profile)
    return {"records": records, "layers": profile.num_layers, "experts": profile.num_experts, "routes": int(frequencies.sum())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--num-experts", type=int, required=True)
    args = parser.parse_args()
    print(build(args.route_dir, args.output, args.num_experts))


if __name__ == "__main__":
    main()
