"""CPU-only orchestration tests; subprocess calls are recorded, never executed."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
import json
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('night_deploy', HERE / 'deploy_conditional.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.original_load, self.original_gate = deploy.load, deploy.require_root_final_review
        self.temporary = tempfile.TemporaryDirectory()
        deploy.load = lambda: {'approval_id': 'RESTORE481-MORNING-20261010-02', 'run_dir': self.temporary.name}
        deploy.require_root_final_review = lambda approval: None
    def tearDown(self):
        deploy.load, deploy.require_root_final_review = self.original_load, self.original_gate
        self.temporary.cleanup()
    def test_failed_smoke_stops_before_rollback(self):
        calls, results = [], iter([0, 75, 0, 0, 0])
        def runner(argv): calls.append(Path(argv[-1]).name); return SimpleNamespace(returncode=next(results))
        self.assertEqual(deploy.execute(runner), 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'stop_approved_restore.py', 'start_approved_rollback.py', 'wait_rollback_and_smoke.py'])
        receipt = json.loads((Path(self.temporary.name) / 'smoke_execution_result.json').read_text())
        self.assertFalse(receipt['smoke_generation_completed'])
    def test_start_failure_records_phase_without_claiming_smoke(self):
        calls, results = [], iter([1, 0, 0, 0])
        def runner(argv): calls.append(Path(argv[-1]).name); return SimpleNamespace(returncode=next(results))
        self.assertEqual(deploy.execute(runner), 0)
        receipt = json.loads((Path(self.temporary.name) / 'smoke_execution_result.json').read_text())
        self.assertEqual(receipt['phase'], 'restore_start_or_readiness')
        self.assertNotIn('wait_release_and_smoke.py', calls)
    def test_stop_failure_blocks_rollback(self):
        calls, results = [], iter([0, 1, 9])
        def runner(argv): calls.append(Path(argv[-1]).name); return SimpleNamespace(returncode=next(results))
        self.assertEqual(deploy.execute(runner), 9)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'stop_approved_restore.py'])
    def test_passing_smoke_reaches_observer_only(self):
        calls, results = [], iter([0, 0, 0])
        def runner(argv): calls.append(Path(argv[-1]).name); return SimpleNamespace(returncode=next(results))
        self.assertEqual(deploy.execute(runner), 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'post_night_observer.py'])

class EntryGuardTests(unittest.TestCase):
    def test_pending_approval_refuses_execution_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = {
                'approval_id': 'RESTORE481-MORNING-20261010-02',
                'rollback_approval': 'ROLLBACK184-MORNING-20261010-02',
                'run_dir': str(root / 'RESTORE481-MORNING-20261010-02'),
                'conditions_met': False,
            }
            (root / 'DEPLOYMENT_APPROVAL.json').write_text(json.dumps(pending))
            (root / 'ROOT_FINAL_REVIEW.json').write_text(json.dumps({'verdict': 'PENDING'}))
            with mock.patch.object(deploy, 'HERE', root):
                with self.assertRaisesRegex(RuntimeError, 'PENDING root final review'):
                    deploy.execute(lambda argv: (_ for _ in ()).throw(AssertionError('runner must not execute')))

    def test_direct_load_refuses_missing_final_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'DEPLOYMENT_APPROVAL.json').write_text(json.dumps({'conditions_met': True}))
            spec = importlib.util.spec_from_file_location('night_approved_guard', HERE / 'approved_attempt.py')
            approved = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(approved)
            approved.__file__ = str(root / 'approved_attempt.py')
            with mock.patch.object(deploy, 'HERE', root), mock.patch.dict('sys.modules', {'deploy_conditional': deploy}), mock.patch('sys.argv', ['script']):
                with self.assertRaisesRegex(RuntimeError, 'PENDING root final review'):
                    approved.load()

    def test_approval_sha_mismatch_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = {'conditions_met': True}
            (root / 'DEPLOYMENT_APPROVAL.json').write_text(json.dumps(approval))
            (root / 'ROOT_FINAL_REVIEW.json').write_text(json.dumps({'approval_sha256': 'wrong'}))
            with mock.patch.object(deploy, 'HERE', root):
                with self.assertRaisesRegex(RuntimeError, 'approval content differs'):
                    deploy.require_root_final_review(approval)

if __name__ == '__main__': unittest.main()
