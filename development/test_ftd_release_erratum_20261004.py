#!/usr/bin/env python3
"""CPU-only regression tests for the FTD-20261004-1 immutable erratum."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("erratum", HERE / "ftd_release_erratum_20261004.py")
assert SPEC and SPEC.loader
erratum = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(erratum)
REPO_ROOT = HERE.parent


class ErratumTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.releases = self.root / "ft_releases"
        self.base_dir = self.releases / erratum.BASE_RELEASE_ID
        self.base_dir.mkdir(parents=True)
        rounds = [{"round_id": name} for name in sorted(erratum.REQUIRED_ROUNDS)]
        self.base = self.base_dir / "manifest.json"
        self.base.write_text(
            json.dumps(
                {
                    "schema": "ft_data_release/v1",
                    "release_id": erratum.BASE_RELEASE_ID,
                    "code_versions": {"required": {"baseline": erratum.BASE_CODE_VERSION}},
                    "rounds": rounds,
                }
            ),
            encoding="utf-8",
        )
        self.expected_hash = hashlib.sha256(self.base.read_bytes()).hexdigest()
        self.base.chmod(0o444)
        self.base_dir.chmod(0o555)
        self.local_dir = self.root / "local"
        self.local_dir.mkdir()

    def tearDown(self) -> None:
        for path in sorted(self.root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            try:
                path.chmod(0o755)
            except OSError:
                pass
        self.temp.cleanup()

    def build(self) -> dict:
        return erratum.build_erratum(self.base, REPO_ROOT, expected_base_hash=self.expected_hash)

    def test_explicit_semantic_scopes_and_e2_r009_membership(self) -> None:
        document = self.build()
        actual = {(item["round_id"], item["claim_id"], item["release_status"])
                  for item in document["release_only_claim_overrides"]}
        self.assertEqual(
            actual,
            {
                ("E2-R006", "prefix_hit_continuation_output", "hypothesis"),
                ("E2-R006", "cold_versus_warm_output", "hypothesis"),
                ("E2-R017", "prefix_hit_continuation_output", "hypothesis"),
                ("E2-R017", "cold_versus_warm_output", "hypothesis"),
                ("E2-R008", "warm_replay_output_text", "hypothesis"),
                ("E2-R009", "warm_replay_output_text", "hypothesis"),
                ("E2-R009", "multi_round_60_quality", "hypothesis"),
                ("E2-R009-p64k", "warm_replay_output_text", "hypothesis"),
            },
        )
        rule = document["protocol_scoped_rules"][0]
        self.assertEqual(rule["release_contained_evidence_rounds"], ["E2-R009"])
        self.assertIn("not GPU-verified", document["known_defect"]["candidate_status"])
        self.assertIn("Cold", document["preserved_base_claims"]["cold_timing_and_output"])

    def test_bad_hash_rejected(self) -> None:
        with self.assertRaisesRegex(erratum.ErratumError, "hash mismatch"):
            erratum.build_erratum(self.base, REPO_ROOT, expected_base_hash="0" * 64)

    def test_missing_source_rejected(self) -> None:
        missing_root = self.root / "missing-source"
        missing_root.mkdir()
        with self.assertRaisesRegex(erratum.ErratumError, "source reference"):
            erratum.build_erratum(self.base, missing_root, expected_base_hash=self.expected_hash)

    def test_nonreadonly_base_rejected(self) -> None:
        self.base_dir.chmod(0o755)
        self.base.chmod(0o644)
        with self.assertRaisesRegex(erratum.ErratumError, "read-only"):
            self.build()

    def test_overwrite_and_alias_rejected(self) -> None:
        target_dir = self.releases / erratum.ERRATUM_ID
        target_dir.mkdir()
        local = self.local_dir / "erratum.json"
        with self.assertRaisesRegex(erratum.ErratumError, "already exists"):
            erratum.create_erratum(
                self.base, REPO_ROOT, target_dir, local, expected_base_hash=self.expected_hash
            )
        target_dir.rmdir()
        alias_parent = self.root / "alias"
        try:
            os.symlink(self.local_dir, alias_parent, target_is_directory=True)
        except (NotImplementedError, OSError):
            if os.name != "nt":
                self.skipTest("symlink creation is unavailable on this platform")
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(alias_parent), str(self.local_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("symlink and junction creation are unavailable on this platform")
        with self.assertRaisesRegex(erratum.ErratumError, "symlink"):
            erratum.create_erratum(
                self.base,
                REPO_ROOT,
                target_dir,
                alias_parent / "erratum.json",
                expected_base_hash=self.expected_hash,
            )

    def test_apply_creates_readonly_byte_identical_pair(self) -> None:
        server_dir = self.releases / erratum.ERRATUM_ID
        local = self.local_dir / "erratum.json"
        document = erratum.create_erratum(
            self.base, REPO_ROOT, server_dir, local, expected_base_hash=self.expected_hash
        )
        server = server_dir / "erratum.json"
        self.assertEqual(server.read_bytes(), local.read_bytes())
        self.assertFalse(stat.S_IMODE(server.stat().st_mode) & 0o222)
        self.assertFalse(stat.S_IMODE(server_dir.stat().st_mode) & 0o222)
        self.assertEqual(document["base_release"]["manifest_sha256"], self.expected_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
