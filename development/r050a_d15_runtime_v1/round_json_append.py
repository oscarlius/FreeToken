#!/usr/bin/env python3
"""Append-only writer for a closed FreeToken round.json and its snapshot chain."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VERSION = re.compile(r"round\.v(\d+)\.json\Z")
CST = timezone(timedelta(hours=8), "CST")
VERDICTS = {"kept", "reverted", "rejected", "blocked", "not_met", "kept_pending_gate", "measured", "pending_review", "failed_harness"}
SUB_STATUSES = {"kept", "retracted", "hypothesis", "pending"}


class RoundError(ValueError):
    def __init__(self, path: str, message: str):
        self.path, self.message = path, message
        super().__init__(f"{path}: {message}")


def cst_now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def load_json_bytes(path: Path, label: str) -> tuple[bytes, Any]:
    try:
        raw = path.read_bytes()
        return raw, json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RoundError(label, f"invalid JSON: {exc}") from exc


def no_symlink(path: Path, label: str, *, directory: bool | None = None) -> Path:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RoundError(label, f"missing or inaccessible: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RoundError(label, "symlink is forbidden")
    if directory is True and not stat.S_ISDIR(info.st_mode):
        raise RoundError(label, "must be a directory")
    if directory is False and not stat.S_ISREG(info.st_mode):
        raise RoundError(label, "must be a regular file")
    expected_uid = getattr(os, "getuid", lambda: info.st_uid)()
    if info.st_uid != expected_uid:
        raise RoundError(label, "is not owned by the invoking user")
    return path.resolve(strict=True)


def guarded_round(round_dir: Path, *, writing: bool = False) -> tuple[Path, Path, Path]:
    # Check the un-resolved absolute spelling first: resolving before this loop would
    # hide a symlinked ancestor from the guard.
    raw_root = Path(os.path.abspath(round_dir))
    current = raw_root
    while current != current.parent:
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise RoundError("$round", "ancestor symlink is forbidden")
        except OSError as exc:
            raise RoundError("$round", f"missing or inaccessible ancestor: {exc}") from exc
        current = current.parent
    root = no_symlink(raw_root, "$round", directory=True)
    round_json = no_symlink(root / "round.json", "$.round.json", directory=False)
    history = root / "round_history"
    if history.exists():
        no_symlink(history, "$.round_history", directory=True)
        for item in history.iterdir():
            no_symlink(item, f"$.round_history/{item.name}", directory=False)
    return root, round_json, history


def exact_type(left: Any, right: Any) -> bool:
    return type(left) is type(right)


def exact_equal(left: Any, right: Any) -> bool:
    if not exact_type(left, right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right))
    return left == right


def first_immutable_difference(old: Any, new: Any, path: str = "$") -> str | None:
    """Return the first non-exception append-only violation, including exact type checks."""
    if isinstance(old, dict):
        if not isinstance(new, dict):
            return path
        for key, value in old.items():
            if key not in new:
                return f"{path}.{key}"
            child = first_immutable_difference(value, new[key], f"{path}.{key}")
            if child is not None:
                return child
        return None
    if isinstance(old, list):
        if not isinstance(new, list) or len(new) < len(old):
            return path
        for index, value in enumerate(old):
            child = first_immutable_difference(value, new[index], f"{path}[{index}]")
            if child is not None:
                return child
        return None
    return None if exact_type(old, new) and old == new else path


def history_entry(entry: Any, path: str) -> None:
    if not isinstance(entry, dict):
        raise RoundError(path, "must be an object")
    required = ("time", "old", "new", "reason", "evidence", "by")
    for key in required:
        if key not in entry:
            raise RoundError(f"{path}.{key}", "is required")
    if not isinstance(entry["time"], str):
        raise RoundError(f"{path}.time", "must be a CST timestamp")
    try:
        datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S CST")
    except ValueError as exc:
        raise RoundError(f"{path}.time", "must be a CST timestamp") from exc
    if not all(isinstance(entry[key], str) and entry[key].strip() for key in ("old", "new", "reason", "by")):
        raise RoundError(path, "old/new/reason/by must be nonempty strings")
    if entry["new"] not in VERDICTS:
        raise RoundError(f"{path}.new", "is not an allowed verdict")
    if not isinstance(entry["evidence"], list) or not entry["evidence"] or any(not isinstance(x, str) or not x.strip() for x in entry["evidence"]):
        raise RoundError(f"{path}.evidence", "must be a nonempty list of strings")


def retraction_entry(entry: Any, path: str) -> None:
    if not isinstance(entry, dict):
        raise RoundError(path, "must be an object")
    for key in ("time", "target", "reason", "evidence", "by"):
        if key not in entry:
            raise RoundError(f"{path}.{key}", "is required")
    if not isinstance(entry["time"], str):
        raise RoundError(f"{path}.time", "must be a CST timestamp")
    try:
        datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S CST")
    except ValueError as exc:
        raise RoundError(f"{path}.time", "must be a CST timestamp") from exc
    if not all(isinstance(entry[key], str) and entry[key].strip() for key in ("target", "reason", "by")):
        raise RoundError(path, "target/reason/by must be nonempty strings")
    if not isinstance(entry["evidence"], list) or not entry["evidence"] or any(not isinstance(x, str) or not x.strip() for x in entry["evidence"]):
        raise RoundError(f"{path}.evidence", "must be a nonempty list of strings")


def validate_change(old: Any, new: Any) -> None:
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise RoundError("$", "round root must be an object")
    old_history, new_history = old.get("verdict_history", []), new.get("verdict_history", [])
    old_retractions, new_retractions = old.get("retractions", []), new.get("retractions", [])
    if not isinstance(old_history, list) or not isinstance(new_history, list):
        raise RoundError("$.verdict_history", "must be a list")
    if not isinstance(old_retractions, list) or not isinstance(new_retractions, list):
        raise RoundError("$.retractions", "must be a list")
    if len(new_history) < len(old_history):
        raise RoundError("$.verdict_history", "cannot delete existing history entries")
    if len(new_retractions) < len(old_retractions):
        raise RoundError("$.retractions", "cannot delete existing retraction entries")
    if not all(exact_equal(before, after) for before, after in zip(old_history, new_history[:len(old_history)])):
        raise RoundError("$.verdict_history", "existing history is not an unchanged type-exact prefix")
    if not all(exact_equal(before, after) for before, after in zip(old_retractions, new_retractions[:len(old_retractions)])):
        raise RoundError("$.retractions", "existing retractions are not an unchanged type-exact prefix")
    for index, entry in enumerate(new_history):
        history_entry(entry, f"$.verdict_history[{index}]")
    for index, entry in enumerate(new_retractions):
        retraction_entry(entry, f"$.retractions[{index}]")

    allowed_status: set[int] = set()
    old_sub, new_sub = old.get("sub_conclusions", []), new.get("sub_conclusions", [])
    if not isinstance(old_sub, list) or not isinstance(new_sub, list) or len(new_sub) < len(old_sub):
        raise RoundError("$.sub_conclusions", "must retain its original list prefix")
    appended_retractions = new_retractions[len(old_retractions):]
    targets = [entry["target"] for entry in appended_retractions]
    if len(set(targets)) != len(targets):
        raise RoundError("$.retractions", "new retractions must target distinct existing sub_conclusions")
    history_reasons = [entry["reason"] for entry in new_history[len(old_history):]]
    matched_retraction_indices: set[int] = set()
    for index, (before, after) in enumerate(zip(old_sub, new_sub)):
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise RoundError(f"$.sub_conclusions[{index}]", "must be objects")
        changed_existing = [key for key in before if key not in after or not exact_equal(before[key], after[key])]
        if not changed_existing:
            continue  # New dictionary keys remain append-only additions.
        if changed_existing != ["status"] or after.get("status") not in SUB_STATUSES:
            raise RoundError(f"$.sub_conclusions[{index}]", "only status may change to an allowed status")
        identifiers = tuple(identifier for identifier in (str(before.get("id", "")), str(before.get("text", ""))) if identifier)
        retraction_matches = [position for position, target in enumerate(targets) if target in identifiers]
        verdict_match = any(identifier in reason for identifier in identifiers for reason in history_reasons)
        if len(retraction_matches) > 1 or not (retraction_matches or verdict_match):
            raise RoundError(f"$.sub_conclusions[{index}].status", "has no unique matching appended retraction or verdict reason")
        if retraction_matches:
            if after.get("status") != "retracted":
                raise RoundError(f"$.sub_conclusions[{index}].status", "matching retraction requires retracted status")
            matched_retraction_indices.add(retraction_matches[0])
        allowed_status.add(index)
    if matched_retraction_indices != set(range(len(appended_retractions))):
        raise RoundError("$.retractions", "each appended retraction must match one old sub_conclusion with retracted status")

    # Compare a copy with the two governed fields restored, then separately validate them.
    normalized = copy.deepcopy(new)
    normalized["verdict"] = old.get("verdict")
    normalized["verdict_history"] = copy.deepcopy(old_history)
    normalized["retractions"] = copy.deepcopy(old_retractions)
    if isinstance(normalized.get("sub_conclusions"), list):
        for index in allowed_status:
            normalized["sub_conclusions"][index]["status"] = old_sub[index].get("status")
    violation = first_immutable_difference(old, normalized)
    if violation is not None:
        raise RoundError(violation, "existing value changed, deleted, or changed type")

    verdict_changed = old.get("verdict") != new.get("verdict") or type(old.get("verdict")) is not type(new.get("verdict"))
    appended_history = new_history[len(old_history):]
    if verdict_changed:
        if len(appended_history) != 1:
            raise RoundError("$.verdict", "requires exactly one appended verdict_history entry")
        item = appended_history[0]
        if item["old"] != old.get("verdict") or item["new"] != new.get("verdict"):
            raise RoundError("$.verdict", "must equal the appended verdict_history transition")
    elif appended_history:
        raise RoundError("$.verdict_history", "cannot append history without changing verdict")


def merge_add(old: Any, patch: Any, path: str = "$") -> Any:
    if not isinstance(old, dict) or not isinstance(patch, dict):
        raise RoundError(path, "--json patch root and nested existing objects must be objects")
    out = copy.deepcopy(old)
    for key, value in patch.items():
        child_path = f"{path}.{key}"
        if key not in old:
            out[key] = copy.deepcopy(value)
        elif isinstance(old[key], dict):
            out[key] = merge_add(old[key], value, child_path)
        elif isinstance(old[key], list):
            if not isinstance(value, list):
                raise RoundError(child_path, "existing list requires a list of items to append")
            out[key] = copy.deepcopy(old[key]) + copy.deepcopy(value)
        else:
            raise RoundError(child_path, "existing scalar cannot be overwritten by --json")
    return out


def version_files(history: Path) -> list[Path]:
    if not history.exists():
        return []
    files = []
    for path in history.iterdir():
        match = VERSION.fullmatch(path.name)
        if match:
            files.append(path)
    return sorted(files, key=lambda path: int(VERSION.fullmatch(path.name).group(1)))


def sums_bytes(files: list[Path]) -> bytes:
    return "".join(f"{digest(path.read_bytes())}  {path.name}\n" for path in files).encode("ascii")


def validate_history(round_json: Path, history: Path) -> tuple[bytes, Any, list[Path]]:
    current_raw, current = load_json_bytes(round_json, "$.round.json")
    files = version_files(history)
    if history.exists() and not files:
        raise RoundError("$.round_history", "exists but contains no round.vNNN.json snapshot")
    if not files:
        return current_raw, current, files
    numbers = [int(VERSION.fullmatch(path.name).group(1)) for path in files]
    expected = list(range(numbers[0], numbers[-1] + 1))
    if numbers != expected:
        raise RoundError("$.round_history", "version numbers are not contiguous")
    if files and files[0].name == "round.v000.json":
        annotation = history / "legacy_snapshot.json"
        no_symlink(annotation, "$.round_history/legacy_snapshot.json", directory=False)
        _, legacy = load_json_bytes(annotation, "$.round_history/legacy_snapshot.json")
        if legacy != {"legacy_snapshot": "round.v000.json", "sha256": digest(files[0].read_bytes())}:
            raise RoundError("$.round_history/legacy_snapshot.json", "does not bind the byte-exact v000 snapshot")
    snapshots = []
    for index, path in enumerate(files):
        _, value = load_json_bytes(path, f"$.round_history/{path.name}")
        snapshots.append(value)
        if index:
            validate_change(snapshots[index - 1], value)
    sums = history / "SHA256SUMS"
    no_symlink(sums, "$.round_history/SHA256SUMS", directory=False)
    if sums.read_bytes() != sums_bytes(files):
        raise RoundError("$.round_history/SHA256SUMS", "does not match immutable snapshots")
    if current_raw != files[-1].read_bytes():
        raise RoundError("$.round.json", "does not byte-equal latest round_history snapshot")
    return current_raw, current, files


def collect_modes(paths: list[Path]) -> dict[Path, int]:
    return {path: stat.S_IMODE(path.stat().st_mode) for path in paths if path.exists()}


def temporarily_writable(modes: dict[Path, int]) -> None:
    for path, mode in modes.items():
        os.chmod(path, mode | stat.S_IWUSR)


def restore_modes(modes: dict[Path, int]) -> None:
    for path, mode in modes.items():
        if path.exists():
            os.chmod(path, mode)


def make_readonly(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            os.chmod(path, stat.S_IMODE(path.stat().st_mode) & ~0o222)


def atomic_write(path: Path, data: bytes) -> None:
    handle = tempfile.NamedTemporaryFile(prefix=".round-append-", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def commit(round_dir: Path, new: Any) -> None:
    root, round_json, history = guarded_round(round_dir, writing=True)
    old_raw, old, files = validate_history(round_json, history)
    validate_change(old, new)
    new_raw = json_bytes(new)
    history_existed = history.exists()
    legacy = not history_existed
    next_number = 1 if legacy else int(VERSION.fullmatch(files[-1].name).group(1)) + 1
    new_name = f"round.v{next_number:03d}.json"
    new_snapshot = history / new_name
    if new_snapshot.exists():
        raise RoundError(f"$.round_history/{new_name}", "already exists")
    # Capture every original mode before the first chmod.  This lets a failure on
    # any later chmod restore permissions as well as bytes.
    modes = collect_modes([root, round_json, history, history / "SHA256SUMS"])
    created_history = False
    sums_path = history / "SHA256SUMS"
    original_sums = sums_path.read_bytes() if sums_path.exists() else None
    original_annotation = None
    snapshot_created = False
    round_replaced = False
    try:
        temporarily_writable(modes)
        if not history.exists():
            history.mkdir(mode=0o700)
            created_history = True
            modes[history] = stat.S_IMODE(history.stat().st_mode)
        annotation = history / "legacy_snapshot.json"
        if legacy:
            legacy_snapshot = history / "round.v000.json"
            atomic_write(legacy_snapshot, old_raw)
            original_annotation = annotation.read_bytes() if annotation.exists() else None
            atomic_write(annotation, json_bytes({"legacy_snapshot": "round.v000.json", "sha256": digest(old_raw)}))
            files = [legacy_snapshot]
        sums = history / "SHA256SUMS"
        atomic_write(new_snapshot, new_raw)
        snapshot_created = True
        new_files = files + [new_snapshot]
        atomic_write(sums, sums_bytes(new_files))
        atomic_write(round_json, new_raw)
        round_replaced = True
        # Readonly restoration is part of the transaction: a chmod error follows
        # the same rollback path as a write error.
        readonly = [root, round_json, history, sums, *new_files]
        if legacy:
            readonly.append(annotation)
        make_readonly(readonly)
    except BaseException:
        try:
            # A partial readonly pass may have removed directory write permission.
            for path in (root, history, round_json, history / "SHA256SUMS"):
                if path.exists():
                    os.chmod(path, stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
            if round_replaced:
                atomic_write(round_json, old_raw)
            if snapshot_created:
                new_snapshot.unlink(missing_ok=True)
            sums = history / "SHA256SUMS"
            if original_sums is None:
                sums.unlink(missing_ok=True)
            else:
                atomic_write(sums, original_sums)
            if legacy:
                (history / "round.v000.json").unlink(missing_ok=True)
                if original_annotation is None:
                    annotation.unlink(missing_ok=True)
                else:
                    atomic_write(annotation, original_annotation)
            if created_history:
                history.rmdir()
        finally:
            restore_modes(modes)
        raise


def require_text(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoundError(f"$.{name}", "is required and must be nonempty")
    return value


def require_evidence(values: list[str] | None) -> list[str]:
    if not values or any(not item.strip() for item in values):
        raise RoundError("$.evidence", "at least one nonempty evidence item is required")
    return values


def run_verdict(old: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    new = copy.deepcopy(old)
    verdict, reason, by, evidence = require_text(args.new, "new"), require_text(args.reason, "reason"), require_text(args.by, "by"), require_evidence(args.evidence)
    previous = old.get("verdict")
    if not isinstance(previous, str):
        raise RoundError("$.verdict", "must be an existing string")
    new.setdefault("verdict_history", []).append({"time": cst_now(), "old": previous, "new": verdict,
                                                     "reason": reason, "evidence": evidence, "by": by})
    new["verdict"] = verdict
    return new


def run_retract(old: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    target, reason, by, evidence = require_text(args.target, "target"), require_text(args.reason, "reason"), require_text(args.by, "by"), require_evidence(args.evidence)
    conclusions = old.get("sub_conclusions")
    if not isinstance(conclusions, list):
        raise RoundError("$.sub_conclusions", "must be a list for retract")
    matches = [index for index, item in enumerate(conclusions) if isinstance(item, dict) and target in (item.get("id"), item.get("text"))]
    if len(matches) != 1:
        raise RoundError("$.target", "must match exactly one sub_conclusion id or text")
    index = matches[0]
    if conclusions[index].get("status") == "retracted":
        raise RoundError(f"$.sub_conclusions[{index}].status", "is already retracted")
    new = copy.deepcopy(old)
    new.setdefault("retractions", []).append({"time": cst_now(), "target": target, "reason": reason,
                                                 "evidence": evidence, "by": by})
    new["sub_conclusions"][index]["status"] = "retracted"
    return new


def run_add(old: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    patch_path = no_symlink(Path(args.json), "$.patch", directory=False)
    _, patch = load_json_bytes(patch_path, "$.patch")
    if not isinstance(patch, dict):
        raise RoundError("$.patch", "--json patch root must be an object")
    forbidden = {"verdict", "verdict_history", "retractions"} & set(patch)
    if forbidden:
        raise RoundError("$.patch", f"governed field(s) require verdict/retract command: {sorted(forbidden)}")
    return merge_add(old, patch)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round_dir", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    verdict = commands.add_parser("verdict")
    verdict.add_argument("--new", required=True)
    verdict.add_argument("--reason", required=True)
    verdict.add_argument("--evidence", nargs="+", required=True)
    verdict.add_argument("--by", required=True)
    retract = commands.add_parser("retract")
    retract.add_argument("--target", required=True)
    retract.add_argument("--reason", required=True)
    retract.add_argument("--evidence", nargs="+", required=True)
    retract.add_argument("--by", required=True)
    add = commands.add_parser("add")
    add.add_argument("--json", required=True)
    commands.add_parser("check")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root, round_json, history = guarded_round(args.round_dir)
        _, old, _ = validate_history(round_json, history)
        if args.command == "check":
            print(json.dumps({"round": str(root), "history": str(history), "ok": True}, ensure_ascii=False))
            return 0
        if args.command == "verdict":
            new = run_verdict(old, args)
        elif args.command == "retract":
            new = run_retract(old, args)
        else:
            new = run_add(old, args)
        commit(root, new)
        print(json.dumps({"round": str(root), "command": args.command, "ok": True}, ensure_ascii=False))
        return 0
    except RoundError as exc:
        print(f"ERROR {exc.path}: {exc.message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR $: filesystem failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
