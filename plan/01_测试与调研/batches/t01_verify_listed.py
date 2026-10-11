import json, hashlib
m = json.load(open("manifest.json", encoding="utf-8"))
def h(p):
    x = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            x.update(b)
    return x.hexdigest()
ok = bad = miss = 0
items = []
for d in m["directories"].values():
    items += [(f["path"], f["sha256"]) for f in d["files"]]
for r in m["rounds"]:
    rj = r["round_json"]
    if rj.get("path") and len(rj.get("sha256", "")) == 64:
        items.append((rj["path"], rj["sha256"]))
    items += [(b["path"], b["sha256"]) for b in r["batch_logs"] if len(b["sha256"]) == 64]
items += [(b["path"], b["sha256"]) for b in m["global_batch_logs"] if len(b["sha256"]) == 64]
for e in m["external_sources"]:
    if "sha256" in e and "path" in e:
        items.append((e["path"], e["sha256"]))
seen = set()
for p, s in items:
    if p in seen:
        continue
    seen.add(p)
    try:
        a = h(p)
    except FileNotFoundError:
        miss += 1
        print("MISSING", p)
        continue
    if a == s:
        ok += 1
    else:
        bad += 1
        print("MISMATCH", p, "listed", s, "now", a)
print("VERIFY ok=%d mismatch=%d missing=%d" % (ok, bad, miss))
