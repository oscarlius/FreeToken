"""Refresh pins for the single current T16 protocol; never edit archived rounds."""
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def pin(name, values):
    path = ROOT / name
    source = path.read_text(encoding="utf-8")
    for key, digest in values.items():
        source, count = re.subn(r'(?m)^' + re.escape(key) + r' = [\'\"][0-9a-f]{64}[\'\"]$',
                               key + ' = "' + digest + '"', source)
        if count != 1:
            raise ValueError("ambiguous pin: " + name + ":" + key)
    path.write_text(source, encoding="utf-8", newline="\n")


base = sha("t16_full_tail_base_runner.py")
pin("t16_candidate_runner_full_tail.py", {"BASE_SHA256": base})
adapter = sha("t16_candidate_runner_full_tail.py")
pin("t16_d14_runner.py", {"ADAPTER_SHA256": adapter, "BASE_SHA256": base})
pin("t16_d14_cpu_stage.py", {"ADAPTER_SHA": adapter, "BASE_SHA": base})
print("base=" + base + " adapter=" + adapter + " d14=" + sha("t16_d14_runner.py"))
