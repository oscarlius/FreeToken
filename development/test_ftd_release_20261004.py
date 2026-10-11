import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "development" / "ftd_release_20261004.py"
WRITER = ROOT / "scripts" / "round_json_append.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("ftd_release", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class ReleasePreparationTests(unittest.TestCase):
    def make_previous_release(self, rounds_root):
        directory = rounds_root.parent / "ft_releases" / load_tool().PREVIOUS_RELEASE
        directory.mkdir(parents=True)
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"release_id": load_tool().PREVIOUS_RELEASE}) + "\n", encoding="utf-8")
        os.chmod(manifest, 0o444)
        os.chmod(directory, 0o555)

    def make_round(self, root, round_id, verdict, evidence, *, hypothesis=False):
        directory = root / round_id
        history = directory / "round_history"
        history.mkdir(parents=True)
        for name in evidence:
            (directory / name).write_text("fixture\n", encoding="utf-8")
        conclusion_id = next(iter(load_tool().HYPOTHESIS_CONCLUSIONS.get(round_id, {"SC1"})))
        doc = {"schema": "ft_round/v2", "round_id": round_id, "verdict": verdict,
               "closed_at": "2026-10-04 00:00:00 CST",
               "verdict_history": [{"time": "2026-10-04 00:00:00 CST", "old": "pending_review", "new": verdict,
                                    "reason": "fixture", "evidence": evidence, "by": "test"}] if verdict != "pending_review" else [],
               "retractions": [], "sub_conclusions": [{"id": key, "status": "hypothesis" if hypothesis else "kept"} for key in (load_tool().HYPOTHESIS_CONCLUSIONS.get(round_id, {conclusion_id}) if hypothesis else {conclusion_id})]}
        data = json.dumps(doc, indent=2) + "\n"
        (directory / "round.json").write_text(data, encoding="utf-8")
        (history / "round.v001.json").write_text(data, encoding="utf-8")
        digest = hashlib.sha256((history / "round.v001.json").read_bytes()).hexdigest()
        (history / "SHA256SUMS").write_bytes(f"{digest}  round.v001.json\n".encode("ascii"))
        rows = [f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  ./{name}" for name in evidence]
        (directory / "MANIFEST.sha256").write_bytes(("\n".join(rows) + "\n").encode("ascii"))
        for item in [directory, history, *directory.rglob("*")]:
            os.chmod(item, 0o555 if item.is_dir() else 0o444)
        return directory

    def test_prepare_uses_writer_allowlist_and_marks_missing_append(self):
        tool = load_tool()
        original = tool.TARGETS
        tool.TARGETS = (("E2-R006", "kept", "reason"), ("E2-R001", "failed_harness", "reason"))
        try:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "rounds"; root.mkdir()
                self.make_previous_release(root)
                self.make_round(root, "E2-R006", "pending_review", ["review.json"], hypothesis=True)
                self.make_round(root, "E2-R001", "failed_harness", ["status_batch28.json"])
                review = tool.build_review(root, WRITER)
            self.assertTrue(review["ready_for_apply"])
            self.assertEqual(review["planned_appends"], ["E2-R006"])
            self.assertTrue(review["rounds"][0]["hypothesis_constraint_satisfied"])
        finally:
            tool.TARGETS = original

    def test_apply_is_explicit_and_keeps_byte_identical_release_copy(self):
        tool = load_tool()
        original = tool.TARGETS
        tool.TARGETS = (("E2-R001", "failed_harness", "reason"),)
        try:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "rounds"; root.mkdir()
                self.make_previous_release(root)
                self.make_round(root, "E2-R001", "pending_review", ["status_batch28.json"])
                review = tool.build_review(root, WRITER)
                result = tool.apply(review, WRITER, by="test", server_release_dir=Path(raw) / "ft_releases" / tool.RELEASE_ID, local_release_copy=Path(raw) / "local.json")
                self.assertTrue((Path(result["server_manifest"])).is_file())
                self.assertEqual(Path(result["server_manifest"]).read_bytes(), Path(result["local_copy"]).read_bytes())
                final = json.loads((root / "E2-R001" / "round.json").read_text())
                self.assertEqual(final["verdict"], "failed_harness")
        finally:
            tool.TARGETS = original

    def test_cli_prepare_is_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "rounds"; root.mkdir()
            tool = load_tool()
            self.make_previous_release(root)
            for round_id, verdict, _ in tool.TARGETS:
                evidence = ["status_batch28.json"] if verdict == "failed_harness" else ["review.json"]
                self.make_round(root, round_id, verdict, evidence,
                                hypothesis=round_id in tool.HYPOTHESIS_CONCLUSIONS)
            before = (root / "E2-R001" / "round.json").read_bytes()
            run = subprocess.run([sys.executable, str(TOOL), "--mode", "prepare", "--rounds-root", str(root), "--writer", str(WRITER), "--out", str(Path(raw) / "review.json"), "--release-out", str(Path(raw) / "proposal.json")], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(before, (root / "E2-R001" / "round.json").read_bytes())
            proposal = json.loads((Path(raw) / "proposal.json").read_text(encoding="utf-8"))
            self.assertEqual(proposal["previous_release_manifest"]["sha256"], hashlib.sha256((root.parent / "ft_releases" / tool.PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest())
            self.assertTrue(any("actual-state corruption" in item for item in proposal["known_discrepancies"]))
            overlays = next(row for row in proposal["rounds"] if row["round_id"] == "E2-R009")["affected_subconclusion_overlays"]
            self.assertEqual(overlays[0]["id"], "P0_quality_alignment")
            self.assertEqual(overlays[0]["release_status"], "hypothesis")
            failed = next(row for row in proposal["rounds"] if row["round_id"] == "E2-R001")
            self.assertEqual(failed["local_result_document"]["path"], tool.FAILED_RESULT_DOCUMENTS["E2-R001"]["path"])

    def test_manifest_rejects_duplicate_tampering_and_escape(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)/'rounds'; root.mkdir()
            directory = self.make_round(root, 'E2-R001', 'failed_harness', ['status_batch28.json'])
            manifest = directory/'MANIFEST.sha256'
            original = manifest.read_text()
            self.assertEqual(tool.verify_manifest(directory, manifest), [])
            for text in (original+original, '0'*64+'  ../outside.json\n', '0'*64+'  status_batch28.json\n'):
                manifest.chmod(0o644); manifest.write_text(text); manifest.chmod(0o444)
                self.assertTrue(tool.verify_manifest(directory, manifest))

    def test_apply_refuses_changed_round_before_any_mutation(self):
        tool = load_tool(); tool.TARGETS = (('E2-R001','failed_harness','reason'),)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)/'rounds'; root.mkdir(); self.make_previous_release(root)
            directory = self.make_round(root,'E2-R001','failed_harness',['status_batch28.json'])
            review = tool.build_review(root,WRITER)
            document = directory/'round.json'
            document.chmod(0o644); document.write_bytes(document.read_bytes()+b' '); document.chmod(0o444)
            server = root.parent/'ft_releases'/tool.RELEASE_ID
            with self.assertRaisesRegex(ValueError,'changed after review'):
                tool.apply(review,WRITER,by='test',server_release_dir=server,local_release_copy=root.parent/'local.json')
            self.assertFalse(server.exists())

    def test_atomic_create_never_overwrites_collision(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)/'manifest.json'; target.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                tool.atomic_create(target,b'replacement')
            self.assertEqual(target.read_bytes(),b'keep')

    def test_round_relative_rejects_foreign_and_parent_paths(self):
        tool=load_tool()
        for value in ('../secret','/absolute','C:/foreign','a/../../secret','a\\foreign','.'):
            self.assertFalse(tool.is_round_relative(value),value)

    def test_apply_refuses_existing_release_before_verdict(self):
        tool = load_tool()
        original = tool.TARGETS
        tool.TARGETS = (("E2-R001", "failed_harness", "reason"),)
        try:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "rounds"; root.mkdir()
                self.make_previous_release(root)
                self.make_round(root, "E2-R001", "pending_review", ["status_batch28.json"])
                before = (root / "E2-R001" / "round.json").read_bytes()
                release_dir = Path(raw) / "ft_releases" / tool.RELEASE_ID
                release_dir.mkdir()
                review = tool.build_review(root, WRITER)
                with self.assertRaises(ValueError):
                    tool.apply(review, WRITER, by="test", server_release_dir=release_dir, local_release_copy=Path(raw) / "local.json")
                self.assertEqual(before, (root / "E2-R001" / "round.json").read_bytes())
        finally:
            tool.TARGETS = original

    def test_apply_rejects_result_output_alias(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "rounds"; root.mkdir()
            self.make_previous_release(root)
            server = Path(raw) / "ft_releases" / tool.RELEASE_ID
            local = Path(raw) / "local.json"
            review = {"rounds_root": str(root)}
            with self.assertRaises(ValueError):
                tool.validate_apply_destinations(review, server, local, local)

    def test_failed_result_document_fingerprints_match_local_sources(self):
        tool = load_tool()
        for details in tool.FAILED_RESULT_DOCUMENTS.values():
            self.assertEqual(hashlib.sha256((ROOT / details["path"]).read_bytes()).hexdigest(), details["sha256"])

    def test_release_snapshot_rejects_a_round_changed_after_review(self):
        tool = load_tool()
        original = tool.TARGETS
        tool.TARGETS = (("E2-R001", "failed_harness", "reason"),)
        try:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw) / "rounds"; root.mkdir()
                self.make_previous_release(root)
                directory = self.make_round(root, "E2-R001", "failed_harness", ["status_batch28.json"])
                review = tool.build_review(root, WRITER)
                round_json = directory / "round.json"
                os.chmod(round_json, 0o644)
                round_json.write_text("{}\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    tool.snapshot_release_inputs(review)
        finally:
            tool.TARGETS = original


if __name__ == "__main__":
    unittest.main()
