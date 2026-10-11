#!/usr/bin/env python3
"""CPU-only, independent R044b admission and historical-log replay.

The old retry2 bytes are input evidence only.  This script deliberately has no
launch, port, HTTP, GPU, or source-copy side effect.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[3] / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))
from experiment_harness.evidence import parse_key_values, replay_text, sha256

RID = "E2-R044b-20261010"
RETRY2_LOG = Path("/data2/_shared/runs/ft_rounds/E2-R044-night-20261010-retry2/ordinary/B1/serve.log")
R047_LOG = Path("/data2/FreeToken/runs/dev_R047_anchor_diag/E2-R047-ANCHOR-DIAG-night-20261010/serve.log")
LOCAL_OLD_TERMINAL = Path("../r044_retry2_actual_terminal_reviews/review.json")
LOCAL_OLD_STARTUP = Path("../r044_retry2_actual_startup_reviews/review.json")
TARGET_OLD_STARTUP = Path("/data2/FreeToken/runs/dev_T10/reviews/E2-R044-night-20261010-retry2/review.json")
TARGET_OLD_TERMINAL = Path("/data2/_shared/runs/ft_rounds/E2-R044-night-20261010-retry2/failed_harness.json")


def parse_server_args(text: str) -> dict[str, str]:
    """Extract a ServerArgs-like key/value dump without importing runtime code."""
    parsed = parse_key_values(text)
    if "max_extend_tokens" in parsed:
        parsed["max_prefill_length"] = parsed["max_extend_tokens"]
    return parsed


def replay_log(path: Path) -> dict:
    raw = replay_text(path)
    parsed = parse_server_args(raw.pop("text"))
    return {
        **raw,
        "parsed_keys": sorted(parsed),
        "alias": {"external": "max_prefill_length", "ServerArgs": "max_extend_tokens", "value": parsed.get("max_prefill_length")},
        "alias_resolved": "max_extend_tokens" in parsed,
    }


def historical_reviews() -> tuple[Path, Path]:
    """Bind only existing retained bytes; do not manufacture an old approval."""
    local_startup = (Path(__file__).resolve().parent / LOCAL_OLD_STARTUP).resolve()
    local_terminal = (Path(__file__).resolve().parent / LOCAL_OLD_TERMINAL).resolve()
    if local_startup.is_file() and local_terminal.is_file():
        return local_startup, local_terminal
    if TARGET_OLD_STARTUP.is_file() and TARGET_OLD_TERMINAL.is_file():
        return TARGET_OLD_STARTUP, TARGET_OLD_TERMINAL
    raise FileNotFoundError("retained R044 retry2 startup/terminal evidence is unavailable")


def packet(retry2_log: Path = RETRY2_LOG, r047_log: Path = R047_LOG) -> dict:
    old_startup, old_terminal = historical_reviews()
    return {
        "schema": "ft_r044b_cpu_admission/v1", "rid": RID,
        "scope": "new independent round packet; CPU replay only; no reclassification of prior formal result",
        "prior_three_failed_harnesses_preserved": {
            "retry2_startup_review": {"path": str(old_startup), "sha256": sha256(old_startup)},
            "retry2_terminal_evidence": {"path": str(old_terminal), "sha256": sha256(old_terminal)},
            "disposition": "diagnostic input only; original bytes and formal classification unchanged",
        },
        "historical_replay": {"retry2": replay_log(retry2_log), "r047": replay_log(r047_log)},
        "alias_contract": {"requested_flag": "--max-prefill-length", "ServerArgs_field": "max_extend_tokens", "rule": "both historical logs must resolve the alias before admission"},
        "capture_contract": {
            "direct_forward_input_output": "reuse the retained capture path; bind actual ForwardInput/ForwardOutput rather than sampler-only inference",
            "chunked_req": "retain actual ChunkedReq intermediate-prefill non-delivery receipt handling",
            "non_delivery_receipts": 19,
            "physical_capture_cap": 5824,
            "sampler_rows_cap": 4800,
            "capture_bytes_cap": 8 * 1024**3,
        },
        "startup_review_required": ["one current manifest", "CPU proof", "independent startup review", "terminal review"],
        "source_manifest": {"imported_leaf": str((SHARED / "experiment_harness/evidence.py").resolve()), "sha256": sha256(SHARED / "experiment_harness/evidence.py")},
        "gpu_admission": "root-only; no HTTP/service/GPU action by this packet",
    }


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--retry2-log", type=Path, default=RETRY2_LOG); parser.add_argument("--r047-log", type=Path, default=R047_LOG)
    args = parser.parse_args(); result = packet(args.retry2_log, args.r047_log)
    if not all(item["alias_resolved"] for item in result["historical_replay"].values()):
        raise SystemExit("admission blocked: max_prefill_length alias did not resolve in both historical logs")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
