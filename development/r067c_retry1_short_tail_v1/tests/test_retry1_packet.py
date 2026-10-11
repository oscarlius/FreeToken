from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]


class Retry1PacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((HERE / "RETRY1_CONFIG_CPU_ONLY.json").read_text())
        cls.packet = json.loads((HERE / "RETRY1_PREPARED_RUNNER_PACKET.json").read_text())

    def test_scope_and_retry_contract_are_fixed(self):
        self.assertEqual(self.config["rid"], "E2-R067c-d20-short-tail-retry1")
        self.assertEqual(self.config["scope"], {"services": 10, "generation_calls": 14, "generation_calls_upper": 14})
        self.assertEqual(self.config["retry"]["retry_index"], 1)
        self.assertEqual(self.config["retry"]["classification"], "failed_harness")
        self.assertFalse(self.config["retry"]["automatic_retry"])
        self.assertEqual(self.config["retry"]["root_shared_retry_ledger"],
                         "/data2/FreeToken/development/r067c_production_control_20261009/ROOT_ATTEMPT_LEDGER.jsonl")
        self.assertFalse(self.config["admission"]["admit"])

    def test_only_geometry_predicate_changes_and_binds_new_config(self):
        config_sha = hashlib.sha256((HERE / "RETRY1_CONFIG_CPU_ONLY.json").read_bytes()).hexdigest()
        source = self.packet["child_source"]
        self.assertEqual(self.packet["config_sha256"], config_sha)
        self.assertIn(f"assert sha(FD)=='{config_sha}'", source)
        self.assertNotIn("/development/r067c_short_tail_v1/", source)
        self.assertIn("/development/r067c_retry1_short_tail_v1/", source)
        self.assertNotIn("sum(r['new_sequences'] for r in rows)==1", source)
        self.assertIn("all(r['new_sequences']==1 for r in rows)", source)
        self.assertIn("usage']['prompt_tokens']==len(ids)", source)
        self.assertIn("window.count(b'POST /internal/t17/exact-ids HTTP/1.1\" 200 OK')==1", source)
        self.assertIn("art.request_evidence", source)
        self.assertIn("usage']['cached_tokens']", source)

    def test_cpu_filedry_and_run_prohibition(self):
        spec = importlib.util.spec_from_file_location("retry1_cpu_validate", HERE / "retry1_cpu_validate.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            receipt = module.filedry(Path(temp) / "filedry")
        self.assertEqual((receipt["services"], receipt["calls"], receipt["artifacts"]), (10, 14, 30))
        self.assertFalse(receipt["admit"])
        with self.assertRaises(RuntimeError):
            module.main(["--run"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
