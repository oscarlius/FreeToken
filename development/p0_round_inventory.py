#!/usr/bin/env python3
"""Read-only canonical round inventory for P0 verdict review."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
    except OSError:
        return False


def inventory_one(root: Path, name: str) -> dict[str, Any]:
    directory = root / name
    item: dict[str, Any] = {"requested_id": name, "directory": str(directory), "exists": directory.is_dir() and not directory.is_symlink()}
    if not item["exists"]:
        return item
    item["directory_readonly"] = (directory.stat().st_mode & 0o222) == 0
    for relative in ("round.json", "MANIFEST.sha256"):
        path = directory / relative
        entry = {"exists": regular(path)}
        if entry["exists"]:
            entry["sha256"] = sha256(path)
            entry["readonly"] = (path.stat().st_mode & 0o222) == 0
        item[relative] = entry
    history = directory / "round_history"
    item["round_history"] = {"exists": history.is_dir() and not history.is_symlink()}
    if item["round_history"]["exists"]:
        snapshots: list[dict[str, Any]] = []
        for path in sorted(history.iterdir()):
            if regular(path):
                snapshots.append({"name": path.name, "sha256": sha256(path), "readonly": (path.stat().st_mode & 0o222) == 0})
        item["round_history"]["snapshots"] = snapshots
        item["round_history"]["readonly"] = (history.stat().st_mode & 0o222) == 0
    round_json = directory / "round.json"
    if regular(round_json):
        try:
            data = json.loads(round_json.read_text(encoding="utf-8"))
            item["round"] = {
                key: data.get(key)
                for key in ("schema", "round_id", "card", "verdict", "proposed_verdict", "closed_at", "base", "experimental", "sub_conclusions", "verdict_history", "retractions")
            }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            item["round_parse_error"] = str(exc)
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = args.root
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"invalid canonical root: {root}")
    payload = {"schema": "p0_round_inventory/v1", "root": str(root), "rounds": [inventory_one(root, name) for name in args.ids]}
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out is None:
        print(text, end="")
    else:
        with args.out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
