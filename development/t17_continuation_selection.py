"""CPU-only case selection for a new T17/T20 runner version.

This module allocates neither a round nor a GPU.  It only emits the exact case
and ordinary-cold-envelope lists a future runner must consume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import struct
import importlib.util

INPUTS_SHA256 = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"
BOUNDARIES = (8192, 12416, 12736, 18944)
TAILS = (65, 4095, 4096, 4097, 8191, 8192, 8193)
SAMPLE4 = ("prefix-8192-tail-65", "prefix-12416-tail-4097", "prefix-12736-tail-8193", "prefix-18944-tail-4097")
DIRS = ("python/freetoken/engine", "python/freetoken/attention", "python/freetoken/scheduler", "python/freetoken/kvcache", "python/freetoken/models")
RID_RE = re.compile(r"E2-R0(?:3[5-9]|40)$")
RETAINED_SOURCE_RID = "E2-R036"
RETAINED_SOURCE_CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
RETAINED_TARGET_CANDIDATE = "a9dca443cd07e1f60d1533e0a678935a09d21636"
RETAINED_CASE_VERDICT = "measurements_pass_pending_independent_review"


class SelectionError(ValueError):
    pass


def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()

def _token_sha(ids: list[int]) -> str:
    return _sha(struct.pack("<%di" % len(ids), *ids))


def _cases(document: dict) -> list[dict]:
    if not isinstance(document, dict): raise SelectionError("realinput28 object required")
    rows = document.get("cases")
    if not isinstance(rows, list) or len(rows) != 28:
        raise SelectionError("realinput28 must contain exactly 28 cases")
    expected = {f"prefix-{length}-tail-{tail}" for length in BOUNDARIES for tail in TAILS}
    actual = {row.get("name") for row in rows if isinstance(row, dict)}
    if actual != expected or len(actual) != len(rows):
        raise SelectionError("realinput28 has unknown, duplicate, or missing canonical cases")
    for row in rows:
        try:
            length, tail = int(row["length"]), int(row["tail"])
        except (KeyError, TypeError, ValueError) as error:
            raise SelectionError("case dimensions are invalid") from error
        if row["name"] != f"prefix-{length}-tail-{tail}" or length not in BOUNDARIES or tail not in TAILS:
            raise SelectionError("case name differs from realinput28 dimensions")
        donor, query = row.get("donor"), row.get("query")
        if (not isinstance(donor, list) or not isinstance(query, list) or any(type(x) is not int for x in donor + query)
                or len(donor) != length + 1 or len(query) != length + tail
                or row.get("donor_input_ids_sha256") != _token_sha(donor) or row.get("input_ids_sha256") != _token_sha(query)):
            raise SelectionError("case lacks byte-bound real donor/query input IDs")
    return rows


def load_realinput28(path: Path | str, *, expected_document_sha256: str = INPUTS_SHA256) -> dict:
    """Load one exact raw real_inputs.json; summary receipts cannot substitute for IDs."""
    raw = Path(path).read_bytes()
    if _sha(raw) != expected_document_sha256: raise SelectionError("realinput28 raw document SHA differs")
    data = json.loads(raw)
    _cases(data)
    return data


def validate_assigned_rid(rid: str | None) -> str | None:
    if rid is not None and (not isinstance(rid, str) or RID_RE.fullmatch(rid) is None):
        raise SelectionError("only M-assigned E2-R035 through E2-R040 may identify a new run")
    return rid


def _sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SelectionError(field + " must be a lowercase SHA-256")
    return value


def _regular(path: Path, *, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise SelectionError(label + " must be a regular file")
    return path


def _retained_cases(document: dict, *, resume_review: Path | str | None,
                    resume_review_sha256: str | None, target_candidate: str | None) -> dict:
    """Recompute the narrowly reusable R036 prefix; receipt claims alone never suffice."""
    if resume_review is None or resume_review_sha256 is None:
        raise SelectionError("remaining requires an independently hashed R036 reuse receipt")
    if target_candidate != RETAINED_TARGET_CANDIDATE:
        raise SelectionError("remaining is bound to the explicit a9 target candidate")
    review_path = Path(resume_review)
    if not review_path.is_absolute():
        raise SelectionError("resume review path must be absolute")
    _regular(review_path, label="resume review")
    expected_review_sha = _sha256(resume_review_sha256, field="resume review SHA")
    if _sha(review_path.read_bytes()) != expected_review_sha:
        raise SelectionError("resume review bytes differ from caller-pinned SHA")
    try:
        receipt = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SelectionError("resume review must be JSON") from error
    if not isinstance(receipt, dict) or receipt.get("schema") != "ft_t17_retained_cases_review/v1":
        raise SelectionError("unsupported retained-cases review schema")
    if (receipt.get("source_rid") != RETAINED_SOURCE_RID
            or receipt.get("source_candidate") != RETAINED_SOURCE_CANDIDATE
            or receipt.get("target_candidate") != target_candidate):
        raise SelectionError("retained review source/target candidate binding differs")
    if receipt.get("admitted") is not False or receipt.get("model_accepted") is not False:
        raise SelectionError("retained review may not claim admission or model acceptance")
    if receipt.get("reuse_permitted") is not True:
        raise SelectionError("retained review does not explicitly permit cross-candidate reuse")
    source_round = receipt.get("source_round")
    if not isinstance(source_round, str) or not Path(source_round).is_absolute():
        raise SelectionError("retained review requires an absolute source round")
    source_root = Path(source_round)
    if source_root.is_symlink() or not source_root.is_dir():
        raise SelectionError("retained source round must be a regular directory")
    rows = _cases(document)
    by_name = {row["name"]: row for row in rows}
    retained_names = [f"prefix-{length}-tail-{tail}" for length in BOUNDARIES[:2] for tail in TAILS]
    expected = [by_name[name] for name in retained_names]
    computed = receipt.get("computed_cases")
    if not isinstance(computed, list) or len(computed) != len(expected):
        raise SelectionError("retained review must contain exactly the original first 14 cases")
    retained = []
    for position, (canonical, entry) in enumerate(zip(expected, computed), start=1):
        if not isinstance(entry, dict):
            raise SelectionError("retained computed case must be an object")
        name = canonical["name"]
        if (type(entry.get("position")) is not int or entry.get("position") != position or entry.get("case") != name
                or entry.get("input_ids_sha256") != canonical["input_ids_sha256"]
                or entry.get("verdict") != RETAINED_CASE_VERDICT):
            raise SelectionError("retained cases must be the continuous canonical R036 prefix")
        case_sha = _sha256(entry.get("case_doc_sha256"), field="case document SHA")
        schedule_sha = _sha256(entry.get("schedule_sha256"), field="schedule SHA")
        case_path = _regular(source_root / "cases" / (name + ".json"), label="retained case document")
        schedule_path = _regular(source_root / "schedules" / name / "schedule.json", label="retained schedule")
        if _sha(case_path.read_bytes()) != case_sha or _sha(schedule_path.read_bytes()) != schedule_sha:
            raise SelectionError("retained case or schedule bytes differ from review")
        try:
            case_document = json.loads(case_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SelectionError("retained case document must be JSON") from error
        if not isinstance(case_document, dict) or case_document.get("case") != name:
            raise SelectionError("retained case document identity differs")
        retained.append(name)
    return {"review": str(review_path), "review_sha256": expected_review_sha,
            "source_round": str(source_root), "source_rid": RETAINED_SOURCE_RID,
            "source_candidate": RETAINED_SOURCE_CANDIDATE,
            "target_candidate": target_candidate, "retained_cases": retained}


def _closure_module(expected_sha256: str):
    path = Path(__file__).resolve().parent / "t20_r041_sample4_closure.py"
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or _sha(path.read_bytes()) != expected_sha256:
        raise SelectionError("caller-pinned R041 closure verifier source SHA differs")
    spec = importlib.util.spec_from_file_location("t20_r041_sample4_closure", path)
    if spec is None or spec.loader is None:
        raise SelectionError("R041 closure verifier is unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _r041_sample4(document: dict, by_name: dict[str, dict], *, proof: dict) -> dict:
    required = ("r041_round", "r041_independent_review", "caller_ir_sha256", "accepted_t17_path", "accepted_t17_review",
                "expected_tag", "expected_d17_commit", "expected_d17_worktree", "expected_gate_case_sha256",
                "expected_artifacts_sha256", "expected_t16_runner_sha256", "expected_parser_sha256", "expected_d04_checker_sha256",
                "expected_verifier_sha256")
    if any(proof.get(key) in (None, "") for key in required):
        raise SelectionError("R041 sample4 proof is incomplete")
    verifier = _closure_module(proof["expected_verifier_sha256"])
    result = verifier.verify_sealed_startup(**{key: proof[key] for key in required if key != "expected_verifier_sha256"})
    if result.get("permit") is not True or result.get("admitted") is not False or result.get("model_admitted") is not False:
        raise SelectionError("R041 verifier did not issue a bounded sample4 permit")
    if not isinstance(result.get("r041_result_sha256"), str) or re.fullmatch(r"[0-9a-f]{64}", result["r041_result_sha256"]) is None:
        raise SelectionError("R041 verifier did not bind a raw-result SHA")
    rows = result.get("cases")
    if not isinstance(rows, dict) or set(rows) != set(SAMPLE4):
        raise SelectionError("R041 permit lacks exact four recomputed cases")
    for name in SAMPLE4:
        if rows[name].get("input_ids_sha256") != by_name[name]["input_ids_sha256"]:
            raise SelectionError("R041 recomputed case input SHA differs from selector inputs")
    verification_inputs = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in proof.items()
    }
    return {"verifier": str((Path(__file__).resolve().parent / "t20_r041_sample4_closure.py")),
            "verifier_sha256": proof["expected_verifier_sha256"], "r041_round": str(proof["r041_round"]),
            "independent_review": str(proof["r041_independent_review"]), "caller_ir_sha256": proof["caller_ir_sha256"],
            "accepted_t17": str(proof["accepted_t17_path"]), "accepted_t17_review": str(proof["accepted_t17_review"]),
            "verification_inputs": verification_inputs,
            "result_sha256": result.get("r041_result_sha256"), "cases": rows}


def d17_tree_proof(worktree: Path | str, base_commit: str, candidate_commit: str) -> dict:
    """Recompute, rather than trust, whether five D17-sensitive trees differ."""
    declared = Path(worktree)
    if declared.is_symlink(): raise SelectionError("D17 worktree may not be a symlink")
    root = declared.resolve()
    if not (root / ".git").exists() or not re.fullmatch(r"[0-9a-f]{40}", base_commit) or not re.fullmatch(r"[0-9a-f]{40}", candidate_commit):
        raise SelectionError("a real git worktree and complete commit identifiers are required")
    command = ["git", "-C", str(root), "diff", "--name-status", base_commit, candidate_commit, "--", *DIRS]
    run = subprocess.run(command, text=True, capture_output=True)
    if run.returncode: raise SelectionError("D17 sensitive-tree git diff failed")
    changed = []
    for line in run.stdout.splitlines():
        if not line: continue
        status, path = line.split("\t", 1)
        if not status or not any(path.startswith(directory + "/") for directory in DIRS): raise SelectionError("git diff listed a path outside the requested five trees")
        changed.append((status, path))
    if any(not any(path.startswith(directory + "/") for directory in DIRS) for _, path in changed):
        raise SelectionError("git diff listed a path outside the requested five trees")
    file_sha256 = {}
    for status, path in changed:
        show = subprocess.run(["git", "-C", str(root), "show", f"{candidate_commit}:{path}"], capture_output=True)
        if show.returncode:
            if not status.startswith("D"): raise SelectionError("candidate changed file cannot be read from git")
            file_sha256[path] = {"status": status, "sha256": None}
        else: file_sha256[path] = {"status": status, "sha256": _sha(show.stdout)}
    return {"base_commit": base_commit, "candidate_commit": candidate_commit, "git_worktree": str(root),
            "directories": list(DIRS), "command": command, "command_sha256": _sha("\0".join(command).encode()),
            "stdout_sha256": _sha(run.stdout.encode()), "changed_paths": [path for _, path in changed], "file_sha256": file_sha256,
            "five_tree_diff_empty": not changed}


def select(document: dict, *, cases: str, envelope_cases: str, run_kind: str,
           assigned_rid: str | None = None, d17_worktree: Path | str | None = None,
           d17_base: str | None = None, d17_candidate: str | None = None,
           d14_baseline_receipt: Path | str | None = None, r041_round=None, r041_independent_review=None,
           caller_ir_sha256=None, accepted_t17_path=None, accepted_t17_review=None, expected_tag=None,
           expected_d17_commit=None, expected_d17_worktree=None, expected_gate_case_sha256=None,
           expected_artifacts_sha256=None, expected_t16_runner_sha256=None, expected_parser_sha256=None,
           expected_d04_checker_sha256=None, expected_verifier_sha256=None,
           resume_review: Path | str | None = None, resume_review_sha256: str | None = None,
           target_candidate: str | None = None) -> dict:
    rows = _cases(document); validate_assigned_rid(assigned_rid)
    if run_kind == "t17" and assigned_rid == "E2-R040": raise SelectionError("E2-R040 is reserved for T20")
    if run_kind == "t20" and assigned_rid is not None and assigned_rid != "E2-R040": raise SelectionError("T20 requires E2-R040 when a RID is assigned")
    if cases not in {"all", "remaining", "t20-sample4"} or envelope_cases not in {"all", "sample4", "none"}:
        raise SelectionError("unsupported case selection")
    if run_kind not in {"t17", "t20"}: raise SelectionError("run_kind must be t17 or t20")
    if cases == "remaining" and run_kind != "t17":
        raise SelectionError("remaining continuation selection is T17-only")
    if cases != "remaining" and (resume_review is not None or resume_review_sha256 is not None):
        raise SelectionError("resume review is only valid with --cases remaining")
    by_name = {row["name"]: row for row in rows}
    if run_kind == "t17":
        if cases == "all":
            selected, reason, retained_review = [row["name"] for row in rows], "formal_t17_all28", None
        elif cases == "remaining":
            retained_review = _retained_cases(document, resume_review=resume_review,
                                               resume_review_sha256=resume_review_sha256,
                                               target_candidate=target_candidate)
            retained = retained_review["retained_cases"]
            canonical = [f"prefix-{length}-tail-{tail}" for length in BOUNDARIES for tail in TAILS]
            selected = [name for name in canonical if name not in retained]
            reason = "t17_r036_retained_prefix_remaining"
        else:
            raise SelectionError("formal T17 accepts only all 28 or an independently reviewed remaining suffix")
    elif cases == "all":
        selected, reason = [row["name"] for row in rows], "t20_explicit_all28"
    else:
        # PLAN 13:35 replaces the old five-tree criterion with R041's cold
        # and four-case bitwise continuation gate against accepted D14.
        # That immutable closure does not exist yet. Diff remains diagnostic.
        if d14_baseline_receipt is not None:
            raise SelectionError("bare D14 baseline receipt cannot replace R041 closure verifier")
        tree = (d17_tree_proof(d17_worktree, d17_base, d17_candidate)
                if d17_worktree is not None and d17_base is not None and d17_candidate is not None else None)
        proof_input = {"r041_round": r041_round, "r041_independent_review": r041_independent_review,
                       "caller_ir_sha256": caller_ir_sha256, "accepted_t17_path": accepted_t17_path,
                       "accepted_t17_review": accepted_t17_review, "expected_tag": expected_tag,
                       "expected_d17_commit": expected_d17_commit, "expected_d17_worktree": expected_d17_worktree,
                       "expected_gate_case_sha256": expected_gate_case_sha256, "expected_artifacts_sha256": expected_artifacts_sha256,
                       "expected_t16_runner_sha256": expected_t16_runner_sha256, "expected_parser_sha256": expected_parser_sha256,
                       "expected_d04_checker_sha256": expected_d04_checker_sha256, "expected_verifier_sha256": expected_verifier_sha256}
        try:
            r041_proof = _r041_sample4(document, by_name, proof=proof_input)
        except (SelectionError, OSError, ValueError, KeyError, TypeError, RuntimeError):
            r041_proof = None
        if r041_proof is None:
            selected, reason = [row["name"] for row in rows], "t20_r041_bitwise_closure_missing_or_invalid_all28"
        else:
            selected, reason = list(SAMPLE4), "t20_r041_archived_sample4"
        proof = tree
    envelope = [row["name"] for row in rows] if envelope_cases == "all" else (list(SAMPLE4) if envelope_cases == "sample4" else [])
    if run_kind == "t17" and cases == "remaining":
        # The retained prefix has no work in this round; its ordinary-cold arm
        # cannot be scheduled merely because it belongs to the historical sample.
        envelope = [name for name in envelope if name in selected]
    if any(name not in selected for name in envelope):
        raise SelectionError("ordinary-cold envelope cannot include an unselected measurement case")
    return {"schema": "ft_t17_continuation_selection/v2", "admitted": False, "requests_sent": False,
            "run_kind": run_kind, "assigned_rid": assigned_rid, "case_mode": cases, "envelope_mode": envelope_cases,
            "measurement_cases": selected, "ordinary_cold_envelope_cases": envelope,
            "case_input_sha256": {name: by_name[name]["input_ids_sha256"] for name in selected},
            "selection_reason": reason, "d17_tree_proof": proof if run_kind == "t20" and cases == "t20-sample4" else None,
            "r041_proof": r041_proof if run_kind == "t20" and cases == "t20-sample4" else None,
            "retained_review": retained_review if run_kind == "t17" and cases == "remaining" else None,
            "d14_baseline_receipt": str(d14_baseline_receipt) if d14_baseline_receipt else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--realinput28", required=True); parser.add_argument("--run-kind", choices=("t17", "t20"), required=True)
    parser.add_argument("--cases", choices=("all", "remaining", "t20-sample4"), default="all")
    parser.add_argument("--envelope-cases", choices=("all", "sample4", "none"), default="sample4")
    parser.add_argument("--rid"); parser.add_argument("--d17-worktree"); parser.add_argument("--d17-base"); parser.add_argument("--d17-candidate");
    parser.add_argument("--resume-review"); parser.add_argument("--resume-review-sha256"); parser.add_argument("--target-candidate")
    for key in ("r041_round", "r041_independent_review", "caller_ir_sha256", "accepted_t17_path", "accepted_t17_review", "expected_tag", "expected_d17_commit", "expected_d17_worktree", "expected_gate_case_sha256", "expected_artifacts_sha256", "expected_t16_runner_sha256", "expected_parser_sha256", "expected_d04_checker_sha256", "expected_verifier_sha256"): parser.add_argument("--" + key.replace("_", "-"), dest=key)
    args = parser.parse_args(); document = load_realinput28(args.realinput28)
    print(json.dumps(select(document, cases=args.cases, envelope_cases=args.envelope_cases, run_kind=args.run_kind, assigned_rid=args.rid,
                            d17_worktree=args.d17_worktree, d17_base=args.d17_base, d17_candidate=args.d17_candidate,
                            resume_review=args.resume_review, resume_review_sha256=args.resume_review_sha256,
                            target_candidate=args.target_candidate, **{key:getattr(args,key) for key in ("r041_round", "r041_independent_review", "caller_ir_sha256", "accepted_t17_path", "accepted_t17_review", "expected_tag", "expected_d17_commit", "expected_d17_worktree", "expected_gate_case_sha256", "expected_artifacts_sha256", "expected_t16_runner_sha256", "expected_parser_sha256", "expected_d04_checker_sha256", "expected_verifier_sha256")}), sort_keys=True))


if __name__ == "__main__": main()
