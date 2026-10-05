import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys

import pytest


torch = pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
reader = importlib.import_module("equiv_suite.retained_state")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_arm(root, *, seq, uid, offset=0.0):
    root.mkdir()
    tensors = {
        "conv_states": torch.tensor([[[1.0 + offset]]], dtype=torch.float32),
        "recurrent_states": torch.tensor([[[2.0]]], dtype=torch.float32),
        "slot:ple_conv": torch.tensor([[[3.0]]], dtype=torch.float32),
        "slot:ple_ngram_ctx": torch.tensor([[[7]]], dtype=torch.int32),
    }
    files = {}
    for role, tensor in tensors.items():
        name = role.replace(":", "_") + ".pt"
        torch.save(tensor, root / name)
        files[role] = name
    row = {"kind": "donate", "seq": seq, "uid": uid, "length": 8256,
           "conv_states_sha16hex": "legacy", "recurrent_states_sha16hex": "legacy", "slot_sha16hex": "legacy"}
    line = json.dumps(row, separators=(",", ":")).encode() + b"\n"
    (root / "index.jsonl").write_bytes(line)
    return line, files


def bind(path, root, line, files, *, seq, uid, process):
    index = (root / "index.jsonl").read_bytes()
    document = {"schema": reader.SIDECAR_SCHEMA, "index_sha256": hashlib.sha256(index).hexdigest(),
                "capture_receipt_sha256": hashlib.sha256(line).hexdigest(), "kind": "donate", "seq": seq, "uid": uid,
                "process_identity": process, "event_identity": process["execution_id"] + ":donate",
                "input_ids": [11, 12, 13, 14], "input_ids_sha256": reader._token_sha([11, 12, 13, 14]),
                "snapshot_length": 3, "snapshot_prefix_ids": [11, 12, 13],
                "snapshot_prefix_ids_sha256": reader._token_sha([11, 12, 13]),
                "role_files": {role: {"path": name, "sha256": digest(root / name)} for role, name in files.items()}}
    path.write_text(json.dumps(document, separators=(",", ":")))
    return digest(path)


def args(left, right, left_line, right_line, left_files, right_files):
    left_sidecar, right_sidecar = left.parent / "left.json", right.parent / "right.json"
    left_sha = bind(left_sidecar, left, left_line, left_files, seq=7, uid="warm",
                    process={"pid": 1, "start_ticks": 2, "execution_id": "warm-run"})
    right_sha = bind(right_sidecar, right, right_line, right_files, seq=8, uid="cold",
                     process={"pid": 3, "start_ticks": 4, "execution_id": "cold-run"})
    return {"left_selection": {"kind": "donate", "seq": 7, "uid": "warm"},
            "right_selection": {"kind": "donate", "seq": 8, "uid": "cold"},
            "left_sidecar": left_sidecar, "left_sidecar_sha256": left_sha,
            "right_sidecar": right_sidecar, "right_sidecar_sha256": right_sha}


def test_retained_state_reads_old_index_with_pinned_sidecars(tmp_path):
    left, right = tmp_path / "warm", tmp_path / "cold"
    left_line, left_files = make_arm(left, seq=7, uid="warm", offset=0.0)
    right_line, right_files = make_arm(right, seq=8, uid="cold", offset=0.25)
    result = reader.read_retained_state(left, right, **args(left, right, left_line, right_line, left_files, right_files))
    assert result["verdict"] == "recorded" and result["admitted"] is False
    assert result["first_role_difference"] == "conv_states"
    assert result["roles"]["conv_states"]["max_abs"] == pytest.approx(0.25)
    assert result["roles"]["slot:ple_ngram_ctx"] == {"dtype": "torch.int32", "shape": [1, 1, 1], "exact_equal": True, "bitwise_equal": True}
    assert base64.b64decode(result["sources"]["left"]["capture_receipt"]["bytes_base64"]) == left_line
    assert json.loads(json.dumps(result))["sources"]["right"]["sidecar"]["role_files"]["conv_states"]["sha256"] == digest(right / right_files["conv_states"])


