"""Read-only D05 v2 evidence inventory; never derives IDs from response text."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D0 = ROOT / "development/d10_reanalysis_20261010/closed_loop_20261010/raw_d0_2308"
TOKENS = D0 / "service/observer/tokens.jsonl"
RAW = D0 / "metrics/d0/Y/profile_export_raw.jsonl"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    token_rows = [json.loads(line) for line in TOKENS.read_text(encoding="utf-8").splitlines() if line]
    raw_rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line]
    by_uid: dict[int, int] = {}
    for row in token_rows:
        by_uid[row["uid"]] = by_uid.get(row["uid"], 0) + 1
    api_fields = {"content": False, "reasoning_content": False, "tool_calls": False}
    for raw in raw_rows:
        for response in raw.get("responses", []):
            for packet in response.get("packets", []):
                try:
                    event = json.loads(packet.get("value", ""))
                except (TypeError, json.JSONDecodeError):
                    continue
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    for field in api_fields:
                        api_fields[field] |= bool(delta.get(field))
    # These records deliberately have no following client turn / frontend-ID binding.
    unavailable = {
        "content_only": "no same-generation native-ID to following-client-messages/template-ID chain",
        "reasoning_content": "native IDs exist by UID only; no request-id/next-messages/template-ID binding",
        "tool_calls": "no tool_calls API delta and no native-ID/next-messages/template-ID chain",
    }
    result = {
        "schema": "d05_value_inventory/v1",
        "source_pins": {str(TOKENS.relative_to(ROOT)): sha(TOKENS), str(RAW.relative_to(ROOT)): sha(RAW)},
        "native_token_rows_by_uid": by_uid,
        "api_fields_seen_in_Y": api_fields,
        "forbidden_method": "re-tokenize SSE/API text to manufacture generated token IDs",
        "cases": {name: {"status": "unavailable", "reason": reason, "reusable_decode_tokens": None}
                  for name, reason in unavailable.items()},
        "decision": "BLOCKED_NO_VALUE_DECISION: no case has all required bound artifacts; do not implement or claim zero value",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
