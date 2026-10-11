"""Prepare, but do not close, the D03 T16 gate measurement.

This is deliberately narrower than a round closer.  It validates the frozen
runner artefacts and writes only the initial metadata and byte-for-byte batch
wrapper needed by the independent D04 close step.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


RID = "E2-R002-gate-D03"
PARENT_COMMIT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE_COMMIT = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
CONTROL_NAMES = ("round.json", "round_history", "MANIFEST.sha256")
ARM_FILES = ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt", "det.json", "tax.json", "prefill_seq.txt")
PID_RE = re.compile(r"['\"]?\.pid=(\d+)['\"]?")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def require_file(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"missing or empty required artifact: {path}")
    return path


def assert_owned_tree(directory):
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    for path in [directory, *directory.rglob("*")]:
        if path.is_symlink() or (uid is not None and path.stat().st_uid != uid):
            raise ValueError(f"foreign owner or symlink: {path}")


def terminal_pid(pid):
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return True
    tail = stat.read_text(encoding="utf-8").partition(") ")[2]
    if not tail:
        raise ValueError(f"malformed proc stat for PID {pid}")
    return tail[0] == "Z"


def finite_numeric_leaves(value, prefix=""):
    """Return all numeric leaves, rejecting non-finite values on the way."""
    found = {}
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"non-finite gate metric: {prefix}")
        found[prefix] = value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(finite_numeric_leaves(item, f"{prefix}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("non-string gate metric key")
            found.update(finite_numeric_leaves(item, f"{prefix}.{key}" if prefix else key))
    return found


def service_pid(arm):
    """Read the runner's archived parsed-argument PID ownership proof."""
    text = require_file(arm / "serve_args.txt").read_text(encoding="utf-8")
    matches = PID_RE.findall(text)
    if len(matches) != 1:
        raise ValueError(f"cannot uniquely recover owned service PID from {arm / 'serve_args.txt'}")
    pid = int(matches[0])
    if pid <= 0:
        raise ValueError("invalid owned service PID")
    return pid


def expected_commit(arm_name):
    return PARENT_COMMIT if arm_name.startswith("PARENT") else CANDIDATE_COMMIT


def validate_arm(directory, arm_name):
    if not re.fullmatch(r"(?:PARENT|NEW)(?:_P)?_b\d+", arm_name):
        raise ValueError(f"unexpected D03 arm: {arm_name}")
    arm = directory / arm_name
    if not arm.is_dir():
        raise ValueError(f"arm directory missing: {arm_name}")
    for name in ARM_FILES:
        require_file(arm / name)
    pid = service_pid(arm)
    if not terminal_pid(pid):
        raise ValueError(f"owned service PID is still live: {pid}")
    environment = (arm / "ENV.txt").read_text(encoding="utf-8")
    if expected_commit(arm_name) not in environment:
        raise ValueError(f"full source commit missing from environment: {arm_name}")
    return {"serve_cmd": f"{arm_name}/SERVE_CMD.txt", "serve_args": f"{arm_name}/serve_args.txt",
            "environment_snapshot": f"{arm_name}/ENV.txt", "owned_service_pid": pid,
            "ownership_proof": f"{arm_name}/serve_args.txt:_unique_suffix"}


def validate_gate(directory, batch):
    gate_path = require_file(directory / f"gate_batch{batch}.json")
    gate = read_json(gate_path)
    if (gate.get("gate") != "D03" or gate.get("proposed_verdict") != "kept"
            or gate.get("parent_commit") != PARENT_COMMIT or gate.get("new_commit") != CANDIDATE_COMMIT):
        raise ValueError("D03 gate identity or kept verdict mismatch")
    arms = gate.get("arms")
    expected_arms = {f"{name}_b{batch}" for name in ("PARENT", "NEW", "PARENT_P", "NEW_P")}
    if not isinstance(arms, list) or len(arms) != 4 or set(arms) != expected_arms:
        raise ValueError("D03 gate must contain exactly four unique arms")
    layer_major = gate.get("layer_major")
    if not isinstance(layer_major, dict) or set(("D0", "PROD")) - set(layer_major):
        raise ValueError("D03 layer_major D0/PROD evidence missing")
    prefill = layer_major.get("prefill")
    if not isinstance(prefill, dict) or prefill.get("parent_rows") != 13 or prefill.get("new_rows") != 13:
        raise ValueError("D03 requires 13 parent and 13 candidate prefill rows")
    finite_numeric_leaves(layer_major, "layer_major")
    return gate, gate_path


def validate_status(directory, batch):
    status_path = require_file(directory / f"status_batch{batch}.json")
    status = read_json(status_path)
    pid = status.get("batch_pid")
    if (status.get("gate") != "D03" or status.get("batch") != batch or status.get("state") != "complete"
            or type(pid) is not int or pid <= 0):
        raise ValueError("D03 status is not the exact completed batch")
    if not terminal_pid(pid):
        raise ValueError(f"owned batch PID is still live: {pid}")
    return status, status_path


def validate_review(path, batch):
    review = read_json(require_file(path))
    if review.get("verdict") != "PASS" or review.get("rid") != RID or review.get("batch") != batch:
        raise ValueError("independent review is not PASS for this D03 RID/batch")
    return review


