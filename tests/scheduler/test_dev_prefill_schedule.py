"""Host-only contracts for the opt-in strict schedule parser."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

PATH = Path(__file__).parents[2] / "python/freetoken/scheduler/dev_prefill_schedule.py"
SPEC = importlib.util.spec_from_file_location("dev_prefill_schedule", PATH)
MODULE = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MODULE; SPEC.loader.exec_module(MODULE)

EXACT = [
    {"start": 0, "end": 512, "mode": "ordinary", "subchunks": [512]},
    {"start": 512, "end": 8193, "mode": "layer_major", "subchunks": [4096, 3585]},
    {"start": 8192, "end": 8257, "mode": "ordinary", "subchunks": [65]},
]


def test_default_environment_is_absent():
    assert MODULE.from_env({}) is None


def test_environment_requires_a_utf8_json_file(tmp_path):
    path = tmp_path / "schedule.json"; path.write_text(json.dumps(EXACT), encoding="utf-8")
    assert MODULE.from_env({MODULE.ENV_NAME: str(path)}).segments[1].subchunks == (4096, 3585)
    with pytest.raises(ValueError, match="readable JSON file"):
        MODULE.from_env({MODULE.ENV_NAME: json.dumps(EXACT)})


def test_exact_512_4096_3585_65_geometry_is_preserved():
    schedule = MODULE.parse(json.dumps(EXACT))
    assert [(row.start, row.end, row.mode, row.subchunks) for row in schedule.segments] == [
        (0, 512, "ordinary", (512,)), (512, 8193, "layer_major", (4096, 3585)), (8192, 8257, "ordinary", (65,))]
    assert MODULE.admit(schedule, prompt_len=8257, cached_len=0, device_len=8257, request_count=1,
                        first_generation=True, has_multimodal=False, disk_ple=False, rewind_alignment=8192) == schedule.segments


@pytest.mark.parametrize("value", ["{}", "[{}]", json.dumps([{**EXACT[0], "unexpected": 1}]),
                                   json.dumps([{**EXACT[0], "subchunks": [511]}]),
                                   json.dumps([{**EXACT[0], "subchunks": [256, 256]}])])
def test_malformed_schedule_has_no_fallback(value):
    with pytest.raises(ValueError): MODULE.parse(value)


def test_unaligned_rewind_and_unsupported_request_are_rejected():
    bad = [*EXACT[:-1], {"start": 8192, "end": 8257, "mode": "ordinary", "subchunks": [65]}]
    schedule = MODULE.parse(json.dumps(bad))
    with pytest.raises(ValueError, match="grid aligned"):
        MODULE.admit(schedule, prompt_len=8257, cached_len=0, device_len=8257, request_count=1,
                     first_generation=True, has_multimodal=False, disk_ple=False, rewind_alignment=4097)
    for change in ({"cached_len": 1}, {"request_count": 2}, {"has_multimodal": True}, {"disk_ple": True}):
        args = dict(prompt_len=8257, cached_len=0, device_len=8257, request_count=1, first_generation=True,
                    has_multimodal=False, disk_ple=False, rewind_alignment=8192); args.update(change)
        with pytest.raises(ValueError): MODULE.admit(schedule, **args)


def test_injected_grid_that_would_split_fla_track_is_rejected():
    rows = [*EXACT]
    rows[1] = {**rows[1], "subchunks": [4000, 3681]}
    schedule = MODULE.parse(json.dumps(rows))
    with pytest.raises(ValueError, match="interior FLA track"):
        MODULE.admit(schedule, prompt_len=8257, cached_len=0, device_len=8257, request_count=1,
                     first_generation=True, has_multimodal=False, disk_ple=False,
                     rewind_alignment=8192, fla_chunk_size=64)
