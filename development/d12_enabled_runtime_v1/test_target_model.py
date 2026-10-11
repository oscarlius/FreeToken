"""Verify the real target config and native metadata without loading any weights."""
import json
import os
from pathlib import Path

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires pinned native Linux modules and target config", allow_module_level=True)

import torch
from freetoken import env
from freetoken.kvcache import linear_state_pool
from freetoken.models.qwen4_exp import config as qwen_config

import target_model as target


def verify(**kwargs):
    args = dict(served_model=target.MODEL_NAME, tp_size=1, model_dtype="bfloat16", ssm_dtype="float32")
    args.update(kwargs)
    return target.verify_target_model(os.environ["FT_D12_NATIVE_SOURCE"], **args)


def test_real_target_uses_original_overlay_and_native_storage_free_geometry(tmp_path, monkeypatch):
    # Every native allocator used by the pool must remain on meta; a large real
    # state bank or GPU initialization would be a regression in this preflight.
    for name in ("zeros", "full"):
        original = getattr(torch, name)

        def guarded(*args, _original=original, **kwargs):
            assert torch.device(kwargs["device"]).type == "meta"
            return _original(*args, **kwargs)

        monkeypatch.setattr(torch, name, guarded)
    initialized = torch.cuda.is_initialized()
    result = verify()
    assert torch.cuda.is_initialized() == initialized
    assert result["config_target"].endswith("config.json.qwen4_exp.orig")
    assert result["reader_arguments"]["expected_vocab_size"] == 248320
    layout = result["reader_arguments"]["expected_state_layout"]
    assert layout["conv_states"]["shape"] == [36, 1, 10240, 3]
    assert layout["recurrent_states"]["shape"] == [36, 1, 48, 128, 128]
    assert layout["slot:ple_conv"]["layer_ids"] == [1]
    assert layout["slot:ple_ngram_ctx"]["dtype"] == "torch.int32"
    assert result["reader_arguments"]["expected_moe_layer_ids"] == list(range(48))
    assert result["configuration_and_native_geometry_verified"] is True
    assert all(result[key] is False for key in ("model_weights_verified", "actual_serving_settings_verified",
                                               "output_equivalence_verified", "performance_eligible"))
    (tmp_path / "target_model_expectations.json").write_text(json.dumps(result, indent=2) + "\n")


@pytest.mark.parametrize("changes", [dict(tp_size=2), dict(tp_size=True), dict(served_model="small-model"),
                                      dict(model_dtype="float16"), dict(ssm_dtype="bfloat16")])
def test_incompatible_serving_expectations_rejected(changes):
    with pytest.raises(ValueError, match="TP1/bfloat16/float32"):
        verify(**changes)


@pytest.mark.parametrize("fault", ["flat_config", "retarget", "config_bytes", "source_bytes",
                                    "module_origin", "live_ssm", "imported_ssm", "native_layout", "native_vocab"])
def test_wrong_target_and_configuration_drift_rejected(tmp_path, monkeypatch, fault):
    if fault == "flat_config":
        monkeypatch.setattr(target, "CONFIG", Path("/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json"))
    elif fault in ("retarget", "config_bytes"):
        path = tmp_path / "config.json"
        path.write_bytes(target.CONFIG.read_bytes() + (b" " if fault == "config_bytes" else b""))
        monkeypatch.setattr(target, "CONFIG", path)
        if fault == "config_bytes": monkeypatch.setattr(target, "CONFIG_TARGET", path)
    elif fault == "source_bytes":
        monkeypatch.setattr(target, "SOURCES", {**target.SOURCES,
            "python/freetoken/models/qwen4_exp/config.py": "0" * 64})
    elif fault == "module_origin":
        monkeypatch.setattr(qwen_config, "__file__", str(tmp_path / "config.py"))
    elif fault == "live_ssm":
        # Native ssm_state_dtype silently falls back for unknown values; this
        # expectation verifier must reject a misspelled serving override.
        monkeypatch.setenv("FREETOKEN_MAMBA_SSM_DTYPE", "misspelled")
    elif fault == "imported_ssm":
        monkeypatch.setattr(env.ENV.MAMBA_SSM_DTYPE, "value", "bfloat16")
    elif fault == "native_layout":
        original = linear_state_pool.LinearStatePool

        def changed(*args, **kwargs):
            pool = original(*args, **kwargs)
            pool._state_layer_index["ple_conv"] = {2: 0}
            return pool

        monkeypatch.setattr(linear_state_pool, "LinearStatePool", changed)
    elif fault == "native_vocab":
        original = qwen_config.parse_config

        def changed(hf):
            cfg = original(hf)
            return __import__("dataclasses").replace(cfg, vocab_size=5)

        monkeypatch.setattr(qwen_config, "parse_config", changed)
    with pytest.raises(ValueError, match="D12 target model"):
        verify()
