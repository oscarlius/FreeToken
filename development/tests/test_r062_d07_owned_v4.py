"""Actual R062 entry and retained child lock lifecycle with CPU IO fixtures."""
import importlib.util, json
from pathlib import Path
from types import SimpleNamespace
import pytest
DEV=Path(__file__).parents[1]
def load(path):
 s=importlib.util.spec_from_file_location('fixture_'+path.stem,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_native_reads_proof_and_rejects_byte_and_pin_changes(tmp_path,monkeypatch):
 m=load(DEV/'r062_d07_owned_launch_v4.py');a=tmp_path/'parent.so';b=tmp_path/'candidate.so'
 for p in (a,b):p.write_bytes(b'fixture-native');p.chmod(0o444)
 d={'schema':'ft_r062_native_provenance/v1','parent_commit':'151ee718b88882b57dba75317bb53c697d5f235f','candidate_commit':'4fc2320dc0a29422ab61e383e5e1579460e9926e','kernel_source_diff_empty':True,'native':{'_cpu_moe':{'parent_path':str(a),'candidate_path':str(b),'sha256':m.sha(a),'size':a.stat().st_size,'candidate_regular_copy':True}}}
 p=tmp_path/'proof.json';p.write_text(json.dumps(d));p.chmod(0o444);monkeypatch.setattr(m,'PROOF',p);monkeypatch.setattr(m,'PIN',m.sha(p))
 assert m.native()['native']['_cpu_moe']['size']==len(b'fixture-native')
 b.chmod(0o600);b.write_bytes(b'changed');b.chmod(0o444)
 with pytest.raises(RuntimeError,match='native bytes'):m.native()
 monkeypatch.setattr(m,'PIN','wrong')
 with pytest.raises(RuntimeError,match='native proof'):m.native()
def test_actual_child_argv_targets_current_entry_and_round():
 r=load(DEV/'r062_d07_owned_launch_v4.py').runtime();a=r.argv('D07',3,Path('/tmp/fixture.json'))
 assert a[1]==str(DEV/'r062_d07_owned_launch_v4.py')
 assert a[2:6]==['--run','--card','D07','--owned-child']
 assert r.SPECS['D07'][:2]==('E2-R062-gate-D07','4fc2320dc0a29422ab61e383e5e1579460e9926e')
 assert r.PARENT_COMMIT=='151ee718b88882b57dba75317bb53c697d5f235f'
def test_actual_retained_child_sets_owner_before_native_gate_and_acquires_once(tmp_path,monkeypatch):
 r=load(DEV/'r062_d07_owned_launch_v4.py').runtime();r.sys=SimpleNamespace(platform='linux')
 lock=tmp_path/'gpu.lock';native_gate,_=load(DEV/'tests/test_r060_oom_runtime_v4.py').native_gate(lock);calls=[]
 def take(rid,batch):
  assert not lock.exists();lock.write_text('exact-owner');calls.append('take');return {'lock_token':lock.read_text(),'lock_inode':lock.stat().st_ino}
 def release(owner):
  assert lock.read_text()==owner['lock_token'] and lock.stat().st_ino==owner['lock_inode'];lock.unlink();calls.append('release')
 g=SimpleNamespace(take_d07_gpu_lock=take,release_d07_gpu_lock=release,load_owned_lifecycle=lambda:SimpleNamespace(owned_group_alive=lambda pid:False))
 monkeypatch.setattr(r,'d07',lambda:g);monkeypatch.setattr(r,'admission',lambda g,c:calls.append('admission'));monkeypatch.setattr(r,'require_receipt',lambda *args:calls.append('receipt'))
 class Candidate:
  proc=None
  environment=staticmethod(lambda tree:{})
  def __init__(self,options):self.options=options
  def execute(self):
   native_gate(self,tmp_path,'a'*40);self.lock_take();self.lock_release()
   assert lock.exists() and calls.count('take')==1 and self.options.rid=='E2-R062-gate-D07';calls.append('execute')
 monkeypatch.setattr(r,'adapter_module',lambda name:SimpleNamespace(CandidateRunner=Candidate))
 result=r.child('D07',3,tmp_path/'launch.json')
 assert result['rid']=='E2-R062-gate-D07' and calls==['admission','receipt','take','execute','release']
 assert not lock.exists()
