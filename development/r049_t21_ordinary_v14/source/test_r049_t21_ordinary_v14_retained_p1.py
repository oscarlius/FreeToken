import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent

def load():
 spec=importlib.util.spec_from_file_location('r049_v14_driver',HERE/'r049_t21_ordinary_prepare_v14.py')
 m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_file_dry_driver_emits_exact_seven_service_directories(monkeypatch,tmp_path):
 m=load(); observed=[]
 monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace())
 monkeypatch.setattr(m,'dynamic_private_port',lambda:12345)
 def build(run,**kwargs):
  p=run/'seed12k_only.strp'; p.write_text('profile'); return p,['build']
 monkeypatch.setattr(m,'build_profile',build)
 monkeypatch.setattr(m,'service_files',lambda d,directory,port,policy,profile,d0,**kwargs: observed.append((directory.name,policy,d0)))
 monkeypatch.setattr(m,'run_workloads',lambda *args,**kwargs: {})
 receipt=m.run_measurements(file_dry_run=True,file_dry_run_path=tmp_path/'dry')
 assert receipt['arms']==['PA1','L2','P2','PA2','L_D0','P_D0','PA_D0']
 assert [name for name,_,_ in observed]==receipt['arms']

def test_mismatched_retained_p1_metadata_rejects_before_service_start(monkeypatch,tmp_path):
 m=load(); started=[]
 monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace())
 monkeypatch.setattr(m,'retained_l1_baseline',lambda:{'texts':{},'timing':{},'request_input_bindings':{},'outputs':{},'generated_tokens':1})
 monkeypatch.setattr(m,'require_retained_p1_review',lambda:(_ for _ in ()).throw(RuntimeError('T21 retained P1 review conclusion differs')))
 def build(run,**kwargs):
  p=run/'seed12k_only.strp'; p.write_text('profile'); return p,['build']
 monkeypatch.setattr(m,'build_profile',build)
 monkeypatch.setattr(m,'start_service',lambda *args:started.append(args) or None)
 with pytest.raises(RuntimeError,match='retained P1 review conclusion differs'):
  m.run_measurements(batch=1,output_root=tmp_path)
 assert started==[]