@pytest.mark.parametrize("change", ["missing_binding", "tampered_file", "wrong_prefix", "same_process", "same_event", "missing_role", "shape", "nonfinite"])
def test_retained_state_fails_closed_for_invalid_proof(tmp_path, change):
    left, right = tmp_path / "warm", tmp_path / "cold"
    left_line, left_files = make_arm(left, seq=7, uid="warm")
    right_line, right_files = make_arm(right, seq=8, uid="cold")
    value = args(left, right, left_line, right_line, left_files, right_files)
    if change == "missing_binding":
        value["left_sidecar"].unlink()
    elif change == "tampered_file":
        torch.save(torch.tensor([[[99.0]]]), left / left_files["conv_states"])
    elif change == "wrong_prefix":
        sidecar = json.loads(value["left_sidecar"].read_text())
        sidecar["snapshot_prefix_ids"] = [11, 12, 99]
        value["left_sidecar"].write_text(json.dumps(sidecar))
        value["left_sidecar_sha256"] = digest(value["left_sidecar"])
    elif change == "same_event":
        sidecar = json.loads(value["right_sidecar"].read_text())
        sidecar["event_identity"] = json.loads(value["left_sidecar"].read_text())["event_identity"]
        value["right_sidecar"].write_text(json.dumps(sidecar))
        value["right_sidecar_sha256"] = digest(value["right_sidecar"])
    elif change == "same_process":
        sidecar = json.loads(value["right_sidecar"].read_text())
        sidecar["process_identity"] = {"pid": 1, "start_ticks": 2, "execution_id": "cold-run"}
        value["right_sidecar"].write_text(json.dumps(sidecar))
        value["right_sidecar_sha256"] = digest(value["right_sidecar"])
    elif change == "missing_role":
        sidecar = json.loads(value["right_sidecar"].read_text())
        sidecar["role_files"].pop("slot:ple_ngram_ctx")
        value["right_sidecar"].write_text(json.dumps(sidecar))
        value["right_sidecar_sha256"] = digest(value["right_sidecar"])
    elif change == "shape":
        torch.save(torch.ones((2, 1, 1), dtype=torch.float32), right / right_files["conv_states"])
        sidecar = json.loads(value["right_sidecar"].read_text())
        sidecar["role_files"]["conv_states"]["sha256"] = digest(right / right_files["conv_states"])
        value["right_sidecar"].write_text(json.dumps(sidecar))
        value["right_sidecar_sha256"] = digest(value["right_sidecar"])
    else:
        torch.save(torch.tensor([[[float("nan")]]]), right / right_files["conv_states"])
        sidecar = json.loads(value["right_sidecar"].read_text())
        sidecar["role_files"]["conv_states"]["sha256"] = digest(right / right_files["conv_states"])
        value["right_sidecar"].write_text(json.dumps(sidecar))
        value["right_sidecar_sha256"] = digest(value["right_sidecar"])
    result = reader.read_retained_state(left, right, **value)
    assert result["verdict"] == "indeterminate" and result["admitted"] is False


def test_retained_state_rejects_wrong_uid_selection_and_symlinked_role(tmp_path):
    left, right = tmp_path / "warm", tmp_path / "cold"
    left_line, left_files = make_arm(left, seq=7, uid="warm")
    right_line, right_files = make_arm(right, seq=8, uid="cold")
    value = args(left, right, left_line, right_line, left_files, right_files)
    value["left_selection"] = {"kind": "donate", "seq": 7, "uid": "wrong"}
    assert reader.read_retained_state(left, right, **value)["verdict"] == "indeterminate"
    value = args(left, right, left_line, right_line, left_files, right_files)
    outside = tmp_path / "outside.pt"
    outside.write_bytes((left / left_files["conv_states"]).read_bytes())
    try:
        (left / left_files["conv_states"]).unlink()
        (left / left_files["conv_states"]).symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert reader.read_retained_state(left, right, **value)["verdict"] == "indeterminate"
