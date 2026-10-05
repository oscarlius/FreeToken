import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

import pytest


torch = pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
reader = importlib.import_module("equiv_suite.retained_d03")
TOOL = Path(os.environ.get("FT_D16_D03_TOOL", Path(__file__).resolve().parents[3] / "e2d03" / "scripts" / "logits_probe.py"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path, *, index, line, seq, uid, identity, event):
    value = {"schema": reader.SERVICE_SCHEMA, "index_sha256": hashlib.sha256(index).hexdigest(),
             "capture_receipt_sha256": hashlib.sha256(line).hexdigest(), "seq": seq, "uid": uid,
             "process_identity": identity, "event_identity": event}
    path.write_text(json.dumps(value, separators=(",", ":")))
    return digest(path)


def arm(root, *, logits, seq, uid):
    root.mkdir()
    tensors = {
        "logits": torch.tensor([logits], dtype=torch.float32),
        "conv_states": torch.ones((1, 1, 1), dtype=torch.float32),
        "recurrent_states": torch.ones((1, 1, 1), dtype=torch.float32),
        "slot:ple_conv": torch.ones((1, 1, 1), dtype=torch.float32),
        "slot:ple_ngram_ctx": torch.ones((1, 1, 1), dtype=torch.int32),
    }
    files = {}
    for role, value in tensors.items():
        filename = f"{role.replace(':', '_')}.pt"
        torch.save(value, root / filename)
        files[role] = filename
    row = {"kind": "logits", "seq": seq, "uid": uid, "files": files,
           "sha256": {role: digest(root / path) for role, path in files.items()},
           "extra": {"input_prefix_sha256": "a" * 64, "k": 1, "input_length": 5, "positions": [4],
                     "layer_ids": {role: [1] for role in tensors if role != "logits"}}}
    raw = json.dumps(row, separators=(",", ":")).encode() + b"\n"
    (root / "index.jsonl").write_bytes(raw)
    return raw


def args(left, right, left_line, right_line):
    left_sidecar, right_sidecar = left.parent / "left_service.json", right.parent / "right_service.json"
    left_index, right_index = (left / "index.jsonl").read_bytes(), (right / "index.jsonl").read_bytes()
    left_sha = binding(left_sidecar, index=left_index, line=left_line, seq=7, uid="u0",
                       identity={"pid": 1, "start_ticks": 2, "execution_id": "left"}, event="left:event")
    right_sha = binding(right_sidecar, index=right_index, line=right_line, seq=8, uid="u1",
                        identity={"pid": 3, "start_ticks": 4, "execution_id": "right"}, event="right:event")
    return {"left_selection": {"seq": 7, "uid": "u0"}, "right_selection": {"seq": 8, "uid": "u1"},
            "logits_probe": TOOL, "logits_probe_sha256": digest(TOOL), "left_sidecar": left_sidecar,
            "left_sidecar_sha256": left_sha, "right_sidecar": right_sidecar, "right_sidecar_sha256": right_sha}


def test_retained_reader_accepts_old_index_with_sidecars_and_different_uid_seq(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left_line = arm(left, logits=[1.0, 0.0, -1.0], seq=7, uid="u0")
    right_line = arm(right, logits=[0.0, 1.0, -1.0], seq=8, uid="u1")
    result = reader.read_retained(left, right, **args(left, right, left_line, right_line))
    assert result["verdict"] == "recorded" and result["admitted"] is False
    assert result["peer_vs_recompute"]["first_top1_mismatch"] == 0
    assert result["sources"]["recompute"]["capture_receipt"]["uid"] == "u0"
    assert result["sources"]["peer"]["capture_receipt"]["uid"] == "u1"
    assert base64.b64decode(result["sources"]["recompute"]["capture_receipt"]["bytes_base64"]) == left_line
    assert json.loads(json.dumps(result))["sources"]["peer"]["service_binding"]["event_identity"] == "right:event"


def test_retained_reader_rejects_missing_sidecar_and_wrong_index_binding(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left_line = arm(left, logits=[1.0, 0.0, -1.0], seq=7, uid="u0")
    right_line = arm(right, logits=[1.0, 0.0, -1.0], seq=8, uid="u1")
    value = args(left, right, left_line, right_line)
    value["left_sidecar"].unlink()
    assert reader.read_retained(left, right, **value)["verdict"] == "indeterminate"
    value = args(left, right, left_line, right_line)
    sidecar = json.loads(value["left_sidecar"].read_text())
    sidecar["index_sha256"] = "b" * 64
    value["left_sidecar"].write_text(json.dumps(sidecar))
    value["left_sidecar_sha256"] = digest(value["left_sidecar"])
    assert reader.read_retained(left, right, **value)["verdict"] == "indeterminate"


def test_retained_reader_rejects_symlink_ancestor(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left_line = arm(left, logits=[1.0, 0.0, -1.0], seq=7, uid="u0")
    right_line = arm(right, logits=[1.0, 0.0, -1.0], seq=8, uid="u1")
    nested, outside = left / "nested", tmp_path / "outside"
    outside.mkdir()
    (outside / "logits.pt").write_bytes((left / "logits.pt").read_bytes())
    try:
        nested.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    row = json.loads((left / "index.jsonl").read_text())
    row["files"]["logits"] = "nested/logits.pt"
    (left / "index.jsonl").write_text(json.dumps(row) + "\n")
    value = args(left, right, left_line, right_line)
    assert reader.read_retained(left, right, **value)["verdict"] == "indeterminate"
