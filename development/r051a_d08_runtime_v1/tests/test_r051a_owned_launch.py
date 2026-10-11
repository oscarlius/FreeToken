import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
p=Path(__file__).parents[1]/'r051a_owned_launch.py';s=importlib.util.spec_from_file_location('owned',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_default_prepare(capsys):
 assert m.main([])==0; assert 'E2-R051a-gate-D08' in capsys.readouterr().out; assert set(m.SPECS)=={'D08'}
def test_dispatch(monkeypatch,tmp_path):
 seen=[]; monkeypatch.setattr(m,'controller',lambda c:seen.append(('c',c))); monkeypatch.setattr(m,'child',lambda c,b,r:seen.append(('x',c,b,r)))
 assert m.main(['--run','--card','D08'])==0; assert m.main(['--run','--card','D08','--owned-child','--batch','7','--launch-receipt',str(tmp_path/'r')])==0; assert seen[0]==('c','D08') and seen[1][0:3]==('x','D08',7)
def test_bad_combo_rejected():
 with pytest.raises(SystemExit):m.main(['--card','D08'])
 with pytest.raises(SystemExit):m.main(['--run','--card','D08','--owned-child'])


class Gate:
 def __init__(self, lock, fail=None):
  self.LOCK = lock
  self.fail = fail
  self.calls = []
 def require_closed_round(self, rid, verdict):
  self.calls.append((rid, verdict))
  if self.fail == 'round':
   raise RuntimeError('round unavailable')
 def load_owned_lifecycle(self):
  pytest.fail('admission failure must precede lifecycle/batch allocation')


def test_d08_admission_uses_registered_verdict_classes(monkeypatch, tmp_path):
 gate = Gate(tmp_path / 'gpu.lock')
 monkeypatch.setattr(m, 'require_candidate', lambda card: None)
 monkeypatch.setattr(m, 'require_leaf_review', lambda card: None)
 m.admission(gate, 'D08')
 assert gate.calls == [('E2-R041-gate-D17', 'kept'), ('E2-R051-gate-D08', 'kept'), ('E2-R048a', 'failed_harness')]


def test_d08_cold_gate_can_start_before_t21_and_pause_gate(monkeypatch, tmp_path):
 gate = Gate(tmp_path / 'gpu.lock')
 monkeypatch.setattr(m, 'require_candidate', lambda card: None)
 monkeypatch.setattr(m, 'require_leaf_review', lambda card: None)
 m.admission(gate, 'D08')
 assert gate.calls == [('E2-R041-gate-D17', 'kept'), ('E2-R051-gate-D08', 'kept'), ('E2-R048a', 'failed_harness')]


def test_leaf_review_binds_actual_leaf_sources(monkeypatch, tmp_path):
 review = tmp_path / 'review.json'
 monkeypatch.setattr(m, 'review_path', lambda card: review)
 monkeypatch.setattr(m, 'source_hashes', lambda card: {'launcher.py': 'a' * 64, 'adapter.py': 'b' * 64})
 dry_run = tmp_path / 'dryrun.json'; dry_run.write_text('{}')
 monkeypatch.setattr(m, 'require_file_dry_run', lambda card: dry_run)
 value = {'schema': 'ft_t16_leaf_startup_review/v1', 'rid': 'E2-R051a-gate-D08', 'card': 'D08',
          'candidate_commit': m.SPECS['D08'][1], 'parent_commit': m.PARENT_COMMIT,
          'verdict': 'PASS', 'approved': True, 'source_sha256': m.source_hashes('D08'),
          'file_dry_run_sha256': __import__('hashlib').sha256(dry_run.read_bytes()).hexdigest()}
 review.write_text(json.dumps(value), encoding='utf-8'); review.chmod(0o444)
 try:
  assert m.require_leaf_review('D08') == review
  review.chmod(0o644); value['source_sha256']['adapter.py'] = '0' * 64
  review.write_text(json.dumps(value), encoding='utf-8'); review.chmod(0o444)
  with pytest.raises(RuntimeError, match='binding differs'):
   m.require_leaf_review('D08')
 finally:
  review.chmod(0o644)


@pytest.mark.parametrize('failure', ['round', 'candidate', 'review', 'foreign_lock'])
def test_rejected_admission_never_allocates_batch(monkeypatch, tmp_path, failure):
 gate = Gate(tmp_path / 'gpu.lock', 'round' if failure == 'round' else None)
 if failure == 'foreign_lock':
  gate.LOCK.write_text('foreign')
 if failure == 'candidate':
  monkeypatch.setattr(m, 'require_candidate', lambda card: (_ for _ in ()).throw(RuntimeError('bad candidate')))
 else:
  monkeypatch.setattr(m, 'require_candidate', lambda card: None)
 if failure == 'review':
  monkeypatch.setattr(m, 'require_leaf_review', lambda card: (_ for _ in ()).throw(RuntimeError('bad review')))
 else:
  monkeypatch.setattr(m, 'require_leaf_review', lambda card: None)
 monkeypatch.setattr(m, 'd07', lambda: gate)
 monkeypatch.setattr(m.sys, 'platform', 'linux')
 with pytest.raises(RuntimeError):
  m.controller('D08')


def receipt(gate, path, *, state='reserved', child=None, batch_pid=None, commit=None):
 document = {'schema': 'ft_t16_owned_launch/v1', 'state': state, 'rid': 'E2-R051a-gate-D08',
             'batch': 7, 'candidate_commit': commit or m.SPECS['D08'][1],
             'argv_sha256': gate.argv_sha256(m.argv('D08', 7, path))}
 if child is not None:
  document['child'] = child
 if batch_pid is not None:
  document['batch_pid'] = batch_pid
 path.write_text(json.dumps(document), encoding='utf-8')
 return document


def test_receipt_waits_for_reserved_to_launched(monkeypatch, tmp_path):
 path, mine = tmp_path / 'launch.json', {'pid': 91, 'start_ticks': 42, 'execution_id': '91:42'}
 gate = SimpleNamespace(process_birth=lambda: mine, argv_sha256=lambda argv: 'argv')
 reserved = receipt(gate, path)
 def publish(_):
  receipt(gate, path, state='launched', child=mine, batch_pid=91)
 monkeypatch.setattr(m.time, 'sleep', publish)
 assert m.require_receipt(gate, 'D08', 7, path)['state'] == 'launched'
 assert json.loads(path.read_text()) != reserved


def test_receipt_timeout_and_wrong_identity_do_not_wait(monkeypatch, tmp_path):
 path, mine = tmp_path / 'launch.json', {'pid': 91, 'start_ticks': 42, 'execution_id': '91:42'}
 gate = SimpleNamespace(process_birth=lambda: mine, argv_sha256=lambda argv: 'argv')
 receipt(gate, path)
 clock = [0]
 monkeypatch.setattr(m, 'RECEIPT_WAIT_SECONDS', .1)
 monkeypatch.setattr(m.time, 'monotonic', lambda: clock.pop(0) if clock else 1)
 monkeypatch.setattr(m.time, 'sleep', lambda _: None)
 with pytest.raises(RuntimeError, match='did not reach'):
  m.require_receipt(gate, 'D08', 7, path)
 receipt(gate, path, state='launched', child={**mine, 'pid': 92}, batch_pid=92)
 monkeypatch.setattr(m.time, 'sleep', lambda _: pytest.fail('wrong identity must not wait'))
 with pytest.raises(RuntimeError, match='binding differs'):
  m.require_receipt(gate, 'D08', 7, path)


def prepare_real_adapter(monkeypatch, tmp_path, arms, *, card="D08", stop_error=False):
 adapter = m.adapter_module(m.SPECS[card][2])
 monkeypatch.setattr(adapter, 'ROOT', tmp_path / 'source')
 monkeypatch.setattr(adapter, 'ROUNDS', tmp_path)
 monkeypatch.setattr(adapter, 'WRAPPERS', tmp_path)
 monkeypatch.setitem(adapter.base, 'ROOT', tmp_path / 'source')
 monkeypatch.setitem(adapter.base, 'ROUNDS', tmp_path)
 monkeypatch.setattr(adapter.base['runpy'], 'run_path', lambda _: {'parse': lambda _: {}})
 monkeypatch.setitem(adapter.base, 'has_d02_prefill_tail', lambda *_: True)
 monkeypatch.setitem(adapter.base, 'TOOL_MD5', {})
 monkeypatch.setitem(adapter.base, 'command', lambda argv, **_: adapter.CASES[card]['parent_commit'] if argv[0] == 'git' else '')
 monkeypatch.setattr(adapter.CandidateRunner, 'gate', lambda *_: None)
 if card == 'D08': monkeypatch.setattr(adapter, 'require_native_provenance', lambda: None)
 def extensions(_self, wt):
  role = 'parent' if wt.name == adapter.CASES[card]['parent_wt'] else 'new'
  records = {}
  for name, sha in adapter.EXTENSION_SHA256[role].items():
   path = wt / 'python/freetoken/kernel' / (name + '.cpython-310-x86_64-linux-gnu.so')
   path.parent.mkdir(parents=True, exist_ok=True)
   path.write_bytes(b'fixture')
   records[name] = {'sha256': sha, 'path': str(path), 'size': adapter.EXTENSION_SIZE[role][name]}
  return records
 monkeypatch.setattr(adapter.CandidateRunner, 'compiled_extensions', extensions)
 monkeypatch.setattr(adapter.CandidateRunner, 'run_arm', lambda self, name, *_args, **_kwargs: arms.append(name) or self.directory / name)
 monkeypatch.setattr(adapter.CandidateRunner, 'compare', lambda *_args, **_kwargs: {'bitwise': True})
 monkeypatch.setattr(adapter.CandidateRunner, 'stop',
                     (lambda self: (_ for _ in ()).throw(RuntimeError('cleanup failed'))) if stop_error else (lambda self: None))
 (tmp_path / f'batch7_{m.SPECS[card][0]}_python.sh').write_text('owned wrapper')
 return adapter


@pytest.mark.parametrize("card", ["D08"])
def test_child_uses_real_adapter_execute_for_four_arms(monkeypatch, tmp_path, card):
 arms, released = [], []
 adapter = prepare_real_adapter(monkeypatch, tmp_path, arms, card=card)
 lifecycle = SimpleNamespace(owned_group_alive=lambda _: False)
 gate = SimpleNamespace(load_owned_lifecycle=lambda: lifecycle,
                        take_d07_gpu_lock=lambda *args: {'owner': args, 'lock_token':'fixture', 'lock_inode':42},
                        release_d07_gpu_lock=lambda owner: released.append(owner))
 monkeypatch.setattr(m, 'd07', lambda: gate)
 monkeypatch.setattr(m, 'admission', lambda *_: None)
 monkeypatch.setattr(m, 'require_receipt', lambda *_: None)
 monkeypatch.setattr(m, 'adapter_module', lambda _: adapter)
 monkeypatch.setattr(m.sys, 'platform', 'linux')
 result = m.child(card, 7, tmp_path / 'launch.json')
 assert len(arms) == 4 and result['verdict'] == 'pending_review' and len(released) == 1


def test_child_cleanup_failure_keeps_outer_lock(monkeypatch, tmp_path):
 arms, released = [], []
 adapter = prepare_real_adapter(monkeypatch, tmp_path, arms, card='D08', stop_error=True)
 gate = SimpleNamespace(load_owned_lifecycle=lambda: SimpleNamespace(owned_group_alive=lambda _: False),
                        take_d07_gpu_lock=lambda *args: {'owner': args, 'lock_token':'fixture', 'lock_inode':42},
                        release_d07_gpu_lock=lambda owner: released.append(owner))
 monkeypatch.setattr(m, 'd07', lambda: gate)
 monkeypatch.setattr(m, 'admission', lambda *_: None)
 monkeypatch.setattr(m, 'require_receipt', lambda *_: None)
 monkeypatch.setattr(m, 'adapter_module', lambda _: adapter)
 monkeypatch.setattr(m.sys, 'platform', 'linux')
 with pytest.raises(RuntimeError, match='cleanup failed'):
  m.child('D08', 7, tmp_path / 'launch.json')
 assert released == []


def test_file_dry_run_uses_real_four_arm_writers_and_never_launches(monkeypatch, tmp_path):
 adapter = m.adapter_module(m.SPECS['D08'][2])
 monkeypatch.setattr(adapter, 'ROOT', tmp_path / 'sources')
 monkeypatch.setitem(adapter.base, 'ROOT', tmp_path / 'sources')
 monkeypatch.setitem(adapter.base, 'ROUNDS', tmp_path)
 monkeypatch.setitem(adapter.base, 'has_d02_prefill_tail', lambda *_: True)
 monkeypatch.setitem(adapter.base, 'TOOL_MD5', {})
 monkeypatch.setitem(adapter.base, 'command', lambda argv, **_: adapter.CASES['D08']['parent_commit'] if argv[0] == 'git' else 'metadata')
 monkeypatch.setattr(adapter.CandidateRunner, 'gate', lambda *_: 'source fixture')
 monkeypatch.setattr(adapter, 'require_native_provenance', lambda: None)
 monkeypatch.setattr(adapter, 'validate_extensions', lambda *_: None)
 monkeypatch.setattr(adapter.CandidateRunner, 'compiled_extensions', lambda *_: {'cpu': {'sha256': 'same'}})
 monkeypatch.setattr(adapter.base['subprocess'], 'Popen', lambda *_a, **_k: pytest.fail('dry run launched a subprocess/service'))
 wrapper = tmp_path / 'wrapper.sh'; wrapper.write_text('frozen CPU wrapper'); wrapper.chmod(0o444)
 options = SimpleNamespace(case='D08', rid=m.SPECS['D08'][0], batch=1,
     candidate_commit=m.SPECS['D08'][1], run=True, gate=None,
     file_dry_run=True, dry_run_wrapper=str(wrapper))
 runner = adapter.CandidateRunner(options)
 runner.directory = tmp_path / '.dryrun_gate' / 'round'
 runner.directory.parent.mkdir(); runner.status = runner.directory / 'status.json'
 monkeypatch.setattr(runner, 'lock_take', lambda: pytest.fail('dry run took a GPU lock'))
 runner.execute()
 assert not (tmp_path / m.SPECS['D08'][0]).exists()
 assert runner.proc is None and runner.token is None
 complete = json.loads((runner.directory / 'file_dry_run_complete.json').read_text())
 assert len(complete['arms']) == 4 and complete['service_started'] is False
 for arm in complete['arms']:
  path = runner.directory / arm
  assert (path / 'ENV.txt').is_file() and (path / 'SERVE_CMD.txt').is_file()
  command = (path / 'SERVE_CMD.txt').read_text()
  assert '--kv-reserve-tokens 98304' in command and '--max-seq-len-override 98304' in command
  assert '--moe-strategy offload' in command and '--prefill-layer-major' in command
  assert '49152' not in command and 'FT_DEV_HYB_TRACE' not in command
  assert 'CPU FILE WRITABILITY PROBE ONLY' in (path / 'serve.log').read_text()
  assert 'append verified' in (path / 'det.json').read_text()
  assert json.loads((path / 'file_dry_run.json').read_text())['requests_sent'] is False
 assert (runner.directory / 'batch.sh').read_bytes() == wrapper.read_bytes()
 wrapper.chmod(0o644)


@pytest.mark.parametrize('drift', [None, 'source', 'script', 'uid', 'service', 'writable', 'cwd', 'user', 'worktree', 'formal'])
def test_real_path_dry_run_receipt_rejects_drift(monkeypatch, tmp_path, drift):
 path = tmp_path / 'dryrun.json'
 monkeypatch.setattr(m, 'dry_run_receipt_path', lambda _: path)
 monkeypatch.setattr(m, 'ROOT', Path.cwd())
 monkeypatch.setattr(m, 'source_hashes', lambda _: {'source.py': 'a' * 64})
 monkeypatch.setattr(m.os, 'getuid', lambda: 1000, raising=False)
 doc = {'schema': 'ft_t16_real_path_dry_run/v1', 'rid': m.SPECS['D08'][0],
        'candidate_commit': m.SPECS['D08'][1], 'parent_commit': m.PARENT_COMMIT,
        'source_sha256': m.source_hashes('D08'), 'script': str(Path(m.__file__).resolve()),
        'uid': 1000, 'passed': True, 'batch_allocated': False, 'gpu_lock_taken': False,
        'service_started': False, 'requests_sent': False,
        'user': __import__('getpass').getuser(), 'cwd': str(m.ROOT),
        'candidate_worktree': str(m.ROOT / 'wt/e2d08-capture-trace'), 'formal_round_created': False}
 if drift == 'source': doc['source_sha256'] = {}
 elif drift == 'script': doc['script'] = '/different/source.py'
 elif drift == 'uid': doc['uid'] = 1001
 elif drift == 'service': doc['service_started'] = True
 elif drift == 'cwd': doc['cwd'] = '/tmp/wrong'
 elif drift == 'user': doc['user'] = 'foreign'
 elif drift == 'worktree': doc['candidate_worktree'] = '/wrong'
 elif drift == 'formal': doc['formal_round_created'] = True
 path.write_text(json.dumps(doc)); path.chmod(0o644 if drift == 'writable' else 0o444)
 try:
  if drift is None: assert m.require_file_dry_run('D08') == path
  else:
   with pytest.raises(RuntimeError, match='dry-run receipt'): m.require_file_dry_run('D08')
 finally: path.chmod(0o644)
