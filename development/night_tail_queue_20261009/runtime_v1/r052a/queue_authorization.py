"""Narrow authorization record for the independent night-tail FILEdry queue.

It records factual failed/not_met evidence.  It never represents either item as
``measured`` and it leaves the frozen v12/v8/v7 sources untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RECORD = HERE / "night_tail_queue_authorization.json"
CANDIDATE = "0aa23431e5b800797543bdecbf35a01045131d7d"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> dict:
    value = json.loads(RECORD.read_text(encoding="utf-8"))
    if value.get("schema") != "ft_night_tail_queue_authorization/v1":
        raise RuntimeError("night-tail authorization schema differs")
    if value.get("candidate_commit") != CANDIDATE:
        raise RuntimeError("night-tail authorization candidate differs")
    return value


def factual(name: str) -> dict:
    value = load().get("factual_predecessors", {}).get(name)
    if not isinstance(value, dict):
        raise RuntimeError(f"night-tail factual predecessor missing: {name}")
    path = Path(value["path"])
    if path.is_symlink() or not path.is_file() or sha256(path) != value["sha256"]:
        raise RuntimeError(f"night-tail factual predecessor binding differs: {name}")
    document = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in value["facts"].items():
        if document.get(key) != expected:
            raise RuntimeError(f"night-tail factual predecessor status differs: {name}.{key}")
    return {"path": str(path), "sha256": value["sha256"], "facts": value["facts"]}


def policy(item: str) -> dict:
    value = load().get("independent_queue", {}).get(item)
    if not isinstance(value, dict) or value.get("authorization") != "user_authorized_independent_terminal":
        raise RuntimeError(f"night-tail queue authorization missing: {item}")
    return value
