"""CPU-only validation of one logical request represented by multiple prefill logs."""
from __future__ import annotations

import re


PREFILL = re.compile(r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)")


def prefill_rows(window: str) -> list[dict[str, int]]:
    return [{"new_sequences": int(sequences), "new_tokens": int(tokens), "cached_tokens": int(cached)}
            for sequences, tokens, cached in PREFILL.findall(window)]


def valid_geometry(rows: list[dict[str, int]], *, expected_cached: int, expected_new: int) -> bool:
    """Accept segmented logs for one request; never sum duplicate per-row request counts."""
    return (bool(rows)
            and all(row["cached_tokens"] == expected_cached for row in rows)
            and sum(row["new_tokens"] for row in rows) == expected_new
            and all(row["new_sequences"] == 1 for row in rows))
