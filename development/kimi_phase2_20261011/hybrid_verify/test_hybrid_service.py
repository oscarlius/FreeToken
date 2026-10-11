import unittest
from unittest.mock import patch
from types import SimpleNamespace
from hybrid_service import expected_argv, capture_birth, require_master_context

BASELINE = ['taskset', '-c', '1,3-47', '/data2/FreeToken/venv/bin/ft', 'serve',
            '--model-path', '/m', '--host', '172.16.108.9', '--port', '8095',
            '--moe-strategy', 'offload', '--mamba-host-slots', '0']


class ArgvGate(unittest.TestCase):
    def test_offload_moves_only_host_and_port(self):
        actual = expected_argv(BASELINE, 'offload', '127.0.0.1', 8123)
        self.assertEqual(actual, ['taskset', '-c', '1,3-47', '/data2/FreeToken/venv/bin/ft', 'serve',
                                  '--model-path', '/m', '--host', '127.0.0.1', '--port', '8123',
                                  '--moe-strategy', 'offload', '--mamba-host-slots', '0'])
        self.assertEqual(len(actual), len(BASELINE))

    def test_hybrid_adds_exactly_the_two_section05_changes(self):
        actual = expected_argv(BASELINE, 'hybrid', '127.0.0.1', 8123)
        self.assertEqual(actual, ['numactl', '--interleave=all', 'taskset', '-c', '1,3-23,25,27-47',
                                  '/data2/FreeToken/venv/bin/ft', 'serve',
                                  '--model-path', '/m', '--host', '127.0.0.1', '--port', '8123',
                                  '--moe-strategy', 'hybrid', '--mamba-host-slots', '0'])

    def test_unknown_prefix_rejected(self):
        with self.assertRaises(ValueError):
            expected_argv(['taskset', '-c', '0', 'ft', 'serve', '--host', 'x', '--port', '1',
                           '--moe-strategy', 'offload'], 'hybrid', '127.0.0.1', 8123)

    def test_baseline_strategy_must_be_offload(self):
        baseline = list(BASELINE)
        baseline[baseline.index('offload')] = 'hybrid'
        with self.assertRaises(ValueError):
            expected_argv(baseline, 'hybrid', '127.0.0.1', 8123)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            expected_argv(BASELINE, 'eager', '127.0.0.1', 8123)

    def test_missing_birth_uses_fresh_private_session_proof(self):
        d07 = SimpleNamespace(process_identity=lambda pid: None)
        with patch('hybrid_service.os.getpgid', return_value=123, create=True), \
                patch('hybrid_service.os.getsid', return_value=123, create=True):
            proof = capture_birth(SimpleNamespace(pid=123), d07)
        self.assertEqual(proof['pgid'], 123)
        self.assertIsNone(proof['start_ticks'])

    def test_foreign_group_not_claimed_after_missing_birth(self):
        d07 = SimpleNamespace(process_identity=lambda pid: None)
        with patch('hybrid_service.os.getpgid', return_value=999, create=True), \
                patch('hybrid_service.os.getsid', return_value=123, create=True):
            with self.assertRaises(RuntimeError):
                capture_birth(SimpleNamespace(pid=123), d07)

    def test_direct_import_cannot_start_service_component(self):
        with self.assertRaisesRegex(RuntimeError, 'actual GPU master entry'):
            require_master_context({}, 9999999999, None)


if __name__ == '__main__':
    unittest.main()
