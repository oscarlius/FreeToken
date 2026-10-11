"""Prepare open D03 phase-2 measurements for the existing initial closer.

The command deliberately has no close mode.  It validates producer artefacts,
then writes only an exclusive ``initial_metadata.json`` (and an absent
``batch.sh`` archive) when explicitly invoked with ``--prepare`` on Linux.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys


PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
CANDIDATE = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
SPECS = {
    "E2-R014": {"card": "T04", "kind": "t04", "title": "T04 phase-2 logits measurement"},
    "E2-R015": {"card": "T04", "kind": "t04", "title": "T04 controlled restore/fresh logits retry", "controlled": True},
    "E2-R012": {"card": "T10", "kind": "t10p1", "title": "T10 phase-1 engine token measurement"},
    "E2-R016": {"card": "T10", "kind": "t10p1", "title": "T10 phase-1 engine token retry"},
    "E2-R013": {"card": "T10", "kind": "t10p2", "title": "T10 phase-2 fresh logits measurement"},
}
CONTROL = ("round.json", "round_history", "MANIFEST.sha256")
ARM_FILES = ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt", "owned_process.json")
T04_CONTROLLED_SOURCE_HASHES = {
    "terminal_tokens.json": "916ee8575d692b4452f4df6fae4d5fe4208ad776b11f9a3ba02979f1c79b712e",
    "raw_binding_manifest.json": "6a08e2e855acacab103eeb4ea0d07972f3e477506020783ec930dbca744fa1e2",
    "trace.json": "097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def require(path: Path) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"missing or empty artifact: {path}")
    if path.is_symlink():
        raise ValueError(f"symlink artifact refused: {path}")
    return path


def assert_owned(directory: Path) -> None:
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    for path in (directory, *directory.rglob("*")):
        if path.is_symlink() or (uid is not None and path.stat().st_uid != uid):
            raise ValueError(f"foreign owner or symlink: {path}")


def terminal(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return True
    state = stat_path.read_text(encoding="utf-8").partition(") ")[2]
    return bool(state) and state[0] == "Z"


def verify_manifest(directory: Path, filename="RUN_MANIFEST.sha256") -> tuple[str, dict[str, str]]:
    manifest = require(directory / filename)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("empty RUN_MANIFEST")
    declared = {}
    for line in lines:
        digest, marker, relative = line.partition("  ")
        if not marker or not re.fullmatch(r"[0-9a-f]{64}", digest) or not relative:
            raise ValueError("invalid RUN_MANIFEST line")
        path = directory / relative
        resolved = path.resolve()
        normalized = resolved.relative_to(directory).as_posix() if directory in resolved.parents else None
        if (normalized is None or normalized in declared or path.is_symlink()
                or not path.is_file() or sha(path) != digest):
            raise ValueError(f"{filename} mismatch: {relative}")
        declared[normalized] = digest
    return sha(manifest), declared


def manifest_covers(directory: Path, declared: dict[str, str], paths: list[Path]) -> None:
    for path in paths:
        relative = path.relative_to(directory).as_posix()
        if declared.get(relative) != sha(path):
            raise ValueError(f"RUN_MANIFEST does not cover consumed artifact: {relative}")


def numeric_leaves(value: object, prefix: str = "") -> tuple[dict[str, float | int], list[dict[str, str]]]:
    good, bad = {}, []
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return good, bad
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            good[prefix] = value
        else:
            bad.append({"path": prefix, "value": repr(value)})
    elif isinstance(value, list):
        for index, item in enumerate(value):
            g, b = numeric_leaves(item, f"{prefix}[{index}]")
            good.update(g); bad.extend(b)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                g, b = numeric_leaves(item, f"{prefix}.{key}" if prefix else key)
                good.update(g); bad.extend(b)
    return good, bad


def evidence_equal(left: object, right: object) -> bool:
    """Compare archived JSON while treating matching non-finite evidence as evidence."""
    if type(left) is not type(right):
        return False
    if isinstance(left, float) and not math.isfinite(left):
        return not math.isfinite(right) and repr(left) == repr(right)
    if isinstance(left, dict):
        return set(left) == set(right) and all(evidence_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(evidence_equal(a, b) for a, b in zip(left, right))
    return left == right


def validate_admission(directory: Path, spec: dict, batch: int) -> tuple[dict, Path]:
    path = require(directory / "admission.json")
    admission = read_json(path)
    if (admission.get("rid") != directory.name or admission.get("batch") != batch
            or admission.get("card") != spec["card"] or admission.get("commit") != PARENT
            or admission.get("code_version") != "E2-base@23f2e2c"
            or admission.get("candidate_commit") != CANDIDATE):
        raise ValueError("admission does not bind this parent/candidate/card/batch")
    return admission, path


def validate_status(directory: Path, spec: dict, batch: int) -> tuple[dict, Path]:
    path = require(directory / f"status_batch{batch}.json")
    status = read_json(path)
    pid = status.get("batch_pid")
    if (status.get("rid") != directory.name or status.get("batch") != batch or status.get("gate") != spec["card"]
            or status.get("state") not in ("complete", "complete_measurements_pending_review")
            or type(pid) is not int or pid <= 0 or not terminal(pid)):
        raise ValueError("status is not this terminal completed measurement")
    return status, path


def validate_wrapper(directory: Path, admission: dict, status: dict, batch: int) -> Path:
    wrapper = require(directory / "batch.sh")
    digest = sha(wrapper)
    if admission.get("batch_wrapper_sha256") != digest or status.get("batch_wrapper_sha256") != digest:
        raise ValueError("producer batch.sh SHA does not bind admission and status")
    return wrapper


def validate_arm(directory: Path, name: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"bad arm name: {name}")
    arm = directory / name
    if not arm.is_dir():
        raise ValueError(f"missing arm directory: {name}")
    for filename in ARM_FILES:
        require(arm / filename)
    owned = read_json(arm / "owned_process.json")
    pid = owned.get("pid")
    if type(pid) is not int or pid <= 0 or not terminal(pid):
        raise ValueError(f"arm has non-terminal owned PID: {name}")
    environment = (arm / "ENV.txt").read_text(encoding="utf-8")
    if CANDIDATE not in environment:
        raise ValueError(f"candidate full commit missing in {name}/ENV.txt")
    pgid = owned.get("pgid")
    if type(pgid) is not int or pgid <= 0:
        raise ValueError(f"arm lacks archived service PGID: {name}")
    return {"serve_cmd": f"{name}/SERVE_CMD.txt", "serve_args": f"{name}/serve_args.txt",
            "environment_snapshot": f"{name}/ENV.txt", "owned_service_pid": pid, "owned_service_pgid": pgid,
            "validation_scope": "producer_live_check_archived_not_recomputed_after_exit"}


def token(path: Path) -> dict:
    record = read_json(path)
    prompt, generated = record.get("prompt_ids"), record.get("generated_ids")
    if (record.get("schema") != "ft_dev_tokens/v1" or not isinstance(prompt, list) or not isinstance(generated, list)
            or not prompt or not generated or record.get("finish_reason") not in ("stop", "length")
            or type(record.get("uid")) is not int or record["uid"] < 0
            or type(record.get("pid")) is not int or record["pid"] <= 0
            or any(type(item) is not int or not 0 <= item < 2**31 for item in prompt + generated)):
        raise ValueError(f"invalid terminal token record: {path}")
    digest = lambda values: hashlib.sha256(struct.pack(f"<{len(values)}i", *values)).hexdigest()
    if (record.get("prompt_length") != len(prompt)
            or record.get("prompt_ids_sha256_int32le") != digest(prompt)
            or record.get("generated_ids_sha256_int32le") != digest(generated)
            or record.get("input_ids_sha256_int32le") != digest(prompt + generated)):
        raise ValueError(f"terminal token ID hashes/lengths do not bind: {path}")
    return record


def common_prefix(values: list[list[int]]) -> int:
    return min(next((i for i, pair in enumerate(zip(values[0], value)) if pair[0] != pair[1]), min(len(values[0]), len(value)))
               for value in values[1:])


def trace_keys(path: Path) -> set[str]:
    rows = read_json(path).get("rounds")
    if not isinstance(rows, list):
        raise ValueError("T10 trace round list missing")
    keys = set()
    for row in rows:
        messages, record = row.get("messages"), row.get("record") or {}
        key = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        if record.get("messages_sha") != key:
            raise ValueError("T10 trace messages digest mismatch")
        keys.add(key)
    if len(keys) != 12:
        raise ValueError("T10 trace must retain exactly 12 canonical message keys")
    return keys


def t10_phase1(directory: Path, admission: dict) -> tuple[dict, dict[str, float | int], list[Path]]:
    manifest_path = require(directory / "phase1_manifest.json")
    manifest = read_json(manifest_path)
    arms = manifest.get("arms")
    if (manifest.get("schema") != "t10_engine_tokens/v1" or manifest.get("rid") != directory.name
            or directory.name not in {"E2-R012", "E2-R016"}
            or not isinstance(arms, dict) or set(arms) != {"B1", "B2", "B3"}):
        raise ValueError("T10 phase1 manifest lacks exact B1/B2/B3 arms")
    frontend_path, reverse_path, forward_path = (require(directory / name) for name in
                                                  ("frontend_manifest.json", "reverse_trace.json", "forward_trace.json"))
    if (admission.get("frontend_manifest_sha256") != sha(frontend_path)
            or admission.get("reverse_trace_sha256") != sha(reverse_path)
            or admission.get("forward_trace_sha256") != sha(forward_path)
            or manifest.get("frontend_manifest_sha256") != sha(frontend_path)):
        raise ValueError("T10 phase1 frontend/trace SHA provenance mismatch")
    frontend = read_json(frontend_path).get("rounds")
    if not isinstance(frontend, list) or len(frontend) != 12:
        raise ValueError("T10 phase1 frontend manifest must retain 12 inputs")
    frontend_by_key = {row.get("messages_sha"): row for row in frontend}
    frontend_keys = set(frontend_by_key)
    if len(frontend_keys) != 12 or None in frontend_keys:
        raise ValueError("T10 phase1 frontend message keys are invalid")
    if trace_keys(reverse_path) != frontend_keys or trace_keys(forward_path) != frontend_keys:
        raise ValueError("T10 frontend inputs do not bind both canonical traces")
    total, completion, consumed = 0, 0, [manifest_path, frontend_path, reverse_path, forward_path]
    sequences, paths_seen, uids_seen = {}, set(), set()
    for arm in ("B1", "B2", "B3"):
        phases = arms[arm]
        validate_arm(directory, arm)
        if not isinstance(phases, dict) or set(phases) != {"cold", "warm"}:
            raise ValueError("T10 phase1 lacks cold/warm streams")
        for phase in ("cold", "warm"):
            rows = phases[phase]
            if not isinstance(rows, dict) or len(rows) != 12:
                raise ValueError("T10 phase1 requires 12 terminal rows per stream")
            if set(rows) != frontend_keys:
                raise ValueError("T10 phase1 stream keys do not exactly bind frontend inputs")
            for message_sha, record in rows.items():
                file = directory / arm / "logits" / record.get("terminal_file", "")
                if not file.is_file() or sha(file) != record.get("terminal_sha256"):
                    raise ValueError("T10 phase1 terminal token file/hash mismatch")
                relative = file.relative_to(directory).as_posix()
                if relative in paths_seen:
                    raise ValueError("T10 phase1 reuses a terminal file")
                paths_seen.add(relative)
                terminal_record = token(file)
                if (terminal_record.get("uid") != record.get("uid") or terminal_record.get("pid") != record.get("pid")
                        or terminal_record["prompt_ids"] != record.get("prompt_ids")
                        or terminal_record["generated_ids"] != record.get("generated_ids")):
                    raise ValueError("T10 phase1 terminal token identity mismatch")
                expected = frontend_by_key[message_sha]
                if (terminal_record["prompt_ids"] != expected.get("prompt_ids")
                        or terminal_record["prompt_ids_sha256_int32le"] != expected.get("prompt_ids_sha256_int32le")):
                    raise ValueError("T10 terminal prompt does not bind canonical frontend input")
                identity = (terminal_record["pid"], terminal_record["uid"])
                if identity in uids_seen:
                    raise ValueError("T10 phase1 repeats a terminal PID/UID identity")
                uids_seen.add(identity)
                sequences.setdefault(message_sha, []).append(terminal_record["generated_ids"])
                consumed.append(file)
                total += 1; completion += len(terminal_record["generated_ids"])
    if total != 72:
        raise ValueError("T10 phase1 must retain 72 terminal token records")
    forks = manifest.get("forkpoints")
    if not isinstance(forks, list):
        raise ValueError("T10 phase1 forkpoint list missing")
    derived = []
    for message_sha, values in sorted(sequences.items()):
        if not all(value == values[0] for value in values[1:]):
            k = common_prefix(values)
            source = frontend_by_key[message_sha]
            derived.append({"round": source.get("round"), "messages_sha": message_sha,
                            "prompt_ids": source.get("prompt_ids"),
                            "prompt_ids_sha256_int32le": source.get("prompt_ids_sha256_int32le"),
                            "common_generated_ids": values[0][:k], "first_difference_index": k, "k": k,
                            "observed_next_ids": [value[k] if k < len(value) else None for value in values]})
    if len({(item["messages_sha"], tuple(item["common_generated_ids"])) for item in derived}) != len(derived):
        raise ValueError("T10 derived fork identities are duplicated")
    claimed = sorted(forks, key=lambda item: (str(item.get("messages_sha")), tuple(item.get("common_generated_ids", []))))
    derived = sorted(derived, key=lambda item: (item["messages_sha"], tuple(item["common_generated_ids"])))
    if derived != claimed:
        raise ValueError("T10 phase1 forkpoints do not equal six-stream rederivation")
    return manifest, {"terminal_records": total, "generated_tokens": completion, "forkpoints": len(derived)}, consumed


def verify_sealed_parent(parent: Path) -> dict:
    assert_owned(parent)
    if os.name == "posix" and any(path.stat().st_mode & 0o222 for path in (parent, *parent.rglob("*"))):
        raise ValueError("T10 phase2 parent contains writable artifacts")
    _, declared = verify_manifest(parent, "MANIFEST.sha256")
    writer = require(parent / "round_json_append.py")
    if hashlib.md5(writer.read_bytes()).hexdigest() != "88178a9a3c83dec204e90e6dcf8c4db9":
        raise ValueError("T10 phase2 parent archived D04 writer differs from reviewed version")
    manifest_covers(parent, declared, [writer])
    checked = subprocess.run([sys.executable, str(writer), str(parent), "check"],
                             capture_output=True, text=True, timeout=60)
    if checked.returncode:
        raise ValueError(f"T10 phase2 parent D04 history check failed: {checked.stderr.strip()}")
    proof = read_json(require(parent / "round.json"))
    if parent.name not in {"E2-R012", "E2-R016"} or proof.get("round_id") != parent.name or proof.get("card") != "T10":
        raise ValueError("T10 phase2 parent round identity mismatch")
    admission_path = require(parent / "admission.json")
    admission = read_json(admission_path)
    if admission.get("candidate_commit") != CANDIDATE or admission.get("commit") != PARENT:
        raise ValueError("T10 phase2 parent candidate/lineage mismatch")
    phase, _, consumed = t10_phase1(parent, admission)
    arm_files = [parent / arm / name for arm in phase["arms"] for name in ARM_FILES]
    manifest_covers(parent, declared, [admission_path, *consumed, *arm_files])
    return phase


def last_json(path: Path) -> dict:
    try:
        lines = [line for line in require(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        result = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise ValueError(f"capture/comparison log lacks final JSON: {path}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"capture/comparison log must end with a JSON object: {path}")
    return result


def capture_evidence(directory: Path, arm: str, capture: dict, log_name: str) -> list[Path]:
    capture_path = require(directory / arm / "capture.json")
    if not evidence_equal(read_json(capture_path), capture):
        raise ValueError(f"{arm} capture.json differs from measurement")
    uid, pid, seq = (capture.get(key) for key in ("uid", "capture_pid", "dump_seq"))
    if (type(uid) is not int or uid < 0 or type(pid) is not int or pid <= 0
            or type(seq) is not int or seq <= 0):
        raise ValueError(f"{arm} capture lacks valid UID/PID/dump sequence")
    logits = directory / arm / "logits"
    token_path = require(logits / f"tokens_uid{uid}_pid{pid}.json")
    record = token(token_path)
    if (record["uid"] != uid or record["pid"] != pid
            or record["prompt_length"] != capture.get("input_length")
            or record["prompt_ids_sha256_int32le"] != capture.get("input_sha256")):
        raise ValueError(f"{arm} terminal token UID/PID/input does not bind capture")
    log = require(directory / arm / log_name)
    if not evidence_equal(last_json(log), {key: value for key, value in capture.items() if key != "capture_pid"}):
        raise ValueError(f"{arm} capture log differs before producer PID annotation")
    index_path = require(logits / "index.jsonl")
    try:
        rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ValueError(f"{arm} invalid logits index") from exc
    matches = [row for row in rows if isinstance(row, dict) and row.get("kind") == "logits"
               and row.get("uid") == uid and row.get("seq") == seq]
    if len(matches) != 1:
        raise ValueError(f"{arm} logits index UID/seq must be unique")
    row, length = matches[0], capture.get("input_length")
    extra = row.get("extra") or {}
    if (row.get("length") != length or extra.get("input_length") != length
            or extra.get("input_prefix_sha256") != capture.get("input_sha256")
            or extra.get("k") != capture.get("k") or extra.get("positions") != capture.get("positions")):
        raise ValueError(f"{arm} logits index input/K/positions differs from capture")
    return [capture_path, token_path, log, index_path]


def validate_controlled_source(directory: Path) -> list[Path]:
    """Admit only the already frozen c30 G4 source, including its trace binding."""
    files = [require(directory / name) for name in T04_CONTROLLED_SOURCE_HASHES]
    for path in files:
        if sha(path) != T04_CONTROLLED_SOURCE_HASHES[path.name]:
            raise ValueError("controlled T04 frozen source artifact changed: " + path.name)
    source = token(directory / "terminal_tokens.json")
    binding = read_json(directory / "raw_binding_manifest.json")
    admission = read_json(directory / "admission.json")
    evidence = admission.get("input") or {}
    if (evidence.get("token_file_sha256") != sha(files[0])
            or evidence.get("binding_manifest_sha256") != sha(files[1])
            or evidence.get("trace_sha256") != sha(files[2])
            or evidence.get("terminal_uid") != source["uid"] or evidence.get("terminal_pid") != source["pid"]
            or evidence.get("prompt_length") != source["prompt_length"] or evidence.get("k") != 32
            or binding.get("trace_sha256") != sha(files[2])
            or binding.get("raw_ids_sha256") != source["prompt_ids_sha256_int32le"]
            or binding.get("input_length") != source["prompt_length"] or admission.get("binding") != binding
            or not re.fullmatch(r"[0-9a-f]{64}", str(binding.get("request_sha256", "")))
            or binding.get("messages_sha") not in trace_keys(directory / "trace.json")):
        raise ValueError("controlled T04 admission does not bind the frozen terminal/binding/trace source")
    return files


def validate_controlled_history(directory: Path, arm: str, capture: dict) -> list[Path]:
    """Bind the R015 request history to its actual raw-input and cache evidence."""
    source_path = require(directory / "terminal_tokens.json")
    prefix_path = require(directory / "prompt_ids.json")
    suffix_path = require(directory / "output_ids_first_k.json")
    source = token(source_path)
    prefix = json.loads(prefix_path.read_text(encoding="utf-8"))
    suffix = json.loads(suffix_path.read_text(encoding="utf-8"))
    k = capture.get("k")
    digest = lambda values: hashlib.sha256(struct.pack(f"<{len(values)}i", *values)).hexdigest()
    if (type(k) is not int or not 1 <= k <= 64 or prefix != source["prompt_ids"]
            or suffix != source["generated_ids"][:k] or len(suffix) != k
            or capture.get("input_sha256") != digest(prefix + suffix)):
        raise ValueError("controlled capture does not bind the immutable source P+X")
    logits = directory / arm / "logits"
    controlled_path = require(logits / "controlled_capture.json")
    if not evidence_equal(read_json(controlled_path), {key: value for key, value in capture.items() if key != "capture_pid"}):
        raise ValueError("controlled capture artifact differs from producer capture")
    mode = {"candidate_boundary": "diagnostic", "restore": "branch-bank", "recompute": "fresh", "legal": "fresh"}[arm]
    if capture.get("mode") != mode or capture.get("warm_usage") is not None:
        raise ValueError("controlled capture mode/warm-prefix contract failed")
    priming = capture.get("priming")
    if not isinstance(priming, dict) or priming.get("warm_usage") is not None:
        raise ValueError("controlled capture lacks explicit request history")
    index_path = require(logits / "index.jsonl")
    rows = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    matched = [row for row in rows if row.get("kind") == "logits" and row.get("uid") == capture.get("uid")
               and row.get("seq") == capture.get("dump_seq")]
    if len(matched) != 1:
        raise ValueError("controlled capture has no unique index binding")
    extra = matched[0].get("extra") or {}
    if (extra.get("cached_len") != capture.get("cached_len")
            or not evidence_equal(extra.get("restore_proof"), capture.get("restore_proof"))):
        raise ValueError("controlled capture cache/proof differs from raw index")
    files = [source_path, prefix_path, suffix_path, controlled_path]
    if mode == "diagnostic":
        return files
    proof = capture.get("restore_proof")
    if mode == "fresh":
        if capture.get("cached_len") != 0 or proof is not None or capture.get("branch_usage") is not None:
            raise ValueError("fresh capture used cached state or a priming branch")
        if set(priming) != {"warm_usage"}:
            raise ValueError("fresh capture request history includes priming")
        return files
    length, tail_count = 12672, 96
    if (capture.get("cached_len") != length or not isinstance(proof, dict) or proof.get("length") != length
            or proof.get("kind") not in {"host", "device"} or proof.get("uid") != capture.get("uid")
            or any(type(proof.get(key)) is not int or proof[key] <= 0 for key in ("source_slot", "destination_slot"))):
        raise ValueError("branch-bank capture lacks exact intermediate-prefix restore proof")
    branch_path = require(logits / "branch_ids.json")
    branch = read_json(branch_path)
    branch_ids = branch.get("branch_ids")
    if (not isinstance(branch_ids, list) or any(type(item) is not int or not 0 <= item < 2**31 for item in branch_ids)
            or len(prefix) <= length or len(branch_ids) != length + tail_count
            or branch_ids[:length] != prefix[:length] or branch_ids[length] == prefix[length]
            or branch.get("common_prefix_length") != length or branch.get("branch_token_count") != tail_count
            or branch.get("prefix_length") != len(prefix) or branch.get("branch_sha256") != digest(branch_ids)
            or branch.get("full_input_sha256") != capture.get("input_sha256")
            or branch.get("full_input_length") != capture.get("input_length")
            or branch.get("full_prompt_next_token") != prefix[length]
            or branch.get("branch_first_token") != branch_ids[length]):
        raise ValueError("branch-bank priming raw IDs do not bind the declared competing branch")
    if (priming.get("branch_input_length") != len(branch_ids) or priming.get("common_prefix_length") != length
            or not evidence_equal(priming.get("branch_usage"), capture.get("branch_usage"))):
        raise ValueError("branch-bank request history differs from archived branch")
    branch_tokens = []
    for path in logits.glob("tokens_uid*_pid*.json"):
        record = token(path)
        if record["prompt_ids"] == branch_ids and record["pid"] == capture.get("capture_pid") and record["uid"] != capture.get("uid"):
            branch_tokens.append(path)
    if len(branch_tokens) != 1:
        raise ValueError("branch-bank priming terminal input/PID/UID is not unique")
    return files + [branch_path, branch_tokens[0]]


def validate_measurement(directory: Path, spec: dict) -> tuple[dict, dict[str, dict], dict[str, float | int], list[dict[str, str]], list[Path]]:
    metadata_path = require(directory / "round_metadata.json")
    metadata = read_json(metadata_path)
    if metadata.get("rid") != directory.name or metadata.get("status") != "complete_measurements_pending_review":
        raise ValueError("round_metadata is not completed for this RID")
    diagnostics, files = [], [metadata_path]
    arms, results = {}, {}
    if spec["kind"] == "t04":
        if spec.get("controlled"):
            files.extend(validate_controlled_source(directory))
        captures = metadata.get("arms")
        comparison = metadata.get("comparison")
        capture_names = {"candidate_boundary", "restore", "recompute", "legal"}
        expected_names = capture_names | {"candidate_boundary_regenerated_x", "candidate_boundary_terminal"}
        if not isinstance(captures, dict) or set(captures) != expected_names:
            raise ValueError("T04 requires four captures and two boundary diagnostics")
        boundary = captures["candidate_boundary_terminal"]
        if not isinstance(boundary, dict):
            raise ValueError("T04 boundary terminal diagnostic missing")
        boundary_path = Path(boundary.get("path", ""))
        if (not boundary_path.is_absolute() or directory not in boundary_path.resolve().parents
                or not boundary_path.is_file() or sha(boundary_path) != boundary.get("sha256")):
            raise ValueError("T04 boundary terminal path/SHA does not bind an archived token")
        boundary_token = token(boundary_path)
        if boundary_token.get("uid") != boundary.get("uid") or boundary_token.get("pid") != boundary.get("pid"):
            raise ValueError("T04 boundary terminal UID/PID mismatch")
        files.append(boundary_path)
        for arm in capture_names:
            capture = captures[arm]
            arms[arm] = validate_arm(directory, arm)
            capture_path = require(directory / arm / "capture.json")
            capture_actual = read_json(capture_path)
            if not isinstance(capture, dict) or capture_actual != capture:
                raise ValueError("T04 round metadata capture differs from archived capture.json")
            if capture_actual.get("k") is None or not capture_actual.get("input_sha256") or type(capture_actual.get("capture_pid")) is not int:
                raise ValueError("T04 capture lacks K/input hash binding")
            input_evidence = read_json(directory / "admission.json").get("input")
            if (not isinstance(input_evidence, dict) or capture_actual.get("k") != input_evidence.get("k")
                    or capture_actual.get("input_sha256") != input_evidence.get("full_input_sha256")
                    or capture_actual.get("input_length") != input_evidence.get("prompt_length", 0) + input_evidence.get("k", 0)
                    or capture_actual.get("positions") != list(range(capture_actual["input_length"] - capture_actual["k"], capture_actual["input_length"]))):
                raise ValueError("T04 capture does not bind admission full input/K/positions")
            files.extend(capture_evidence(directory, arm, capture_actual, "logits_capture.log"))
            if spec.get("controlled"):
                files.extend(validate_controlled_history(directory, arm, capture_actual))
        compare_path = require(directory / "logits_compare.json")
        try:
            compare_actual = json.loads(compare_path.read_text(encoding="utf-8").splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise ValueError("T04 comparison log lacks final JSON") from exc
        if not evidence_equal(compare_actual, comparison):
            raise ValueError("T04 comparison log final JSON differs from round metadata")
        files.append(compare_path)
        results, nonfinite = numeric_leaves(comparison, "comparison")
        if not results:
            raise ValueError("T04 comparison has no finite numeric statistics")
        diagnostics.extend(nonfinite)
    elif spec["kind"] == "t10p1":
        manifest, results, extra = t10_phase1(directory, read_json(directory / "admission.json"))
        arms = {arm: validate_arm(directory, arm) for arm in manifest["arms"]}
        files.extend(extra)
    else:
        result_path = require(directory / "stage2_results.json")
        stage2 = read_json(result_path)
        rows = stage2.get("results")
        if stage2.get("schema") != "t10_logits_stage2/v1" or not isinstance(rows, list) or not rows:
            raise ValueError("T10 phase2 needs at least one actual completed fork pair")
        phase_manifest = require(directory / "phase1_manifest.json")
        phase_round = require(directory / "phase1_round_proof.json")
        admission = read_json(directory / "admission.json")
        parent_rid = admission.get("parent_rid")
        if parent_rid not in {"E2-R012", "E2-R016"}:
            raise ValueError("T10 phase2 parent is not an assigned phase1 measurement")
        parent = directory.parent / parent_rid
        if not parent.is_dir():
            raise ValueError("T10 phase2 parent is not a sealed snapshot")
        parent_phase_manifest = verify_sealed_parent(parent)
        parent_round = require(parent / "round.json")
        parent_phase = parent / "phase1_manifest.json"
        if not parent_phase.is_file() or phase_manifest.read_bytes() != parent_phase.read_bytes() or phase_round.read_bytes() != parent_round.read_bytes():
            raise ValueError("T10 phase2 copied parent proof does not byte-bind the sealed parent")
        # The actual stage-2 producer rederives these six fields; phase-1's
        # diagnostic round/prompt-SHA fields are not in its row schema.
        fork_fields = ("messages_sha", "prompt_ids", "common_generated_ids", "k", "first_difference_index", "observed_next_ids")
        expected_forks = [{key: fork[key] for key in fork_fields}
                          for fork in sorted(parent_phase_manifest["forkpoints"], key=lambda item: item["messages_sha"])]
        if (admission.get("phase1_manifest_sha256") != sha(phase_manifest)
                or admission.get("phase1_round_proof_sha256") != sha(phase_round)
                or admission.get("forkpoints") != len(rows) or metadata.get("fresh_pairs") != len(rows)
                or [row.get("forkpoint") for row in rows] != expected_forks):
            raise ValueError("T10 phase2 admission does not bind complete parent/fork chain")
        for index, row in enumerate(rows):
            fork = row.get("forkpoint")
            if not isinstance(fork, dict) or not isinstance(fork.get("prompt_ids"), list) or not isinstance(fork.get("common_generated_ids"), list):
                raise ValueError("T10 phase2 row lacks actual forkpoint IDs")
            input_ids = fork["prompt_ids"] + fork["common_generated_ids"]
            if not input_ids:
                raise ValueError("T10 phase2 forkpoint has no final actual input ID")
            expected_sha = hashlib.sha256(struct.pack(f"<{len(input_ids)}i", *input_ids)).hexdigest()
            for side in ("capture_a", "capture_b"):
                capture = row.get(side)
                arm_name = f"fork{index:02d}_{'a' if side.endswith('a') else 'b'}"
                if (not isinstance(capture, dict) or capture.get("k") != 1 or capture.get("input_sha256") != expected_sha
                        or capture.get("input_length") != len(input_ids) or capture.get("positions") != [len(input_ids) - 1]):
                    raise ValueError("T10 phase2 capture lacks actual K=1 input binding")
                arms[arm_name] = validate_arm(directory, arm_name)
                files.extend(capture_evidence(directory, arm_name, capture, "capture.log"))
            a, b = (arms[f"fork{index:02d}_{side}"] for side in ("a", "b"))
            if (a["owned_service_pid"] == b["owned_service_pid"]
                    or a["owned_service_pgid"] == b["owned_service_pgid"]
                    or row["capture_a"]["capture_pid"] == row["capture_b"]["capture_pid"]):
                raise ValueError("T10 phase2 pair must use distinct service PID/PGID and worker PID")
            compare_path = require(directory / f"fork{index:02d}_compare.log")
            if not evidence_equal(last_json(compare_path), row.get("comparison")):
                raise ValueError("T10 phase2 comparison log differs from result row")
            files.append(compare_path)
        results, nonfinite = numeric_leaves([row["comparison"] for row in rows], "stage2_comparisons")
        if not results:
            raise ValueError("T10 phase2 has no finite comparison statistics")
        diagnostics.extend(nonfinite); files.extend([result_path, phase_manifest, phase_round])
    return metadata, arms, results, diagnostics, files


def prepare(directory: Path, batch: int, review_path: Path, *, now=None) -> dict:
    directory = directory.resolve(strict=True)
    spec = SPECS.get(directory.name)
    if spec is None:
        raise ValueError("RID is not an assigned D03 phase-2 consumer")
    if any((directory / name).exists() for name in CONTROL) or (directory / "initial_metadata.json").exists():
        raise ValueError("formal controls or initial metadata already exist")
    assert_owned(directory)
    if review_path.parent.resolve() != directory or review_path.is_symlink():
        raise ValueError("review must be a non-symlink local round artifact")
    review = read_json(require(review_path))
    if review.get("rid") != directory.name or review.get("batch") != batch or review.get("verdict") != "PASS":
        raise ValueError("exact independent PASS review required")
    manifest_sha, declared = verify_manifest(directory)
    admission, admission_path = validate_admission(directory, spec, batch)
    status, status_path = validate_status(directory, spec, batch)
    actual_wrapper = validate_wrapper(directory, admission, status, batch)
    measurement, arms, results, nonfinite, source_files = validate_measurement(directory, spec)
    arm_files = [directory / arm / filename for arm in arms for filename in ARM_FILES]
    manifest_covers(directory, declared, [admission_path, status_path, actual_wrapper, *source_files, *arm_files])
    wrapper = directory / "batch.sh"
    if wrapper != actual_wrapper:
        raise AssertionError("producer batch.sh must be used directly")
    created = []
    document = {
        "schema": "ft_round/v2", "round_id": directory.name, "epoch": 2, "card": spec["card"],
        "title": spec["title"], "created_at": (now or datetime.now(timezone(timedelta(hours=8)))).strftime("%Y-%m-%d %H:%M:%S CST"),
        "parent": "E2-R000", "base": {"repo": "fork/FreeToken", "commit": PARENT,
                 "code_version": "E2-base@23f2e2c", "worktree": "/data2/FreeToken/wt/e2base"},
        "experimental": {"candidate_commit": CANDIDATE, "worktree": "/data2/FreeToken/wt/e1r003st"},
        "design": {"batch": batch, "phase": spec["kind"]}, "serve": {"arms": arms},
        "results": {"numeric": results}, "first_shots": [],
        "diagnostics": {"run_manifest_sha256": manifest_sha, "admission_sha256": sha(admission_path),
                        "status_sha256": sha(status_path), "review_sha256": sha(review_path),
                        "source_files": [path.relative_to(directory).as_posix() for path in source_files],
                        "raw_measurement_path": "round_metadata.json", "raw_measurement_sha256": sha(directory / "round_metadata.json"),
                        "nonfinite_statistics": nonfinite},
        "sub_conclusions": [{"id": "SC1", "text": "Measurement retained for independent scientific review", "status": "pending",
                              "evidence": ["round_metadata.json", review_path.name]}], "anomalies": [],
        "proposed_verdict": None, "verdict": "pending_review", "verdict_history": [], "retractions": [],
        "histories": [], "independent_review_sha256": sha(review_path),
    }
    encoded = json_bytes(document)
    try:
        output = directory / "initial_metadata.json"
        with output.open("xb") as stream:
            # All validation and serialization precede the exclusive write.
            created.append(output)
            stream.write(encoded)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return {"rid": directory.name, "initial_metadata_sha256": sha(directory / "initial_metadata.json"),
            "review_sha256": sha(review_path), "run_manifest_sha256": manifest_sha}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--round-dir", type=Path)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    if not args.prepare or args.round_dir is None or args.batch is None or args.review is None:
        parser.error("--prepare --round-dir --batch and --review are required")
    if os.name != "posix":
        parser.error("--prepare requires Linux")
    print(json.dumps(prepare(args.round_dir, args.batch, args.review), sort_keys=True))


if __name__ == "__main__":
    main()
