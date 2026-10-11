import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).with_name('t2_actual_v5.py')
spec = importlib.util.spec_from_file_location('t2_actual_test', PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ReplayTests(unittest.TestCase):
    def test_all_frozen_requests_edits_and_stream_timing(self):
        module, plan, bindings = runner.prepare()
        receipt = runner.file_dry(module, plan, bindings)
        self.assertEqual(receipt['actual_mock_calls'], 36)
        self.assertLess(receipt['first_delta_s'], receipt['stream_complete_s'])

    def test_failed_http_attempt_preserves_raw_and_terminal(self):
        module, plan, _ = runner.prepare()
        class BrokenOpener:
            def open(self, request, timeout):
                raise TimeoutError('injected transport failure')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / 'serve.log'
            log.write_bytes(b'')
            output = root / 'output'
            with self.assertRaisesRegex(RuntimeError, 'injected transport failure'):
                runner.execute(module, plan, BrokenOpener(), 'http://127.0.0.1:1', log, output)
            terminal = json.loads((output / 'terminal.json').read_text())
            self.assertEqual(terminal['generation_calls_attempted'], 1)
            self.assertEqual(terminal['completed'], 0)
            self.assertEqual(terminal['verdict'], 'failed_harness')
            self.assertTrue((output / 'reverse_cold_00.sse.json').exists())


if __name__ == '__main__':
    unittest.main()
