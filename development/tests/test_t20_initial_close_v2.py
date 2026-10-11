import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("t20close", HERE / "t20_initial_close_v2.py")
t20 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(t20)


class Generic:
    def __init__(self):
        self.live = set()
    def assert_owned_tree(self, directory):
        return None
    def live_or_zombie(self, pid):
        return pid in self.live
    def build_control(self, directory, document):
        return {"round.json": b"{}\n"}
    def publish(self, directory, controls):
        (directory / "round.json").write_bytes(controls["round.json"])


def put(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(tmp_path):
    root = tmp_path / "E2-R040"; root.mkdir()
    put(root / "status_batch71.json", {"rid": t20.RID, "batch": 71, "batch_pid": 771,
        "card": "T20", "state": "complete_measurements_pending_independent_review"})
    put(root / "prerequisite.json", {"round": "E2-R041-gate-D17", "batch": 68,
        "candidate_commit": t20.CANDIDATE, **{k: "a" * 64 for k in ("round_sha256", "manifest_sha256", "closure_sha256")}})
    put(root / "execution_archive.json", {"files": {"t20_measurements.py": "b" * 64,
        "t17_continuation_runner_v2.py": "c" * 64}, "cpu_report_sha256": "d" * 64})
    review = root / "independent_review.json"
    put(review, {"rid": t20.RID, "batch": 71, "candidate_commit": t20.CANDIDATE, "verdict": "PASS"})
    receipt = tmp_path / "launch.json"
    put(receipt, {"schema": "ft_t20_actual_launch/v1", "rid": t20.RID, "batch": 71,
        "candidate_commit": t20.CANDIDATE, "batch_pid": 771, "batch_start_ticks": 9,
        "argv": ["/tmp/t17_continuation_runner_v2.py"]})
    (tmp_path / "batch71.sh").write_text("#!/bin/sh\n")
    (tmp_path / "batch71.log").write_text("PASS\n")
    for arm in t20.ARMS:
        place = root / arm; place.mkdir()
        put(place / "source.json", {"commit": t20.CANDIDATE, "code_version": t20.CODE_VERSION})
        for name in t20.ARM_FILES[1:]:
            (place / name).write_text("ok\n")
    return root, review, receipt, Generic(), tmp_path / "batch71.sh"


def test_terminal_fixture_validates(tmp_path, monkeypatch):
    root, review, receipt, generic, batch_script = fixture(tmp_path)
    monkeypatch.setattr(t20, "sha256", lambda path: "d" * 64)
    assert t20.validate(root, review, receipt, generic, batch_script=batch_script)["verdict"] == "pending_review"


def test_default_cli_is_inert(capsys):
    assert t20.main([]) == 0
    assert json.loads(capsys.readouterr().out)["closed"] is False


def test_live_controller_rejected(tmp_path):
    root, review, receipt, generic, batch_script = fixture(tmp_path); generic.live.add(771)
    with pytest.raises(ValueError, match="controller remains live"):
        t20.validate(root, review, receipt, generic, batch_script=batch_script)


def test_missing_review_rejected(tmp_path):
    root, review, receipt, generic, batch_script = fixture(tmp_path); review.unlink()
    with pytest.raises(FileNotFoundError): t20.validate(root, review, receipt, generic, batch_script=batch_script)


def test_unexpected_admission_identity_drift_rejected(tmp_path):
    root, review, receipt, generic, batch_script = fixture(tmp_path)
    put(root / "admission.json", {"rid": "E2-R999"})
    with pytest.raises(ValueError, match="unexpected admission"):
        t20.validate(root, review, receipt, generic, batch_script=batch_script)


def test_nonterminal_status_rejected(tmp_path):
    root, review, receipt, generic, batch_script = fixture(tmp_path)
    put(root / "status_batch71.json", {"rid": t20.RID, "batch": 71, "batch_pid": 771,
        "card": "T20", "state": "loading"})
    with pytest.raises(ValueError, match="not terminal"):
        t20.validate(root, review, receipt, generic, batch_script=batch_script)


def test_reclose_rejected(tmp_path):
    root, review, receipt, generic, batch_script = fixture(tmp_path); (root / "round.json").write_text("{}")
    with pytest.raises(ValueError, match="initial closure only"):
        t20.validate(root, review, receipt, generic, batch_script=batch_script)


def test_generic_publish_rollback_is_byte_preserving(tmp_path):
    """The immutable generic publisher's injected failure restores open bytes."""
    generic_path = HERE / "initial_measurement_close.py"
    spec = importlib.util.spec_from_file_location("generic_close", generic_path)
    generic = importlib.util.module_from_spec(spec); spec.loader.exec_module(generic)
    directory = tmp_path / "open"; directory.mkdir(); payload = directory / "raw.json"; payload.write_bytes(b"raw")
    controls = {"round.json": b"{}\n", "round_history/round.v001.json": b"{}\n",
                "round_history/SHA256SUMS": b"x\n", "MANIFEST.sha256": b"x\n"}
    with pytest.raises(RuntimeError):
        generic.publish(directory, controls, inject=lambda phase: (_ for _ in ()).throw(RuntimeError("boom")) if phase == "round_published" else None)
    assert payload.read_bytes() == b"raw" and not (directory / "round.json").exists()
