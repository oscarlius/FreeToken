from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


PATH = Path(__file__).with_name("gpu_window_oom.py")
SPEC = importlib.util.spec_from_file_location("gpu_window_oom", PATH)
window = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(window)


class WindowContracts(unittest.TestCase):
    def test_client_interface_and_caps(self):
        argv = window.client_argv("candidate_on", Path("/tmp/on"), 123.0)
        self.assertEqual(argv[:5], ["gpu_http_check.py", "--arm", "candidate_on", "--base-url", "http://127.0.0.1:8095"])
        self.assertEqual(window.CALL_CAPS, {"main": 3, "candidate_off": 3, "candidate_on": 4})

    def test_summary_requires_canonical_refs_and_match(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            refs_doc = {"short512": list(range(128)), "long8257": list(range(128))}
            (path / "SUMMARY.json").write_text(json.dumps({"classification": "kept", "calls": 3, "refs": refs_doc}))
            refs = window.verify_summary("main", path)
            (path / "SUMMARY.json").write_text(json.dumps({"classification": "kept", "calls": 4, "refs": refs_doc}))
            self.assertEqual(window.verify_summary("candidate_on", path, refs), refs)

    def test_unauthorized_packet_blocks_before_any_lifecycle_action(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "WINDOW_AUTHORIZATION.json").write_text(json.dumps({"authorized": False}))
            with mock.patch.object(window, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "authorization"):
                    window.load_authorization()

    def test_restore_package_requires_source_identical_adapters(self):
        with tempfile.TemporaryDirectory() as td:
            base, root = Path(td), Path(td) / "upstream_oom_pr_20261014"
            source = base / "upstream_layer_major_pr_20261014" / "restore_e3"
            package = root / "restore_e3"
            source.mkdir(parents=True); package.mkdir(parents=True)
            files = {}
            for name in window.RESTORE_ADAPTERS:
                (source / name).write_text("frozen:" + name)
                (package / name).write_text("frozen:" + name)
                files[name] = window.sha(package / name)
            (package / "SOURCE_MANIFEST.json").write_text(json.dumps({"identity": window.RESTORE_ID, "files": files}))
            (package / "DEPLOYMENT_APPROVAL.json").write_text(json.dumps({"approval_id": window.RESTORE_ID}))
            with mock.patch.object(window, "ROOT", root):
                self.assertEqual(window.verify_restore_package(), package)
                (package / "approved_attempt.py").write_text("changed")
                with self.assertRaisesRegex(RuntimeError, "adapter differs"):
                    window.verify_restore_package()

    def test_restore_budget_leaves_only_bounded_measurement_time(self):
        self.assertEqual(window.RESTORE_RESERVE_SECONDS, 2100)
        self.assertEqual(2700 - window.RESTORE_RESERVE_SECONDS, 600)

    def test_restore_admission_rejects_mutated_guard_before_import(self):
        class Gate:
            def require_root_final_review(self, _approval): pass
        class Guard:
            def verify_sources(self, _approval): pass
        with tempfile.TemporaryDirectory() as td:
            base, root = Path(td), Path(td) / "upstream_oom_pr_20261014"
            package = root / "restore_e3"; package.mkdir(parents=True)
            (package / "DEPLOYMENT_APPROVAL.json").write_text(json.dumps({"approval_id": window.RESTORE_ID}))
            frozen = base / "upstream_layer_major_pr_20261014"; frozen.mkdir()
            (frozen / "recovery_guard.py").write_text("frozen")
            (root / "recovery_guard.py").write_text("frozen")
            with mock.patch.object(window, "ROOT", root), mock.patch.object(window, "load_module", side_effect=[Gate(), Guard()]):
                self.assertEqual(window.verify_restore_admission(package)["approval_id"], window.RESTORE_ID)
            (root / "recovery_guard.py").write_text("mutated")
            with mock.patch.object(window, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "recovery_guard"):
                    window.verify_restore_admission(package)

    def test_partial_stop_failure_restores_when_active_pointer_is_absent(self):
        """A stop adapter can fail after stopping production; finally must restore once."""
        class Lifecycle:
            def stop_owned_process(self, *_args):
                raise AssertionError("no candidate service started after stop failure")

        class Helper:
            def load_owned_lifecycle(self):
                return Lifecycle()

            def process_identity(self, pid):
                return {"pid": pid, "start_ticks": 1, "pgid": 2, "session": 3}

            def take_d07_gpu_lock(self, *_args):
                raise AssertionError("lock must not be acquired after failed stop")

            def release_d07_gpu_lock(self, *_args):
                raise AssertionError("no lock acquired")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            active = {
                "supervisor": {"pid": 11, "start_ticks": 1, "pgid": 2, "session": 3},
                "service": {"pid": 12, "start_ticks": 1, "pgid": 2, "session": 3},
            }
            active_path = root / "production.active.json"
            active_path.write_text(json.dumps(active))
            auth = {
                "window_seconds": 2700,
                "frozen_ops": {"path": str(root / "frozen.py")},
                "old_stop_adapter": "stop.py",
                "test_python": window.NEWPY,
                "active_snapshot": active,
            }
            (root / "WINDOW_AUTHORIZATION.json").write_text(json.dumps({"authorized": True}))
            calls = []

            def fake_command(argv, **_kwargs):
                calls.append(argv)
                if argv == [window.OLDPY, "stop.py"]:
                    active_path.unlink()
                    raise RuntimeError("stop adapter failed after stopping production")

            with mock.patch.object(window, "ROOT", root), \
                 mock.patch.object(window, "ACTIVE_PATH", active_path), \
                 mock.patch.object(window, "load_authorization", return_value=auth), \
                 mock.patch.object(window, "verify_pins"), \
                 mock.patch.object(window, "verify_restore_package", return_value=root / "restore_e3"), \
                 mock.patch.object(window, "verify_restore_admission"), \
                 mock.patch.object(window, "load_module", return_value=Helper()), \
                 mock.patch.object(window, "run_command", side_effect=fake_command), \
                 mock.patch.object(window, "wait_gpu_idle"):
                with self.assertRaises(RuntimeError):
                    window.run()

            terminal = json.loads((root / "GPU_WINDOW_TERMINAL.json").read_text())
            self.assertTrue(terminal["restored"])
            self.assertEqual(calls[1], [window.OLDPY, str(root / "restore_e3" / "start_approved_release.py")])
            self.assertEqual(calls[2], [window.OLDPY, str(root / "restore_e3" / "wait_release_and_smoke.py")])

    def test_complete_window_runs_three_arms_then_restores(self):
        class Lifecycle:
            def __init__(self): self.stopped = 0
            def stop_owned_process(self, *_args): self.stopped += 1

        lifecycle = Lifecycle()
        class Helper:
            def load_owned_lifecycle(self): return lifecycle
            def process_identity(self, pid): return {"pid": pid, "start_ticks": 1, "pgid": 2, "session": 3}
            def take_d07_gpu_lock(self, *_args): return "lock"
            def release_d07_gpu_lock(self, lock): self.released = lock
        helper = Helper()
        class Proc:
            pid = 99
            def poll(self): return None

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_main, source_candidate = root / "main", root / "candidate"
            source_main.mkdir(); source_candidate.mkdir()
            active = {name: {"pid": pid, "start_ticks": 1, "pgid": 2, "session": 3}
                      for name, pid in (("supervisor", 11), ("service", 12))}
            active_path = root / "production.active.json"; active_path.write_text(json.dumps(active))
            auth = {"window_seconds": 2700, "frozen_ops": {"path": str(root / "frozen.py")},
                    "old_stop_adapter": "stop.py", "test_python": window.NEWPY,
                    "active_snapshot": active, "main_source": str(source_main),
                    "candidate_source": str(source_candidate)}
            (root / "WINDOW_AUTHORIZATION.json").write_text(json.dumps({"authorized": True}))
            seen_arms = []
            def fake_command(argv, **_kwargs):
                if argv == [window.OLDPY, "stop.py"]:
                    active_path.unlink()
                elif str(root / "gpu_http_check.py") in argv:
                    arm = argv[argv.index("--arm") + 1]; out = Path(argv[argv.index("--out") + 1])
                    refs = {"short512": list(range(128)), "long8257": list(range(128))}
                    (out / "SUMMARY.json").write_text(json.dumps({"classification": "kept", "calls": window.CALL_CAPS[arm], "refs": refs}))
                    seen_arms.append(arm)
                elif "start_approved_release.py" in argv[1]:
                    self.assertEqual(helper.released, "lock")
            with mock.patch.object(window, "ROOT", root), mock.patch.object(window, "ACTIVE_PATH", active_path), \
                 mock.patch.object(window, "load_authorization", return_value=auth), mock.patch.object(window, "verify_pins"), \
                 mock.patch.object(window, "verify_restore_package", return_value=root / "restore_e3"), \
                 mock.patch.object(window, "verify_restore_admission"), \
                 mock.patch.object(window, "load_module", return_value=helper), mock.patch.object(window, "run_command", side_effect=fake_command), \
                 mock.patch.object(window, "wait_gpu_idle"), mock.patch.object(window, "wait_ready"), \
                 mock.patch.object(window, "snapshot_environment"), \
                 mock.patch.object(window.subprocess, "Popen", return_value=Proc()):
                window.run()
            terminal = json.loads((root / "GPU_WINDOW_TERMINAL.json").read_text())
            self.assertEqual(seen_arms, list(window.ARMS))
            self.assertEqual(terminal["classification"], "kept")
            self.assertTrue(terminal["restored"])
            self.assertEqual(lifecycle.stopped, 6)  # per-arm cleanup plus final belt-and-braces pass

    def test_partial_stop_that_leaves_original_live_does_not_restore_or_wait_idle(self):
        class Lifecycle:
            def stop_owned_process(self, *_args):
                raise AssertionError("no candidate service started")
        class Helper:
            def load_owned_lifecycle(self): return Lifecycle()
            def process_identity(self, pid): return {"pid": pid, "start_ticks": 1, "pgid": 2, "session": 3}

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            active = {name: {"pid": pid, "start_ticks": 1, "pgid": 2, "session": 3}
                      for name, pid in (("supervisor", 11), ("service", 12))}
            active_path = root / "production.active.json"; active_path.write_text(json.dumps(active))
            auth = {"window_seconds": 2700, "frozen_ops": {"path": str(root / "frozen.py")},
                    "old_stop_adapter": "stop.py", "test_python": window.NEWPY,
                    "active_snapshot": active}
            (root / "WINDOW_AUTHORIZATION.json").write_text(json.dumps({"authorized": True}))
            calls = []
            def fake_command(argv, **_kwargs):
                calls.append(argv)
                if argv == [window.OLDPY, "stop.py"]:
                    raise RuntimeError("stop command failed before changing owner")
            with mock.patch.object(window, "ROOT", root), mock.patch.object(window, "ACTIVE_PATH", active_path), \
                 mock.patch.object(window, "load_authorization", return_value=auth), mock.patch.object(window, "verify_pins"), \
                 mock.patch.object(window, "verify_restore_package", return_value=root / "restore_e3"), \
                 mock.patch.object(window, "verify_restore_admission"), \
                 mock.patch.object(window, "load_module", return_value=Helper()), mock.patch.object(window, "run_command", side_effect=fake_command), \
                 mock.patch.object(window, "wait_gpu_idle") as idle:
                with self.assertRaises(RuntimeError):
                    window.run()
            terminal = json.loads((root / "GPU_WINDOW_TERMINAL.json").read_text())
            self.assertTrue(terminal["restored"])
            self.assertTrue(terminal["production_already_live"])
            self.assertEqual(calls, [[window.OLDPY, "stop.py"]])
            idle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
