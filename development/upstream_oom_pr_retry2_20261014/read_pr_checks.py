"""Read the published PR and current provider check state without mutation."""
import json
from pathlib import Path
import subprocess
import urllib.request

root = Path(__file__).resolve().parent
tree = root.parent / "upstream_oom_recovery_20261014"
receipt = json.loads((root / "PR_PUBLISHED.json").read_text())
credential = subprocess.run(["git", "-c", "credential.interactive=never", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True, check=True, cwd=tree)
token = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)["password"]


def get(path):
    request = urllib.request.Request("https://api.github.com/" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "FreeToken-contribution"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


repo = "repos/FlashML-org/FreeToken/"
pr = get(repo + "pulls/" + str(receipt["number"]))
runs = get(repo + "commits/" + receipt["head"] + "/check-runs")
statuses = get(repo + "commits/" + receipt["head"] + "/status")
result = {"url": pr["html_url"], "state": pr["state"], "draft": pr["draft"],
          "head": pr["head"]["sha"], "mergeable": pr["mergeable"],
          "checks": [{"name": item["name"], "status": item["status"], "conclusion": item["conclusion"]}
                     for item in runs["check_runs"]],
          "commit_status": statuses["state"], "statuses": [{"context": item["context"], "state": item["state"]}
                                                             for item in statuses["statuses"]]}
assert result["head"] == receipt["head"] and result["state"] == "open" and not result["draft"]
with (root / "PR_READBACK.json").open("x") as handle:
    json.dump(result, handle, indent=2)
print(json.dumps(result, indent=2))
