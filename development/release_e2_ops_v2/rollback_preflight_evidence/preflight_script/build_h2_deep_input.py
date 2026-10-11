"""Bind the checked-in cached_rows regex for read-only H2 analysis."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "r066b_canary_v2" / "sdk_adapter.py"
OUT = Path(__file__).resolve().parents[1] / "h2_deep_input.json"

def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"def cached_rows\(text\):\s*\n\s*return .*?re\.findall\(r'([^']+)'", text)
    if not match:
        raise RuntimeError("cached_rows regex unavailable")
    payload = {"schema":"ft_release_h2_deep_input/v1", "cached_rows_source":{"path":str(SOURCE),"sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"regex":match.group(1)}}
    OUT.write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
