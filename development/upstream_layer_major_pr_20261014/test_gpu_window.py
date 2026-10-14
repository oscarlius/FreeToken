"""CPU-only contracts for the approved GPU-window runner."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


RUNNER_PATH = Path(__file__).with_name("gpu_window_ready.py")
SPEC = importlib.util.spec_from_file_location("gpu_window_ready_test", RUNNER_PATH)
window = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(window)


class GpuWindowReadyTests(unittest.TestCase):
    def test_service_command_has_only_the_candidate_flag_difference(self):
        off = window.service_command(False)
        on = window.service_command(True)

        self.assertEqual(on, off + ["--prefill-layer-major"])
        self.assertNotIn("--prefill-layer-major", off)
        self.assertEqual(off[:6], [
            "taskset", "-c", "1,3-47", window.NEW_PYTHON,
            "-m", "freetoken.cli",
        ])
        self.assertEqual(off[6], "serve")
        expected_values = {
            "--model-path": window.MODEL_PATH,
            "--memory-ratio": "0.88",
            "--kv-reserve-tokens": "98304",
            "--max-seq-len-override": "98304",
            "--max-prefill-length": "4096",
        }
        for flag, value in expected_values.items():
            self.assertEqual(off[off.index(flag) + 1], value)
        for forbidden in (
            "--num-tokens", "--mem-fraction-static", "--max-seq-len",
            "--mamba-host-slots", "--prefill-anchor-cut",
        ):
            self.assertNotIn(forbidden, off)

    def test_measurement_env_binds_source_observer_and_native_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            native = Path(temporary) / "native"
            with mock.patch.dict(os.environ, {
                "PATH": "/base/path", "FT_STALE": "1", "PYTHONPATH": "old",
                "CUDA_VISIBLE_DEVICES": "7",
            }, clear=True):
                env = window.measurement_env(source, native)

        self.assertEqual(
            env["PYTHONPATH"],
            ":".join((str(window.ROOT / "observer"), str(window.ROOT), str(source / "python"))),
        )
        self.assertEqual(env["FT_UPSTREAM_NATIVE_IDS"], str(native))
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0")
        self.assertEqual(env["VIRTUAL_ENV"], str(window.ROOT / "main-venv"))
        self.assertNotIn("FT_STALE", env)

    def test_compare_rejects_mismatched_native_ids(self):
        reference = {"long1-cold": {"native_token_ids": [1, 2, 3]}}
        self.assertIsNone(window.compare(reference, dict(reference)))
        with self.assertRaisesRegex(ValueError, "not_met"):
            window.compare(reference, {"long1-cold": {"native_token_ids": [1, 2, 4]}})

    def test_remaining_rejects_an_expired_deadline(self):
        with mock.patch.object(window.time, "time", return_value=10.0):
            with self.assertRaises(TimeoutError):
                window.remaining(10.0)
            self.assertEqual(window.remaining(11.0), 1.0)

    def test_wait_ready_rejects_early_exit_without_http(self):
        process = mock.Mock()
        process.poll.return_value = 17
        process.returncode = 17
        opener = mock.Mock()
        with mock.patch.object(window.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "exited before readiness"):
                window.wait_ready(process, window.time.time() + 30)
        opener.open.assert_not_called()

    def test_verify_tree_accepts_canonical_source_then_rejects_extra_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            module_path = source / "python" / "freetoken" / "module.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("VALUE = 1\n", encoding="utf-8")
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.comment = b"canonical-commit"
                bundle.write(module_path, "python/freetoken/module.py")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            self.assertEqual(
                window.verify_tree(archive, source, digest, "canonical-commit"),
                {"commit": "canonical-commit", "archive_sha256": digest},
            )
            (source / "python" / "freetoken" / "extra.py").write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unexpected or unpinned importable file"):
                window.verify_tree(archive, source, digest, "canonical-commit")


if __name__ == "__main__":
    unittest.main()
