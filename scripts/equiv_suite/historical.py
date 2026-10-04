"""Read-only historical replay using the retained T16 validator."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from .gate import ROLES


T16_RUNNER_SHA = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"
T16_FIXTURE_SHA = "ca114c706bcfa9474831ec089586ce612c1a836deba7a15cf692e25e0d3b7ce3"


def replay_t16(fixture: Path, runner: Path) -> dict:
    for path, expected in ((fixture, T16_FIXTURE_SHA), (runner, T16_RUNNER_SHA)):
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"retained source binding differs: {path}")
    spec = importlib.util.spec_from_file_location("ft_equiv_retained_t16", runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = json.loads(fixture.read_bytes())
    results = {}
    with tempfile.TemporaryDirectory(prefix="ft-equiv-fixtures-") as temp:
        for rid, record in data.items():
            arms = {}
            for name, arm in record["arms"].items():
                directory = Path(temp) / rid / name
                directory.mkdir(parents=True)
                (directory / "serve.log").write_text("".join(
                    "#new-seq: %d, #new-token: %d, #cached-token: %d\n" % tuple(event)
                    for event in arm["events"]), encoding="utf-8")
                (directory / "d0_prefill.jsonl").write_text("".join(
                    json.dumps(row) + "\n" for row in arm["rows"]), encoding="utf-8")
                arms["parent" if name.startswith("PARENT_") else "new"] = directory
            result = module.check_prefill(arms["parent"], arms["new"], True, True)
            if not (result["parent_rows"] == result["new_rows"] == result["all_prefill_events"] == 13):
                raise ValueError("historical full-tail fixture did not retain both 13-event sequences")
            results[rid] = {"verdict": "fixture_consistent", "comparison": result,
                            "original_failure_preserved": True, "inequivalence_claim": False,
                            "sources": record["sources"]}
    return results


def replay_r023(review: dict, *, review_sha256: str) -> dict:
    if review.get("rid") != "E2-R023-gate-T17" or review.get("batch") != 51:
        raise ValueError("historical review identity differs from R023")
    observed = review.get("observed", {})
    roles = observed.get("restore_roles", {})
    if set(roles) != set(ROLES) or any(value is not True for value in roles.values()):
        raise ValueError("R023 review does not establish all four state restores")
    return {"round": "E2-R023-gate-T17", "review_sha256": review_sha256,
            "state_restore": {"verdict": "PASS", "roles": roles},
            "child_observations": observed.get("long_children", []),
            "same_structure_reference": {"verdict": "indeterminate", "reason": "reference_missing"},
            "verdict": "indeterminate", "admitted": False,
            "historical_verdict_preserved": "not_met",
            "limits": "long-child initialization is separate evidence; short-child fresh-state flags were not captured"}
