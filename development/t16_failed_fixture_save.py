"""Retain compact regression fields and source hashes from two actual failures."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
process = subprocess.run(["python", str(HERE / "remote.py"), str(HERE / "t16_failed_fixture_read.sh")],
                         capture_output=True, check=True)
data = json.loads(process.stdout)
path = HERE / "tests/fixtures/t16_failed_full_tail.json"
path.parent.mkdir(exist_ok=True)
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(data, stream, indent=2)
    stream.write("\n")
print(str(path), path.stat().st_size)
