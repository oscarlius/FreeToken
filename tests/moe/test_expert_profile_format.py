from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

import numpy as np

from freetoken.moe.expert_profile import MAGIC, read_profile, rank_frequencies, write_profile


def test_strp_profile_is_strata_layout_and_round_trips(tmp_path):
    profile = rank_frequencies(2, 4, [1, 9, 2, 0, 3, 1, 7, 4])
    output = tmp_path / "profile.strp"
    write_profile(output, profile)
    assert output.read_bytes()[:4] == MAGIC
    assert struct.unpack_from("<5I", output.read_bytes(), 4) == (1, 2, 4, 8, 8)
    assert read_profile(output, num_layers=2, num_experts=4).ranked == profile.ranked


def test_profile_tool_consumes_d07_synthetic_trace(tmp_path):
    route_dir = tmp_path / "route"
    route_dir.mkdir()
    ids = np.array([[[1] * 10, [1] * 10], [[3] * 10, [2] * 10]], dtype=np.int16)
    np.savez_compressed(route_dir / "route-00000000.npz", expert_ids=ids)
    spec = importlib.util.spec_from_file_location("d15_profile_tool", Path("tools/build_expert_profile.py"))
    tool = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(tool)
    output = tmp_path / "profile.strp"
    assert tool.build(route_dir, output, 4)["routes"] == 40
    assert read_profile(output).ranked[:3] == ((0, 1), (1, 2), (1, 3))
