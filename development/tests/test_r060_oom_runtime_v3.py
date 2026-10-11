import importlib.util
from pathlib import Path


DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('r060a',DEV/'r060_oom_owned_launch_v3.py');m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m

def test_outer_owner_executes_real_method_and_never_reopens_lock(tmp_path):
 m=load(); calls=[];lock=tmp_path/'gpu.lock';lock.write_text('token')
 class Runner:
  proc=None
  def lock_take(self): raise AssertionError('base lock_take must be replaced')
  def lock_release(self): raise AssertionError('base lock_release must be replaced')
  def execute(self): self.lock_take(); self.lock_release(); calls.append('execute'); return 'done'
 class D: LOCK=lock
 owner={'lock_inode':lock.stat().st_ino,'lock_token':'token'}
 assert m.run_owned_runner(Runner(),owner,D())=='done'
 assert calls==['execute'] and lock.exists()
