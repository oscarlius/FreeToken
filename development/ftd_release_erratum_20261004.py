#!/usr/bin/env python3
"""Create the immutable erratum for the sealed FTD-20261004-1 release.

This tool deliberately creates a separate document.  It never edits the base
manifest, round records, raw artifacts, or paper material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


ERRATUM_ID = "FTD-20261004-1-erratum-1"
BASE_RELEASE_ID = "FTD-20261004-1"
BASE_RELEASE_SHA256 = "836217380206fef106aa71dd6713cab0f18222932b9f884ba36d5ac4130ef014"
BASE_CODE_VERSION = "E2-base@23f2e2c"
REQUIRED_ROUNDS = frozenset({"E2-R006", "E2-R017", "E2-R008", "E2-R009", "E2-R009-p64k"})

# These are source documents, not copied release artifacts.  Verifying them
# makes the erratum's scope auditable without changing their immutable source.
SOURCE_REFERENCES = {
    "plan/CODEX_HANDOFF_20261004b.md": "9d4876cceeb157efd8d765482689967a5fbe6d314904fb2ea81fdcd0c4a9b651",
    "plan/02_开发任务/D14_层优先快照计划与前缀续算修复.md": "83a87d5bab0e08c5dae7d0c740c002b368ecef47c5f44cda52afeceae9f7a7af",
    "plan/01_测试与调研/results/T03-E2-R008_20261004.md": "5640ae5a4a012f2e4bc8831f47ac769835824b89d38d69d3ac405087b84fbcfa",
    "plan/01_测试与调研/results/T08-E2-R009_20261004.md": "77b5289576a70b13a0b1f21dbb5f187aa0124ceab8a1ed4901e0f891dbc87ff6",
    "plan/01_测试与调研/results/T08-E2-R009-p64k_20261004.md": "854696dddef91e63d95046a750d39314527d63af34ff0562f99a396935907422",
}


class ErratumError(RuntimeError):
    """An invariant needed for an immutable erratum was not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _existing_ancestors(path: Path) -> Iterable[Path]:
    current = path
    while True:
        if current.exists() or current.is_symlink():
            yield current
        if current.parent == current:
            return
        current = current.parent


