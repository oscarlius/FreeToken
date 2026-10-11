"""Actual HTTP-normalized tokenizer replay; no model service or GPU."""
from pathlib import Path
import importlib.util
import json
import os
import hashlib

import pytest

DEV = Path(__file__).parents[1]
WT = os.environ.get("FT_CPU_ACTUAL_CANDIDATE_ROOT")
ROUND = os.environ.get("FT_RECORDED_R046F_ROOT")
pytestmark = pytest.mark.skipif(not WT or not ROUND, reason="requires CPU-only candidate tokenizer and sealed b98")

def driver():
    spec = importlib.util.spec_from_file_location("r046g_actual_frontend", DEV / "r046c_ordinary_seed_driver_v3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_actual_candidate_api_frontend_matches_all_sealed_worker_input_ids():
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    import sitecustomize
    assert sitecustomize.FT_CPU_FIXTURE_NETWORK_GUARD is True
    arm = Path(ROUND) / "G_seed12k"
    payload = json.loads((arm / "round-00.payload.json").read_text())
    actual = json.loads((arm / "ordinary_observer/input-0.json").read_text())
    tool = driver()
    frontend = tool.candidate_frontend(Path(WT), Path("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"))
    ids = tool.input_ids_for_payload(frontend, payload)
    assert ids == actual
    assert len(ids) == 12660
    assert hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest() == "5248e2f4c23b06270f2b78f5b9575de420011e3c9f40ce2d404abad949d8ea6b"

def test_recursive_wire_key_order_normalizes_to_identical_worker_ids():
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    arm = Path(ROUND) / "G_seed12k"
    payload = json.loads((arm / "round-00.payload.json").read_text())
    def reverse_keys(value):
        if isinstance(value, dict):
            return {key: reverse_keys(value[key]) for key in reversed(list(value))}
        if isinstance(value, list):
            return [reverse_keys(item) for item in value]
        return value
    variant = reverse_keys(payload)
    assert variant == payload
    tool = driver()
    frontend = tool.candidate_frontend(Path(WT), Path("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"))
    actual = json.loads((arm / "ordinary_observer/input-0.json").read_text())
    assert frontend(variant) == actual
    assert frontend(payload) == actual
