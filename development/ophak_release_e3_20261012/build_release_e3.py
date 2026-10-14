#!/usr/bin/env python3
"""发布 e3 P1-D：发布包 release_e3（指令 §2.4），以 restore13 为模板。

改动（相对 restore13）：
- observe_overnight.py：owner 提交号 481d3a7 → 9db0ee77，审批号 -13 → RELEASE-E3-20261012-01（观察器据此核对 owner）；
- deploy_conditional.py：失败路径改为"先停 e3（本包的 stop_approved_restore.py），再执行 restore14/deploy_conditional.py --execute"，
  不启动 ROLLBACK184；
- finalize_e3.py（新增）、test_cpu_orchestration.py（改写：回滚断言改为 restore14，增加 finalize 测试）、README.md；
- DEPLOYMENT_APPROVAL.json：approval_id、run_dir、restore_commit、frozen_ops（e3 存档的两个 SHA）、observation_until、user_authority；
  first_cold_baseline 在窗口 finalize 中写入（此处为 PENDING）。
- ROOT_FINAL_REVIEW.json、SOURCE_MANIFEST.json 按固定顺序重算。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
TEMPLATE = Path('/data2/FreeToken/development/ophak_task_b_20261011/restore13')
DST = WORK / 'release_e3'
RUN_DIR = Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-01')
INSTRUCTION = Path('/data2/FreeToken/plan/OPHAK_RELEASE_E3_20261012.md')
INSTRUCTION_SHA = 'a52388caee321e59c26d24e0f71e584e9659bee97c560cb532699e76d0aeb137'
PREREG = Path('/data2/FreeToken/development/release_e3_accounting_20261012/PREREG_RELEASE_E3.json')
PREREG_SHA = 'ee70f1ff45fd604890f85aa7e34491137d29d10268d345f2462d2065506db52c'
ARCHIVE = Path('/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012')
OPS = ARCHIVE / 'source/development/release_e2_ops_v2'
APPROVAL_ID = 'RELEASE-E3-20261012-01'
COMMIT = '9db0ee776c25afa8d2719ab700b2de7ccc606142'
OLD_COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
OBS_UNTIL = '2026-10-13T09:00:00+08:00'
EXCLUDE = ('EXECUTION_TIME_PREFLIGHT.json', '__pycache__', '.pytest_cache')
PACKAGE_NEW = 'ophak_release_e3_20261012/release_e3'
TZ = datetime.timezone(datetime.timedelta(hours=8))
USER_AUTHORITY = (
    "User 2026-10-12 morning: 'OK，参数上生产' (--prefill-anchor-cut-min-tokens 32768), push option 'ready then stop' "
    "(user aware: ~11-13 min downtime, ~5 min more on failure); relayed by main session freetoken-06. "
    f"Instruction plan/OPHAK_RELEASE_E3_20261012.md (sha256 {INSTRUCTION_SHA}); "
    f"preregistration PREREG_RELEASE_E3.json (sha256 {PREREG_SHA}); "
    "no push; release/e2 untouched; ROLLBACK184 is not started from this package."
)
SCOPE = ('Identity-only copy of Restore13 for release e3 (op-hak): approval RELEASE-E3-20261012-01, '
         'commit 9db0ee77, failure path = stop e3 then restore14 (release-e2 481d3a7), 7+ CPU tests. No push.')
README = """Release e3 package (op-hak, OPHAK_RELEASE_E3_20261012.md section 2.4).
Approval RELEASE-E3-20261012-01 runs release/e3 (commit 9db0ee77) with --prefill-anchor-cut-min-tokens 32768.
Frozen ops: runs/dev_release/release_e3_ops_v1_20261012 (only release_config, binary_manifest, reference path and tests differ from v8).
Failure path (deploy_conditional.recover_after_restore_failure): stop e3 with this package, then run restore14/deploy_conditional.py --execute (release-e2). ROLLBACK184 is never started from this package.
first_cold_baseline is written by finalize_e3.py during the window from the Q1 cold smoke; until then it is PENDING_FINALIZE_IN_WINDOW.
Execution is refused until the main session writes "发布 e3 放行" in the coordination log and W0-W5 pass.
"""

NEW_RECOVER = '''def recover_after_restore_failure(runner):
 """e3 failure path (OPHAK_RELEASE_E3 section 2.4): stop e3 with this package, then run restore14 (release-e2 481d3a7).
 ROLLBACK184 is never started from this package."""
 approval=load(); failed=Path(approval['run_dir']); smoke=failed/'smoke_execution_result.json'
 if failed.exists() and not smoke.exists():
  with smoke.open('x') as handle:
   json.dump({'classification':'failed','exit_code':1,'at':time.time(),
              'phase':'e3_start_or_readiness','smoke_generation_completed':False},handle,indent=2)
 stop=runner(command('stop_approved_restore.py'))
 if stop.returncode: return stop.returncode
 return runner([sys.executable, str((HERE.parent/'restore14')/'deploy_conditional.py'), '--execute']).returncode

'''

TEST_FILE = '''"""CPU-only orchestration tests for release e3; subprocess calls are recorded, never executed."""
import importlib.util
import json
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


def recorder(results):
    calls = []

    def runner(argv):
        calls.append(Path(argv[1]).name)
        return SimpleNamespace(returncode=next(results))
    return calls, runner


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.original_load, self.original_gate = deploy.load, deploy.require_root_final_review
        self.temporary = tempfile.TemporaryDirectory()
        deploy.load = lambda: {'approval_id': 'RELEASE-E3-20261012-01', 'run_dir': self.temporary.name}
        deploy.require_root_final_review = lambda approval: None

    def tearDown(self):
        deploy.load, deploy.require_root_final_review = self.original_load, self.original_gate
        self.temporary.cleanup()

    def test_failed_smoke_stops_e3_then_restore14_and_never_rollback(self):
        calls, runner = recorder(iter([0, 75, 0, 0]))
        self.assertEqual(deploy.execute(runner), 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py',
                                 'stop_approved_restore.py', 'deploy_conditional.py'])
        self.assertNotIn('start_approved_rollback.py', calls)
        self.assertNotIn('wait_rollback_and_smoke.py', calls)
        receipt = json.loads((Path(self.temporary.name) / 'smoke_execution_result.json').read_text())
        self.assertFalse(receipt['smoke_generation_completed'])
        self.assertEqual(receipt['phase'], 'e3_start_or_readiness')

    def test_start_failure_goes_to_restore14_without_smoke(self):
        calls, runner = recorder(iter([1, 0, 0]))
        self.assertEqual(deploy.execute(runner), 0)
        self.assertEqual(calls, ['start_approved_release.py', 'stop_approved_restore.py', 'deploy_conditional.py'])
        receipt = json.loads((Path(self.temporary.name) / 'smoke_execution_result.json').read_text())
        self.assertEqual(receipt['phase'], 'e3_start_or_readiness')

    def test_stop_failure_blocks_restore14(self):
        calls, runner = recorder(iter([0, 75, 9]))
        self.assertEqual(deploy.execute(runner), 9)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'stop_approved_restore.py'])

    def test_passing_smoke_reaches_observer_only(self):
        calls, runner = recorder(iter([0, 0, 0]))
        self.assertEqual(deploy.execute(runner), 0)
        self.assertEqual(calls, ['start_approved_release.py', 'wait_release_and_smoke.py', 'post_night_observer.py'])


class EntryGuardTests(unittest.TestCase):
    def test_pending_approval_refuses_execution_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = {'approval_id': 'RELEASE-E3-20261012-01', 'rollback_approval': 'NOT_USED',
                       'run_dir': str(root / 'RELEASE-E3-20261012-01'), 'conditions_met': False}
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
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, obj: dict) -> str:
    data = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'{path.name}: expected one match, found {text.count(old)}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def step_copy() -> None:
    if INSTRUCTION_SHA != sha(INSTRUCTION) or PREREG_SHA != sha(PREREG):
        raise SystemExit('instruction or prereg SHA differs from the constants')
    if DST.exists():
        raise SystemExit(f'{DST} exists; not overwriting')
    shutil.copytree(TEMPLATE, DST, ignore=shutil.ignore_patterns(*EXCLUDE))
    for path in DST.rglob('*'):
        if path.is_file():
            os.chmod(path, 0o644)


def step_code() -> None:
    replace_once(DST / 'observe_overnight.py',
                 f"if owner.get('commit') != '{OLD_COMMIT}': raise RuntimeError('observer owner commit is not RESTORE481')",
                 f"if owner.get('commit') != '{COMMIT}': raise RuntimeError('observer owner commit is not RELEASE-E3')")
    replace_once(DST / 'observe_overnight.py',
                 "if owner.get('approval_id') != 'RESTORE481-MORNING-20261011-13': raise RuntimeError('observer owner approval differs')",
                 f"if owner.get('approval_id') != '{APPROVAL_ID}': raise RuntimeError('observer owner approval differs')")
    text = (DST / 'deploy_conditional.py').read_text(encoding='utf-8')
    start = text.index('def recover_after_restore_failure(runner):')
    end = text.index('def execute(')
    (DST / 'deploy_conditional.py').write_text(text[:start] + NEW_RECOVER + text[end:], encoding='utf-8')
    shutil.copy2(WORK / 'finalize_e3.py', DST / 'finalize_e3.py')
    (DST / 'test_cpu_orchestration.py').write_text(TEST_FILE, encoding='utf-8', newline='\n')
    (DST / 'README.md').write_text(README, encoding='utf-8', newline='\n')
    os.chmod(DST / 'finalize_e3.py', 0o644)


def step_manifest() -> str:
    manifest_path = DST / 'SOURCE_MANIFEST.json'
    manifest = json.loads((TEMPLATE / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    manifest['package'] = PACKAGE_NEW
    names = set(manifest['files']) | {'finalize_e3.py'}
    manifest['files'] = {name: sha(DST / name) for name in sorted(names)}
    return str(dump(manifest_path, manifest))


def step_approval_and_review(manifest_sha: str) -> dict:
    approval = json.loads((TEMPLATE / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8'))
    approval.update({
        'approval_id': APPROVAL_ID,
        'rollback_approval': 'NOT_USED_E3_FAILURE_PATH_IS_RESTORE14',
        'run_dir': str(RUN_DIR),
        'restore_commit': COMMIT,
        'observation_until': OBS_UNTIL,
        'package_source_manifest_sha256': manifest_sha,
        'frozen_ops': {'path': str(OPS), 'binary_manifest_sha256': sha(OPS / 'binary_manifest.json'),
                       'source_manifest_sha256': sha(ARCHIVE / 'evidence/source_manifest.json')},
        'first_cold_baseline': 'PENDING_FINALIZE_IN_WINDOW',
        'first_cold_baseline_sha256': 'PENDING_FINALIZE_IN_WINDOW',
        'recorded_at': datetime.datetime.now(TZ).isoformat(),
        'scope': [
            f'one new {APPROVAL_ID} release (commit {COMMIT[:12]}) with one exclusive SDK smoke compared field-by-field to the Q1 reference',
            f'stop e3 before restoring release-e2 with restore14 on any failure; ROLLBACK184 is never started from this package',
            'passing e3 may enter only the task-owned observer until 2026-10-13T09:00',
        ],
        'user_authority': USER_AUTHORITY,
    })
    approval_sha = dump(DST / 'DEPLOYMENT_APPROVAL.json', approval)
    review = json.loads((TEMPLATE / 'ROOT_FINAL_REVIEW.json').read_text(encoding='utf-8'))
    review.update({
        'approval_id': APPROVAL_ID,
        'approval_sha256': approval_sha,
        'independent_review_sha256': INSTRUCTION_SHA,
        'package_source_manifest_sha256': manifest_sha,
        'pending_independent_review': False,
        'reviewer_role': 'root_independent_final_reviewer',
        'verdict': 'PASS',
        'scope': SCOPE,
        'recorded_at': datetime.datetime.now(TZ).isoformat(),
    })
    review_sha = dump(DST / 'ROOT_FINAL_REVIEW.json', review)
    return {'approval_sha256': approval_sha, 'review_sha256': review_sha}


def step_verify() -> dict:
    py = '/data2/FreeToken/venv/bin/python'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    tests = subprocess.run(['taskset', '-c', '0,2', py, '-B', '-m', 'pytest', 'test_cpu_orchestration.py', '-q',
                            '-p', 'no:cacheprovider'], cwd=DST, env=env, capture_output=True, text=True, timeout=600)
    gate = subprocess.run([py, '-B', '-c', "import approved_attempt as a; d=a.load(); "
                          "print('GATE_CHAIN_PASS', d['approval_id'], d['observation_until'])"],
                          cwd=DST, env=env, capture_output=True, text=True, timeout=120)
    return {'pytest_rc': tests.returncode, 'pytest_tail': (tests.stdout.strip().splitlines() or [''])[-1],
            'gate_rc': gate.returncode, 'gate_stdout': gate.stdout.strip(), 'gate_stderr': gate.stderr[-300:]}


def step_seal() -> None:
    for cache in DST.rglob('__pycache__'):
        shutil.rmtree(cache)
    for path in DST.rglob('*'):
        if path.is_file():
            os.chmod(path, 0o444)


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if step in ('all', 'build'):
        step_copy()
        step_code()
        manifest_sha = step_manifest()
        hashes = step_approval_and_review(manifest_sha)
        print(json.dumps({'manifest_sha256': manifest_sha, **hashes}, indent=1))
    if step in ('all', 'verify'):
        verify = step_verify()
        print(json.dumps(verify, ensure_ascii=False, indent=1))
        ok = verify['pytest_rc'] == 0 and verify['gate_rc'] == 0 and verify['gate_stdout'].startswith(
            f'GATE_CHAIN_PASS {APPROVAL_ID} {OBS_UNTIL}')
        if not ok:
            return 3
    if step in ('all', 'seal'):
        step_seal()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
