"""Frozen target geometry for the D12 TP1 Qwen3.8 ordinary-capture caller.

Checks config bytes and native meta tensors only; never loads model weights.
The result is an external expectation for capture readers, not a model verdict.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace


MODEL_NAME = "Qwen3.8-Flash-Next-NVFP4"
CONFIG = Path("/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json")
CONFIG_TARGET = Path("/data2/model/Qwen3.8-Flash-Next-NVFP4/config.json.qwen4_exp.orig")
CONFIG_SHA256 = "deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80"
SOURCES = {
    "python/freetoken/models/qwen4_exp/config.py": "72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607",
    "python/freetoken/models/qwen4_exp/model.py": "d7f2a1d3d1ff390ec2a7ea1e17a3100a4c6d184c8ac405e96b718bb79e42de9a",
    "python/freetoken/models/config.py": "ffa7e3531c901f21eae31b5d572ea772a09b9d2c5eb1cf611fe8f06cde67f21b",
    "python/freetoken/models/qwen3_vl/config.py": "3029f4cfb57d1aad5bed9b2b41b5f792629e35a3e3b616d2c0b3c09010da77e3",
    "python/freetoken/kvcache/linear_state_pool.py": "51da1151a7674298e010548b1fb529f9cc331420cf89f25cd877cb97df296f53",
    "python/freetoken/engine/engine.py": "ee25277aac43720514cad160f2f886761d147235efde3baf27e93914e66cbbde",
    "python/freetoken/utils/misc.py": "4200d5a441db89ff64e8caf96f67e23ece7da6275f54c6c2217ef2d547860430",
    "python/freetoken/env.py": "94e00b6cbebe0fbfb12d504d958224cd85048d69faa85116f97db5384892b2c3",
    "python/freetoken/server/args.py": "f7bc3abba641e19ba0b8137094d424e26c75872a588d25ff906f7c52dbd6fa4c",
    "python/freetoken/layers/quantization/configs/base.py": "e363da0d70319f0f403e532e50e6fd32706226cf9a3073ca0d4989a96b951605",
    "python/freetoken/layers/quantization/configs/modelopt.py": "b8665fce08af709c3572053a77428b9c23d32bc89ab8c41efe037c5f91e53f07",
    "python/freetoken/layers/quantization/configs/__init__.py": "b24a837df6cae3a75681d2ad46384fdafa6d5dfe871007d7396f42ae937c9c66",
}


def _require(condition, message):
    if not condition:
        raise ValueError("D12 target model: " + message)


def _frozen_layout():
    linear = [i for i in range(48) if (i + 1) % 4]
    return {
        "conv_states": {"shape": [36, 1, 10240, 3], "dtype": "torch.bfloat16", "layer_ids": linear},
        "recurrent_states": {"shape": [36, 1, 48, 128, 128], "dtype": "torch.float32", "layer_ids": linear.copy()},
        "slot:ple_conv": {"shape": [1, 1, 10240, 9], "dtype": "torch.bfloat16", "layer_ids": [1]},
        "slot:ple_ngram_ctx": {"shape": [1, 1, 2], "dtype": "torch.int32", "layer_ids": [-1]},
    }


def verify_target_model(candidate_root, *, served_model, tp_size, model_dtype, ssm_dtype):
    """Verify independently frozen expectations against config + native meta pool.

    Arguments are caller-declared resolved serving settings. They must also be
    checked against actual launch/worker metadata by the formal caller. This
    function neither observes a running service nor authenticates a launch.
    """
    _require(served_model == MODEL_NAME and type(tp_size) is int and tp_size == 1
             and model_dtype == "bfloat16" and ssm_dtype == "float32",
             "requires the frozen target with TP1/bfloat16/float32")
    _require(os.environ.get("FREETOKEN_MAMBA_SSM_DTYPE", "float32").lower() == "float32",
             "SSM environment differs from frozen serving settings")
    root = Path(candidate_root).absolute()
    _require(root.resolve() == root and root.is_dir(), "physical candidate root required")

    def check_files():
        _require(CONFIG.resolve() == CONFIG_TARGET and CONFIG.is_file(), "overlay target differs")
        raw = CONFIG.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == CONFIG_SHA256, "overlay config SHA differs")
        for relative, digest in SOURCES.items():
            path = root / relative
            _require(path.resolve() == path and path.is_file()
                     and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                     "native source differs: " + relative)
        return raw

    raw = check_files()
    import torch
    from freetoken import env
    from freetoken.kvcache import linear_state_pool
    from freetoken.models.qwen4_exp import config as qwen_config
    from freetoken.models import config as model_config
    from freetoken.models.qwen3_vl import config as vision_config
    from freetoken.layers.quantization.configs import base, modelopt
    from freetoken.utils import misc

    for module in (env, linear_state_pool, qwen_config, model_config, vision_config, base, modelopt, misc):
        relative = "python/" + module.__name__.replace(".", "/") + ".py"
        _require(Path(module.__file__).resolve() == root / relative, "imported native module differs: " + relative)
    _require(str(env.ENV.MAMBA_SSM_DTYPE).lower() == "float32", "imported SSM setting differs")
    doc = json.loads(raw)
    _require(doc["model_type"] == "qwen4_exp"
             and doc["architectures"] == ["Qwen4ExpForConditionalGeneration"], "model architecture differs")
    hf = SimpleNamespace(**{**doc, "text_config": SimpleNamespace(**doc["text_config"]),
                            "vision_config": SimpleNamespace(**doc["vision_config"])})
    cfg = qwen_config.parse_config(hf)
    _require(cfg.vocab_size == 248320 and cfg.num_layers == 48 and cfg.moe_enabled is True
             and cfg.num_experts == 512 and cfg.num_experts_per_tok == 10 and cfg.expert_quant == "nvfp4",
             "native vocabulary/MoE geometry differs")
    # Use the real allocation geometry, but retain no CPU/GPU tensor storage.
    # Engine allocates the same pool with resolved model dtype and TP size.
    pool = linear_state_pool.LinearStatePool(cfg.linear_attention_group(), 1, torch.bfloat16,
        torch.device("meta"), tp_size=tp_size, slot_states=cfg.slot_states)
    tensors = {"conv_states": pool.conv_states, "recurrent_states": pool.recurrent_states,
               **{"slot:" + name: value for name, value in pool.slot_states.items()}}
    layers = {role: list(pool._group.layer_ids) for role in ("conv_states", "recurrent_states")}
    layers.update({"slot:" + name: list(pool._state_layer_index[name]) or [-1] for name in pool.slot_states})
    observed = {role: {"shape": list(value.shape), "dtype": str(value.dtype), "layer_ids": layers[role]}
                for role, value in tensors.items()}
    _require(all(value.is_meta for value in tensors.values()), "metadata validation allocated tensor storage")
    _require(observed == _frozen_layout(), "native state layout differs from frozen target")
    _require(check_files() == raw, "target config changed during validation")
    return {
        "schema": "ft_d12_target_model_expectations/v1", "served_model": MODEL_NAME,
        "config_path": str(CONFIG), "config_target": str(CONFIG_TARGET), "config_sha256": CONFIG_SHA256,
        "source_sha256": dict(SOURCES), "tp_size": 1, "model_dtype": "bfloat16", "ssm_dtype": "float32",
        "reader_arguments": {"expected_vocab_size": 248320, "expected_state_layout": _frozen_layout(),
                             "expected_moe_layer_ids": list(range(48))},
        "configuration_and_native_geometry_verified": True, "model_weights_verified": False,
        "actual_serving_settings_verified": False, "output_equivalence_verified": False,
        "performance_eligible": False,
        "scope": "frozen external target expectations verified with native meta tensors; no model/worker execution",
    }
