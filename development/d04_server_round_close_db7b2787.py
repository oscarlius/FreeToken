#!/usr/bin/env python3
"""Validate and seal the first snapshot of a round; append only with round_json_append."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from round_json_append import RoundError, cst_now, guarded_round, json_bytes, load_json_bytes, no_symlink

ARM_NAME = re.compile(r"[A-Za-z0-9_]+\Z")
ROUND_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")
REQUIRED = ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt")


def failed_archive_missing_args(root, doc):
    """Allow an explicitly proved failed startup to retain its missing argument dump."""
    archive = doc.get("failure_archive", {})
    entries = archive.get("missing_serve_args", []) if isinstance(archive, dict) else None
    if not isinstance(entries, list):
        raise RoundError("$.failure_archive.missing_serve_args", "must be a list")
    allowed = set()
    for entry in entries:
        if doc.get("proposed_verdict") != "failed_harness" or not isinstance(entry, dict):
            raise RoundError("$.failure_archive", "missing args exception requires a failed_harness proposal")
        arm = entry.get("arm")
        if not isinstance(arm, str) or not ARM_NAME.fullmatch(arm) or arm in allowed:
            raise RoundError("$.failure_archive.arm", "must name one distinct declared service arm")
        arms = doc.get("serve", {}).get("arms", {})
        if arm not in arms or (root / arm / "serve_args.txt").exists():
            raise RoundError("$.failure_archive.arm", "must identify an actual missing serve_args dump")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise RoundError("$.failure_archive.reason", "must explain the missing dump")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RoundError("$.failure_archive.evidence", "must bind original evidence")
        names, terminal_failure = set(), False
        for record in evidence:
            name = record.get("path") if isinstance(record, dict) else None
            if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
                raise RoundError("$.failure_archive.evidence.path", "must be inside this round")
            path = root / name
            for part in [path, *path.parents]:
                if part == root:
                    break
                no_symlink(part, "$.failure_archive.evidence.path")
            no_symlink(path, "$.failure_archive.evidence.path", directory=False)
            if record.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
                raise RoundError("$.failure_archive.evidence.sha256", "does not match original evidence")
            names.add(name)
            if path.parent == root and path.name.startswith("status_batch") and path.suffix == ".json":
                _, status = load_json_bytes(path, "$.failure_archive.status")
                terminal_failure = (isinstance(status, dict) and status.get("rid") == root.name
                    and status.get("state") in {"failed", "error"}
                    and isinstance(status.get("error"), str) and bool(status["error"].strip()))
        if not {f"{arm}/SERVE_CMD.txt", f"{arm}/serve.log"} <= names or not terminal_failure:
            raise RoundError("$.failure_archive.evidence", "requires command, service log, and terminal failure status")
        allowed.add(arm)
    return allowed


def prepare(root):
    root, round_path, _ = guarded_round(root)
    for name in ("round_history", "MANIFEST.sha256"):
        if (root / name).exists() or (root / name).is_symlink():
            raise RoundError(f"$.{name}", "already exists; a closed round cannot be resealed")
    raw, doc = load_json_bytes(round_path, "$.round.json")
    if not isinstance(doc, dict) or doc.get("round_id") != root.name:
        raise RoundError("$.round_id", "must equal the round directory name")
    if doc.get("schema") != "ft_round/v2":
        raise RoundError("$.schema", "must be ft_round/v2")
    if doc.get("verdict") != "pending_review":
        raise RoundError("$.verdict", "first snapshot must be pending_review")
    for name in ("verdict_history", "retractions"):
        value = doc.get(name, [])
        if type(value) is not list or value:
            raise RoundError(f"$.{name}", "first snapshot requires an empty list")
        doc.setdefault(name, [])
    no_symlink(root / "batch.sh", "$.batch.sh", directory=False)
    missing_args_arms = failed_archive_missing_args(root, doc)
    serve = doc.get("serve")
    if serve != "none":
        arms = serve.get("arms") if isinstance(serve, dict) else None
        if not isinstance(arms, dict) or not arms:
            raise RoundError("$.serve.arms", "must declare each serving arm or set serve to none")
        for name, details in arms.items():
            if not ARM_NAME.fullmatch(name) or not isinstance(details, dict):
                raise RoundError(f"$.serve.arms.{name}", "invalid arm declaration")
            directory = no_symlink(root / name, f"$.serve.arms.{name}", directory=True)
            for required in REQUIRED:
                if required == "serve_args.txt" and name in missing_args_arms:
                    continue
                path = no_symlink(directory / required, f"$.serve.arms.{name}.{required}", directory=False)
                if not path.stat().st_size:
                    raise RoundError(f"$.serve.arms.{name}.{required}", "must not be empty")
    for index, entry in enumerate(doc.get("batch_logs", [])):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RoundError(f"$.batch_logs[{index}]", "must bind a batch log path and SHA256")
        path = no_symlink(Path(entry["path"]), f"$.batch_logs[{index}].path", directory=False)
        if not path.is_absolute() or entry.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise RoundError(f"$.batch_logs[{index}].sha256", "does not match the actual batch log")
    paths = [root, *sorted(root.rglob("*"))]
    for path in paths:
        no_symlink(path, f"$round/{path.relative_to(root)}")
        if not (path.is_file() or path.is_dir()):
            raise RoundError(str(path), "only regular files and directories may be sealed")
    if not doc.get("closed_at"):
        doc["closed_at"] = cst_now()
    elif not isinstance(doc["closed_at"], str) or not doc["closed_at"].endswith(" CST"):
        raise RoundError("$.closed_at", "must be a CST timestamp")
    doc.setdefault("manifest", "MANIFEST.sha256")
    if doc["manifest"] != "MANIFEST.sha256":
        raise RoundError("$.manifest", "must be MANIFEST.sha256")
    encoded = json_bytes(doc)
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.relative_to(root).as_posix()}\n"
        for path in paths if path.is_file() and path != round_path
    ).encode("utf-8")
    return root, round_path, raw, encoded, paths, manifest


def close(root):
    root, round_path, old_raw, encoded, paths, manifest = prepare(root)
    modes = {path: stat.S_IMODE(path.stat().st_mode) for path in paths}
    history = root / "round_history"
    manifest_path = root / "MANIFEST.sha256"
    created = []
    try:
        os.chmod(root, modes[root] | stat.S_IWUSR)
        os.chmod(round_path, modes[round_path] | stat.S_IWUSR)
        round_path.write_bytes(encoded)
        history.mkdir(mode=0o700)
        created.append(history)
        snapshot = history / "round.v001.json"
        with snapshot.open("xb") as handle:
            handle.write(encoded)
        created.append(snapshot)
        sums = history / "SHA256SUMS"
        with sums.open("xb") as handle:
            handle.write(f"{hashlib.sha256(encoded).hexdigest()}  round.v001.json\n".encode())
        created.append(sums)
        with manifest_path.open("xb") as handle:
            handle.write(manifest)
        created.append(manifest_path)
        for path in reversed([*paths, *created]):
            os.chmod(path, stat.S_IMODE(path.stat().st_mode) & ~0o222)
    except BaseException:
        os.chmod(root, modes[root] | stat.S_IWUSR)
        if history.exists():
            os.chmod(history, stat.S_IMODE(history.stat().st_mode) | stat.S_IWUSR)
        os.chmod(round_path, modes[round_path] | stat.S_IWUSR)
        round_path.write_bytes(old_raw)
        for path in reversed(created):
            if path.is_dir():
                path.rmdir()
            else:
                if path.exists():
                    os.chmod(path, stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
                path.unlink(missing_ok=True)
        for path, mode in modes.items():
            os.chmod(path, mode)
        raise
    return hashlib.sha256(manifest).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round_id")
    parser.add_argument("--round-root", type=Path, default=Path("/data2/_shared/runs/ft_rounds"))
    args = parser.parse_args()
    if not ROUND_NAME.fullmatch(args.round_id):
        parser.error("round_id must be one directory name")
    try:
        sha = close(args.round_root / args.round_id)
    except (RoundError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"round_id": args.round_id, "manifest_sha256": sha}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
