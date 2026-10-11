"""Final pytest comparator for all four approved batch/single API pairs."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sdk_completions import compare_completion


@pytest.mark.skipif("D16_API_RUN_DIR" not in os.environ, reason="requires completed owned scope")
def test_all_four_approved_pairs_have_equal_text_finish_and_usage():
    root = Path(os.environ["D16_API_RUN_DIR"])
    scope = json.loads((Path(__file__).parent / "scope_payloads.json").read_text())
    rows: dict[str, list[dict]] = {}
    for item in scope["calls"]:
        name = "single.json" if item["label"] == "single" else f"{item['label']}.json"
        artifact = json.loads((root / item["service"] / "calls" / name).read_text())
        rows.setdefault(item["compare"], []).append(artifact["projection"])
    assert sorted(rows) == ["pair_0", "pair_1", "pair_2", "pair_3"]
    for pair, values in rows.items():
        assert len(values) == 2, pair
        compare_completion(*values)
    target = root / "comparison.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump({"schema": "ft_d16_api_comparison/v2", "pairs": sorted(rows),
                   "text_finish_usage_equal": True}, handle, sort_keys=True, indent=2)
        handle.write("\n")
