import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import gpu_window
import hybrid_service
import payload_freeze
import window_measure

HERE = Path(__file__).resolve().parent
SERVER_MARK = Path('/data2/FreeToken/wt/release-e2/python').exists()


class ControllerPins(unittest.TestCase):
    def test_pin_set_is_exactly_the_four_controller_files(self):
        pins = {str(HERE / name): hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                for name in gpu_window.CONTROLLER_FILES}
        gpu_window.validate_controller_pins({'controller_source_pins': pins})
        del pins[str(HERE / 'warmup_client.py')]
        with self.assertRaisesRegex(ValueError, 'pin set'):
            gpu_window.validate_controller_pins({'controller_source_pins': pins})

    def test_measurement_rejects_writable_or_unpinned_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'admission.json'
            path.write_text(json.dumps({'admit': True, 'schema': 'ft_hybrid_verify_20261011/v1'}))
            with patch('window_measure.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'sealed'):
                    window_measure.run(path, 'O1', 'x_single', 1, 1, 1, time.time() + 60)
                run.assert_not_called()

    def test_measurement_rejects_foreign_schema_before_spawn(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'admission.json'
            path.write_text(json.dumps({'admit': True, 'schema': 'ft_d08_d10_eta_retry2_admission/v1'}))
            path.chmod(0o444)
            with patch('window_measure.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'scope'):
                    window_measure.run(path, 'O1', 'x_single', 1, 1, 1, time.time() + 60)
                run.assert_not_called()


class WarmupContract(unittest.TestCase):
    def test_warmup_uses_exact_sdk_short_long_on_the_test_endpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / 'inputs.json'
            adapter = root / 'sdk.py'
            inputs.write_text(json.dumps({'items': {'short': {'n': 512}, 'long': {'n': 8257}}}))
            adapter.write_text(
                "def collect_one(base, model, key, item, out):\n"
                "    assert base == 'http://127.0.0.1:8123', base\n"
                "    return {'projection': {'usage': {'prompt_tokens': item['n'], "
                "'completion_tokens': 128}, 'finish_reason': 'length'}}\n")
            doc = {'warmup_inputs_path': str(inputs), 'warmup_adapter_path': str(adapter),
                   'warmup_inputs_sha256': hashlib.sha256(inputs.read_bytes()).hexdigest(),
                   'warmup_adapter_sha256': hashlib.sha256(adapter.read_bytes()).hexdigest(),
                   'host': '127.0.0.1', 'port': 8123}
            old = SimpleNamespace(sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest())
            with patch('window_measure.load_old', return_value=old):
                hybrid_service.warmup(doc, root, time.time() + 10)
            receipt = json.loads((root / 'warmup/terminal.json').read_text())
            self.assertTrue(receipt['not_scored'])
            self.assertEqual(receipt['endpoint'], 'http://127.0.0.1:8123')
            self.assertEqual([x['usage']['prompt_tokens'] for x in receipt['records']], [512, 8257])


class IdlePorts(unittest.TestCase):
    def test_idle_binds_exactly_the_requested_endpoints(self):
        binds = []

        class Probe:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def setsockopt(self, *args):
                pass

            def bind(self, address):
                binds.append(address)

        d07 = SimpleNamespace(require_gpu_idle=lambda: None)
        with patch('hybrid_service.socket.socket', return_value=Probe()), \
                patch('hybrid_service.subprocess.check_output', return_value=''):
            hybrid_service.idle(d07, [('127.0.0.1', 8123)])
        self.assertEqual(binds, [('127.0.0.1', 8123)])


class Lc2TruncationRule(unittest.TestCase):
    @staticmethod
    def count(messages):
        return sum(len(m['content']) for m in messages)

    def messages(self, sizes):
        roles = ['user', 'assistant', 'tool', 'assistant', 'tool']
        return [{'role': roles[i % len(roles)], 'content': 'x' * n} for i, n in enumerate(sizes)]

    def test_keeps_longest_complete_prefix_under_cap(self):
        rule = payload_freeze.truncate_message_granularity(self.count, self.messages([10, 5, 5, 5, 5]), 20)
        self.assertEqual(rule['kept_roles'], ['user', 'assistant', 'tool'])
        self.assertEqual(rule['kept_rendered_tokens'], 20)
        self.assertTrue(rule['feasible'])

    def test_drops_trailing_assistant(self):
        rule = payload_freeze.truncate_message_granularity(self.count, self.messages([10, 5, 100]), 15)
        self.assertEqual(rule['kept_roles'], ['user'])
        self.assertTrue(rule['dropped_trailing_assistant'])

    def test_oversized_first_message_is_infeasible(self):
        rule = payload_freeze.truncate_message_granularity(self.count, self.messages([100, 5, 5]), 32)
        self.assertFalse(rule['feasible'])
        self.assertEqual(rule['kept_roles'], [])
        self.assertEqual(rule['per_message_cumulative_tokens'][0]['cumulative_tokens'], 100)

    def test_prefix_proposal_binary_searches_the_cap(self):
        messages, tokens, kept, total = payload_freeze.prefix_proposal(
            self.count, {'role': 'user', 'content': 'x' * 100}, 32)
        self.assertEqual((kept, total), (32, 100))
        self.assertEqual(tokens, 32)
        self.assertEqual(messages[0]['role'], 'user')


class ArgvParserDryRun(unittest.TestCase):
    @unittest.skipUnless(SERVER_MARK, 'release-e2 worktree only exists on the server')
    def test_both_final_argvs_pass_the_release_e2_parser(self):
        import prepare_root_admission as prep
        baseline = json.loads((HERE / 'BASELINE_OWNER_FREEZE.json').read_text())
        for mode in ('offload', 'hybrid'):
            argv = hybrid_service.expected_argv(baseline['argv'], mode, prep.HOST, prep.PORT)
            receipt = prep.parser_dry_run(argv)
            self.assertEqual(receipt['exit_code'], 0)


if __name__ == '__main__':
    unittest.main()
