#!/usr/bin/env python3
"""任务 B 离线核对（CPU）：冻结 payload → 渲染 → 切段规则（真实 PrefillManager）→ 与 PREREG_TASK_B_v2 逐轮比较。

用法（PYTHONPATH 指向被测代码的 python 目录，例如 release-e2 或候选工作树）：
  python3 -B offline_check_b.py --mode {release,candidate} --out <json>

步骤：
1. 渲染核对：每个 payload 按 freeze_inputs.py 的口径渲染（render_messages + render_prompt + encode），
   token 数与哈希（json.dumps(ids) 的 SHA256 前 16 位）必须与 INPUTS.json 一致，否则停止。
2. 切段：PrefillManager.schedule_next_batch 的真实代码，layer_major 开启（生产 --prefill-layer-major），
   anchor 集合与 segment_sim 相同，page_size 64，token budget 4096。
   第一次调度的 cached_len 取预登记的 cached（模拟器对前缀复用规则的结果；只替换 match_req 的返回值，
   其余分配路径用真实 CacheManager）。续段在每段结束后调用 complete_one()，cached_len 推进到段尾。
3. 比较：N = 0 的切段与 on_segments 比较；N = 32768 的切段与 thresh_segments 比较。逐轮写出。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

PRE = Path("/data2/FreeToken/development/anchor_cut_accounting_20261011/PREREG_TASK_B_v2.json")
INPUTS = Path("/data2/FreeToken/development/ophak_task_a_20261011/INPUTS.json")
TASK_A_DIR = Path("/data2/FreeToken/development/ophak_task_a_20261011")
MODEL = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"
PAGE = 64
TOKEN_BUDGET = 4096
THRESH_N = 32768


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Handle:
    """match_req 的桩句柄：只提供 cached_len 与 get_matched_indices（分配路径所需）。"""

    def __init__(self, cached_len: int) -> None:
        self.cached_len = cached_len

    def get_matched_indices(self):
        import torch

        return torch.empty(0, dtype=torch.int32)


def render_ids(manager, tokenizer, messages, tools) -> list[int]:
    from freetoken.server.generation import render_messages

    text = render_messages(copy.deepcopy(messages))
    prompt = manager.render_prompt(type("M", (), {"text": text, "tools": tools, "chat_template_kwargs": {}})())
    return tokenizer.encode(prompt, add_special_tokens=False)


def build_anchors(tokenizer) -> frozenset[int]:
    from freetoken.server.function_call_parser import toolcall_opener_for
    from freetoken.utils.hf import load_toolcall_anchor_id

    anchors = set()
    for marker in ("</think>", "<|im_end|>"):
        ids = tokenizer.encode(marker, add_special_tokens=False)
        if len(ids) == 1:
            anchors.add(ids[0])
    tc = load_toolcall_anchor_id(tokenizer, toolcall_opener_for("qwen3_coder"))
    if tc is not None:
        anchors.add(tc)
    return frozenset(anchors)


def supports_min_tokens() -> bool:
    """被测代码的 PrefillManager 是否有 prefill_anchor_cut_min_tokens 字段（候选有，release-e2 没有）。"""
    import dataclasses

    from freetoken.scheduler.prefill import PrefillManager

    return "prefill_anchor_cut_min_tokens" in {f.name for f in dataclasses.fields(PrefillManager)}


def segment_round(ids: list[int], cached: int, anchors: frozenset[int], min_tokens: int | None) -> list[int]:
    """用被测代码的 PrefillManager 切段；返回每段的 extend_len（按顺序）。
    min_tokens 为 None 时不传该参数（release-e2 的行为）。"""
    import torch

    from freetoken.core import Context, SamplingParams, get_global_ctx, set_global_ctx
    from freetoken.scheduler.cache import CacheManager
    from freetoken.scheduler.decode import DecodeManager
    from freetoken.scheduler.prefill import ChunkedReq, PrefillManager
    from freetoken.scheduler.table import TableManager
    from freetoken.scheduler.utils import PendingReq

    extra = {} if min_tokens is None else {"prefill_anchor_cut_min_tokens": min_tokens}

    try:
        get_global_ctx()
    except AssertionError:
        set_global_ctx(Context(page_size=PAGE))
    length = len(ids)
    table = torch.zeros((8, length + PAGE), dtype=torch.int32)
    cache = CacheManager(num_pages=length // PAGE + 64, page_size=PAGE, page_table=table, type="radix")
    cache.match_req = lambda req: SimpleNamespace(cuda_handle=_Handle(cached), mamba_value=None, mamba_host=None)
    cache.lock = lambda handle: None
    cache.unlock = lambda handle: None
    mgr = PrefillManager(cache, TableManager(max_running_reqs=7, page_table=table), DecodeManager(page_size=PAGE),
                         anchor_ids=anchors, prefill_anchor_cut=True, layer_major=True, **extra)
    mgr.pending_list = [PendingReq(1, torch.tensor(ids, dtype=torch.int32), SamplingParams(max_tokens=1))]
    segments: list[int] = []
    for _ in range(16):
        if not mgr.pending_list:
            break
        batch = mgr.schedule_next_batch(TOKEN_BUDGET)
        if batch is None:
            raise RuntimeError("schedule_next_batch 返回 None，切段无法继续")
        req = batch.reqs[0]
        segments.append(req.extend_len)
        if isinstance(req, ChunkedReq):
            req.complete_one()  # 段结束：cached_len 推进到段尾（同引擎 forward 之后的推进）
    if mgr.pending_list:
        raise RuntimeError("切段超过 16 次仍未完成")
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(description="任务 B 离线核对")
    parser.add_argument("--mode", choices=["release", "candidate"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from freetoken.scheduler.prefill_trace import SEG_REASON_OTHER  # noqa: F401 - 确认被测包可导入
    from freetoken.utils import load_tokenizer
    from freetoken.tokenizer.tokenize import TokenizeManager

    global SUPPORTS
    SUPPORTS = supports_min_tokens()
    prereg = json.loads(PRE.read_text(encoding="utf-8"))
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    rows = {(r["trajectory"], r["round"]): r for r in inputs["rounds"]}
    tokenizer = load_tokenizer(MODEL)
    manager = TokenizeManager(tokenizer)
    anchors = build_anchors(tokenizer)

    result = {"mode": args.mode, "package": __import__("freetoken").__file__, "anchors": sorted(anchors),
              "render": [], "rounds": [], "mismatch": []}
    for traj in ("seed_real", "T2"):
        for spec in prereg["trajectories"][traj]:
            k = spec["round"]
            row = rows[(traj, k)]
            payload = json.loads((TASK_A_DIR / row["file"]).read_bytes())
            ids = render_ids(manager, tokenizer, payload["messages"], payload.get("tools"))
            ids_hash = sha256_hex(json.dumps(ids).encode())[:16]
            render_ok = len(ids) == row["prompt_tokens"] and ids_hash == row["ids_sha256_16"]
            result["render"].append({"traj": traj, "round": k, "prompt_tokens": len(ids),
                                     "expected_prompt_tokens": row["prompt_tokens"], "ids_sha256_16": ids_hash,
                                     "ok": render_ok})
            if not render_ok:
                result["mismatch"].append(f"{traj}/{k}: 渲染不符（prompt {len(ids)} vs {row['prompt_tokens']}）")
                continue
            cached = spec["cached"]
            if SUPPORTS:
                n0 = segment_round(ids, cached, anchors, 0)
                n32 = segment_round(ids, cached, anchors, THRESH_N)
            else:  # release-e2：只有现行为，对应 N = 0 的 on_segments
                n0 = segment_round(ids, cached, anchors, None)
                n32 = None
            result["rounds"].append({"traj": traj, "round": k, "cached": cached, "prompt_tokens": len(ids),
                                     "N0": n0, "on_segments": spec["on_segments"],
                                     "N32768": n32, "thresh_segments": spec["thresh_segments"]})
            if n0 != spec["on_segments"]:
                result["mismatch"].append(f"{traj}/{k}: N=0 切段 {n0} != on {spec['on_segments']}")
            if SUPPORTS and n32 != spec["thresh_segments"]:
                result["mismatch"].append(f"{traj}/{k}: N=32768 切段 {n32} != thresh {spec['thresh_segments']}")
    result["all_render_ok"] = all(r["ok"] for r in result["render"])
    result["all_match"] = not result["mismatch"] and len(result["rounds"]) == 20
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": args.mode, "rounds": len(result["rounds"]), "render_ok": result["all_render_ok"],
                      "all_match": result["all_match"], "mismatch": result["mismatch"][:6]}, ensure_ascii=False))
    return 0 if result["all_match"] else 3


if __name__ == "__main__":
    sys.exit(main())
