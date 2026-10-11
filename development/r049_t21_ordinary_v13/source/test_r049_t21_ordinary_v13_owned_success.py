"""Exercise actual child lock lifetime without a GPU or formal round."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

def setup_child(monkeypatch,tmp_path,*,measurement_error=None,release_error=None):
    path=Path(__file__).with_name('r049_t21_ordinary_prepare_v13.py')
    spec=importlib.util.spec_from_file_location('r049_v13_child',path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setattr(m,'sys',SimpleNamespace(platform='linux'))
    events=[]; owner={'owner':m.RID,'pid':123,'start_ticks':456}; result={'measured':True}
    def take(rid,batch): events.append(('take',rid,batch)); return owner
    def release(value):
        assert value is owner
        events.append(('release',value))
        if release_error is not None: raise release_error
    d=SimpleNamespace(take_d07_gpu_lock=take,release_d07_gpu_lock=release)
    monkeypatch.setattr(m,'load_d07',lambda:d)
    monkeypatch.setattr(m,'require_section13_runtime_tooling',lambda:None)
    monkeypatch.setattr(m,'require_dry_run_receipt',lambda:{})
    monkeypatch.setattr(m,'admission',lambda receipt:None)
    monkeypatch.setattr(m,'require_receipt',lambda *args:None)
    monkeypatch.setattr(m,'ROUNDS',tmp_path)
    def measure(batch):
        events.append(('measurement',batch))
        if measurement_error is not None: raise measurement_error
        return result
    monkeypatch.setattr(m,'run_measurements',measure)
    monkeypatch.setattr(m,'_write_child_terminal',lambda run,error,actual_owner,**kwargs:events.append(('terminal',error,kwargs['release_state'])))
    return m,events,owner,result

def test_success_releases_own_lock_before_return(monkeypatch,tmp_path):
    m,events,owner,result=setup_child(monkeypatch,tmp_path)
    assert m.child(999,tmp_path/'receipt.json') is result
    assert [row[0] for row in events]==['take','measurement','release']
    assert events[-1][1] is owner

def test_measurement_failure_releases_owned_lock_and_preserves_error(monkeypatch,tmp_path):
    failure=RuntimeError('measurement failure')
    m,events,_,_=setup_child(monkeypatch,tmp_path,measurement_error=failure)
    with pytest.raises(RuntimeError) as raised: m.child(999,tmp_path/'receipt.json')
    assert raised.value is failure
    assert [row[0] for row in events]==['take','measurement','release','terminal']
    assert events[-1][2]=='released'

def test_unterminated_service_preserves_lock(monkeypatch,tmp_path):
    failure=RuntimeError('service cleanup failure'); failure.owned_cleanup_failed=True
    m,events,_,_=setup_child(monkeypatch,tmp_path,measurement_error=failure)
    with pytest.raises(RuntimeError) as raised: m.child(999,tmp_path/'receipt.json')
    assert raised.value is failure
    assert [row[0] for row in events]==['take','measurement','terminal']
    assert events[-1][2]=='not_attempted_service_cleanup_failed'

def test_successful_measurement_lock_release_failure_has_terminal_evidence(monkeypatch,tmp_path):
    failure=RuntimeError('owned release failed')
    m,events,_,_=setup_child(monkeypatch,tmp_path,release_error=failure)
    with pytest.raises(RuntimeError) as raised: m.child(999,tmp_path/'receipt.json')
    assert raised.value is failure
    assert [row[0] for row in events]==['take','measurement','release','terminal']
    assert events[-1][2]=='failed'

