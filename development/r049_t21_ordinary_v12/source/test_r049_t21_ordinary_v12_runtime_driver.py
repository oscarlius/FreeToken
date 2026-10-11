import importlib.util
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
def load():
 s=importlib.util.spec_from_file_location('v12',HERE/'r049_t21_ordinary_prepare_v12.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_run_measurements_uses_retained_l1_and_runs_exact_remaining_eight(monkeypatch,tmp_path):
 m=load(); seen=[]
 def build(run,file_dry_run=False):
  q=tmp_path/'p';q.write_text('profile');return q,['build']
 monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace())
 monkeypatch.setattr(m,'build_profile',build)
 monkeypatch.setattr(m,'dynamic_private_port',lambda:12345)
 monkeypatch.setattr(m,'service_files',lambda d,di,po,pol,pr,d0,file_dry_run=False:seen.append(di.name) or ({},[],None))
 monkeypatch.setattr(m,'run_workloads',lambda *a,**k:{'cpu_file_probe':True})
 out=m.run_measurements(file_dry_run=True,file_dry_run_path=tmp_path/'dry')
 assert out['arms']==['P1','PA1','L2','P2','PA2','L_D0','P_D0','PA_D0'] and seen==out['arms']
