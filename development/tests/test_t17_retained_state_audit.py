import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE = Path(__file__).parents[1] / "t17_retained_state_audit.py"
spec = importlib.util.spec_from_file_location("t17_retained_state_audit", MODULE)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class Reader:
    def __init__(self):
        self.calls = []

    def read_retained(self, left, right, **kwargs):
        self.calls.append((left, right, kwargs))
        return {"admitted": False, "verdict": "recorded", "roles": {}}


def make_arm(root, label):
    root.mkdir(parents=True)
    dump = root / "dump"; dump.mkdir()
    files = {}
    for role in audit.ROLES:
        name = role.replace(":", "_") + ".pt"
        (dump / name).write_bytes((role + label).encode())
        files[role] = name
    ids = list(range(1, 18))
    row = {"kind": "donate", "seq": 1, "uid": "0", "length": len(ids) - 1, "files": files}
    (dump / "index.jsonl").write_text(json.dumps(row) + "\n")
    event = {"kind": "input", "uid": "0", "input_ids": ids, "input_length": len(ids),
             "ids_int32le_sha256": audit.token_sha(ids)}
    (root / "observations.jsonl").write_text(json.dumps(event) + "\n")
    inputs = root / "inputs"; inputs.mkdir()
    (inputs / "0.json").write_text(json.dumps({"uid": 0, "numel": len(ids), "int32le_sha256": audit.token_sha(ids)}))
    (root / "d0_decode.json").write_text("{}")
    (root / "d0_prefill.jsonl").write_text("{}\n")
    if label == "warm":
        (root / "donor.response.bin").write_bytes(b"donor"); (root / "hit.response.bin").write_bytes(b"hit")
    else:
        (root / "query.response.bin").write_bytes(b"query")
    return ids


def fixture(tmp_path, *, receipt_case="prefix-8192-tail-65"):
    base = tmp_path / "prefix_8192_tail_65"
    ids = {label: make_arm(base.with_name(base.name + "_" + label), label) for label in audit.ARM_NAMES}
    refs = []
    for number, label in enumerate(("reference_1", "reference_2"), 1):
        arm = base.with_name(base.name + "_" + label)
        refs.append({"input_ids_sha256": audit.token_sha(ids[label]), "process_identity": {"pid": number,
                     "start_ticks": number + 10, "execution_id": label}, "d0_sha256": audit.sha((arm / "d0_prefill.jsonl").read_bytes()),
                     "actual_segments": [{"start": 0, "end": len(ids[label])}]})
    receipt = tmp_path / "case.json"
    receipt.write_text(json.dumps({"case": receipt_case, "result": {"verdict": "measurements_pass_pending_independent_review"},
                                   "evidence": {"references": refs}, "ordinary_cold_envelope": {"recorded": True}}))
    return base, receipt


@pytest.mark.parametrize("receipt_case", ["prefix-8192-tail-65", "prefix_8192_tail_65"])
def test_canonical_case_mapping_accepts_case_and_arm_spellings(tmp_path, receipt_case):
    base, receipt = fixture(tmp_path, receipt_case=receipt_case)
    assert audit.saved_case_receipt(receipt, base)[1][0]["process_identity"]["pid"] == 1


def test_audit_uses_actual_case_reference_schema_and_only_compares_references(tmp_path):
    base, receipt = fixture(tmp_path)
    reader = Reader()
    result = audit.audit(base, tmp_path / "out", reader, case_receipt=receipt)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    assert len(reader.calls) == 1 and result["reference_repeat_envelope"]["verdict"] == "recorded"
    assert set(reader.calls[0][2]["left_selection"]) == {"kind", "seq", "uid"}
    assert result["unbound_arms"]["warm"]["verdict"] == "indeterminate"
    source = result["reference_sources"]["reference_1"]
    assert source["selected_index_line"]["seq"] == 1
    assert source["input"]["input_ids_sha256"] == audit.token_sha(list(range(1, 18)))
    assert json.loads((tmp_path / "out" / "reference_1.json").read_text())["snapshot_length"] == 16


@pytest.mark.parametrize("change", ["missing_process", "wrong_uid", "wrong_request_hash"])
def test_audit_fails_closed_when_case_or_row_binding_is_invalid(tmp_path, change):
    base, receipt = fixture(tmp_path)
    document = json.loads(receipt.read_text())
    if change == "missing_process":
        document["evidence"]["references"][0].pop("process_identity")
        receipt.write_text(json.dumps(document))
        expected = "physical process"
    elif change == "wrong_request_hash":
        document["evidence"]["references"][0]["input_ids_sha256"] = "a" * 64
        receipt.write_text(json.dumps(document))
        expected = "input IDs/UID"
    else:
        path = base.with_name(base.name + "_reference_1") / "dump" / "index.jsonl"
        row = json.loads(path.read_text()); row["uid"] = "7"; path.write_text(json.dumps(row) + "\n")
        expected = "selection"
    with pytest.raises(audit.AuditError, match=expected):
        audit.audit(base, tmp_path / "out", Reader(), case_receipt=receipt)
