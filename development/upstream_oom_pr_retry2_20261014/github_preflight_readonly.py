"""Read GitHub account/fork/upstream state without any push or API mutation."""
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

root = Path(__file__).resolve().parent
tree = root.parent / "upstream_oom_recovery_20261014"
credential = subprocess.run(["git", "-c", "credential.interactive=never", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True, check=True, cwd=tree)
fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
token = fields["password"]


def get(path):
    request = urllib.request.Request("https://api.github.com/" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "FreeToken-contribution"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


user = get("user")
fork = get("repos/oscarlius/FreeToken")
main = get("repos/FlashML-org/FreeToken/branches/main")
query = urllib.parse.urlencode({"head": "oscarlius:contrib/oom-recovery-20261014", "state": "all"})
existing = get("repos/FlashML-org/FreeToken/pulls?" + query)
print(json.dumps({"account": user["login"], "fork_push": fork["permissions"]["push"],
                  "upstream": main["commit"]["sha"], "existing_same_branch_prs":
                  [{"url": item["html_url"], "state": item["state"]} for item in existing]}, indent=2))
