import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

p=Path(__file__).with_name('runner.py')
s=importlib.util.spec_from_file_location('d09_wait',p)
r=importlib.util.module_from_spec(s);s.loader.exec_module(r)

def test_driver_context_lag_after_owned_exit_is_waited():
    rows=iter([RuntimeError('22598'),RuntimeError('5120'),[4]])
    elapsed=[0]
    def idle():
        value=next(rows)
        if isinstance(value,Exception):raise value
        return value
    def sleep(t):elapsed[0]+=t
    assert r.wait_gpu_idle(SimpleNamespace(require_gpu_idle=idle),timeout=3,clock=lambda:elapsed[0],sleep=sleep)==[4]
    assert elapsed[0]==2

def test_foreign_or_stuck_gpu_never_becomes_accepted():
    elapsed=[0]
    def idle():raise RuntimeError('foreign active GPU')
    def sleep(t):elapsed[0]+=t
    with pytest.raises(RuntimeError,match='foreign active'):
        r.wait_gpu_idle(SimpleNamespace(require_gpu_idle=idle),timeout=3,clock=lambda:elapsed[0],sleep=sleep)
    assert elapsed[0]==3
