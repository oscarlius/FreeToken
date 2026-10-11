import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


PATH = Path(__file__).with_name("t17_d14_runner.py")
SPEC = importlib.util.spec_from_file_location("t17_d14_runner", PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class T17D14RunnerTests(unittest.TestCase):
    def test_exact_context_uses_absolute_boundary(self):
        self.assertEqual(runner.exact_context([3, 5, 7, 11], 2), [3, 5])
        self.assertEqual(runner.exact_context([3, 5, 7, 11], 4), [7, 11])
        with self.assertRaises(ValueError):
            runner.exact_context([3], 1)

    def test_cpu_replay_is_real_frontend_protocol_and_cpu_only(self):
        for required in ("ChatCompletionRequest", "chat_request_to_genspec", "TokenizeManager",
                         "torch.cuda.is_initialized", "E2-R002", "e2d14"):
            self.assertIn(required, runner.CPU_REPLAY)
        self.assertNotIn("ft serve", runner.CPU_REPLAY)

    def test_manifest_rejects_escape(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "MANIFEST.sha256").write_text("0" * 64 + "  ../outside\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runner.sealed_manifest(directory)

    def test_preflight_constants_bind_assigned_t16(self):
        self.assertEqual(runner.T16_RID, "E2-R022-gate-D14")
        self.assertEqual(runner.T16_BATCH, 50)
        self.assertEqual(len(runner.CANDIDATE), 40)
        self.assertIn("review_batch50.json", runner.T16_PREFLIGHT)
        self.assertIn("'gpu_started':False", runner.T16_PREFLIGHT)

    def test_startup_wrapper_calls_original_once_without_request_mutation(self):
        class Pool:
            def __init__(self): self.calls = []
            def dump_state(self, *args, **kwargs): self.calls.append((args, kwargs))
        class Scheduler:
            calls = 0
            def __init__(self): self.engine = SimpleNamespace(linear_state_pool=Pool())
            def _restore_linear_states(self, batch):
                type(self).calls += 1
                return "original-return"
        request = SimpleNamespace(uid=7, cached_len=8193, mamba_restore_src=3, mamba_restore_host=None,
                                  linear_slot_idx=9)
        batch = SimpleNamespace(reqs=[request])
        runner.install_resume_device_dump(Scheduler)
        subject = Scheduler()
        self.assertEqual(subject._restore_linear_states(batch), "original-return")
        self.assertEqual(Scheduler.calls, 1)
        self.assertEqual(request.mamba_restore_src, 3)
        self.assertEqual(subject.engine.linear_state_pool.calls,
                         [(('resume-device',), {'dev_slots': 9, 'length': 8193, 'uid': '7'})])
        self.assertNotIn("forward", runner.STARTUP_WRAPPER)

    def test_receipt_requires_actual_hit_and_all_state_roles(self):
        cases = {}
        for case in runner.BOUNDARY_PLAN:
            cases[case["name"]] = {"prompt_ids_sha256": "a", "actual_cached_tokens": 64,
                "donor_ngram": [1, 2], "resume_ngram": [1, 2], "expected_ngram": [1, 2],
                "cold_text": "same", "hit_text": "same",
                "state_roles": {role: "equal" for role in runner.STATE_ROLES}}
        good = {"gpu_started": True, "mamba_host_slots": 0, "cases": cases}
        runner.validate_hit_receipt(good)
        cases[runner.BOUNDARY_PLAN[0]["name"]]["actual_cached_tokens"] = 0
        with self.assertRaises(ValueError):
            runner.validate_hit_receipt(good)

    def test_manifest_binds_wrapper_and_assigned_identity(self):
        manifest = runner.launch_manifest("E2-R999-gate-D14", 123, PATH)
        self.assertEqual(manifest["mamba_host_slots"], 0)
        self.assertEqual(manifest["boundary_plan"], runner.BOUNDARY_PLAN)
        self.assertEqual(len(manifest["startup_wrapper_sha256"]), 64)
        with self.assertRaises(ValueError):
            runner.launch_manifest("", 0, PATH)

    def test_freeze_wrapper_preserves_ft_serve_argv(self):
        with tempfile.TemporaryDirectory() as raw:
            wrapper = runner.freeze_startup_wrapper(Path(raw))
            argv = runner.startup_argv(wrapper, ["serve", "model", "--port", "8095"])
            self.assertEqual(argv[-4:], ["serve", "model", "--port", "8095"])
            self.assertEqual(oct(wrapper.stat().st_mode & 0o777), "0o444")
            with self.assertRaises(FileExistsError):
                runner.freeze_startup_wrapper(Path(raw))

    def test_reviewed_t16_lifecycle_hashes_and_stop_contract(self):
        development = PATH.parent
        evidence = runner.verify_t16_lifecycle(
            development / "t16_full_tail_base_runner.py",
            development / runner.T16_LAUNCH_PROTOCOL,
        )
        self.assertEqual(evidence["base_runner_sha256"], runner.T16_BASE_SHA256)

    def test_exact_id_http_payload_and_terminal_failure_are_not_accepted(self):
        payload = runner.completion_payload([1, 2, 3], 1)
        self.assertEqual(payload["prompt"], [1, 2, 3])
        with self.assertRaises(RuntimeError):
            runner.require_completion_success({"status": 400, "payload": payload,
                                               "response": {"error": {"message": "unsupported"}}})

    def test_frozen_wrapper_installs_private_exact_id_endpoint(self):
        for required in ("/internal/t17/exact-ids", "T17ExactIdsMsg", "input_ids_exact",
                         "input_ids_sha256"):
            self.assertIn(required, runner.STARTUP_WRAPPER + runner.EXACT_ID_PATCH)
        self.assertIn("t17_d14_observe.startup()", runner.STARTUP_WRAPPER)
        self.assertIn("resume-device", PATH.with_name("t17_d14_observe.py").read_text())
        self.assertNotIn("model.forward", runner.STARTUP_WRAPPER)

    def test_case_runner_rejects_uncovered_real_trace_before_http(self):
        with self.assertRaises(ValueError):
            runner.donor_hit_cold("http://127.0.0.1:8095", [1] * 64, 8192)

    def test_actual_http_failure_is_retained_before_rejection(self):
        failure=HTTPError('http://127.0.0.1:8095/internal/t17/exact-ids',400,'bad',{},io.BytesIO(b'{"detail":"unsupported"}'))
        with tempfile.TemporaryDirectory() as raw, patch.object(runner.urllib.request,'urlopen',side_effect=failure):
            target=Path(raw)/'failure.json'
            with self.assertRaises(RuntimeError):
                runner.exact_id_request('http://127.0.0.1:8095',[1469,17],128,output_path=target)
            retained=json.loads(target.read_text())
            self.assertEqual(retained['status'],400)
            self.assertEqual(retained['payload']['input_ids'],[1469,17])
            self.assertEqual(retained['response']['detail'],'unsupported')
            self.assertEqual((Path(raw)/'failure.response.bin').read_bytes(),b'{"detail":"unsupported"}')
            self.assertEqual(retained['raw_response_file'],'failure.response.bin')
            self.assertEqual(retained['expected_input_ids_sha256'],__import__('hashlib').sha256(
                __import__('struct').pack('<2i',1469,17)).hexdigest())
            self.assertEqual(retained['observation_range'],{'start':0,'end':0})

    def test_dump_parser_requires_all_real_roles_and_bound_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            files = {}
            for role in runner.STATE_ROLES:
                name = role.replace(":", "_") + ".pt"
                (directory / name).write_bytes(b"proof")
                files[role] = name
            (directory / "index.jsonl").write_text(
                '{"kind":"resume-device","length":12416,"uid":"7","files":' + __import__("json").dumps(files) + '}\n',
                encoding="utf-8")
            row = runner.load_dump_record(directory, kind="resume-device", length=12416, uid="7")
            self.assertEqual(row["files"], files)
            with self.assertRaises(ValueError):
                runner.load_dump_record(directory, kind="resume-device", length=12416, uid="8")


if __name__ == "__main__":
    unittest.main()
