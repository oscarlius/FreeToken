# 按提交号在本地 plan/ 档案中交叉检索（只读），输出 JSON 供 VERSION_REGISTRY 编写使用。
import json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))           # freetoken/development/kimi_phase2_20261011
FT = os.path.abspath(os.path.join(ROOT, "..", ".."))        # freetoken/
TSV = os.path.join(ROOT, "version_registry_raw.tsv")
SEARCH_ROOTS = [
    os.path.join(FT, "plan", "02_开发任务"),
    os.path.join(FT, "plan", "01_测试与调研"),
]
SEARCH_FILES = [os.path.join(FT, "plan", "COORDINATION_LOG.md")]

rows = []
with open(TSV, encoding="utf-8") as f:
    for line in f:
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 6:
            rows.append(parts[:6])

hashes = {}  # hash -> [name,...]
for name, head, *_ in rows:
    if head == "ERROR":
        continue
    hashes.setdefault(head, []).append(name)

needles = {}
for h in hashes:
    needles[h] = [h, h[:8]]

hits = {h: [] for h in hashes}

def scan_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return
    for i, text in enumerate(lines, 1):
        for h, pats in needles.items():
            for p in pats:
                if p in text:
                    hits[h].append({
                        "file": os.path.relpath(path, FT),
                        "line": i,
                        "text": text.strip()[:240],
                        "pat": p,
                    })
                    break

for root in SEARCH_ROOTS:
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            scan_file(os.path.join(dirpath, fn))
for p in SEARCH_FILES:
    scan_file(p)

out = []
for name, head, log, dirty, a481, abd57 in rows:
    out.append({
        "worktree": name, "head": head, "log": log, "dirty_lines": dirty,
        "contains_481": a481, "contains_bd57": abd57,
        "hits": hits.get(head, []),
    })

with open(os.path.join(ROOT, "version_registry_xref.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

for e in out:
    print(f"{e['worktree']}\t{e['head'][:8]}\thits={len(e['hits'])}")
