import importlib.util
import json
import os
import stat
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).parents[1] / "round_json_append.py"
spec = importlib.util.spec_from_file_location("round_json_append", MODULE)
writer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = writer
spec.loader.exec_module(writer)


def document():
    return {
        "schema": "ft_round/v2", "round_id": "E2-R999", "results": {"ttft_s": 1.0},
        "first_shots": [1], "verdict": "pending_review", "verdict_history": [], "retractions": [],
        "sub_conclusions": [{"id": "SC1", "text": "claim", "status": "pending"}],
    }


def initialize(root: Path, raw: bytes | None = None):
    root.mkdir()
    round_json = root / "round.json"
    raw = writer.json_bytes(document()) if raw is None else raw
    round_json.write_bytes(raw)
    history = root / "round_history"; history.mkdir()
    first = history / "round.v001.json"; first.write_bytes(raw)
    (history / "SHA256SUMS").write_bytes(writer.sums_bytes([first]))
    return round_json, history


class RoundAppendTests(unittest.TestCase):
    def test_verdict_retract_check_and_hash_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"; original, history = initialize(root)
            old_manifest = b"kept outside history"; (root / "MANIFEST.sha256").write_bytes(old_manifest)
            args = type("Args", (), {"new": "kept", "reason": "reviewed", "evidence": ["gate.json"], "by": "root"})()
            writer.commit(root, writer.run_verdict(document(), args))
            current_raw, current, snapshots = writer.validate_history(original, history)
            self.assertEqual(current["verdict"], "kept")
            self.assertEqual(len(snapshots), 2)
            self.assertEqual((root / "MANIFEST.sha256").read_bytes(), old_manifest)
            retract = type("Args", (), {"target": "SC1", "reason": "superseded", "evidence": ["new.json"], "by": "root"})()
            writer.commit(root, writer.run_retract(current, retract))
            _, current, snapshots = writer.validate_history(original, history)
            self.assertEqual(current["sub_conclusions"][0]["status"], "retracted")
            self.assertEqual(len(snapshots), 3)

    def test_failed_harness_verdict_append_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"; round_json, history = initialize(root)
            manifest = b"preexisting measurement manifest\n"; (root / "MANIFEST.sha256").write_bytes(manifest)
            before_round = round_json.read_bytes()
            before_snapshot = (history / "round.v001.json").read_bytes()
            args = type("Args", (), {"new": "failed_harness", "reason": "launch prerequisite failed",
                                    "evidence": ["failure_result.json"], "by": "root"})()
            writer.commit(root, writer.run_verdict(document(), args))
            _, current, snapshots = writer.validate_history(round_json, history)
            self.assertEqual(current["verdict"], "failed_harness")
            self.assertEqual(current["results"], document()["results"])
            self.assertEqual((history / "round.v001.json").read_bytes(), before_snapshot)
            self.assertEqual(before_round, before_snapshot)
            self.assertEqual((root / "MANIFEST.sha256").read_bytes(), manifest)
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(current["verdict_history"][-1]["old"], "pending_review")
            self.assertEqual(current["verdict_history"][-1]["new"], "failed_harness")

    def test_unknown_verdict_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"; round_json, history = initialize(root)
            before = (round_json.read_bytes(), (history / "SHA256SUMS").read_bytes())
            args = type("Args", (), {"new": "not_a_verdict", "reason": "bad",
                                    "evidence": ["failure_result.json"], "by": "root"})()
            with self.assertRaisesRegex(writer.RoundError, "not an allowed verdict"):
                writer.commit(root, writer.run_verdict(document(), args))
            self.assertEqual(before, (round_json.read_bytes(), (history / "SHA256SUMS").read_bytes()))
            self.assertFalse((history / "round.v002.json").exists())

    def test_add_is_documented_append_only_candidate_patch(self):
        old = document()
        new = writer.merge_add(old, {"new_evidence": ["x"], "first_shots": [2]})
        writer.validate_change(old, new)
        self.assertEqual(new["first_shots"], [1, 2])
        with self.assertRaisesRegex(writer.RoundError, "scalar cannot be overwritten"):
            writer.merge_add(old, {"verdict": "kept"})
        with self.assertRaisesRegex(writer.RoundError, "existing value"):
            broken = document(); broken["results"]["ttft_s"] = True; writer.validate_change(old, broken)

    def test_deletion_middle_list_and_unbound_verdict_are_rejected(self):
        old = document()
        deleted = document(); del deleted["results"]["ttft_s"]
        with self.assertRaisesRegex(writer.RoundError, "results.ttft_s"):
            writer.validate_change(old, deleted)
        middle = document(); middle["first_shots"] = [2]
        with self.assertRaisesRegex(writer.RoundError, "first_shots"):
            writer.validate_change(old, middle)
        verdict = document(); verdict["verdict"] = "kept"
        with self.assertRaisesRegex(writer.RoundError, "verdict"):
            writer.validate_change(old, verdict)

    def test_history_drift_and_legacy_v000_byte_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "legacy"; root.mkdir()
            raw = b'{\n  "verdict": "pending_review", "verdict_history": [], "retractions": [], "sub_conclusions": []\n}\n'
            (root / "round.json").write_bytes(raw)
            old = json.loads(raw)
            args = type("Args", (), {"new": "kept", "reason": "reviewed", "evidence": ["x"], "by": "root"})()
            writer.commit(root, writer.run_verdict(old, args))
            history = root / "round_history"
            self.assertEqual((history / "round.v000.json").read_bytes(), raw)
            self.assertNotIn(b"legacy_snapshot", (history / "round.v000.json").read_bytes())
            self.assertTrue((history / "legacy_snapshot.json").is_file())
            sums = history / "SHA256SUMS"
            sums.chmod(sums.stat().st_mode | 0o200)
            history.chmod(history.stat().st_mode | 0o200)
            sums.write_bytes(b"bad\n")
            with self.assertRaisesRegex(writer.RoundError, "SHA256SUMS"):
                writer.validate_history(root / "round.json", history)

    def test_commit_rolls_back_after_readonly_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"; round_json, history = initialize(root)
            before_round, before_sums = round_json.read_bytes(), (history / "SHA256SUMS").read_bytes()
            args = type("Args", (), {"new": "kept", "reason": "reviewed", "evidence": ["x"], "by": "root"})()
            with patch.object(writer, "make_readonly", side_effect=OSError("chmod failed")):
                with self.assertRaises(OSError):
                    writer.commit(root, writer.run_verdict(document(), args))
            self.assertEqual(round_json.read_bytes(), before_round)
            self.assertEqual((history / "SHA256SUMS").read_bytes(), before_sums)
            self.assertFalse((history / "round.v002.json").exists())

    def test_validation_failure_never_mutates_round_or_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"; round_json, history = initialize(root)
            before = (round_json.read_bytes(), (history / "SHA256SUMS").read_bytes(),
                      (history / "round.v001.json").read_bytes())
            invalid = document(); invalid["results"]["ttft_s"] = 2.0
            with self.assertRaisesRegex(writer.RoundError, "results.ttft_s"):
                writer.commit(root, invalid)
            self.assertEqual(before, (round_json.read_bytes(), (history / "SHA256SUMS").read_bytes(),
                                      (history / "round.v001.json").read_bytes()))

    def test_invalid_json_cli_returns_nonzero_first_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bad"; root.mkdir()
            (root / "round.json").write_text("{not json", encoding="utf-8")
            result = subprocess.run([sys.executable, str(MODULE), str(root), "check"], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stderr.startswith("ERROR $.round.json:"))
            self.assertEqual((root / "round.json").read_text(encoding="utf-8"), "{not json")

    def test_chmod_failure_restores_all_original_bytes_and_modes(self):
        for failure_call in (1, 2, 5):
            with self.subTest(failure_call=failure_call), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "E2-R999"; round_json, history = initialize(root)
                tracked = [root, round_json, history, history / "SHA256SUMS", history / "round.v001.json"]
                before_modes = {path: stat.S_IMODE(path.stat().st_mode) for path in tracked}
                before_bytes = {path: path.read_bytes() for path in tracked if path.is_file()}
                real_chmod, calls = writer.os.chmod, []
                def fail_selected(path, mode):
                    calls.append((Path(path), mode))
                    if len(calls) == failure_call:
                        raise OSError("injected chmod failure")
                    return real_chmod(path, mode)
                args = type("Args", (), {"new": "kept", "reason": "reviewed", "evidence": ["x"], "by": "root"})()
                with patch.object(writer.os, "chmod", side_effect=fail_selected):
                    with self.assertRaises(OSError):
                        writer.commit(root, writer.run_verdict(document(), args))
                self.assertEqual(before_bytes, {path: path.read_bytes() for path in before_bytes})
                self.assertEqual(before_modes, {path: stat.S_IMODE(path.stat().st_mode) for path in tracked})
                self.assertFalse((history / "round.v002.json").exists())

    def test_legacy_annotation_is_readonly_and_empty_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "legacy"; root.mkdir()
            (root / "round.json").write_bytes(writer.json_bytes(document()))
            args = type("Args", (), {"new": "kept", "reason": "reviewed", "evidence": ["x"], "by": "root"})()
            writer.commit(root, writer.run_verdict(document(), args))
            history = root / "round_history"
            for path in [root, root / "round.json", history, *history.iterdir()]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o222, 0, path)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "bad_history"; root.mkdir()
            (root / "round.json").write_bytes(writer.json_bytes(document()))
            (root / "round_history").mkdir()
            with self.assertRaisesRegex(writer.RoundError, "contains no round"):
                writer.validate_history(root / "round.json", root / "round_history")

    def test_history_prefix_is_type_exact_and_symlink_ancestor_is_rejected(self):
        old = document()
        entry = {"time": "2026-10-04 12:00:00 CST", "old": "pending_review", "new": "kept",
                 "reason": "SC1 reviewed", "evidence": ["x"], "by": "root"}
        old["verdict_history"] = [entry]
        new = json.loads(json.dumps(old)); new["verdict_history"][0]["evidence"] = [True]
        with self.assertRaisesRegex(writer.RoundError, "type-exact"):
            writer.validate_change(old, new)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); actual = base / "actual"; actual.mkdir()
            (actual / "round.json").write_bytes(writer.json_bytes(document()))
            link = base / "link"
            try:
                os.symlink(actual, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable on this platform")
            with self.assertRaisesRegex(writer.RoundError, "ancestor symlink"):
                writer.guarded_round(link)

    def test_ledger_truncation_and_unbound_retraction_reject(self):
        old = document()
        verdict = {"time": "2026-10-04 12:00:00 CST", "old": "pending_review", "new": "kept",
                   "reason": "SC1 reviewed", "evidence": ["x"], "by": "root"}
        retract = {"time": "2026-10-04 12:01:00 CST", "target": "SC1", "reason": "bad",
                   "evidence": ["x"], "by": "root"}
        old["verdict_history"] = [verdict]
        old["retractions"] = [retract]
        shortened_history = json.loads(json.dumps(old)); shortened_history["verdict_history"] = []
        with self.assertRaisesRegex(writer.RoundError, "cannot delete existing history"):
            writer.validate_change(old, shortened_history)
        shortened_retractions = json.loads(json.dumps(old)); shortened_retractions["retractions"] = []
        with self.assertRaisesRegex(writer.RoundError, "cannot delete existing retraction"):
            writer.validate_change(old, shortened_retractions)
        fresh = document(); unbound = json.loads(json.dumps(fresh)); unbound["retractions"].append(retract)
        with self.assertRaisesRegex(writer.RoundError, "each appended retraction"):
            writer.validate_change(fresh, unbound)

    def test_add_forbids_governed_ledgers_but_existing_sub_dict_can_gain_key(self):
        old = document()
        expanded = json.loads(json.dumps(old)); expanded["sub_conclusions"][0]["new_note"] = "append only"
        writer.validate_change(old, expanded)
        with tempfile.TemporaryDirectory() as temporary:
            patch = Path(temporary) / "patch.json"
            patch.write_text(json.dumps({"retractions": []}), encoding="utf-8")
            args = type("Args", (), {"json": str(patch)})()
            with self.assertRaisesRegex(writer.RoundError, "governed field"):
                writer.run_add(old, args)


if __name__ == "__main__":
    unittest.main()
