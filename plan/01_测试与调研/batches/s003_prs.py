import json, urllib.request
UA = {"User-Agent": "freetoken-survey", "Accept": "application/vnd.github+json"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

base = "https://api.github.com/repos/FlashML-org/FreeToken"
for n in (577, 578, 505):
    d = get(f"{base}/pulls/{n}")
    if "message" in d and "state" not in d:
        print("API", d.get("message"))
        raise SystemExit(2)
    head = (d.get("head") or {}).get("sha", "")[:7]
    print(
        "PR", n,
        "state=", d.get("state"),
        "merged=", d.get("merged"),
        "merged_at=", d.get("merged_at"),
        "head=", head,
        "updated=", d.get("updated_at"),
    )
    print("  title:", (d.get("title") or "")[:140])
    cs = get(f"{base}/pulls/{n}/commits?per_page=100")
    print("  commits:", [c["sha"][:7] for c in cs])
    cm = get(f"{base}/issues/{n}/comments?per_page=100")
    last = None
    if cm:
        body = cm[-1]["body"][:300].replace("\n", " ")
        last = (cm[-1]["created_at"], cm[-1]["user"]["login"], body)
    print("  comments:", len(cm), "last:", last)
print("--- main ---")
for c in get(base + "/commits?per_page=5"):
    msg = c["commit"]["message"].splitlines()[0][:80]
    print(c["sha"][:7], c["commit"]["author"]["date"], msg)
