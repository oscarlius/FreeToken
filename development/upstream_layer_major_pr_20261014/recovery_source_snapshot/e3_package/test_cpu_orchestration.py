"""CPU-only orchestration tests for release e3 (OPHAK_RELEASE_E3_ADDENDUM1_20261012.md).

Routing tests run the real stop_approved_restore.py from a re-sealed temporary copy of this package. Only three
things point at temporary locations: the production pointer path, the run directory and the ops directory.
The controller that the stop script calls is a test double: the real release_control.py --stop waits for the
host-wide ports 8095/8096 and GPU compute to be free, and production 481 holds them while these tests run.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('e3_deploy', HERE / 'deploy_conditional.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
spec = importlib.util.spec_from_file_location('e3_finalize', HERE / 'finalize_e3.py')
fin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fin)

APPROVAL_ID = 'RELEASE-E3-20261012-02'
RESTORE_COMMIT = '9db0ee776c25afa8d2719ab700b2de7ccc606142'
OLD_RESTORE_COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
STOP_NAME = 'stop_approved_restore.py'
STOP_ACTIVE_LINE = "active = Path('/data2/FreeToken/run/production.active.json')"
RESTORE14_CALL = 'restore14:deploy_conditional.py'
DAEMON_PID = 4242  # 哑进程的占位 pid：只表示"守护进程存活"，测试中不会向它发信号

FAKE_CONTROLLER = '''#!/usr/bin/env python3
"""Test double for release_control.py --stop (routing tests only). Writes the supervisor's stopped receipt."""
import json
import sys
from pathlib import Path

POINTER = Path(__POINTER__)
FAIL_FLAG = Path(__FAIL__)
args = sys.argv[1:]
if args[:1] != ['--stop']:
    raise SystemExit('test double supports --stop only')
approval = args[args.index('--approval-id') + 1]
state = json.loads(POINTER.read_text(encoding='utf-8'))
if state['approval_id'] != approval:
    raise SystemExit(2)
if FAIL_FLAG.exists():
    raise SystemExit(1)
