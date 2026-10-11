"""Apply B-module (persistent decode workspace) to fused_nvfp4.py. Idempotent."""
import sys

path = sys.argv[1]
src = open(path).read()

if "_DECODE_WS_M_MAX" not in src:
    src = src.replace(
        "from typing import Any, Dict\n",
        "import os\n\nfrom typing import Any, Dict\n",
        1,
    )
    anchor = "def _fused_experts_decode_nvfp4(\n"
    ws_code = (
        '# --- B-module: persistent decode workspace (FT_MOE_DECODE_WS=1) ---\n'
        '_DECODE_WS_M_MAX = 8\n'
        '_DECODE_WS_ENABLED = os.environ.get("FT_MOE_DECODE_WS", "0") == "1"\n'
        '_decode_ws = {}\n'
        '\n'
        '\n'
        'def _decode_ws_get(dev, dt, top_k, two_i, inter, H):\n'
        '    key = (str(dev), str(dt), top_k, two_i, inter, H)\n'
        '    ws = _decode_ws.get(key)\n'
        '    if ws is None:\n'
        '        ws = {\n'
        '            "ic1": torch.empty((_DECODE_WS_M_MAX, top_k, two_i), device=dev, dtype=dt),\n'
        '            "ic2": torch.empty((_DECODE_WS_M_MAX * top_k, inter), device=dev, dtype=dt),\n'
        '            "ic3": torch.empty((_DECODE_WS_M_MAX, top_k, H), device=dev, dtype=dt),\n'
        '            "out": torch.empty((_DECODE_WS_M_MAX, H), device=dev, dtype=dt),\n'
        '        }\n'
        '        _decode_ws[key] = ws\n'
        '    return ws\n'
        '\n'
        '\n'
    )
    assert src.count(anchor) == 1, "anchor not unique"
    src = src.replace(anchor, ws_code + anchor, 1)

old_block = """    ic1 = torch.empty((M, top_k, two_i), device=dev, dtype=dt)
    gemm_fn(
        hidden_states, gate_up_packed, gate_up_scale, gate_up_global,
        ic1, topk_weights, topk_ids, apply_router_weight_on_input, False,
    )
    ic2 = torch.empty((M * top_k, inter), device=dev, dtype=dt)
    gated_act_and_mul(activation, ic1.view(-1, two_i), ic2, alpha=act_alpha, limit=act_limit)
    ic3 = torch.empty((M, top_k, H), device=dev, dtype=dt)
    gemm_fn(
        ic2, down_packed, down_scale, down_global,
        ic3, topk_weights, topk_ids, not apply_router_weight_on_input, True,
    )
    out = torch.empty_like(hidden_states)
    moe_sum_reduce_triton(ic3, out)
    return out"""

new_block = """    use_ws = _DECODE_WS_ENABLED and M <= _DECODE_WS_M_MAX
    ws = _decode_ws_get(dev, dt, top_k, two_i, inter, H) if use_ws else None
    ic1 = ws["ic1"][:M] if use_ws else torch.empty((M, top_k, two_i), device=dev, dtype=dt)
    gemm_fn(
        hidden_states, gate_up_packed, gate_up_scale, gate_up_global,
        ic1, topk_weights, topk_ids, apply_router_weight_on_input, False,
    )
    ic2 = ws["ic2"][: M * top_k] if use_ws else torch.empty((M * top_k, inter), device=dev, dtype=dt)
    gated_act_and_mul(activation, ic1.view(-1, two_i), ic2, alpha=act_alpha, limit=act_limit)
    ic3 = ws["ic3"][:M] if use_ws else torch.empty((M, top_k, H), device=dev, dtype=dt)
    gemm_fn(
        ic2, down_packed, down_scale, down_global,
        ic3, topk_weights, topk_ids, not apply_router_weight_on_input, True,
    )
    out = ws["out"][:M] if use_ws else torch.empty_like(hidden_states)
    moe_sum_reduce_triton(ic3, out)
    return out"""

assert src.count(old_block) == 1, f"body anchor count={src.count(old_block)}"
src = src.replace(old_block, new_block, 1)
import ast

ast.parse(src)
open(path, "w").write(src)
print(f"patched {path}")
