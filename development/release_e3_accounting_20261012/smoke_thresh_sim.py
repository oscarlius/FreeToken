"""CPU only: segments of the two release smoke prompts under prod vs thresh32k (cold, fresh service)."""
import json, sys
from pathlib import Path
sys.path.insert(0, "/data2/FreeToken/development/anchor_cut_accounting_20261011")
import segment_sim_v2 as sim
SMOKE = Path("/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-13/smoke_first")
tok = sim.load_tokenizer(sim.MODEL)
im_start = tok.convert_tokens_to_ids("<|im_start|>")
anchors = set()
for m in ("</think>", "<|im_end|>"):
    ids = tok.encode(m, add_special_tokens=False)
    if len(ids) == 1: anchors.add(ids[0])
tc = sim.load_toolcall_anchor_id(tok, sim.toolcall_opener_for("qwen3_coder"))
if tc is not None: anchors.add(tc)
anchors = frozenset(anchors)
for name in ("short", "long"):
    req = json.loads((SMOKE / f"{name}.json").read_text())["request"]
    ids = tok.encode(req["prompt"], add_special_tokens=False)
    out = {}
    for pol, mt in (("prod", 0), ("thresh32k", 32768)):
        segs = sim.segments(ids, 0, anchors, anchor_cut=True, d09=False, im_start=im_start, min_tokens=mt)
        out[pol] = [e - s for s, e in segs]
    print(name, len(ids), out)
