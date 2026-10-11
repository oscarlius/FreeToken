#!/usr/bin/env python3
"""Prepare, review, or deliberately apply FTD-20261004-1.

The canonical round directories are authoritative.  ``prepare`` and ``review``
only read them.  ``apply`` is intentionally a separate, explicitly confirmed
operation for a leader-owned server checkout: it invokes the existing D04
writer once per nonconforming round, then writes an immutable release manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

RELEASE_ID = "FTD-20261004-1"
PREVIOUS_RELEASE = "FTD-20261003-1"
PAPER_VERSION = "v4.1"
ROOT_DEFAULT = Path("/data2/_shared/runs/ft_rounds")
WRITER_DEFAULT = Path("/data2/FreeToken/scripts/round_json_append.py")
REVIEWED_WRITER_SHA256 = "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"
CST = timezone(timedelta(hours=8), "CST")

# These are formal values accepted by the installed D04 writer.  Do not add a
# local verdict vocabulary: prepare verifies the writer's own allowlist below.
TARGETS = (
    ("E2-R000", "kept", "T00 baseline measurement is retained; no scientific extrapolation. Scope: measurement validity only."),
    ("E2-R003", "kept", "T07 measurement is retained; no unverified downstream claim. Scope: measurement validity only."),
    ("E2-R008", "kept", "T03 measurement is retained; zero-snapshot coverage remains a separate pending question. Scope: measurement validity only."),
    ("E2-R009", "kept", "T08 P1 measurement is retained; quality interpretation remains limited to recorded evidence. Scope: measurement validity only."),
    ("E2-R009-p64k", "kept", "T08 P2 measurement is retained; quality interpretation remains limited to recorded evidence. Scope: measurement validity only."),
    ("E2-R006", "kept", "T10 measurement is retained; prefix-hit continuation/cold-versus-warm attribution remains hypothesis. Scope: measurement validity only."),
    ("E2-R017", "kept", "T10 retry measurement is retained; prefix-hit continuation/cold-versus-warm attribution remains hypothesis. Scope: measurement validity only."),
    ("E2-R011", "kept", "T11 measurement is retained; the restore attribution remains hypothesis. Scope: measurement validity only."),
    ("E2-pre-gate-D00", "kept", "T16 D00 default-output, prefill-sequence and byte-counter gate is retained. Scope: measurement validity only."),
    ("E2-pre-gate-D01", "kept", "T16 D01 default-output, prefill-sequence and byte-counter gate is retained. Scope: measurement validity only."),
    ("E2-pre-gate-D02", "kept", "T16 D02 default-output, prefill-sequence and byte-counter gate is retained. Scope: measurement validity only."),
    ("E2-R002-gate-D03", "kept", "T16 D03 default-output, prefill-sequence and transfer-counter gate is retained. Scope: measurement validity only."),
    ("E2-R018-gate-D03", "kept", "T16 D03 continuation default-output, prefill-sequence and transfer-counter gate is retained. Scope: measurement validity only."),
    ("E2-R001", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R004", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R005", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R012", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R014", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R015", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R016", "failed_harness", "Failed harness; retain the original failure result without scientific interpretation."),
    ("E2-R021-gate-D14", "failed_harness", "D14 live gate omitted parent full-tail coverage; only two D0 arms ran. Original failure is retained."),
)
HYPOTHESIS_ROUNDS = {"E2-R006", "E2-R017", "E2-R011"}
HYPOTHESIS_CONCLUSIONS = {"E2-R006": {"P0_scientific_attribution"}, "E2-R017": {"SC1", "P0_scientific_attribution"}, "E2-R011": {"P0_scientific_attribution"}, "E2-R008": {"P0_snapshot_coverage"}, "E2-R009": {"P0_quality_alignment"}, "E2-R009-p64k": {"P0_quality_alignment"}}
CODE_VERSIONS = {
    "baseline": "E2-base@23f2e2c",
    "baseline_commit": "23f2e2caa3395837c9474735ffc83321f3b9b5a1",
    "baseline_known_defects": [{
        "reference": "plan/02_开发任务/D14_层优先快照计划与前缀续算修复.md",
        "candidate_commit": "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42",
        "description": "Layer-major child relative coordinates reset restored GDN state on eligible prefix-hit continuation; child-local snapshot planning can also corrupt donor PLE context. D14 GPU T16/T17 acceptance remains pending.",
        "unaffected_scope": "Cold output and timings; retained acquisition and timing evidence.",
        "affected_scope": "Prefix-hit continuation outputs, warm replay outputs and multi-round quality claims remain hypothesis.",
    }],
    "candidates": [
        {"name": "D03 candidate c30", "commit": "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"},
        {"name": "D03 continuation candidate f506", "commit": "f5067bbe05da51d5f78185213435a8be095a684a"},
    ],
}
FAILED_RESULT_DOCUMENTS = {
    "E2-R001": {"path": "plan/01_测试与调研/results/T03-E2-R001_20261004.md", "sha256": "ee79797319c57c862b240dbace337618c280c45e5b7b43870fc01bae641f8e58"},
    "E2-R004": {"path": "plan/01_测试与调研/results/T08-E2-R004_20261004.md", "sha256": "b29cb8b5e80d112965cc2f3a4c2a028f2368024c2da03a2fcd92633add1a82a6"},
    "E2-R005": {"path": "plan/01_测试与调研/results/T09-E2-R005_20261004.md", "sha256": "21561b13a228ee06fec8cc298582bced8a52f542fadfd2144009f951b0006b3d"},
    "E2-R012": {"path": "plan/01_测试与调研/results/T10-E2-R017_20261004.md", "sha256": "88ee1b64df813683b20d4196a53d3593f5908fa9b17d4f340fd7af6d8d17d69b"},
    "E2-R014": {"path": "plan/01_测试与调研/results/T04-E2-R014_20261004.md", "sha256": "bf132c8293cfe39d0f491e849b1b57318a227ce8df1551a94a6a571f9707092d"},
    "E2-R015": {"path": "plan/01_测试与调研/results/T04-E2-R015_20261004.md", "sha256": "b36be1a8b5e83c554cfc01a4900fb033b4cd5f3bd4d52a2a2b1bf4ecfd2cbb00"},
    "E2-R016": {"path": "plan/01_测试与调研/results/T10-E2-R016_20261004.md", "sha256": "a017128ad74a4b775d76ba8bd3698ad23896f454a2e39468893ab576d1498ecc"},
}
RELEASE_HYPOTHESIS_OVERLAYS = {
    "E2-R006": ("P0_scientific_attribution",),
    "E2-R017": ("SC1", "P0_scientific_attribution"),
    "E2-R011": ("P0_scientific_attribution",),
    "E2-R008": ("P0_snapshot_coverage",),
    "E2-R009": ("P0_quality_alignment",),
    "E2-R009-p64k": ("P0_quality_alignment",),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def no_symlinks_readonly(root: Path) -> list[str]:
    errors = []
    for item in [root, *root.rglob("*")]:
        try: info = item.lstat()
        except OSError as exc: errors.append(f"{item}: {exc}"); continue
        if stat.S_ISLNK(info.st_mode): errors.append(f"symlink: {item.relative_to(root)}"); continue
        if stat.S_IMODE(info.st_mode) & 0o222: errors.append(f"writable: {item.relative_to(root)}")
    return errors


def verify_manifest(root: Path, manifest: Path) -> list[str]:
    errors = no_symlinks_readonly(root)
    declared = set()
    try: lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc: return errors + [f"manifest unreadable: {exc}"]
    for line in lines:
        try: wanted, rel = line.split(None, 1); rel = rel.strip().removeprefix("./")
        except ValueError: errors.append(f"bad manifest row: {line!r}"); continue
        if not re.fullmatch(r'[0-9a-f]{64}', wanted) or not is_round_relative(rel):
            errors.append(f"unsafe manifest row: {rel}"); continue
        if rel in declared:
            errors.append(f"duplicate manifest row: {rel}"); continue
        candidate = root / rel
        if not safe_round_file(root, rel): errors.append(f"manifest missing/nonregular: {rel}"); continue
        if sha256(candidate) != wanted: errors.append(f"manifest digest mismatch: {rel}")
        declared.add(rel)
    excluded = {"round.json", "MANIFEST.sha256"}
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.is_symlink() and not p.relative_to(root).as_posix().startswith("round_history/") and p.relative_to(root).as_posix() not in excluded}
    if declared != actual: errors.append("manifest entry set differs from sealed payload")
    return errors


def writer_allowlist(writer: Path) -> tuple[str, set[str]]:
    observed = sha256(writer)
    if observed != REVIEWED_WRITER_SHA256: raise ValueError(f"unreviewed D04 writer hash: {observed}")
    namespace = runpy.run_path(str(writer))
    values = namespace.get("VERDICTS")
    if not isinstance(values, set) or not {"kept", "failed_harness"}.issubset(values):
        raise ValueError("D04 writer does not expose the required verdict allowlist")
    return observed, values


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: invalid or inaccessible JSON: {exc}") from exc


def cst_now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")


def safe_evidence(round_dir: Path, document: dict[str, Any], desired: str) -> list[str]:
    """Use existing, small named evidence only; absence stays an evidence gap."""
    history = document.get("verdict_history", [])
    if isinstance(history, list):
        for item in reversed(history):
            if isinstance(item, dict) and item.get("new") == desired:
                evidence = item.get("evidence")
                if isinstance(evidence, list) and evidence and all(safe_round_file(round_dir, x) for x in evidence):
                    return evidence
                return []
    names = ["round.json", "MANIFEST.sha256"]
    if desired == "failed_harness":
        names = [p.name for p in sorted(round_dir.glob("status_batch*.json"))]
    return [name for name in names if (round_dir / name).is_file()]


def is_round_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return not path.is_absolute() and not windows.drive and '\\' not in value and ".." not in path.parts and path != PurePosixPath(".")


def guarded_path(path: Path) -> Path:
    raw = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError(f"symlink path or ancestor: {raw}")
    return raw


def safe_round_file(root: Path, name: str) -> bool:
    if not is_round_relative(name):
        return False
    try:
        path = guarded_path(root / name)
        return root.resolve() in path.resolve().parents and path.is_file()
    except (ValueError, OSError):
        return False


def run_writer_check(writer: Path, round_dir: Path) -> dict[str, Any]:
    command = [sys.executable, str(writer), str(round_dir), "check"]
    run = subprocess.run(command, text=True, capture_output=True, check=False)
    return {"command": command, "returncode": run.returncode, "stdout": run.stdout.strip(), "stderr": run.stderr.strip()}


def requires_hypothesis(round_id: str, document: dict[str, Any]) -> bool:
    # The handoff names these three measured rounds specifically.  A D03 gate
    # may contain the word "continuation" while still being a valid gate, so
    # text matching would incorrectly downgrade unrelated evidence.
    return round_id in HYPOTHESIS_ROUNDS


def bindings(value: Any, path: str = "$") -> list[dict[str, str]]:
    if isinstance(value, dict):
        out = []
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if isinstance(child, str) and any(token in key.lower() for token in ("commit", "code_version", "candidate", "branch", "worktree")):
                out.append({"path": child_path, "value": child})
            out.extend(bindings(child, child_path))
        return out
    if isinstance(value, list):
        return [entry for i, child in enumerate(value) for entry in bindings(child, f"{path}[{i}]")]
    return []


def inspect_target(rounds_root: Path, writer: Path, target: tuple[str, str, str], allowed: set[str]) -> dict[str, Any]:
    round_id, desired, fallback_reason = target
    directory = rounds_root / round_id
    round_json = directory / "round.json"
    manifest = directory / "MANIFEST.sha256"
    if not directory.is_dir() or directory.is_symlink() or not round_json.is_file() or not manifest.is_file():
        return {"round_id": round_id, "desired_verdict": desired, "ready": False, "error": "missing canonical sealed round directory, round.json, or MANIFEST.sha256"}
    document = read_json(round_json)
    if (not isinstance(document, dict) or document.get('schema') != 'ft_round/v2'
            or document.get('round_id') != round_id or not document.get('closed_at')):
        return {"round_id": round_id, "desired_verdict": desired, "ready": False, "error": "round.json root is not an object"}
    check = run_writer_check(writer, directory); manifest_errors = verify_manifest(directory, manifest)
    evidence = safe_evidence(directory, document, desired)
    actual = document.get("verdict")
    hypothesis_required = requires_hypothesis(round_id, document)
    statuses = [{"id": x.get("id"), "status": x.get("status")} for x in document.get("sub_conclusions", []) if isinstance(x, dict)]
    status_map = {x["id"]: x["status"] for x in statuses}
    hypothesis_ok = all(status_map.get(key) == "hypothesis" for key in HYPOTHESIS_CONCLUSIONS.get(round_id, set()))
    history = document.get("verdict_history", [])
    formal_history = isinstance(history, list) and bool(history) and isinstance(history[-1], dict) and history[-1].get("new") == actual
    planned = actual != desired
    return {
        "round_id": round_id,
        "canonical_round_dir": str(directory),
        "desired_verdict": desired,
        "actual_verdict": actual,
        "formal_verdict_state": "append_required" if planned else ("already_appended" if formal_history else "top_level_without_matching_history"),
        "fallback_reason": fallback_reason,
        "evidence": evidence,
        "round_json_sha256": sha256(round_json),
        "manifest_sha256": sha256(manifest),
        "writer_check": check,
        "manifest_errors": manifest_errors,
        "sub_conclusions": statuses,
        "hypothesis_required": hypothesis_required,
        "hypothesis_constraint_satisfied": hypothesis_ok,
        "ready": desired in allowed and check["returncode"] == 0 and not manifest_errors and bool(evidence) and hypothesis_ok and (formal_history or (planned and actual == "pending_review")),
    }


def build_review(rounds_root: Path, writer: Path) -> dict[str, Any]:
    rounds_root = guarded_path(rounds_root)
    writer = guarded_path(writer)
    if not writer.is_file():
        raise ValueError(f"D04 writer is absent: {writer}")
    writer_digest, allowed = writer_allowlist(writer)
    items = [inspect_target(rounds_root, writer, target, allowed) for target in TARGETS]
    errors = [x["round_id"] for x in items if not x["ready"]]
    return {
        "schema": "ftd_release_prepare_review/v1",
        "release_id": RELEASE_ID,
        "mode": "read_only_review",
        "rounds_root": str(rounds_root),
        "writer": str(writer),
        "writer_sha256": writer_digest, "writer_verdicts": sorted(allowed),
        "rounds": items,
        "ready_for_apply": not errors,
        "blocking_rounds": errors,
        "planned_appends": [x["round_id"] for x in items if x.get("formal_verdict_state") == "append_required"],
    }


def release_root(review: dict[str, Any]) -> Path:
    return Path(review["rounds_root"]).parent / "ft_releases"


def previous_release_identity(review: dict[str, Any]) -> dict[str, str]:
    path = release_root(review) / PREVIOUS_RELEASE / "manifest.json"
    guarded_path(path)
    if path.stat().st_mode & 0o222 or path.parent.stat().st_mode & 0o222:
        raise ValueError('previous release is not immutable')
    raw = path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("release_id") != PREVIOUS_RELEASE:
        raise ValueError(f"previous release manifest has the wrong identity: {path}")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def snapshot_release_inputs(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read each already-reviewed input once and bind every emitted value to it."""
    snapshots = {}
    for row in review["rounds"]:
        directory = Path(row["canonical_round_dir"])
        raw = (directory / "round.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["round_json_sha256"]:
            raise ValueError(f"round changed after review: {row['round_id']}")
        document = json.loads(raw)
        if not isinstance(document, dict) or document.get("verdict") != row["actual_verdict"]:
            raise ValueError(f"round verdict changed after review: {row['round_id']}")
        manifest = directory / "MANIFEST.sha256"
        if sha256(manifest) != row["manifest_sha256"]:
            raise ValueError(f"artifact manifest changed after review: {row['round_id']}")
        evidence = []
        for name in row["evidence"]:
            if not is_round_relative(name):
                raise ValueError(f"evidence escapes canonical round: {row['round_id']}: {name!r}")
            path = directory / name
            if not safe_round_file(directory, name):
                raise ValueError(f"evidence is missing or nonregular: {row['round_id']}: {name!r}")
            evidence.append({"path": name, "sha256": sha256(path)})
        snapshots[row["round_id"]] = {"document": document, "evidence": evidence}
    return snapshots


def complete_code_versions(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    observed = []
    code_versions, commits = set(), set()
    for round_id, snapshot in snapshots.items():
        values = bindings(snapshot["document"])
        observed.append({"round_id": round_id, "bindings": values})
        for binding in values:
            if binding["path"].endswith(".code_version"):
                code_versions.add(binding["value"])
            if "commit" in binding["path"].lower():
                commits.add(binding["value"])
    return {
        "required": CODE_VERSIONS,
        "observed_code_versions": sorted(code_versions),
        "observed_commits": sorted(commits),
        "observed_round_bindings": observed,
    }


def release_hypothesis_overlays(round_id: str, document: dict[str, Any]) -> list[dict[str, str]]:
    statuses = {item.get("id"): item.get("status") for item in document.get("sub_conclusions", []) if isinstance(item, dict)}
    return [{
        "id": identifier,
        "source_status": str(statuses.get(identifier, "absent")),
        "release_status": "hypothesis",
        "reason": "Affected by confirmed E2-base actual-state corruption on layer-major prefix-hit continuation, the separate wrong-donor snapshot defect, or the cached first-subchunk new-request defect; source measurements remain retained.",
    } for identifier in RELEASE_HYPOTHESIS_OVERLAYS.get(round_id, ())]


def release_manifest(review: dict[str, Any], snapshots: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if not review["ready_for_apply"] or review["planned_appends"]:
        raise ValueError("cannot create release manifest until every D04 verdict is present and review is clean")
    snapshots = snapshots or snapshot_release_inputs(review)
    previous = previous_release_identity(review)
    return {
        "schema": "ft_data_release/v1",
        "release_id": RELEASE_ID,
        "created_at": cst_now(),
        "created_by": "Codex mainline under CODEX_HANDOFF_20261004b section 2.2 authorization",
        "paper_version": PAPER_VERSION,
        "paper_change_owner": "mainline owner; this tool does not edit paper artifacts",
        "previous_release": PREVIOUS_RELEASE,
        "previous_release_manifest": previous,
        "code_versions": complete_code_versions(snapshots),
        "rounds": [{
            "round_id": row["round_id"], "dir": row["canonical_round_dir"],
            "paper_v4_1_verdict": "pending_mainline_paper_update", "artifact_verdict": row["actual_verdict"],
            "sub_conclusions": snapshots[row["round_id"]]["document"].get("sub_conclusions", []),
            "round_json_sha256": row["round_json_sha256"], "manifest_sha256": row["manifest_sha256"],
            "key_artifacts": snapshots[row["round_id"]]["evidence"],
            "declared_bindings": bindings(snapshots[row["round_id"]]["document"]),
            "affected_subconclusion_overlays": release_hypothesis_overlays(row["round_id"], snapshots[row["round_id"]]["document"]),
            **({"local_result_document": FAILED_RESULT_DOCUMENTS[row["round_id"]]} if row["round_id"] in FAILED_RESULT_DOCUMENTS else {}),
        } for row in review["rounds"]],
        "changes_since_previous": ["Formal D04 verdict records for E2 rounds and T16 gates; retained measurement scope only."],
        "known_discrepancies": [
            "Confirmed E2-base actual-state corruption: a layer-major prefix-hit continuation whose remaining extension triggers layer-major chunking can reset FLA/GDN recurrent, convolution, and PLE n-gram state because cached_len=lo ignores origin>0.",
            "Separate confirmed E2-base defect: short hot continuation can use an incorrect donor snapshot; cached first-subchunk new-request handling is also incorrect.",
            "Cold timings and output measurements remain retained; affected prefix-hit continuation and multi-round 60-question scientific-quality claims are release-only hypothesis overlays.",
            "Candidate repairs are not GPU-verified and are not represented as fixed or accepted here.",
            "T04 E2-R002 has 814 measured points, 199 outside its recorded envelope and maximum 5.489; recovery attribution and a corrected four-role envelope remain pending. It is not promoted to a pass in this release.",
        ],
        "errata": [],
    }


def atomic_create(path: Path, payload: bytes) -> None:
    path = guarded_path(path)
    if path.exists() or not path.parent.is_dir():
        raise ValueError(f"refusing to overwrite immutable target: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=".ftd-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path)
        except FileExistsError as exc:
            raise ValueError(f"refusing to overwrite immutable target: {path}") from exc
    finally:
        Path(temp_name).unlink(missing_ok=True)


def validate_apply_destinations(review: dict[str, Any], server_release_dir: Path, local_release_copy: Path, result_out: Path | None = None) -> None:
    expected = release_root(review) / RELEASE_ID
    server = guarded_path(server_release_dir)
    local = guarded_path(local_release_copy)
    target = server / "manifest.json"
    if server != expected.resolve(strict=False):
        raise ValueError(f"server release directory must be exactly {expected}")
    if server.exists() or not server.parent.is_dir() or server.parent.is_symlink():
        raise ValueError(f"release directory must be a new child of the canonical release root: {server}")
    if local.exists() or not local.parent.is_dir() or local.parent.is_symlink():
        raise ValueError(f"local release copy must be a new file in an existing non-symlink directory: {local}")
    if local == target or server in local.parents:
        raise ValueError("local release copy must be outside the server release directory")
    if result_out is not None and str(result_out) != "-":
        output = guarded_path(result_out)
        if output in {local, target} or server in output.parents:
            raise ValueError("apply result output must not alias an immutable release artifact")
        if output.exists() or not output.parent.is_dir() or output.parent.is_symlink():
            raise ValueError(f"apply result output must be a new file in an existing non-symlink directory: {output}")


def apply(review: dict[str, Any], writer: Path, *, by: str, server_release_dir: Path, local_release_copy: Path) -> dict[str, Any]:
    if not review["ready_for_apply"]:
        raise ValueError(f"review blocked: {review['blocking_rounds']}")
    validate_apply_destinations(review, server_release_dir, local_release_copy)
    digest, _ = writer_allowlist(writer)
    if digest != review.get('writer_sha256'):
        raise ValueError('D04 writer changed after review')
    snapshot_release_inputs(review)
    for row in review["rounds"]:
        if row["formal_verdict_state"] != "append_required":
            continue
        command = [sys.executable, str(writer), row["canonical_round_dir"], "verdict", "--new", row["desired_verdict"], "--reason", row["fallback_reason"], "--evidence", *row["evidence"], "--by", by]
        run = subprocess.run(command, text=True, capture_output=True, check=False)
        if run.returncode:
            raise ValueError(f"D04 append failed for {row['round_id']}: {run.stderr.strip()}")
    post = build_review(Path(review["rounds_root"]), writer) if review['planned_appends'] else review
    snapshots = snapshot_release_inputs(post)
    manifest = release_manifest(post, snapshots)
    payload = json_bytes(manifest)
    target = server_release_dir / "manifest.json"
    server_release_dir.mkdir(mode=0o755)
    atomic_create(target, payload)
    os.chmod(target, 0o444)
    os.chmod(server_release_dir, 0o555)
    atomic_create(local_release_copy, payload)
    if target.read_bytes() != local_release_copy.read_bytes():
        raise ValueError("local release copy is not byte-identical to sealed server manifest")
    os.chmod(local_release_copy, 0o444)
    return {"review": post, "server_manifest": str(target), "local_copy": str(local_release_copy), "sha256": sha256(target)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "review", "apply"), required=True)
    parser.add_argument("--rounds-root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--writer", type=Path, default=WRITER_DEFAULT)
    parser.add_argument("--out", type=Path, required=True, help="review JSON output; may be overwritten as a local proposal")
    parser.add_argument("--release-out", type=Path, help="prepare/review: local, unsealed manifest proposal")
    parser.add_argument("--server-release-dir", type=Path, help="apply only: new /ft_releases/FTD-20261004-1 directory")
    parser.add_argument("--local-release-copy", type=Path, help="apply only: byte-identical local manifest destination")
    parser.add_argument("--by", default="Codex mainline owner under CODEX_HANDOFF_20261004 §2 authorization")
    parser.add_argument("--confirm-apply")
    args = parser.parse_args()
    try:
        review = build_review(args.rounds_root, args.writer)
        if args.mode == "review" and (not review["ready_for_apply"] or review["planned_appends"]):
            raise ValueError("review is not release-ready; inspect the written review JSON")
        if args.mode == "apply":
            if args.confirm_apply != RELEASE_ID or not args.server_release_dir or not args.local_release_copy:
                raise ValueError("apply requires --confirm-apply FTD-20261004-1, --server-release-dir, and --local-release-copy")
            validate_apply_destinations(review, args.server_release_dir, args.local_release_copy, args.out)
            result = apply(review, args.writer, by=args.by, server_release_dir=args.server_release_dir, local_release_copy=args.local_release_copy)
            if str(args.out) == "-":
                sys.stdout.buffer.write(json_bytes(result))
            else:
                atomic_create(args.out, json_bytes(result))
            return 0
        if str(args.out) == "-":
            sys.stdout.buffer.write(json_bytes(review))
        else:
            args.out.write_bytes(json_bytes(review))
        if args.release_out:
            args.release_out.write_bytes(json_bytes(release_manifest(review)))
        return 0
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
