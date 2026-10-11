import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'development' / 'p0_failed_harness_close.py'
CLOSE = ROOT / 'scripts' / 'round_close.py'
WRITER = ROOT / 'scripts' / 'round_json_append.py'
ROUND_IDS = ('E2-R001', 'E2-R004', 'E2-R005', 'E2-R012', 'E2-R014', 'E2-R015', 'E2-R016')


def load_tool():
    spec = importlib.util.spec_from_file_location('p0_failed_harness_close', TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FailedHarnessCloseTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        rounds = root / 'rounds'; sources = root / 'sources'
        rounds.mkdir(); sources.mkdir()
        for index, rid in enumerate(ROUND_IDS, 1):
            directory = rounds / rid; arm = directory / 'A'; arm.mkdir(parents=True)
            (directory / f'status_batch{index}.json').write_text(json.dumps({
                'rid': rid, 'state': 'failed', 'error': f'ValueError({rid!r})', 'batch': index, 'batch_pid': 1000 + index,
            }), encoding='utf-8')
            (sources / f'batch{index}_{rid}_python.sh').write_text(f'#!/bin/sh\n# {rid}\n', encoding='utf-8')
            for name, value in {
                'SERVE_CMD.txt': 'env PYTHONPATH=/tmp/wt/python ft serve\n',
                'serve.log': 'Parsed arguments:\n',
                'ENV.txt': '/tmp/wt/python/freetoken/__init__.py 2.0\n' + 'a' * 40 + '\n',
            }.items():
                (arm / name).write_text(value, encoding='utf-8')
            if rid != 'E2-R012':
                (arm / 'serve_args.txt').write_text("ServerArgs(_unique_suffix='.pid=999999')\n", encoding='utf-8')
            else:
                (arm / 'owned_process.json').write_text('{"pid": 999999, "pgid": 999999, "session": 999999}\n', encoding='utf-8')
        return rounds, sources

    def command(self, rounds: Path, sources: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(TOOL), '--rounds-root', str(rounds), '--batch-source-root', str(sources), '--out', str(out), *extra], text=True, capture_output=True)

    def test_default_preview_writes_only_requested_preview(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); rounds, sources = self.fixture(root)
            before = {path: digest(path) for path in rounds.rglob('*') if path.is_file()}
            out = root / 'preview.json'
            result = self.command(rounds, sources, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            after = {path: digest(path) for path in rounds.rglob('*') if path.is_file()}
            self.assertEqual(after, before)
            report = json.loads(out.read_text())
            self.assertEqual(report['mode'], 'readonly_preview')
            r012 = next(item for item in report['rounds'] if item['round_id'] == 'E2-R012')
            self.assertEqual(r012['arms'][0]['missing_required_files'], ['serve_args.txt'])
            self.assertTrue(r012['arms'][0]['availability_record']['actual_dump_emitted'] is False)
            self.assertNotIn('serve:none', json.dumps(report))

    def test_isolated_close_appends_all_and_preserves_r012_missing_args(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); rounds, sources = self.fixture(root)
            before = {path: digest(path) for path in rounds.rglob('*') if path.is_file()}
            stage = root / 'stage'; out = root / 'close.json'
            result = self.command(rounds, sources, out, '--close', '--output-root', str(stage), '--d04-close-script', str(CLOSE), '--d04-writer', str(WRITER))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path: digest(path) for path in rounds.rglob('*') if path.is_file()}, before)
            report = json.loads(out.read_text())
            closed = {item['round_id']: item['closed'] for item in report['close_results']}
            self.assertTrue(all(closed.values()))
            self.assertTrue(all(item['source_sha256_pre_and_post_equal'] for item in report['source_copy_verification']))
            for rid in ROUND_IDS:
                staged = stage / rid
                self.assertEqual(digest(sources / f'batch{ROUND_IDS.index(rid)+1}_{rid}_python.sh'), digest(staged / 'batch.sh'))
            r012 = stage / 'E2-R012'
            self.assertFalse((r012 / 'A' / 'serve_args.txt').exists())
            availability = json.loads((r012 / 'A' / 'runtime_args_availability.json').read_text())
            self.assertFalse(availability['actual_dump_emitted'])
            r012_metadata = json.loads((r012 / 'round.json').read_text())
            self.assertEqual(r012_metadata['verdict'], 'failed_harness')
            self.assertTrue((r012 / 'round_history' / 'round.v002.json').is_file())
            missing = r012_metadata['failure_archive']['missing_serve_args'][0]
            self.assertEqual(missing['arm'], 'A')
            self.assertEqual([item['path'] for item in missing['evidence']], ['A/SERVE_CMD.txt', 'A/serve.log', 'status_batch4.json'])
            r001 = json.loads((stage / 'E2-R001' / 'round.json').read_text())
            self.assertEqual(r001['verdict'], 'failed_harness')
            self.assertTrue((stage / 'E2-R001' / 'round_history' / 'round.v002.json').is_file())

    def test_new_closer_rejects_r012_missing_environment_without_pass(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); rounds, sources = self.fixture(root)
            module = load_tool()
            stage = root / 'stage'; stage.mkdir()
            prepared = module.copy_checked(rounds / 'E2-R012', stage, sources)
            target = prepared['target']
            (target / 'A' / 'ENV.txt').unlink()
            result = subprocess.run([sys.executable, str(CLOSE), 'E2-R012', '--round-root', str(stage)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ENV.txt', result.stderr)
            self.assertFalse((target / 'round_history').exists())
            self.assertEqual(json.loads((target / 'round.json').read_text())['verdict'], 'pending_review')

    def test_close_requires_distinct_output_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); rounds, sources = self.fixture(root)
            result = self.command(rounds, sources, root / 'x.json', '--close', '--output-root', str(rounds))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('distinct --output-root', result.stderr)


if __name__ == '__main__':
    unittest.main()
