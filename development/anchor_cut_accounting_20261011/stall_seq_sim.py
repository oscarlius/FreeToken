"""Task S structure check: replay the exact production -12 request order (CPU only, test server venv).

Order: smoke short, smoke long (both already served at 22:46), stream A, T2/00..11, L64.
Reuses segment_sim_v2.segments/lcp/floor64 and the same track rule (validated 70/70 in tasks A/A2).
Self-check: the two smoke requests must reproduce the serve.log Prefill batch lines ([512] and [512, 7745]).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
import segment_sim_v2 as sim  # noqa: E402

SRV = Path("/data2/FreeToken")
SMOKE = SRV / "runs/production/RESTORE481-MORNING-20261011-12/smoke_first"
INPUTS = SRV / "development/ophak_task_a_20261011/inputs"
L64 = SRV / "development/gemini_oom_hybrid_20261011/inputs/L64.json"
A_MSG = [{"role": "user", "content": "从 1 开始，每行写一个整数，一直写下去。"}]


def main() -> None:
    tokenizer = sim.load_tokenizer(sim.MODEL)
    manager = sim.TokenizeManager(tokenizer)
    im_start = tokenizer.convert_tokens_to_ids("<|im_start|>")
    anchors = set()
    for marker in ("</think>", "<|im_end|>"):
        ids = tokenizer.encode(marker, add_special_tokens=False)
        if len(ids) == 1:
            anchors.add(ids[0])
    tc = sim.load_toolcall_anchor_id(tokenizer, sim.toolcall_opener_for("qwen3_coder"))
    if tc is not None:
        anchors.add(tc)
    anchors = frozenset(anchors)

    seq = []
    for name in ("short", "long"):
        req = json.loads((SMOKE / f"{name}.json").read_text())["request"]
        seq.append((f"smoke_{name}", tokenizer.encode(req["prompt"], add_special_tokens=False)))
    seq.append(("A", sim.render(manager, tokenizer, A_MSG, None)))
    for k in range(12):
        p = json.loads((INPUTS / f"t2_round_{k:02d}.json").read_text())
        seq.append((f"T2/{k:02d}", sim.render(manager, tokenizer, p["messages"], p.get("tools"))))
    raw = L64.read_bytes()
    p = json.loads(raw)
    seq.append(("L64", sim.render(manager, tokenizer, p["messages"], p.get("tools"))))

    tracks: list[tuple[list[int], int]] = []
    rows = []
    for name, ids in seq:
        probe = ids[:-1]
        cached = 0
        for prev, pos in tracks:
            if pos > cached and sim.lcp(prev[:pos], probe) >= pos:
                cached = pos
        segs = sim.segments(ids, cached, anchors, anchor_cut=True, d09=False, im_start=im_start)
        for s, e in segs:
            t = sim.floor64(e - 1)
            if t > s:
                tracks.append((ids, t))
        lcp_t2 = sim.lcp(ids, seq[3][1]) if name != "T2/00" else None
        rows.append({"event": name, "prompt_tokens": len(ids), "cached": cached,
                     "segments": [e - s for s, e in segs], "lcp_with_T2_00": lcp_t2,
                     "ids_sha16": hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:16]})
    print(json.dumps({"schema": "stall_seq_sim/v1", "l64_sha256": hashlib.sha256(raw).hexdigest(),
                      "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
