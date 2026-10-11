#!/usr/bin/env python3
"""
Setup the framework-specific configuration overlay for Qwen3.8-Flash-Next in FreeToken.
Per the test plan and AGENTS.md rules:
- Original model in /data2/model/Qwen3.8-Flash-Next-NVFP4 remains strictly read-only.
- All weights and assets are soft-linked.
- config.json is pointed to config.json.qwen4_exp.orig
- hf_quant_config.json is pointed to hf_quant_config.json.qwen4_exp.orig
"""

import os
import sys

TARGET_DIR = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
SRC_DIR = "/data2/model/Qwen3.8-Flash-Next-NVFP4"

def setup_overlay():
    print(f"Creating overlay directory: {TARGET_DIR}")
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    # 1. Symlink all standard files from SRC_DIR except config files
    for fname in os.listdir(SRC_DIR):
        if fname.startswith("config.json") or fname.startswith("hf_quant_config.json") or fname == "README.md":
            continue
        src_path = os.path.join(SRC_DIR, fname)
        dst_path = os.path.join(TARGET_DIR, fname)
        if os.path.islink(dst_path) or os.path.exists(dst_path):
            os.remove(dst_path)
        os.symlink(src_path, dst_path)
        print(f"Linked asset: {fname}")
        
    # 2. Symlink config.json -> config.json.qwen4_exp.orig
    cfg_src = os.path.join(SRC_DIR, "config.json.qwen4_exp.orig")
    cfg_dst = os.path.join(TARGET_DIR, "config.json")
    if os.path.islink(cfg_dst) or os.path.exists(cfg_dst):
        os.remove(cfg_dst)
    os.symlink(cfg_src, cfg_dst)
    print("Linked config.json -> config.json.qwen4_exp.orig")
    
    # 3. Symlink hf_quant_config.json -> hf_quant_config.json.qwen4_exp.orig
    qcfg_src = os.path.join(SRC_DIR, "hf_quant_config.json.qwen4_exp.orig")
    qcfg_dst = os.path.join(TARGET_DIR, "hf_quant_config.json")
    if os.path.islink(qcfg_dst) or os.path.exists(qcfg_dst):
        os.remove(qcfg_dst)
    os.symlink(qcfg_src, qcfg_dst)
    print("Linked hf_quant_config.json -> hf_quant_config.json.qwen4_exp.orig")

    # 4. Verify loading using FreeToken's registration system
    print("\nVerifying FreeToken configuration resolution:")
    import freetoken.utils.hf as hf_utils
    from freetoken.models import register

    cfg = hf_utils.cached_load_hf_config(TARGET_DIR)
    print(f"Config loaded successfully: type={type(cfg)}, arch={getattr(cfg, 'architectures', None)}")
    spec = register.get_model_spec(cfg.architectures[0])
    print(f"ModelSpec resolved: {spec.model_cls} in {spec.module}")
    qcfg = register.checkpoint_quant_config(TARGET_DIR, cfg, spec)
    print(f"QuantConfig resolved: {qcfg}")
    print("Verification PASSED!")

if __name__ == "__main__":
    setup_overlay()