run = Path(state['run_dir'])
run.mkdir(parents=True, exist_ok=True)
(run / 'stopped.json').write_text(json.dumps({'approval_id': approval, 'resources_released': True}) + '\\n', encoding='utf-8')
POINTER.unlink()
'''


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    os.chmod(path, 0o644)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    return sha_file(path)


def reseal(package):
    """Re-seal a copy in the build order: SOURCE_MANIFEST, then DEPLOYMENT_APPROVAL, then ROOT_FINAL_REVIEW."""
    manifest_path = package / 'SOURCE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for name in manifest['files']:
        manifest['files'][name] = sha_file(package / name)
    manifest_sha = write_json(manifest_path, manifest)
    approval_path = package / 'DEPLOYMENT_APPROVAL.json'
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    approval['package_source_manifest_sha256'] = manifest_sha
    approval_sha = write_json(approval_path, approval)
    review_path = package / 'ROOT_FINAL_REVIEW.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review.update({'approval_id': approval['approval_id'], 'approval_sha256': approval_sha,
                   'package_source_manifest_sha256': manifest_sha})
    write_json(review_path, review)


def make_copy(root, pointer, fail_flag, run_dir, ops_dir):
    """A re-sealed copy of this package. Only the stop script's pointer path, the approval's run_dir and
    frozen_ops.path change; the stop script itself is otherwise byte-identical."""
    package = root / 'pkg'
    shutil.copytree(HERE, package)
    for path in package.iterdir():
        if path.is_file():
            os.chmod(path, 0o644)
    stop = package / STOP_NAME
    text = stop.read_text(encoding='utf-8')
    assert text.count(STOP_ACTIVE_LINE) == 1
    stop.write_text(text.replace(STOP_ACTIVE_LINE, 'active = Path(%r)' % str(pointer)), encoding='utf-8')
    approval = json.loads((package / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8'))
    approval['run_dir'] = str(run_dir)
    approval['frozen_ops']['path'] = str(ops_dir)
    write_json(package / 'DEPLOYMENT_APPROVAL.json', approval)
    ops_dir.mkdir(parents=True)
    controller = FAKE_CONTROLLER.replace('__POINTER__', repr(str(pointer))).replace('__FAIL__', repr(str(fail_flag)))
    (ops_dir / 'release_control.py').write_text(controller, encoding='utf-8')
    reseal(package)
    spec = importlib.util.spec_from_file_location('e3_deploy_copy', package / 'deploy_conditional.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    """Fake monotonic clock. sleep() advances it and tells the scripted host (on_advance)."""

    def __init__(self, on_advance=None):
        self.now = 0.0
        self.on_advance = on_advance

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.on_advance is not None:
            self.on_advance(self.now)


class World:
    """Scripted host state for the probe. Scheduled events run when the fake clock reaches them."""

    def __init__(self, root):
        self.now = 0.0
        self.processes = []
        self.listeners = []
        self.compute = []
        self.memory = [0]
        self.lock = False
        self.pointer_file = root / 'run' / 'production.active.json'
        self.run_dir = root / 'prod' / APPROVAL_ID
        self.events = []
        self.pointer_file.parent.mkdir(parents=True)
        self.run_dir.parent.mkdir(parents=True)

    def at(self, when, action):
        self.events.append((when, action))

    def advance_to(self, when):
        self.now = when
        due = [action for at, action in self.events if at <= when]
        self.events = [(at, action) for at, action in self.events if at > when]
        for action in due:
            action(self)

    def publish_owner(self):
        self._write_pointer(APPROVAL_ID, RESTORE_COMMIT)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / 'owner.json').write_text('{}\n', encoding='utf-8')

    def publish_foreign(self):
        self._write_pointer('RESTORE481-MORNING-20261011-13', OLD_RESTORE_COMMIT)

    def publish_partial(self):
        self._write_pointer(APPROVAL_ID, OLD_RESTORE_COMMIT)

    def _write_pointer(self, approval_id, commit):
        self.pointer_file.write_text(json.dumps({'approval_id': approval_id, 'commit': commit,
                                                 'run_dir': str(self.run_dir), 'mode': 'release'}), encoding='utf-8')

    def snapshot(self, approval):
        exists = self.pointer_file.exists()
        pointer = json.loads(self.pointer_file.read_text(encoding='utf-8')) if exists else None
        return {'pointer_exists': exists, 'pointer': pointer,
                'owner_json': (self.run_dir / 'owner.json').exists(), 'run_dir_exists': self.run_dir.exists(),
                'lock_exists': self.lock, 'cleanup_failed_exists': False,
                'processes': list(self.processes), 'listeners': list(self.listeners),
                'compute_pids': list(self.compute), 'gpu_memory_mib': list(self.memory), 'at': self.now}


def owner_at_25_seconds(world):
    world.processes = [DAEMON_PID]
    world.at(25.0, lambda w: w.publish_owner())


SCENARIOS = {
    'absent_confirmed_twice': (lambda world: None, False),
    'owner_appears_at_25s': (owner_at_25_seconds, False),
    'daemon_alive_no_owner': (lambda world: setattr(world, 'processes', [DAEMON_PID]), False),
    'foreign_pointer': (lambda world: world.publish_foreign(), False),
    'partial_pointer_match': (lambda world: world.publish_partial(), False),
    'stop_fails_after_owner': (lambda world: world.publish_owner(), True),
}


def run_scenario(root, name):
    """Run the real recover() on a re-sealed copy against a scripted host. Returns what happened."""
    setup, stop_fails = SCENARIOS[name]
    world = World(root)
    fail_flag = root / 'stop-fails.flag'
    if stop_fails:
        fail_flag.write_text('the test double must return 1\n', encoding='utf-8')
    setup(world)
    module = make_copy(root, world.pointer_file, fail_flag, world.run_dir, root / 'ops')
    calls = []

    def runner(argv):
        label = ('restore14:' if 'restore14' in str(argv[1]) else '') + Path(argv[1]).name
        calls.append(label)
        if Path(argv[1]).name == STOP_NAME:
            return subprocess.run(argv, capture_output=True, text=True, timeout=120)  # the real stop script
        return SimpleNamespace(returncode=0)

    clock = Clock(on_advance=world.advance_to)
    rc = module.recover_after_restore_failure(runner, probe=world.snapshot, clock=clock, sleep=clock.sleep)
    return {'scenario': name, 'rc': rc, 'calls': calls, 'now': world.now,
            'stopped': (world.run_dir / 'stopped.json').exists(),
            'ambiguous': (world.run_dir / 'ROUTING_AMBIGUOUS.json').exists(),
            'pointer_left': world.pointer_file.exists()}


def clean_snapshot():
    return {'pointer_exists': False, 'pointer': None, 'owner_json': False, 'run_dir_exists': False,
            'lock_exists': False, 'cleanup_failed_exists': False, 'processes': [], 'listeners': [],
            'compute_pids': [], 'gpu_memory_mib': [0], 'at': 0.0}


class Host:
    """Probe for execute() tests: clean until e3 has started, then e3 owns production."""

    def __init__(self, busy=False):
        self.started = False
        self.busy = busy

    def snapshot(self, approval):
        snapshot = clean_snapshot()
        if self.busy:
            snapshot['listeners'] = ['LISTEN 0 2048 172.16.108.9:8095 0.0.0.0:*']
        if self.started:
            snapshot.update(pointer_exists=True, owner_json=True, run_dir_exists=True,
                            pointer={'approval_id': APPROVAL_ID, 'commit': RESTORE_COMMIT,
                                     'run_dir': approval['run_dir']})
        return snapshot


def scripted_runner(host, results, calls):
    queue = list(results)

    def runner(argv):
        label = ('restore14:' if 'restore14' in str(argv[1]) else '') + Path(argv[1]).name
        calls.append(label)
        code = queue.pop(0)
        if Path(argv[1]).name == 'start_approved_release.py' and code == 0:
            host.started = True
        return SimpleNamespace(returncode=code)
    return runner


def e3_approval(root):
    return {'approval_id': APPROVAL_ID, 'restore_commit': RESTORE_COMMIT,
            'run_dir': str(root / 'prod' / APPROVAL_ID), 'conditions_met': True,
            'package_source_manifest_sha256': 'not-used-by-these-tests',
            'frozen_ops': {'path': str(root / 'ops')}}


class RealStopRoutingTests(unittest.TestCase):
    """The real stop script on a re-sealed copy: the three addendum cases plus the stop-failure case."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def run_case(self, name):
        root = self.root / name
        root.mkdir()
        record = run_scenario(root, name)
        self.assertNotIn('rollback', ' '.join(record['calls']).lower())
        return record

    def test_absent_confirmed_twice_starts_restore14_without_stop(self):
        record = self.run_case('absent_confirmed_twice')
        self.assertEqual(record['calls'], [RESTORE14_CALL])
        self.assertEqual(record['rc'], 0)
        self.assertEqual(record['now'], 2.0)

    def test_owner_appearing_at_25_seconds_stops_then_starts_restore14(self):
        record = self.run_case('owner_appears_at_25s')
        self.assertEqual(record['calls'], [STOP_NAME, RESTORE14_CALL])
        self.assertEqual(record['rc'], 0)
        self.assertEqual(record['now'], 26.0)
        self.assertTrue(record['stopped'])
        self.assertFalse(record['pointer_left'])

    def test_daemon_alive_without_owner_is_ambiguous_after_60_seconds(self):
        record = self.run_case('daemon_alive_no_owner')
        self.assertEqual(record['calls'], [])
        self.assertEqual(record['rc'], deploy.AMBIGUOUS_RC)
        self.assertEqual(record['now'], 60.0)
        self.assertTrue(record['ambiguous'])

    def test_foreign_pointer_is_ambiguous_at_once(self):
        record = self.run_case('foreign_pointer')
        self.assertEqual(record['calls'], [])
        self.assertEqual(record['rc'], deploy.AMBIGUOUS_RC)
        self.assertEqual(record['now'], 0.0)
        self.assertTrue(record['ambiguous'])

    def test_partial_pointer_match_is_ambiguous_at_once(self):
        record = self.run_case('partial_pointer_match')
        self.assertEqual(record['calls'], [])
        self.assertEqual(record['rc'], deploy.AMBIGUOUS_RC)
        self.assertEqual(record['now'], 0.0)

    def test_stop_failure_is_ambiguous_and_never_starts_restore14(self):
        record = self.run_case('stop_fails_after_owner')
        self.assertEqual(record['calls'], [STOP_NAME])
        self.assertEqual(record['rc'], deploy.AMBIGUOUS_RC)
        self.assertTrue(record['ambiguous'])
        self.assertFalse(record['stopped'])


class ExecuteRoutingTests(unittest.TestCase):
    """execute() with a recorder runner: smoke failures, start failures and the W3.5 precheck."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'prod').mkdir()
        self.approval = e3_approval(self.root)
        self.patches = [mock.patch.object(deploy, 'load', lambda: self.approval),
                        mock.patch.object(deploy, 'require_root_final_review', lambda approval: None)]
        for patch in self.patches:
            patch.start()
        self.clock = Clock()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.directory.cleanup()

    def test_failed_smoke_stops_e3_then_restore14_and_never_rollback(self):
        host, calls = Host(), []
        (self.root / 'prod' / APPROVAL_ID).mkdir()  # the real start creates the run directory
        runner = scripted_runner(host, [0, 75, 0, 0], calls)
        rc = deploy.execute(runner, probe=host.snapshot, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py',
                                 'stop_approved_restore.py', RESTORE14_CALL])
        self.assertFalse([name for name in calls if 'rollback' in name.lower()])
        receipt = json.loads((self.root / 'prod' / APPROVAL_ID / 'smoke_execution_result.json').read_text())
        self.assertFalse(receipt['smoke_generation_completed'])
        self.assertEqual(receipt['phase'], 'e3_start_or_readiness')

    def test_start_failure_without_owner_goes_to_restore14_without_stop(self):
        host, calls = Host(), []
        (self.root / 'prod' / APPROVAL_ID).mkdir()
        runner = scripted_runner(host, [1, 0], calls)
        rc = deploy.execute(runner, probe=host.snapshot, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ['start_approved_release.py', RESTORE14_CALL])
        receipt = json.loads((self.root / 'prod' / APPROVAL_ID / 'smoke_execution_result.json').read_text())
        self.assertEqual(receipt['phase'], 'e3_start_or_readiness')

    def test_stop_failure_after_smoke_failure_blocks_restore14(self):
        host, calls = Host(), []
        runner = scripted_runner(host, [0, 75, 9], calls)
        rc = deploy.execute(runner, probe=host.snapshot, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(rc, deploy.AMBIGUOUS_RC)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'stop_approved_restore.py'])
        self.assertTrue((self.root / 'prod' / APPROVAL_ID / 'ROUTING_AMBIGUOUS.json').exists())

    def test_passing_smoke_reaches_observer_only(self):
        host, calls = Host(), []
        runner = scripted_runner(host, [0, 0, 0], calls)
        rc = deploy.execute(runner, probe=host.snapshot, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'post_night_observer.py'])

    def test_precheck_failure_starts_no_service_and_no_routing(self):
        host, calls = Host(busy=True), []
        runner = scripted_runner(host, [], calls)
        rc = deploy.execute(runner, probe=host.snapshot, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(rc, deploy.PRECHECK_RC)
        self.assertEqual(calls, [])
        self.assertTrue((self.root / 'prod' / (APPROVAL_ID + '.W35_SNAPSHOT.json')).exists())
        self.assertFalse((self.root / 'prod' / APPROVAL_ID).exists())


class PrecheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'prod').mkdir()
        self.approval = e3_approval(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def test_passes_once_transient_gpu_memory_is_released(self):
        clock = Clock()

        def probe(approval):
            snapshot = clean_snapshot()
            snapshot['gpu_memory_mib'] = [22454] if clock.now < 10 else [0]
            return snapshot

        self.assertEqual(deploy.run_precheck(self.approval, probe=probe, clock=clock, sleep=clock.sleep), 0)
        self.assertEqual(clock.now, 10.0)

    def test_refuses_after_60_seconds_and_writes_snapshot_outside_run_dir(self):
        clock = Clock()
        host = Host(busy=True)
        rc = deploy.run_precheck(self.approval, probe=host.snapshot, clock=clock, sleep=clock.sleep)
        self.assertEqual(rc, deploy.PRECHECK_RC)
        self.assertGreaterEqual(clock.now, 60.0)
        self.assertTrue((self.root / 'prod' / (APPROVAL_ID + '.W35_SNAPSHOT.json')).exists())
        self.assertFalse((self.root / 'prod' / APPROVAL_ID).exists())


class EntryGuardTests(unittest.TestCase):
    def test_pending_approval_refuses_execution_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = {'approval_id': 'RELEASE-E3-20261012-02', 'rollback_approval': 'NOT_USED',
                       'run_dir': str(root / 'RELEASE-E3-20261012-02'), 'conditions_met': False}
            (root / 'DEPLOYMENT_APPROVAL.json').write_text(json.dumps(pending))
            (root / 'ROOT_FINAL_REVIEW.json').write_text(json.dumps({'verdict': 'PENDING'}))
            with mock.patch.object(deploy, 'HERE', root):
                with self.assertRaisesRegex(RuntimeError, 'PENDING root final review'):
                    deploy.execute(lambda argv: (_ for _ in ()).throw(AssertionError('runner must not execute')))

    def test_approval_sha_mismatch_refused_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = {'conditions_met': True}
            (root / 'DEPLOYMENT_APPROVAL.json').write_text(json.dumps(approval))
            (root / 'ROOT_FINAL_REVIEW.json').write_text(json.dumps({'approval_sha256': 'wrong'}))
            with mock.patch.object(deploy, 'HERE', root):
                with self.assertRaisesRegex(RuntimeError, 'approval content differs'):
                    deploy.require_root_final_review(approval)


def q1_prereg():
    return {'q1_cold_smoke': {
        'short': {'backend_cache_rows': [{'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0}],
                  'usage': {'prompt_tokens': 512, 'completion_tokens': 128, 'total_tokens': 640},
                  'finish_reason': 'length'},
        'long': {'backend_cache_rows': [{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}],
                 'usage': {'prompt_tokens': 8257, 'completion_tokens': 128, 'total_tokens': 8385},
                 'finish_reason': 'length', 'sha256_report_only': {'e2': '9845c386' + '0' * 56}}}}


def q1_payload(long_rows, short_sha=None):
    short = {'sha256': short_sha or fin.E2_SHORT_SHA, 'usage': {'prompt_tokens': 512, 'completion_tokens': 128,
             'total_tokens': 640}, 'finish_reason': 'length', 'api_cached_tokens': None,
             'backend_cache_rows': [{'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0}]}
    long = {'sha256': 'c' * 64, 'usage': {'prompt_tokens': 8257, 'completion_tokens': 128, 'total_tokens': 8385},
            'finish_reason': 'length', 'api_cached_tokens': None, 'backend_cache_rows': long_rows}
    return {'schema': 'ft_release_cold_smoke/v1', 'results': {'short': short, 'long': long},
            'mode': 'release', 'window': 98304, 'chunk': 4096, 'running': 2, 'graph': 2}


class FinalizeTests(unittest.TestCase):
    def test_accepts_single_8257_row_and_reports_long_sha_only(self):
        report = fin.validate_q1(q1_payload([{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}]), q1_prereg())
        self.assertEqual(report['long_sha256_report_only'], 'c' * 64)

    def test_refuses_the_e2_split_of_the_long_request(self):
        split = [{'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0},
                 {'new_sequences': 1, 'new_tokens': 7745, 'cached_tokens': 0}]
        with self.assertRaisesRegex(ValueError, 'Q1 核对未通过'):
            fin.validate_q1(q1_payload(split), q1_prereg())

    def test_refuses_short_request_sha_that_differs_from_e2(self):
        with self.assertRaisesRegex(ValueError, 'e2 参考值'):
            fin.validate_q1(q1_payload([{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}],
                                       short_sha='0' * 64), q1_prereg())

    def test_reference_is_written_once_and_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            ref_dir = Path(directory) / 'ref'
            payload = q1_payload([{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}])
            out = fin.write_reference(ref_dir, payload, 'f' * 64)
            reference = json.loads((ref_dir / 'expected_reference.json').read_text())
            self.assertEqual(reference['results']['short']['sha256'], fin.E2_SHORT_SHA)
            self.assertEqual(reference['results']['long']['backend_cache_rows'], [{'new_sequences': 1,
                             'new_tokens': 8257, 'cached_tokens': 0}])
            self.assertTrue(Path(out['cold_baseline']).exists())
            with self.assertRaisesRegex(ValueError, '已存在'):
                fin.write_reference(ref_dir, payload, 'f' * 64)


if __name__ == '__main__':
    unittest.main()
