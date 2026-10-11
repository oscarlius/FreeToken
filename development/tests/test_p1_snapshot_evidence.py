import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "p1_snapshot_evidence.py"
SPEC = importlib.util.spec_from_file_location("p1_snapshot_evidence", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

COMMIT = "a" * 40


def write(root: Path, name: str, payload: bytes | dict) -> dict:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(payload, sort_keys=True).encode() if isinstance(payload, dict) else payload)
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def chain(root: Path, index: int) -> dict:
    source = {field: write(root, f"p{index}/{field}", f"{field}-{index}".encode()) for field in MODULE._SOURCE_FIELDS}
    decode = {"uid": f"donor-{index}", "slot": index, "device_tokens": 8192, "successful_snapshot_count": 1}
    donation = {"uid": f"donor-{index}", "slot": index, "device_tokens": 8192}
    restore = {"uid": f"consumer-{index}", "slot": index + 10, "device_tokens": 8192, "source_slot": index}
    admission = {"uid": f"consumer-{index}", "cached_tokens": 8192, "prompt_tokens": 8257}
    consumer = {"uid": f"consumer-{index}", "finished": True, "completion_tokens": 128}
    raw = {"process_id": f"p{index}", "commit": COMMIT,
           "source_bindings": {field: source[field]["sha256"] for field in MODULE._SOURCE_FIELDS},
           "decode_snapshot": decode, "donation": donation, "restore": restore,
           "admission": admission, "consumer": consumer}
    return {"process_id": f"p{index}", "commit": COMMIT, "record": write(root, f"p{index}/record.json", raw),
            "source_bindings": source, "decode_snapshot": decode, "donation": donation,
            "restore": restore, "admission": admission, "consumer": consumer}


def packet(root: Path) -> dict:
    accepted = write(root, "base/accepted.json", {"commit": COMMIT, "code_version": "E2-base.1@aaaaaaa", "verdict": "accepted"})
    t16 = write(root, "base/t16.json", {"commit": COMMIT, "verdict": "kept"})
    return {"schema": MODULE.SCHEMA,
            "base": {"commit": COMMIT, "code_version": "E2-base.1@aaaaaaa", "accepted_receipt": accepted},
            "t16_default_gate": {"verdict": "kept", "receipt": t16},
            "tokenized_input": {"input_ids": write(root, "input/ids.bin", b"ids"),
                                "trace_source": write(root, "input/trace.json", b"trace"),
                                "tokenizer_source": write(root, "input/tokenizer.py", b"tokenizer"),
                                "input_tokens": 8257},
            "processes": [chain(root, index) for index in range(3)]}


def test_retained_packet_passes(tmp_path):
    result = MODULE.verify(packet(tmp_path), tmp_path)
    assert result["commit"] == COMMIT
    assert [item["process_id"] for item in result["processes"]] == ["p0", "p1", "p2"]


@pytest.mark.parametrize("mutate, message", [
    (lambda p, root: (root / "input/ids.bin").unlink(), "missing"),
    (lambda p, root: (root / "input/ids.bin").write_bytes(b"tampered"), "does not match"),
    (lambda p, root: p["processes"][0]["record"].update(path="../outside.json"), "escapes"),
    (lambda p, root: p["processes"][0].update(donation={"uid": "wrong", "slot": 0, "device_tokens": 8192}), "differs from retained"),
])
def test_missing_tampered_escape_and_declared_relation_fail_closed(tmp_path, mutate, message):
    value = packet(tmp_path)
    mutate(value, tmp_path)
    with pytest.raises(ValueError, match=message):
        MODULE.verify(value, tmp_path)


def test_symlink_is_rejected(tmp_path):
    value = packet(tmp_path)
    link = tmp_path / "input/link.bin"
    try:
        link.symlink_to(tmp_path / "input/ids.bin")
    except OSError:
        pytest.skip("symlinks unavailable")
    value["tokenized_input"]["input_ids"] = {"path": "input/link.bin", "sha256": hashlib.sha256((tmp_path / "input/ids.bin").read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="symlink"):
        MODULE.verify(value, tmp_path)


def test_receipt_and_raw_source_mismatch_fail_closed(tmp_path):
    value = packet(tmp_path)
    accepted_path = tmp_path / value["base"]["accepted_receipt"]["path"]
    accepted_path.write_text(json.dumps({"commit": COMMIT, "code_version": "E2-base.1@aaaaaaa", "verdict": "rejected"}))
    value["base"]["accepted_receipt"]["sha256"] = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="accepted receipt verdict"):
        MODULE.verify(value, tmp_path)
    value = packet(tmp_path)
    record = tmp_path / value["processes"][0]["record"]["path"]
    raw = json.loads(record.read_text())
    raw["source_bindings"]["runner_sha256"] = "f" * 64
    record.write_text(json.dumps(raw, sort_keys=True))
    value["processes"][0]["record"]["sha256"] = hashlib.sha256(record.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="raw runner_sha256"):
        MODULE.verify(value, tmp_path)


def test_raw_uid_slot_relation_violation_fails(tmp_path):
    value = packet(tmp_path)
    record = tmp_path / value["processes"][1]["record"]["path"]
    raw = json.loads(record.read_text())
    raw["restore"]["source_slot"] = 99
    record.write_text(json.dumps(raw, sort_keys=True))
    value["processes"][1]["record"]["sha256"] = hashlib.sha256(record.read_bytes()).hexdigest()
    value["processes"][1]["restore"]["source_slot"] = 99
    with pytest.raises(ValueError, match="restore does not bind"):
        MODULE.verify(value, tmp_path)