def reject_alias(path: Path, label: str) -> None:
    """Reject links anywhere in a relevant existing path chain.

    Resolving a link and then writing through it is still an alias.  This guard
    is intentionally stricter than Path.resolve() so the named destination is
    the exact release location being reviewed.
    """
    for candidate in _existing_ancestors(path):
        attributes = getattr(candidate.lstat(), "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if candidate.is_symlink() or (reparse_point and attributes & reparse_point):
            raise ErratumError(f"{label} must not be a symlink or be below one: {candidate}")


def require_regular_file(path: Path, label: str) -> None:
    reject_alias(path, label)
    if not path.exists() or not path.is_file():
        raise ErratumError(f"{label} must be an existing regular file: {path}")


def require_read_only(path: Path, label: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o222:
        raise ErratumError(f"{label} must be sealed read-only: {path} mode {mode:04o}")


def verify_source_references(repo_root: Path) -> dict[str, str]:
    reject_alias(repo_root, "repo root")
    if not repo_root.is_dir():
        raise ErratumError(f"repo root is not a directory: {repo_root}")
    verified: dict[str, str] = {}
    for relative, expected_hash in SOURCE_REFERENCES.items():
        source = repo_root / Path(relative)
        require_regular_file(source, f"source reference {relative}")
        actual_hash = sha256_file(source)
        if actual_hash != expected_hash:
            raise ErratumError(
                f"source reference hash mismatch for {relative}: {actual_hash} != {expected_hash}"
            )
        verified[relative] = actual_hash

    r009_text = (repo_root / "plan/01_测试与调研/results/T08-E2-R009_20261004.md").read_text(
        encoding="utf-8"
    )
    if "60题" not in r009_text or "长多轮" not in r009_text:
        raise ErratumError("E2-R009 source result does not establish the 60-question multi-turn evidence")
    return verified


def _round_ids(document: dict[str, Any]) -> set[str]:
    rounds = document.get("rounds")
    if not isinstance(rounds, list):
        raise ErratumError("base release has no rounds list")
    ids = {row.get("round_id") for row in rounds if isinstance(row, dict)}
    if not REQUIRED_ROUNDS.issubset(ids):
        missing = sorted(REQUIRED_ROUNDS - ids)
        raise ErratumError(f"base release is missing affected rounds: {missing}")
    return {value for value in ids if isinstance(value, str)}


def verify_base_release(base_manifest: Path, expected_hash: str = BASE_RELEASE_SHA256) -> dict[str, Any]:
    require_regular_file(base_manifest, "base manifest")
    require_read_only(base_manifest, "base manifest")
    actual_hash = sha256_file(base_manifest)
    if actual_hash != expected_hash:
        raise ErratumError(f"base manifest hash mismatch: {actual_hash} != {expected_hash}")
    try:
        document = json.loads(base_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErratumError(f"base manifest is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ErratumError("base manifest root must be an object")
    if document.get("release_id") != BASE_RELEASE_ID:
        raise ErratumError(f"base manifest release_id is not {BASE_RELEASE_ID}")
    if document.get("schema") != "ft_data_release/v1":
        raise ErratumError("base manifest schema is not ft_data_release/v1")
    required = document.get("code_versions", {}).get("required", {})
    if required.get("baseline") != BASE_CODE_VERSION:
        raise ErratumError(f"base manifest baseline is not {BASE_CODE_VERSION}")
    _round_ids(document)
    return document


def _override(round_id: str, claim_id: str, evidence_scope: str) -> dict[str, str]:
    return {
        "round_id": round_id,
        "claim_id": claim_id,
        "release_status": "hypothesis",
        "basis": "Confirmed E2-base prefix-hit layer-major state corruption; D14 has no accepted GPU runtime proof.",
        "evidence_scope": evidence_scope,
    }


def build_erratum(base_manifest: Path, repo_root: Path, *, expected_base_hash: str = BASE_RELEASE_SHA256) -> dict[str, Any]:
    """Build the exact release-only overlay after all source checks pass."""
    base_document = verify_base_release(base_manifest, expected_base_hash)
    source_hashes = verify_source_references(repo_root)
    base_round_ids = sorted(_round_ids(base_document))
    overrides = [
        _override("E2-R006", "prefix_hit_continuation_output", "Prefix-hit continuation output semantics."),
        _override("E2-R006", "cold_versus_warm_output", "The cold-versus-warm output comparison where warm invokes prefix reuse."),
        _override("E2-R017", "prefix_hit_continuation_output", "Prefix-hit continuation output semantics."),
        _override("E2-R017", "cold_versus_warm_output", "The cold-versus-warm output comparison where warm invokes prefix reuse."),
        _override("E2-R008", "warm_replay_output_text", "Warm replay output text only; cold timings and cold output remain retained."),
        _override("E2-R009", "warm_replay_output_text", "Warm replay output text only; cold timings and cold output remain retained."),
        _override("E2-R009", "multi_round_60_quality", "The release-contained 60-question multi-turn evidence is E2-R009."),
        _override("E2-R009-p64k", "warm_replay_output_text", "Warm replay output text only; cold timings and cold output remain retained."),
    ]
    return {
        "schema": "ft_data_release_erratum/v1",
        "erratum_id": ERRATUM_ID,
        "base_release": {
            "release_id": BASE_RELEASE_ID,
            "manifest_sha256": expected_base_hash,
            "manifest_name": base_manifest.name,
            "sealed_read_only_verified": True,
        },
        "source_references": source_hashes,
        "known_defect": {
            "status": "confirmed",
            "base_code_version": BASE_CODE_VERSION,
            "description": (
                "For a true prefix hit whose remaining extension enters layer-major chunking, "
                "_build_layer_major_chunks uses cached_len=lo and loses origin>0 on its first child. "
                "FLA is initialized without restored state, GDN recurrent/conv state is fresh, and PLE ngram context resets at EOS."
            ),
            "scope": "Single-request extension beyond the 4096 prefill budget; short hot continuation may also be affected by the separate wrong-donor snapshot defect.",
            "candidate_status": "D14 candidate is not GPU-verified or accepted.",
        },
        "release_only_claim_overrides": overrides,
        "protocol_scoped_rules": [
            {
                "claim_id": "multi_round_60_quality",
                "release_status": "hypothesis",
                "protocol": "E2-base multi-turn 60-question quality",
                "release_contained_evidence_rounds": ["E2-R009"],
                "absent_artifacts": "No other base-release round is asserted to contain a 60-question multi-turn result; no membership is fabricated.",
            }
        ],
        "preserved_base_claims": {
            "raw_artifacts": "Unchanged; this erratum contains source references and no raw-artifact copies.",
            "cold_timing_and_output": "Cold no-prefix-hit timing and output claims remain as sealed in the base release.",
            "cold_rounds": ["E2-R000", "E2-R003", "E2-R008", "E2-R009", "E2-R009-p64k"],
        },
        "base_round_ids_observed": base_round_ids,
    }


def canonical_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def require_new_destination(path: Path, label: str) -> None:
    reject_alias(path, label)
    if path.exists() or path.is_symlink():
        raise ErratumError(f"{label} already exists; immutable destinations cannot be overwritten: {path}")
    parent = path.parent
    reject_alias(parent, f"{label} parent")
    if not parent.is_dir():
        raise ErratumError(f"{label} parent does not exist: {parent}")


def atomic_create(path: Path, contents: bytes, label: str) -> None:
    require_new_destination(path, label)
    descriptor: int | None = None
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        # link() fails when another writer won the destination race.  Unlike
        # replace(), it can never overwrite a prior immutable release.
        os.link(temporary_name, path)
    except FileExistsError as exc:
        raise ErratumError(f"{label} appeared during creation; refusing overwrite: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def create_erratum(
    base_manifest: Path,
    repo_root: Path,
    server_erratum_dir: Path,
    local_erratum_copy: Path,
    *,
    expected_base_hash: str = BASE_RELEASE_SHA256,
) -> dict[str, Any]:
    """Create the server/local immutable pair and prove byte identity."""
    reject_alias(server_erratum_dir, "server erratum directory")
    expected_server_dir = base_manifest.parent.parent / ERRATUM_ID
    if server_erratum_dir != expected_server_dir:
        raise ErratumError(f"server erratum directory must be exactly {expected_server_dir}")
    if server_erratum_dir.exists() or server_erratum_dir.is_symlink():
        raise ErratumError(f"server erratum directory already exists: {server_erratum_dir}")
    require_new_destination(local_erratum_copy, "local erratum copy")
    if local_erratum_copy == base_manifest or local_erratum_copy.parent == server_erratum_dir:
        raise ErratumError("local erratum copy must be distinct from the sealed base and server destination")

    # Validate every input before creating the destination directory.  Then
    # perform the sealed-base/source validation again immediately before the
    # irreversible name is claimed, so a changed snapshot cannot be released.
    document = build_erratum(base_manifest, repo_root, expected_base_hash=expected_base_hash)
    document = build_erratum(base_manifest, repo_root, expected_base_hash=expected_base_hash)
    payload = canonical_bytes(document)
    server_erratum_dir.mkdir(mode=0o755)
    # Never remove a directory or a document once it exists: that would erase
    # evidence from a partial immutable publication attempt.
    server_manifest = server_erratum_dir / "erratum.json"
    atomic_create(server_manifest, payload, "server erratum")
    atomic_create(local_erratum_copy, payload, "local erratum copy")
    if server_manifest.read_bytes() != local_erratum_copy.read_bytes():
        raise ErratumError("server and local erratum bytes differ")
    server_manifest.chmod(0o444)
    local_erratum_copy.chmod(0o444)
    server_erratum_dir.chmod(0o555)
    return document


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "apply"), required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True, help="New proposal/receipt file; never overwritten.")
    parser.add_argument("--server-erratum-dir", type=Path)
    parser.add_argument("--local-erratum-copy", type=Path)
    parser.add_argument("--confirm-apply")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        require_new_destination(args.out, "output")
        if args.mode == "prepare":
            document = build_erratum(args.base_manifest, args.repo_root)
        else:
            if args.confirm_apply != ERRATUM_ID:
                raise ErratumError(f"--confirm-apply must equal {ERRATUM_ID}")
            if args.server_erratum_dir is None or args.local_erratum_copy is None:
                raise ErratumError("apply requires --server-erratum-dir and --local-erratum-copy")
            if args.out == args.local_erratum_copy or args.out.parent == args.server_erratum_dir:
                raise ErratumError("output must be distinct from the local and server immutable documents")
            document = create_erratum(
                args.base_manifest, args.repo_root, args.server_erratum_dir, args.local_erratum_copy
            )
        atomic_create(args.out, canonical_bytes(document), "output")
        return 0
    except ErratumError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
