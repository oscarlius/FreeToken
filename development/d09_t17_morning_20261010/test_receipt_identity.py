import importlib.util,json
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('runner',HERE/'runner.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class Life:
 def verified_module(self,*a):return self
 def next_batch(self,*a):return 1
 def reserve_process(self,*a):
  p=a[-1];p['state']='launched';p['batch_pid']=9;Path(a[-2]).write_text(json.dumps(p));return p
class G:
 LOCK=Path('/tmp/d09-receipt-test.lock');ATOMIC_HELPER_SHA='x';ROUNDS=Path('/tmp')
 def __init__(self):self.published=None
 def process_birth(self):return {'pid':9,'start_ticks':77,'execution_id':'9:77'}
 def process_identity(self,p):return {'pid':p,'start_ticks':77,'execution_id':'9:77','pgid':9,'session':9,'state':'S'}
 def load_owned_lifecycle(self):return Life()
 def argv_sha256(self,a):return r.hashlib.sha256(json.dumps(a,separators=(',',':')).encode()).hexdigest()
 def publish_child_binding(self,path,got,identity,lifecycle=None):self.published=identity;got['child']=identity;Path(path).write_text(json.dumps(got));return got
class D:
 def __init__(self):self.g=G();self.root=Path('/tmp/d09-receipt-test')
 def validate_candidate(self):return {}
def test_controller_normalizes_full_identity(monkeypatch,tmp_path):
 d=D();d.root=tmp_path;monkeypatch.setattr(r,'cfg',lambda:{}) ;monkeypatch.setattr(r,'check_admission',lambda *a:None)
 r.controller(tmp_path/'admission',deps=d)
 assert d.g.published=={'pid':9,'start_ticks':77,'execution_id':'9:77'}
def test_receipt_full_shape_or_wrong_ticks_rejected(monkeypatch,tmp_path):
 g=G();p=tmp_path/'r.json';argv=r.child_argv(tmp_path/'a',1,p);base={'state':'launched','rid':r.RID,'batch':1,'candidate_commit':r.CANDIDATE,'argv_sha256':g.argv_sha256(argv)}
 for child in ({**g.process_identity(9)},{'pid':9,'start_ticks':78,'execution_id':'9:78'}):
  p.write_text(json.dumps({**base,'child':child})); it=iter([0,31]);monkeypatch.setattr(r.time,'monotonic',lambda:next(it));monkeypatch.setattr(r.time,'sleep',lambda _:None)
  with pytest.raises(RuntimeError,match='child receipt was not published'):r.require_receipt(g,p,1,tmp_path/'a')
def test_receipt_canonical_birth_passes(tmp_path):
 g=G();p=tmp_path/'r.json';argv=r.child_argv(tmp_path/'a',1,p);p.write_text(json.dumps({'state':'launched','rid':r.RID,'batch':1,'candidate_commit':r.CANDIDATE,'argv_sha256':g.argv_sha256(argv),'child':g.process_birth()}));assert r.require_receipt(g,p,1,tmp_path/'a')['child']==g.process_birth()