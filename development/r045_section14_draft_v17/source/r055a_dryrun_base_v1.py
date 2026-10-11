"""Shared file-only writes for R055a's pre-launch dry-run."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def write_probe(path: Path, text: str = "R055a dry-run writability probe\n") -> str:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("append verified\n")
    if not os.access(path, os.W_OK):
        raise RuntimeError(f"R055a dry-run path is not writable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_probe(path: Path, value: dict) -> str:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
    if not os.access(path, os.W_OK):
        raise RuntimeError(f"R055a dry-run JSON is not writable: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path: Path) -> str:
    path.chmod(0o444)
    if path.is_symlink() or path.stat().st_mode & 0o222:
        raise RuntimeError(f"R055a dry-run freeze failed: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()
