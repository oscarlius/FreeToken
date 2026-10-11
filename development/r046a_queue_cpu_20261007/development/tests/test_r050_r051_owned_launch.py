import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
p=Path(__file__).parents[1]/'r050_r051_owned_launch.py';s=importlib.util.spec_from_file_location('owned',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_default_prepare(capsys):
 assert m.main([])==0; assert 'E2-R050-gate-D15' in capsys.readouterr().out
def test_dispatch(monkeypatch,tmp_path):
 seen=[]; monkeypatch.setattr(m,'controller',lambda c:seen.append(('c',c))); monkeypatch.setattr(m,'child',lambda c,b,r:seen.append(('x',c,b,r)))
 assert m.main(['--run','--card','D15'])==0; assert m.main(['--run','--card','D08','--owned-child','--batch','7','--launch-receipt',str(tmp_path/'r')])==0; assert seen[0]==('c','D15') and seen[1][0:3]==('x','D08',7)
def test_bad_combo_rejected():
 with pytest.raises(SystemExit):m.main(['--card','D15'])
 with pytest.raises(SystemExit):m.main(['--run','--card','D15','--owned-child'])


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


def test_d15_admission_uses_registered_verdict_classes(monkeypatch, tmp_path):
 gate = Gate(tmp_path / 'gpu.lock')
 monkeypatch.setattr(m, 'require_candidate', lambda card: None)
 monkeypatch.setattr(m, 'require_leaf_review', lambda card: None)
 m.admission(gate, 'D15')
 assert gate.calls == [('E2-R055-gate-D06', 'kept'), ('E2-R041-gate-D17', 'kept')]


def test_d08_admission_requires_t21_measured(monkeypatch, tmp_path):
 gate = Gate(tmp_path / 'gpu.lock')
 monkeypatch.setattr(m, 'require_candidate', lambda card: None)
 monkeypatch.setattr(m, 'require_leaf_review', lambda card: None)
 m.admission(gate, 'D08')
 assert gate.calls == [('E2-R049', 'measured'), ('E2-R041-gate-D17', 'kept')]


def test_leaf_review_binds_actual_leaf_sources(monkeypatch, tmp_path):
 review = tmp_path / 'review.json'
 monkeypatch.setattr(m, 'review_path', lambda card: review)
 monkeypatch.setattr(m, 'source_hashes', lambda card: {'launcher.py': 'a' * 64, 'adapter.py': 'b' * 64})
 value = {'schema': 'ft_t16_leaf_startup_review/v1', 'rid': 'E2-R050-gate-D15', 'card': 'D15',
          'candidate_commit': m.SPECS['D15'][1], 'parent_commit': m.PARENT_COMMIT,
          'verdict': 'PASS', 'approved': True, 'source_sha256': m.source_hashes('D15')}
 review.write_text(json.dumps(value), encoding='utf-8'); review.chmod(0o444)
 try:
  assert m.require_leaf_review('D15') == review
  review.chmod(0o644); value['source_sha256']['adapter.py'] = '0' * 64
  review.write_text(json.dumps(value), encoding='utf-8'); review.chmod(0o444)
  with pytest.raises(RuntimeError, match='binding differs'):
   m.require_leaf_review('D15')
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
  m.controller('D15')


def receipt(gate, path, *, state='reserved', child=None, batch_pid=None, commit=None):
 document = {'schema': 'ft_t16_owned_launch/v1', 'state': state, 'rid': 'E2-R050-gate-D15',
             'batch': 7, 'candidate_commit': commit or m.SPECS['D15'][1],
             'argv_sha256': gate.argv_sha256(m.argv('D15', 7, path))}
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
 assert m.require_receipt(gate, 'D15', 7, path)['state'] == 'launched'
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
  m.require_receipt(gate, 'D15', 7, path)
 receipt(gate, path, state='launched', child={**mine, 'pid': 92}, batch_pid=92)
 monkeypatch.setattr(m.time, 'sleep', lambda _: pytest.fail('wrong identity must not wait'))
 with pytest.raises(RuntimeError, match='binding differs'):
  m.require_receipt(gate, 'D15', 7, path)


def prepare_real_adapter(monkeypatch, tmp_path, arms, *, card="D15", stop_error=False):
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
  if card == 'D15':
   return {'cpu': {'sha256': 'same'}}
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


@pytest.mark.parametrize("card", ["D15", "D08"])
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
 adapter = prepare_real_adapter(monkeypatch, tmp_path, arms, stop_error=True)
 gate = SimpleNamespace(load_owned_lifecycle=lambda: SimpleNamespace(owned_group_alive=lambda _: False),
                        take_d07_gpu_lock=lambda *args: {'owner': args, 'lock_token':'fixture', 'lock_inode':42},
                        release_d07_gpu_lock=lambda owner: released.append(owner))
 monkeypatch.setattr(m, 'd07', lambda: gate)
 monkeypatch.setattr(m, 'admission', lambda *_: None)
 monkeypatch.setattr(m, 'require_receipt', lambda *_: None)
 monkeypatch.setattr(m, 'adapter_module', lambda _: adapter)
 monkeypatch.setattr(m.sys, 'platform', 'linux')
 with pytest.raises(RuntimeError, match='cleanup failed'):
  m.child('D15', 7, tmp_path / 'launch.json')
 assert released == []
