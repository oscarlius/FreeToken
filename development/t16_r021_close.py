"""Seal a reviewed D14 gate with the published D04 closer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

RID = "E2-R021-gate-D14"
BATCH = 49
REVIEWER_SHA = "5f38fa87437d36d82ec08f92339a33ff2900183ed30a16a24f3bda1db6512ece"
TOOLS = {"round_json_append.py": "88178a9a3c83dec204e90e6dcf8c4db9", "round_close.py": "415aa82b34c8fd82d09bfe8a8ce67eed", "round_close.sh": "430693122ef66bb5a293fb421ff0f7fc"}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_reviewer():
    path = Path(__file__).with_name("t16_r021_review.py")
    if sha(path) != REVIEWER_SHA:
        raise ValueError("reviewer source changed")
    spec = importlib.util.spec_from_file_location("ft_r021_review_pinned", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def write(path: Path, data: bytes, created: list[Path]) -> None:
    with path.open("xb") as stream:
        stream.write(data)
    created.append(path)


def jb(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def close(directory: Path, root: Path) -> dict:
    review = load_reviewer()
    directory = review.guarded(directory)
    if directory != review.DIRECTORY:
        raise ValueError("exact canonical R021 round required")
    if any((directory / item).exists() for item in review.CONTROL):
        raise ValueError("unsealed exact R021 directory required")
    review_path = directory / f"review_batch{BATCH}.json"
    review_doc = review.load(review_path)
    required = {"schema": "ft_independent_raw_review/v1", "verdict": "PASS", "formal_verdict": "pending_review", "rid": RID, "batch": BATCH}
    if any(review_doc.get(key) != value for key, value in required.items()):
        raise ValueError("independent review is not a positive D14 review")
    # Re-audit prior to any write; a recorded review is never trusted by itself.
    if review.audit(directory, allow_review=True) != review_doc:
        raise ValueError("independent review no longer recomputes")
    root = review.guarded(root)
    sources = {}
    for name, expected in TOOLS.items():
        data = (root / "scripts" / name).read_bytes()
        if hashlib.md5(data).hexdigest() != expected:
            raise ValueError("published D04 tool changed: " + name)
        if (directory / name).exists():
            raise FileExistsError("existing archive retained: " + name)
        sources[name] = data
    if any((directory / name).exists() for name in ("initial_metadata.json", "d04_tool_versions.json", "batch.sh")):
        raise FileExistsError("existing preparation retained")
    wrapper = review.require(directory / f"batch{BATCH}.sh")
    metadata = {"schema": "ft_round/v2", "round_id": RID, "epoch": 2, "card": "T16", "title": "D14 gate",
                "parent": "E2-pre-gate-D00", "base": {"commit": review.PARENT, "worktree": "/data2/FreeToken/wt/e2base", "code_version": "E2-base@23f2e2c"},
                "experimental": {"candidate_commit": review.CANDIDATE, "worktree": "/data2/FreeToken/wt/e2d14", "path_source": f"gate_batch{BATCH}.json"},
                "design": {"batch": BATCH, "gate": "D14", "serve_order": list(review.ARMS), "epoch_baseline_commit": review.PARENT},
                "diagnostics": {"independent_review_sha256": sha(review_path), "review_path": review_path.name, "gate_sha256": review_doc["gate_sha256"], "batch_wrapper_sha256": review.WRAPPER_SHA},
                "verdict": "pending_review", "proposed_verdict": None, "verdict_history": [], "retractions": [], "histories": []}
    created: list[Path] = []
    try:
        write(directory / "initial_metadata.json", jb(metadata), created)
        write(directory / "batch.sh", wrapper.read_bytes(), created)
        for name, data in sources.items():
            write(directory / name, data, created)
        write(directory / "d04_tool_versions.json", jb({name: {"md5": TOOLS[name], "sha256": hashlib.sha256(data).hexdigest()} for name, data in sources.items()}), created)
        final = dict(metadata, manifest="MANIFEST.sha256", batch_logs=[{"path": str(directory.parent / f"batch{BATCH}.log"), "sha256": sha(review.require(directory.parent / f"batch{BATCH}.log"))}])
        write(directory / "round.json", jb(final), created)
        subprocess.run(["bash", str(directory / "round_close.sh"), RID, "--round-root", str(directory.parent)], env={**os.environ, "FT_ROUND_PYTHON": sys.executable}, check=True)
    except BaseException as exc:
        raise RuntimeError("R021 closure failed; artifacts retained for inspection") from exc
    subprocess.run([sys.executable, str(directory / "round_json_append.py"), str(directory), "check"], check=True)
    if (directory / "round.json").read_bytes() != (directory / "round_history/round.v001.json").read_bytes():
        raise ValueError("sealed history differs")
    for line in (directory / "MANIFEST.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        target = (directory / relative).resolve(strict=True)
        if directory not in target.parents or sha(target) != expected:
            raise ValueError("sealed manifest differs")
    return {"rid": RID, "batch": BATCH, "round_sha256": sha(directory / "round.json"), "manifest_sha256": sha(directory / "MANIFEST.sha256"), "independent_review_sha256": sha(review_path), "formal_verdict": "pending_review"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--round-dir", type=Path)
    parser.add_argument("--root", type=Path)
    options = parser.parse_args()
    if not options.close or sys.platform != "linux" or not options.round_dir or not options.root:
        parser.error("--close, --round-dir, --root and Linux required")
    print(json.dumps(close(options.round_dir, options.root), sort_keys=True))
