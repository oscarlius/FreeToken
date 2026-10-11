import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import round_close as closer
import round_json_append as writer


def initialize(root, arm_name="A"):
    root.mkdir()
    arm = root / arm_name
    arm.mkdir()
    for name in closer.REQUIRED:
        (arm / name).write_text("actual evidence", encoding="utf-8")
    (root / "batch.sh").write_text("true", encoding="utf-8")
    document = {"schema": "ft_round/v2", "round_id": root.name, "serve": {"arms": {arm_name: {}}},
                "verdict": "pending_review", "verdict_history": [], "retractions": [],
                "results": {"ttft_s": 1.0},
                "sub_conclusions": [{"id": "SC1", "text": "claim", "status": "pending"}]}
    (root / "round.json").write_bytes(writer.json_bytes(document))
    return document


class CloseTests(unittest.TestCase):
    def test_declared_hyphen_arm_seals_without_renaming_raw_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            arm = "start-short-child-8192_warm"
            initialize(root, arm)
            before = {name: (root / arm / name).read_bytes() for name in closer.REQUIRED}
            closer.close(root)
            self.assertEqual(set(json.loads((root / "round.json").read_bytes())["serve"]["arms"]), {arm})
            for name, data in before.items():
                self.assertEqual((root / arm / name).read_bytes(), data)
            self.assertIn(("./" + arm + "/serve.log").encode(), (root / "MANIFEST.sha256").read_bytes())

    def test_arm_path_separators_are_rejected_before_sealing(self):
        for arm in ("../A", "/A", "A/B", "A\\B", "A."):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "E2-R999"
                doc = initialize(root)
                doc["serve"]["arms"] = {arm: {}}
                before = writer.json_bytes(doc)
                (root / "round.json").write_bytes(before)
                with self.assertRaisesRegex(writer.RoundError, "invalid arm declaration"):
                    closer.close(root)
                self.assertEqual((root / "round.json").read_bytes(), before)
                self.assertFalse((root / "MANIFEST.sha256").exists())

    def test_failed_startup_can_archive_missing_args_without_fabrication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            doc = initialize(root)
            (root / "A/serve_args.txt").unlink()
            status = root / "status_batch1.json"
            status.write_text(json.dumps({"rid": root.name, "state": "error", "error": "CUDA hidden"}))
            doc["proposed_verdict"] = "failed_harness"
            doc["failure_archive"] = {"missing_serve_args": [{"arm": "A", "reason": "startup failed before dump",
                "evidence": [{"path": name, "sha256": hashlib.sha256((root/name).read_bytes()).hexdigest()}
                    for name in ("A/SERVE_CMD.txt", "A/serve.log", status.name)]}]}
            (root / "round.json").write_bytes(writer.json_bytes(doc))
            closer.close(root)
            self.assertFalse((root / "A/serve_args.txt").exists())
            _, old, _ = writer.validate_history(root / "round.json", root / "round_history")
            writer.commit(root, writer.run_verdict(old, SimpleNamespace(new="failed_harness", reason="startup failed",
                evidence=[status.name], by="root")))
            self.assertEqual(json.loads((root / "round.json").read_bytes())["verdict"], "failed_harness")

    def test_missing_args_exception_rejects_normal_round_or_wrong_evidence_before_write(self):
        for bad in ("normal", "hash", "success", "traversal"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "E2-R999"
                doc = initialize(root)
                (root / "A/serve_args.txt").unlink()
                status = root / "status_batch1.json"
                status.write_text(json.dumps({"rid": root.name, "state": "complete" if bad == "success" else "error", "error": "failed"}))
                evidence = [{"path": name, "sha256": hashlib.sha256((root/name).read_bytes()).hexdigest()}
                    for name in ("A/SERVE_CMD.txt", "A/serve.log", status.name)]
                if bad == "hash":
                    evidence[0]["sha256"] = "0" * 64
                if bad == "traversal":
                    evidence[0]["path"] = "../other/serve.log"
                doc["proposed_verdict"] = "measured" if bad == "normal" else "failed_harness"
                doc["failure_archive"] = {"missing_serve_args": [{"arm":"A", "reason":"failed before dump", "evidence":evidence}]}
                before = writer.json_bytes(doc)
                (root / "round.json").write_bytes(before)
                with self.assertRaises(writer.RoundError):
                    closer.close(root)
                self.assertEqual((root / "round.json").read_bytes(), before)
                self.assertFalse((root / "round_history").exists())
                self.assertFalse((root / "MANIFEST.sha256").exists())

    def test_close_verdict_retract_check_preserves_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            initialize(root)
            sha = closer.close(root)
            manifest = (root / "MANIFEST.sha256").read_bytes()
            self.assertEqual(sha, hashlib.sha256(manifest).hexdigest())
            self.assertNotIn(b"round.json", manifest)
            self.assertNotIn(b"round_history", manifest)
            round_path, history = root / "round.json", root / "round_history"
            _, old, _ = writer.validate_history(round_path, history)
            writer.commit(root, writer.run_verdict(old, SimpleNamespace(
                new="measured", reason="verified", evidence=["A/serve.log"], by="root")))
            _, old, _ = writer.validate_history(round_path, history)
            writer.commit(root, writer.run_retract(old, SimpleNamespace(
                target="SC1", reason="revised", evidence=["A/ENV.txt"], by="root")))
            _, old, versions = writer.validate_history(round_path, history)
            self.assertEqual(len(versions), 3)
            self.assertEqual(old["sub_conclusions"][0]["status"], "retracted")
            self.assertEqual((root / "MANIFEST.sha256").read_bytes(), manifest)
            if sys.platform != "win32":
                self.assertTrue(all(not path.stat().st_mode & 0o222 for path in [root, *root.rglob("*")]))
            with self.assertRaisesRegex(writer.RoundError, "already exists"):
                closer.close(root)

    def test_missing_arm_file_refuses_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            initialize(root)
            before = (root / "round.json").read_bytes()
            (root / "A" / "ENV.txt").unlink()
            with self.assertRaisesRegex(writer.RoundError, "ENV.txt"):
                closer.close(root)
            self.assertEqual((root / "round.json").read_bytes(), before)
            self.assertFalse((root / "round_history").exists())
            self.assertFalse((root / "MANIFEST.sha256").exists())

    def test_chmod_failure_restores_all_bytes_and_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            initialize(root)
            before = {path: (path.read_bytes() if path.is_file() else None,
                             stat.S_IMODE(path.stat().st_mode)) for path in [root, *root.rglob("*")]}
            original = closer.os.chmod
            calls = 0

            def fail_once(path, mode):
                nonlocal calls
                calls += 1
                if calls == 5:
                    raise OSError("injected readonly failure")
                original(path, mode)

            with patch.object(closer.os, "chmod", side_effect=fail_once):
                with self.assertRaises(OSError):
                    closer.close(root)
            self.assertEqual(set(before), {root, *root.rglob("*")})
            for path, (data, mode) in before.items():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
                if data is not None:
                    self.assertEqual(path.read_bytes(), data)

    def test_initial_histories_require_empty_lists(self):
        for key in ("verdict_history", "retractions"):
            for value in ({}, "", 0, False):
                with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary) / "E2-R999"
                    doc = initialize(root)
                    doc[key] = value
                    (root / "round.json").write_bytes(writer.json_bytes(doc))
                    before = (root / "round.json").read_bytes()
                    with self.assertRaisesRegex(writer.RoundError, key):
                        closer.close(root)
                    self.assertEqual((root / "round.json").read_bytes(), before)
                    self.assertFalse((root / "MANIFEST.sha256").exists())

    def test_symlink_ancestor_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            real = parent / "real"
            real.mkdir()
            root = real / "E2-R999"
            initialize(root)
            link = parent / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(writer.RoundError, "symlink"):
                closer.close(link / "E2-R999")
            self.assertFalse((root / "MANIFEST.sha256").exists())


if __name__ == "__main__":
    unittest.main()
