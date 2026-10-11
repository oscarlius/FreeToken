"""CPU-only prefill segment accounting for real agent trajectories (release-e2 481d3a7 rules).

Runs on the test server with the FreeToken venv. Renders each round exactly like the API
front end, then replays the PrefillManager chunk rules and the hybrid radix reuse rule:

  * layer-major: remain > token_budget  -> whole remaining prompt is one chunk
  * anchor cap  (prefill.py:179-200, FT_D3_ANCHOR_MODE=last): last anchor p in (c+64, scan_hi],
    scan_hi = min(c+chunk, L-64); cut = p - p % 64 if cut > c
  * D09 cut     (7d8d389 prefill.py:206-212): boundary b with c < b < c+chunk -> chunk = b-c
  * reuse       : each segment end e leaves a mamba track at floor64(e-1) (b164: e=20224 -> 20160);
                  the next request reuses the deepest track <= LCP(prev ids, ids[:L-1])

Policies: prod (anchor cut on), off (--no-prefill-anchor-cut), d09 (prod + D09 boundary cut),
inpass (one segment, exact snapshot at the D09 boundary taken inside the pass).
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

WT = Path("/data2/FreeToken/wt/release-e2/python")
sys.path.insert(0, str(WT))

from freetoken.utils.hf import load_toolcall_anchor_id  # noqa: E402
from freetoken.server.function_call_parser import toolcall_opener_for  # noqa: E402
from freetoken.server.generation import render_messages  # noqa: E402
from freetoken.tokenizer.tokenize import TokenizeManager  # noqa: E402
from freetoken.utils import load_tokenizer  # noqa: E402

PAGE = 64
TOKEN_BUDGET = 4096  # production --max-prefill-length 4096
MODEL = "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay"


def floor64(x: int) -> int:
    return x - x % PAGE


def segments(ids: list[int], cached: int, anchors: frozenset[int], *, anchor_cut: bool,
             d09: bool, im_start: int) -> list[tuple[int, int]]:
    total = len(ids)
    boundary = None
    if d09:
        starts = [i for i, t in enumerate(ids) if t == im_start]
        if len(starts) >= 2 and starts[-2] >= 8192 and starts[-1] - starts[-2] <= 1024:
            boundary = starts[-2]
    out, c = [], cached
    while c < total:
        remain = total - c
        chunk = min(TOKEN_BUDGET, remain)
        if remain > TOKEN_BUDGET:  # layer-major whole
            chunk = remain
        if anchor_cut and anchors and chunk > PAGE:
            scan_hi = min(c + chunk, total - PAGE)
            p = scan_hi
            while p > c + PAGE:
                if ids[p] in anchors:
                    cut = p - p % PAGE
                    if cut > c:
                        chunk = cut - c
                    break
                p -= 1
        if boundary is not None and c < boundary < c + chunk:
            chunk = boundary - c
        out.append((c, c + chunk))
        c += chunk
    return out


def lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def replay(rounds: list[list[int]], anchors: frozenset[int], im_start: int, policy: str):
    tracks: list[tuple[list[int], int]] = []  # (ids, track position)
    rows = []
    for k, ids in enumerate(rounds):
        probe = ids[:-1]
        cached = 0
        for prev, pos in tracks:
            if pos <= cached:
                continue
            if lcp(prev[:pos], probe) >= pos:
                cached = pos
        if policy == "inpass":
            segs = [(cached, len(ids))]
        else:
            segs = segments(ids, cached, anchors, anchor_cut=policy in ("prod", "d09"),
                            d09=policy == "d09", im_start=im_start)
        for s, e in segs:
            t = floor64(e - 1)
            if t > s:
                tracks.append((ids, t))
        if policy == "inpass":
            starts = [i for i, t in enumerate(ids) if t == im_start]
            if len(starts) >= 2:
                tracks.append((ids, starts[-2]))  # exact boundary snapshot taken inside the pass
        rows.append({"round": k, "prompt_tokens": len(ids), "cached": cached,
                     "segments": [e - s for s, e in segs]})
    return rows


def render(manager, tokenizer, messages, tools) -> list[int]:
    text = render_messages(copy.deepcopy(messages))
    prompt = manager.render_prompt(type("M", (), {"text": text, "tools": tools,
                                                  "chat_template_kwargs": {}})())
    return tokenizer.encode(prompt, add_special_tokens=False)


def main() -> None:
    tokenizer = load_tokenizer(MODEL)
    manager = TokenizeManager(tokenizer)
    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    anchors = set()
    for marker in ("</think>", "<|im_end|>"):
        ids = tokenizer.encode(marker, add_special_tokens=False)
        if len(ids) == 1:
            anchors.add(ids[0])
    tc = load_toolcall_anchor_id(tokenizer, toolcall_opener_for("qwen3_coder"))
    if tc is not None:
        anchors.add(tc)
    anchors = frozenset(anchors)

    trajectories = {}
    seed_dir = Path("/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real")
    seed = []
    for i in range(8):
        p = json.loads((seed_dir / f"round-{i:02d}.payload.json").read_text())
        seed.append(render(manager, tokenizer, p["messages"], p.get("tools")))
    trajectories["seed_real"] = seed

    spec = importlib.util.spec_from_file_location("agent_trace", "/data2/FreeToken/scripts/agent_trace.py")
    agent_trace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_trace)
    trace = json.loads(Path("/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json").read_text())
    trajectories["T2"] = [render(manager, tokenizer, r["messages"], trace.get("tools") or agent_trace.tool_specs())
                          for r in trace["rounds"]]

    out = {"schema": "anchor_cut_accounting/v1", "anchors": sorted(anchors), "im_start": im_start,
           "token_budget": TOKEN_BUDGET, "page": PAGE, "trajectories": {}}
    for name, rounds in trajectories.items():
        out["trajectories"][name] = {
            "ids_sha256": [hashlib.sha256(json.dumps(r).encode()).hexdigest()[:16] for r in rounds],
            "policies": {pol: replay(rounds, anchors, im_start, pol) for pol in ("prod", "off", "d09", "inpass")},
        }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
