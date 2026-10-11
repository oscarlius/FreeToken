"""Compile the observed donor and continuation geometry without changing it."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIELDS = ("start", "end", "mode", "subchunks")


def read_schedule(path: Path) -> tuple[list[dict], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("compiled schedule must be a regular file")
    raw = path.read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise ValueError("compiled schedule is empty")
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise ValueError("compiled schedule fields differ")
        checked = dict(row, reqs=[{"rid": "check", "cached_tokens": row["start"],
                                  "new_tokens": row["end"] - row["start"]}])
        segment(checked, "check")
    return rows, hashlib.sha256(raw).hexdigest()


def read_jsonl(path: Path) -> tuple[list[dict], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular evidence file required: {path}")
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("D0 records must be objects")
    return rows, hashlib.sha256(raw).hexdigest()


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def segment(row: dict, uid: str) -> dict:
    requests = row.get("reqs")
    if not isinstance(requests, list) or len(requests) != 1:
        raise ValueError("T17 requires a single-request D0 segment")
    req = requests[0]
    if not isinstance(req, dict) or str(req.get("rid")) != uid:
        raise ValueError("D0 request identity differs")
    if any(field not in row for field in FIELDS):
        raise ValueError("D0 structural metadata missing; no schedule may be inferred")
    start = _integer(row["start"], "start")
    end = _integer(row["end"], "end", 1)
    mode, chunks = row["mode"], row["subchunks"]
    if mode not in ("ordinary", "layer_major") or not isinstance(chunks, list) or not chunks:
        raise ValueError("invalid D0 mode or subchunk grid")
    for chunk in chunks:
        _integer(chunk, "subchunk", 1)
    if end <= start or sum(chunks) != end - start:
        raise ValueError("D0 subchunks do not cover the segment")
    if mode == "ordinary" and chunks != [end - start]:
        raise ValueError("ordinary segment must describe one actual model call")
    # Legacy cached_tokens counts a radix hit, not the consumed prefix of a
    # continuation chunk. The new absolute start is the structural authority.
    if (_integer(req.get("cached_tokens"), "cached_tokens") > start
            or _integer(req.get("new_tokens"), "new_tokens", 1) != end - start):
        raise ValueError("D0 structural and existing request metadata disagree")
    return {"start": start, "end": end, "mode": mode, "subchunks": list(chunks)}


def request_segments(rows: list[dict], uid: str, *, allow_rewind: bool = False) -> list[dict]:
    selected = []
    for row in rows:
        requests = row.get("reqs", [])
        if not isinstance(requests, list):
            raise ValueError("D0 reqs must be a list")
        if any(isinstance(req, dict) and str(req.get("rid")) == uid for req in requests):
            selected.append(segment(row, uid))
    if not selected:
        raise ValueError(f"D0 evidence missing for request {uid}")
    for previous, current in zip(selected, selected[1:]):
        ends = (previous["end"], previous["end"] - 1) if allow_rewind else (previous["end"],)
        if current["start"] not in ends:
            raise ValueError("one request contains a D0 gap or overlapping segment")
    return selected


def compile_schedule(rows: list[dict], *, donor_uid: str, hit_uid: str,
                     cached_tokens: int, prompt_tokens: int) -> list[dict]:
    if donor_uid == hit_uid:
        raise ValueError("donor and continuation must be distinct requests")
    _integer(cached_tokens, "cached_tokens", 1)
    _integer(prompt_tokens, "prompt_tokens", cached_tokens + 1)
    donor = request_segments(rows, donor_uid)
    hit = request_segments(rows, hit_uid)
    if donor[0]["start"] != 0 or hit[0]["start"] != cached_tokens:
        raise ValueError("donor must be cold and continuation must start at the actual hit")
    if donor[-1]["end"] not in (cached_tokens, cached_tokens + 1):
        raise ValueError("unsupported donor rewind; retain the evidence and stop")
    if hit[-1]["end"] != prompt_tokens or any(row["end"] > prompt_tokens for row in donor):
        raise ValueError("observed schedule and full prompt length disagree")
    return donor + hit


def validate_reference(rows: list[dict], *, uid: str, schedule: list[dict]) -> list[dict]:
    actual = request_segments(rows, uid, allow_rewind=True)
    if actual != schedule:
        index = next((i for i, (a, b) in enumerate(zip(actual, schedule)) if a != b),
                     min(len(actual), len(schedule)))
        raise ValueError(f"reference D0 differs from injected schedule at segment {index}")
    return actual


def write_new(path: Path, value: object) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()
