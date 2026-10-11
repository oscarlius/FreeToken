import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('p',Path(__file__).with_name('d10_prototype_owned_parent_v2.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Proc:
    pid=77
    def poll(self): return 1
class Life:
    def __init__(self):self.stopped=False
    def stop_owned_process(self,p,*_):self.stopped=True
    def owned_group_alive(self,_):return False
class Gate:
    def __init__(self):self.life=Life();self.released=False
    def take_d07_gpu_lock(self,*_):return {'lock_token':'x'}
    def load_owned_lifecycle(self):return self.life
    def release_d07_gpu_lock(self,_):self.released=True
class Aiperf:
    def require_admission(self,_):return {'service_argv':['ft','serve','--enable-d10-staggered-decode'],'service_cwd':'.','endpoint':'http://127.0.0.1:1','output':'/tmp/d10-negative'}
    def run(self,*_):raise AssertionError('generation must not run before health')

def setup(monkeypatch,tmp_path):
    wt=tmp_path/'wt/d10-staggered-v1/python/freetoken';(wt/'server').mkdir(parents=True);(wt/'kernel').mkdir()
    (wt/'server/args.py').write_text('x');(wt/'kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so').write_text('x')
    gate=Gate(); monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'admission',lambda _: Aiperf().require_admission(None))
    monkeypatch.setattr(m,'load',lambda n: gate if n=='d07_g3g4_prepare.py' else Aiperf())
    monkeypatch.setattr(m.hashlib,'sha256',lambda *_:type('H',(),{'hexdigest':lambda self:'203c7c850af8bdb8cc96e8280ff5a0ab2b4bef4a2623f36c0b8c8652af151a57'})())
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:Proc())
    return gate

def test_process_failure_before_health_stops_rebinds_and_releases(monkeypatch,tmp_path):
    gate=setup(monkeypatch,tmp_path)
    with pytest.raises(RuntimeError,match='exited before health'):m.child(Path('a'),1,Path('r'))
    assert gate.life.stopped and gate.released

def test_unsafe_rebind_failure_retains_lock(monkeypatch,tmp_path):
    gate=setup(monkeypatch,tmp_path); real=m.reserve_pair; calls=[]
    def reserve():
        calls.append(1)
        if len(calls)>1:raise OSError(98,'in use')
        return real()
    monkeypatch.setattr(m,'reserve_pair',reserve)
    with pytest.raises(OSError):m.child(Path('a'),1,Path('r'))
    assert gate.life.stopped and not gate.released
