import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / 'development' / 'p0_failed_harness_prepare.py'
WRITER = ROOT / 'scripts' / 'round_json_append.py'
CLOSE = ROOT / 'scripts' / 'round_close.py'


def load_module():
    spec = importlib.util.spec_from_file_location('p0_failed_harness_prepare', PREPARE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FailedHarnessPreparationTests(unittest.TestCase):
    def make_round(self, root: Path, round_id: str, *, with_full_service: bool) -> Path:
        round_dir = root / round_id
        arm = round_dir / 'A'
        arm.mkdir(parents=True)
        (round_dir / 'batch.sh').write_text('#!/bin/sh\n', encoding='utf-8')
        (round_dir / 'error.json').write_text('{"error":"fixture"}\n', encoding='utf-8')
        if with_full_service:
            for name, text in {
                'SERVE_CMD.txt': 'CUDA_VISIBLE_DEVICES=0 ft serve\n',
                'serve.log': 'Parsed arguments:\\nServerArgs(model_path="fixture")\\n',
                'serve_args.txt': 'Parsed arguments:\\n',
                'ENV.txt': '/tmp/wt/python/freetoken/__init__.py 2.0\n' + 'a' * 40 + ' test commit\nCUDA_VISIBLE_DEVICES=0\n',
            }.items():
                (arm / name).write_text(text, encoding='utf-8')
        else:
            (arm / 'SERVE_CMD.txt').write_text('ft serve\n', encoding='utf-8')
            (arm / 'serve.log').write_text('startup attempted\n', encoding='utf-8')
        return round_dir

    def test_inventory_preserves_missing_service_fields_as_gap(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'rounds'; root.mkdir()
            source = Path(raw) / 'source'; source.mkdir()
            (source / 'batch99_E2-R001_python.sh').write_text('fixture\n', encoding='utf-8')
            self.make_round(root, 'E2-R001', with_full_service=False)
            item = module.inspect_round(root, source, 'E2-R001')
        self.assertFalse(item['d04_append_eligible'])
        self.assertEqual(item['d04_required_root_missing'], ['round.json', 'round_history', 'MANIFEST.sha256'])
        self.assertEqual(item['service_start_evidence'][0]['missing_required_files'], ['serve_args.txt', 'ENV.txt'])
        self.assertNotIn('serve', item)
        self.assertEqual(len(item['batch_source_candidates']), 1)
        self.assertEqual(item['failure_evidence'][0]['path'], 'error.json')

    def test_full_service_records_exact_original_hashes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'rounds'; root.mkdir()
            source = Path(raw) / 'source'; source.mkdir()
            round_dir = self.make_round(root, 'E2-R001', with_full_service=True)
            item = module.inspect_round(root, source, 'E2-R001')
            command = round_dir / 'A' / 'SERVE_CMD.txt'
            expected = module.sha256(command)
        arm = item['service_start_evidence'][0]
        self.assertEqual(arm['required_files']['SERVE_CMD.txt']['sha256'], expected)
        self.assertEqual(arm['missing_required_files'], [])
        self.assertTrue(any('Parsed arguments:' in line for line in arm['launch_evidence_lines']))
        self.assertEqual(arm['runtime_identity']['freetoken_path'], '/tmp/wt/python/freetoken/__init__.py')
        self.assertEqual(arm['runtime_identity']['worktree'], '/tmp/wt')
        self.assertEqual(arm['runtime_identity']['commit'], 'a' * 40)

    def test_isolated_real_d04_close_then_failed_harness_append(self):
        module = load_module()
        self.assertEqual(module.sha256(WRITER), module.REVIEWED_D04_WRITER_SHA256)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'rounds'; root.mkdir()
            round_dir = root / 'E2-R001'; round_dir.mkdir()
            (round_dir / 'batch.sh').write_text('#!/bin/sh\n', encoding='utf-8')
            (round_dir / 'round.json').write_text(json.dumps({
                'schema': 'ft_round/v2', 'round_id': 'E2-R001', 'serve': 'none',
                'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [], 'closed_at': '2026-10-04 00:00:00 CST',
            }) + '\n', encoding='utf-8')
            closed = subprocess.run([sys.executable, str(CLOSE), 'E2-R001', '--round-root', str(root)], capture_output=True, text=True)
            self.assertEqual(closed.returncode, 0, closed.stderr)
            appended = subprocess.run([
                sys.executable, str(WRITER), str(round_dir), 'verdict', '--new', 'failed_harness',
                '--reason', 'isolated fixture only', '--evidence', 'error.json', '--by', 'test',
            ], capture_output=True, text=True)
            self.assertEqual(appended.returncode, 0, appended.stderr)
            final = json.loads((round_dir / 'round.json').read_text(encoding='utf-8'))
            self.assertEqual(final['verdict'], 'failed_harness')
            self.assertEqual(final['verdict_history'][-1]['new'], 'failed_harness')
            self.assertTrue((round_dir / 'round_history' / 'round.v002.json').is_file())


if __name__ == '__main__':
    unittest.main()
