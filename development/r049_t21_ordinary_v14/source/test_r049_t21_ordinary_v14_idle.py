import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
HERE=Path(__file__).resolve().parent
def load():
 s=importlib.util.spec_from_file_location('v14',HERE/'r049_t21_ordinary_prepare_v14.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_idle_gate_rejects_before_popen(monkeypatch,tmp_path):
 m=load(); calls=[];d=SimpleNamespace(require_gpu_idle=lambda: (_ for _ in ()).throw(RuntimeError('GPU not idle')))
 monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:calls.append(a))
 with pytest.raises(RuntimeError,match='GPU not idle'):m.start_service(d,tmp_path/'P1',12345,'profile',tmp_path/'x',False)
 assert calls==[]
def test_idle_gate_runs_once_before_service_files(monkeypatch,tmp_path):
 m=load(); calls=[];(tmp_path/'P1').mkdir();d=SimpleNamespace(require_gpu_idle=lambda:calls.append('idle'))
 monkeypatch.setattr(m,'service_files',lambda *a:(calls.append('files') or ({},['x'],None)))
 monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('popen-stop')))
 with pytest.raises(RuntimeError,match='popen-stop'):m.start_service(d,tmp_path/'P1',12345,'profile',tmp_path/'x',False)
 assert calls==['idle','files']
