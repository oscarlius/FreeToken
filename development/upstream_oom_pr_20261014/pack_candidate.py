"""Freeze a working-source snapshot for CPU feedback; this does not commit or publish."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "upstream_oom_recovery_20261014"
parser = argparse.ArgumentParser()
parser.add_argument("label")
args = parser.parse_args()
assert args.label.replace("_", "").isalnum()
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=SOURCE).split(b"\0")
untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=SOURCE).split(b"\0")
names = {name.decode("utf-8") for name in tracked if name}
for raw in untracked:
    if not raw:
        continue
    name = raw.decode("utf-8")
    if name == "docs/oom_recovery.md" or (name.startswith("tests/") and name.endswith(".py")):
        names.add(name)
archive = HERE / (args.label + ".zip")
manifest = {}
with archive.open("xb") as output, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
    for name in sorted(names):
        path = SOURCE / name
        assert not path.is_symlink()
        raw = path.read_bytes()
        manifest[name] = hashlib.sha256(raw).hexdigest()
        bundle.writestr(name, raw)
receipt = {"at": datetime.datetime.now().astimezone().isoformat(), "working_tree_snapshot": True,
           "base": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip(),
           "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "files": manifest}
with (HERE / (args.label + ".source.json")).open("x", encoding="utf-8") as handle:
    json.dump(receipt, handle, indent=2)
print(json.dumps({key: value for key, value in receipt.items() if key != "files"}, indent=2))
