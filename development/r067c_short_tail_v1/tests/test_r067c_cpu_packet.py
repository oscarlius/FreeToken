"""Static and CPU-only checks for the non-admitted R067c preparation packet."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]


class R067cCpuPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((HERE / "R067C_CONFIG_CPU_ONLY.json").read_text())
        cls.template = json.loads((HERE / "R067C_COMMAND_TEMPLATE_CPU_ONLY.json").read_text())
        cls.runner_packet = json.loads((HERE / "R067C_PREPARED_RUNNER_PACKET.json").read_text())
        cls.upload_manifest = json.loads((HERE / "R067C_CPU_UPLOAD_MANIFEST.json").read_text())
        cls.source = cls.template["materialization_source"]

    def test_exact_rid_and_separate_non_admitted_scope(self):
        self.assertEqual(self.config["rid"], "E2-R067c-d20-short-tail")
        self.assertTrue(self.config["separate_round"])
        self.assertEqual(self.config["not_a_replay_or_residual_of"], "E2-R067b")
        self.assertFalse(self.config["admission"]["admit"])
        self.assertEqual(self.config["remote_proof"]["status"], "pending_root_remote_validation")
        self.assertEqual(self.config["cpu_file_dry_proof"]["remote_file_dry"]["status"],
                         "pending_root_remote_validation")
        self.assertFalse(self.config["cpu_file_dry_proof"]["remote_file_dry"]["fabricated"])
        proof = self.config["cpu_file_dry_proof"]
        self.assertFalse(proof["inherited_unchanged_tooling_proof"]["new_r067c_signature"])
        self.assertIn("schedule_parse_admit", proof)
        self.assertIn("startup_spawn", proof)

    def test_ten_service_fourteen_call_budget_and_order(self):
        self.assertEqual(self.config["scope"], {
            "services": 10, "generation_calls": 14, "generation_calls_upper": 14,
        })
        self.assertEqual(len(self.config["services"]), 10)
        self.assertEqual([service["name"] for service in self.config["services"]],
                         self.config["execution_order"])
        calls = sum(len(service["requests"]) if service["kind"] == "hot" else 1
                    for service in self.config["services"])
        self.assertEqual(calls, 14)
        for service in self.config["services"]:
            self.assertEqual(
                service["argv_sha256"],
                hashlib.sha256(json.dumps(service["argv"], separators=(",", ":")).encode()).hexdigest(),
            )
            self.assertNotIn("E2-R067b", json.dumps(service["startup_materialization"]))

    def test_manifest_and_fixed_worktree_bindings(self):
        manifest = self.config["binary_manifest"]
        self.assertEqual(manifest["sha256"], "a8e70aef8a555b86cb9c4bd281d3f98939995cdee4799ff1a4c1368970993a18")
        self.assertEqual(manifest["required_entries"], {
            "cpu_moe": "10a2bd8311b9569bd03a6569db59da707699a44e67d7b677c35c3547d77855b4",
            "pinned": "07701be28030c4ebf63c210804b6eba2556cc0f4d2f1e5ed80b9d423ebfe7e68",
        })
        self.assertEqual(manifest["forbidden_entries"], ["row_store"])
        self.assertEqual(self.config["worktree_binding"]["hot"]["commit"],
                         "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9")
        self.assertEqual(self.config["worktree_binding"]["cold"]["commit"],
                         "d50be0f8f84ab1105f788be8f1354773ad539b63")
        self.assertIn("release_e2_ops_v8_20261009_smoke_guarded", manifest["path"])

    def test_prepared_runner_is_corrected_but_not_admitted(self):
        runner = self.runner_packet
        self.assertTrue(runner["execution_prohibited"])
        self.assertEqual(runner["status"], "prepared_but_execution_prohibited")
        self.assertEqual(runner["config_sha256"], self.template["config_sha256"])
        config_sha256 = hashlib.sha256((HERE / "R067C_CONFIG_CPU_ONLY.json").read_bytes()).hexdigest()
        self.assertEqual(runner["config_sha256"], config_sha256)
        self.assertIn(f"assert sha(FD)=='{config_sha256}'", runner["child_source"])
        self.assertIn(f"assert sha(FD)=='{config_sha256}'", runner["parent_tail"])
        ast.parse(runner["child_source"].replace("__ADMISSION_SHA256__", "0" * 64))
        self.assertNotIn("for name in", runner["child_source"])
        self.assertIn("for artifact_name in", runner["child_source"])
        self.assertEqual(runner["runtime_contract"]["scope"],
                         {"services_max": 10, "generation_calls_max": 14})
        self.assertIn("at most two", runner["runtime_contract"]["cold_ab_difference"])
        self.assertIn("restores production", runner["runtime_contract"]["hot_difference_after_equal_ab"])

    def test_upload_manifest_is_exact_cpu_packet_and_not_filedry(self):
        manifest = self.upload_manifest
        self.assertEqual(manifest["remote_directory"],
                         "/data2/FreeToken/development/r067c_short_tail_v1")
        self.assertTrue(manifest["upload_is_not_remote_filedry"])
        self.assertNotIn("__pycache__", "\n".join(manifest["files"]))
        self.assertIn("R067C_PREPARED_RUNNER_PACKET.json", manifest["files"])
        for name, digest in manifest["files"].items():
            self.assertEqual(digest, hashlib.sha256((HERE / name).read_bytes()).hexdigest())

    def test_cpu_validator_materializes_fresh_filedry_and_rejects_run(self):
        spec = importlib.util.spec_from_file_location("r067c_cpu_validate", HERE / "r067c_cpu_validate.py")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "filedry"
            receipt = validator.filedry(out)
            self.assertEqual(receipt["service_count"], 10)
            self.assertEqual(receipt["materialized_artifact_count"], 30)
            self.assertFalse(receipt["admit"])
            self.assertTrue((out / "services" / "hot_p8192" / "no_start.json").is_file())
            with self.assertRaises(RuntimeError):
                validator.main(["--run"])

    def test_root_retry_ledger_is_terminal_and_non_automatic(self):
        ledger = json.loads((HERE / "R067C_ROOT_RETRY_LEDGER_TEMPLATE.json").read_text())
        policy = ledger["policy"]
        self.assertEqual(ledger["owner"], "root")
        self.assertFalse(policy["automatic_retry"])
        self.assertEqual(policy["maximum_failed_harness_retries_across_r067c_rounds"], 2)
        self.assertEqual(policy["not_met"], "terminal_no_retry; root restores production")

    def test_ast_contains_real_artifact_copy_loop_for_all_service_names(self):
        tree = ast.parse(self.source)
        service_loop = next(node for node in ast.walk(tree)
                            if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                            and node.target.id == "service")
        nested_names = [node.target.id for node in ast.walk(service_loop)
                        if isinstance(node, ast.For) and isinstance(node.target, ast.Name)]
        self.assertEqual(nested_names, ["service", "artifact_name"])
        artifact_loop = next(node for node in ast.walk(service_loop)
                             if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                             and node.target.id == "artifact_name")
        code = compile(ast.fix_missing_locations(ast.Module(body=[artifact_loop], type_ignores=[])),
                       "<r067c materialization loop>", "exec")
        artifacts = ("t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_d14_observe.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); tooling = root / "tooling"; tooling.mkdir()
            for artifact in artifacts: (tooling / artifact).write_text(artifact)
            for service in self.config["services"]:
                arm = root / service["name"]; arm.mkdir()
                namespace = {"TOOLING": tooling, "arm": arm, "shutil": shutil,
                             "artifact_name": None, "ARTIFACTS": artifacts, "Path": Path}
                exec(code, namespace)
                self.assertEqual(sorted(path.name for path in arm.iterdir()), sorted(artifacts))

    def test_no_production_ports_or_execution_primitives(self):
        for service in self.config["services"]:
            self.assertNotIn(service["port_pair"]["api"], (8095, 8096))
            self.assertNotIn(service["port_pair"]["tcpstore"], (8095, 8096))
        self.assertTrue(self.template["execution_prohibited"])
        self.assertFalse(self.config["admission"]["admit"])
        for forbidden in ("subprocess", "Popen", "urllib", "socket", "take_d07_gpu_lock"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
