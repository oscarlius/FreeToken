"""Publish only the reviewed OOM contribution after its GPU/restoration gate passes."""
import json
import subprocess
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
TREE = ROOT.parent / "upstream_oom_recovery_20261014"
HEAD = "a4ebbfda742fbad1df240621647014a39c70acd6"
BASE = "f02fbb16a213f5c81094e4017c988d41f0164141"
BRANCH = "contrib/oom-recovery-20261014"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=TREE, text=True).strip()


terminal = json.loads((ROOT / "gpu_evidence/GPU_WINDOW_TERMINAL.json").read_text())
review = json.loads((ROOT / "INDEPENDENT_GPU_REVIEW.json").read_text())
assert terminal["classification"] == "kept" and terminal["restored"] is True
assert review["verdict"] == "PASS" and review["candidate"] == HEAD
assert git("rev-parse", "HEAD") == HEAD and not git("status", "--porcelain")
subprocess.run(["git", "fetch", "origin", "main"], cwd=TREE, check=True)
assert git("rev-parse", "origin/main") == BASE, "Upstream moved; inspect before publishing"
subprocess.run(["git", "diff", "--check", BASE + "...HEAD"], cwd=TREE, check=True)

# The native credential helper supplies the existing GitHub credential. Never print or persist it.
credential = subprocess.run(["git", "-c", "credential.interactive=never", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True, check=True, cwd=TREE)
fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
token = fields["password"]


def api(path, body=None):
    request = urllib.request.Request("https://api.github.com/" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "FreeToken-contribution",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError("GitHub HTTP " + str(error.code) + ": " + error.read().decode()[:1500]) from None


assert api("user")["login"] == "oscarlius"
fork = api("repos/oscarlius/FreeToken")
assert fork["fork"] and fork["parent"]["full_name"] == "FlashML-org/FreeToken"
assert fork["permissions"]["push"]
subprocess.run(["git", "-c", "credential.interactive=never", "push",
    "https://github.com/oscarlius/FreeToken.git", "HEAD:refs/heads/" + BRANCH], cwd=TREE, check=True)
query = urllib.parse.urlencode({"head": "oscarlius:" + BRANCH, "state": "all"})
existing = api("repos/FlashML-org/FreeToken/pulls?" + query)
body = (ROOT / "PR_BODY.md").read_text(encoding="utf-8")
if existing:
    assert len(existing) == 1 and existing[0]["state"] == "open"
    result = existing[0]
    assert result["body"] == body
else:
    result = api("repos/FlashML-org/FreeToken/pulls", {
        "title": "fix(server): opt-in backend recovery after runtime CUDA OOM",
        "head": "oscarlius:" + BRANCH, "base": "main", "body": body, "draft": False})
number = result["number"]
fresh = api(f"repos/FlashML-org/FreeToken/pulls/{number}")
files = api(f"repos/FlashML-org/FreeToken/pulls/{number}/files?per_page=100")
expected = set(git("diff", "--name-only", BASE + "...HEAD").splitlines())
assert fresh["head"]["sha"] == HEAD and fresh["base"]["ref"] == "main"
assert fresh["body"] == body and {item["filename"] for item in files} == expected
assert not fresh["draft"] and fresh["state"] == "open"
receipt = {"url": fresh["html_url"], "number": number, "head": HEAD,
           "base": fresh["base"]["sha"], "files": sorted(expected), "state": fresh["state"],
           "body_readback_matches": True, "mergeable": fresh["mergeable"]}
with (ROOT / "PR_PUBLISHED.json").open("x") as handle:
    json.dump(receipt, handle, indent=2)
print(json.dumps(receipt, indent=2))