def prepare(directory, batch, review_path, now=None):
    directory = directory.resolve(strict=True)
    if directory.name != RID:
        raise ValueError(f"round directory must be exactly {RID}")
    if any((directory / name).exists() for name in CONTROL_NAMES):
        raise ValueError("formal closure artifacts already exist")
    review_path = review_path.resolve(strict=True)
    if review_path != directory / f"review_batch{batch}.json":
        raise ValueError("independent review must belong to the exact round and batch")
    assert_owned_tree(directory)
    gate, gate_path = validate_gate(directory, batch)
    status, status_path = validate_status(directory, batch)
    review = validate_review(review_path, batch)
    arms = {arm: validate_arm(directory, arm) for arm in gate["arms"]}
    wrapper = require_file(directory / f"batch{batch}.sh")
    wrapper_bytes = wrapper.read_bytes()
    archived_wrapper = directory / "batch.sh"
    if archived_wrapper.exists() and archived_wrapper.read_bytes() != wrapper_bytes:
        raise ValueError("existing batch.sh is not byte-exact actual batch wrapper")
    numeric = finite_numeric_leaves(gate["layer_major"], "layer_major")
    first_shots = [{"metric_path": key, "value": value, "unit": "s"}
                   for key, value in numeric.items() if "ttft" in key.lower()]
    created = (now or datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S CST")
    document = {
        "schema": "ft_round/v2", "round_id": RID, "epoch": 2, "card": "T16",
        "title": "D03 default-path losslessness gate", "created_at": created,
        "base": {"repo": "fork/FreeToken", "commit": PARENT_COMMIT,
                 "code_version": "E2-base@23f2e2c", "worktree": "/data2/FreeToken/wt/e2base"},
        "experimental": {"candidate_commit": CANDIDATE_COMMIT,
                           "worktree": "/data2/FreeToken/wt/e1r003st",
                           "path_source": f"gate_batch{batch}.json"},
        "design": {"batch": batch, "gate": "D03", "serve_order": gate["arms"]},
        "serve": {"arms": arms},
        "results": {"parent_prefill_rows": 13, "new_prefill_rows": 13,
                    "gate_numeric": numeric},
        "first_shots": first_shots,
        "diagnostics": {"gate_path": gate_path.name, "gate_sha256": sha256(gate_path),
                        "status_path": status_path.name, "status_sha256": sha256(status_path),
                        "review_path": str(review_path), "review_sha256": sha256(review_path),
                        "batch_wrapper": wrapper.name, "batch_wrapper_sha256": sha256(wrapper),
                        "raw_gate": gate, "tools": status.get("tools")},
        "proposed_verdict": None, "verdict": "pending_review", "verdict_history": [],
        "retractions": [], "histories": [],
        "independent_review_sha256": sha256(review_path),
    }
    output = directory / "initial_metadata.json"
    if output.exists():
        raise ValueError("initial_metadata.json already exists")
    # Both writes are exclusive.  Validation completed before either mutation.
    if not archived_wrapper.exists():
        with archived_wrapper.open("xb") as stream:
            stream.write(wrapper_bytes)
    with output.open("xb") as stream:
        stream.write(json_bytes(document))
    return {"initial_metadata": str(output), "initial_metadata_sha256": sha256(output),
            "batch_sha256": sha256(archived_wrapper), "review_verdict": review["verdict"],
            "batch_pid": status["batch_pid"]}


def self_test():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / RID
        root.mkdir()
        batch = 44
        arms = [f"{name}_b{batch}" for name in ("PARENT", "NEW", "PARENT_P", "NEW_P")]
        for arm in arms:
            path = root / arm
            path.mkdir()
            for name in ARM_FILES:
                (path / name).write_text("x\n", encoding="utf-8")
            (path / "serve_args.txt").write_text("Parsed arguments\n{'_unique_suffix': '.pid=999999'}\n", encoding="utf-8")
            (path / "ENV.txt").write_text(expected_commit(arm) + "\n", encoding="utf-8")
        gate = {"gate": "D03", "proposed_verdict": "kept", "parent_commit": PARENT_COMMIT,
                "new_commit": CANDIDATE_COMMIT, "arms": arms,
                "layer_major": {"D0": {"det": {"records": [{"ttft_s": 1.0}]}},
                                "PROD": {"det": {"records": [{"ttft_s": 2.0}]}},
                                "prefill": {"parent_rows": 13, "new_rows": 13}}}
        (root / f"gate_batch{batch}.json").write_bytes(json_bytes(gate))
        (root / f"status_batch{batch}.json").write_bytes(json_bytes(
            {"gate": "D03", "batch": batch, "state": "complete", "batch_pid": 999999}))
        (root / f"batch{batch}.sh").write_bytes(b"#!/bin/sh\necho exact\n")
        review = root / f"review_batch{batch}.json"
        review.write_bytes(json_bytes({"rid": RID, "batch": batch, "verdict": "PASS"}))
        result = prepare(root, batch, review, datetime(2026, 10, 4, tzinfo=timezone(timedelta(hours=8))))
        assert (root / "batch.sh").read_bytes() == (root / f"batch{batch}.sh").read_bytes()
        metadata = read_json(root / "initial_metadata.json")
        assert metadata["verdict"] == "pending_review" and metadata["results"]["parent_prefill_rows"] == 13
        assert result["review_verdict"] == "PASS"
        try:
            prepare(root, batch, review)
        except ValueError as exc:
            assert "initial_metadata" in str(exc)
        else:
            raise AssertionError("exclusive metadata output was overwritten")
    print("d03_t16_prepare self-test: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-dir", type=Path)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if any(value is not None for value in (args.round_dir, args.batch, args.review)):
            parser.error("--self-test takes no preparation arguments")
        self_test()
        return
    if args.round_dir is None or args.batch is None or args.review is None:
        parser.error("--round-dir, --batch and --review are required")
    print(json.dumps(prepare(args.round_dir, args.batch, args.review), sort_keys=True))


if __name__ == "__main__":
    main()
