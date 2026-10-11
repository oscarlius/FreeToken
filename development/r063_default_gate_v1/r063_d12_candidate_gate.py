"""Fail-closed binding contract for the D12 four-arm T16 candidate.

This module deliberately has no --run path.  It becomes executable only after
root supplies the final candidate commit and an independent review binds the
listed closure.  It does not replace the retained full-tail protocol.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RID = "E2-R063-gate-D12"
PARENT_COMMIT = "effb9969706922ddad9e59b96377e46469ebe97f"
PARENT_WORKTREE = "/data2/FreeToken/wt/e2base1-p1"
CANDIDATE_WORKTREE = "/data2/FreeToken/wt/e2d12-short-suffix"
REUSED_NATIVE_SOURCE_COMMIT = None
FINAL_CANDIDATE_COMMIT = "8f6a912ea6066f192c37dc74435efc9da0c7591c"
ARMS = ("PARENT_D0OFF", "CANDIDATE_D0OFF", "PARENT_D0ON", "CANDIDATE_D0ON")
SOURCE_CLOSURE = (
    "r063_d12_candidate_gate.py", "r063_t16_full_runner.py",
    "r063_owned_launch.py",
    "t16_private_port_dryrun_r063_v1.py", "round_json_append.py", "d07_g3g4_prepare.py",
    "t16_frozen_helpers_v1/cold_eq.py", "t16_frozen_helpers_v1/probe_ft_cold32k.py",
    "t16_frozen_helpers_v1/ft_probe_ckpt_tax.py", "t16_frozen_helpers_v1/serve_args_diff.py",
)


def require_final_candidate(candidate_commit: str | None = None) -> str:
    """Reject all preparation until root binds the final reviewed commit."""
    if FINAL_CANDIDATE_COMMIT is None:
        raise RuntimeError("R063 final candidate commit is unresolved; GPU execution is forbidden")
    if not isinstance(FINAL_CANDIDATE_COMMIT, str) or not re.fullmatch(r"[0-9a-f]{40}", FINAL_CANDIDATE_COMMIT):
        raise RuntimeError("R063 final candidate binding is malformed")
    if candidate_commit is not None and candidate_commit != FINAL_CANDIDATE_COMMIT:
        raise RuntimeError("R063 supplied candidate differs from the final binding")
    return FINAL_CANDIDATE_COMMIT


def candidate_binding(candidate_commit: str | None = None) -> dict:
    commit = require_final_candidate(candidate_commit)
    return {
        "schema": "ft_r063_d12_candidate_binding/v1", "rid": RID,
        "parent_commit": PARENT_COMMIT, "parent_worktree": PARENT_WORKTREE,
        "candidate_commit": commit, "candidate_worktree": CANDIDATE_WORKTREE,
        "arms": list(ARMS), "config": {"kv_reserve_tokens": 98304, "max_seq_len_override": 98304, "memory_ratio": 0.88},
        "disabled": {"FT_DEV_HYB_TRACE": True, "fault_injection": True, "pause": True},
        "native_reuse": {"source_commit": REUSED_NATIVE_SOURCE_COMMIT, "cpp_source_unchanged": True,
                         "required_provenance": "bind final worktree artifact, source, and current commit"},
        "requires": ["full T16 cold plus five multi-probe protocol", "D0 shutdown/full tail", "same output/token comparisons",
                     "owned process-birth and lock lifecycle", "real FILEdry consumer", "independent startup review", "user GPU approval"],
        "source_closure": list(SOURCE_CLOSURE),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--run", action="store_true")
    options = parser.parse_args(argv)
    if options.run:
        raise RuntimeError("R063 has no executable runner before final binding, FILEdry, review, and user approval")
    print(json.dumps(candidate_binding(options.candidate_commit), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
