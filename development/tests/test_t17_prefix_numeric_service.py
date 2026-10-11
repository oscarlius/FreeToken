"""Prove inherited real-service dispatch selects the new observer and default chunks."""
import importlib.util
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('numeric_service_test',HERE/'t17_prefix_numeric_runner.py')
numeric=importlib.util.module_from_spec(spec);spec.loader.exec_module(numeric)


def test_service_keeps_original_parameters_and_uses_numeric_startup(monkeypatch,tmp_path):
    for name in ('t17_prefix_numeric_startup.py','t17_d14_exact_ids.py'):
        path=tmp_path/name;path.write_text('frozen test entry\n');path.chmod(0o444)
    monkeypatch.setattr(numeric,'HERE',tmp_path);monkeypatch.setattr(numeric.original,'HERE',tmp_path)
    run=object.__new__(numeric.Run);run.directory=tmp_path/'round';run.directory.mkdir()
    for name,value in {'gate':lambda *_:'bound source','compiled_extensions':lambda *_:{'binding':'same'},
                       'ready':lambda *_:None,'set_status':lambda **_:None,
                       'stop':lambda:setattr(run,'proc',None)}.items():monkeypatch.setattr(run,name,value)
    run.parser=lambda _:{'_unique_suffix':repr('.pid=4242'),'mamba_host_slots':'0'}
    captured=[]
    class Process:pid=4242
    def start(argv,**kwargs):captured.append((argv,kwargs));return Process()
    monkeypatch.setattr(numeric.original.subprocess,'Popen',start)
    monkeypatch.setitem(numeric.original.protocol,'command',lambda *_:'GPU readonly receipt')
    assert numeric.original.Run.service(run,'owned_arm',lambda arm:('callback',arm.name))==('callback','owned_arm')
    assert len(captured)==1
    argv,kwargs=captured[0]
    assert str(tmp_path/'t17_prefix_numeric_startup.py') in argv
    assert kwargs['start_new_session'] is True
    assert kwargs['env']['FT_LM_CHUNK']=='4096'
    assert kwargs['env']['FT_T17_PREFIX_NUMERIC']==str(run.directory/'owned_arm/numeric')
    assert 'FT_T17_MATCHED' not in kwargs['env']
    assert '--prefill-layer-major' in argv and argv[argv.index('--max-prefill-length')+1]=='4096'


def cold_record():
    return {'uid':'7','absolute_interval':[512,8192],
            'segments':[{'absolute_start':512,'absolute_end':4608,'cached_tokens':512,'device_tokens':4608},
                        {'absolute_start':4608,'absolute_end':8192,'cached_tokens':4608,'device_tokens':8257}],
            'h':{'absolute_boundary':8192,'target_boundary_row':3584,'cached_tokens':4608,'device_tokens':8257,
                 'actual_track_boundary_row':3648,'actual_track_absolute_boundary':8256,
                 'actual_track_h_row':57,'computed_h_row':56}}


def test_cold_coordinates_prove_target_is_different_from_real_tracker():
    numeric.validate_prefix_coordinates(cold_record(),7,8257)


def test_mislabeled_cold_tracker_is_rejected():
    record=cold_record();record['h']['actual_track_boundary_row']=3584
    with pytest.raises(ValueError,match='separately proved'):numeric.validate_prefix_coordinates(record,7,8257)


def test_changed_actual_child_path_is_rejected():
    record=cold_record();record['segments'][1]['cached_tokens']=8192
    with pytest.raises(ValueError,match='coordinates differ'):numeric.validate_prefix_coordinates(record,7,8257)
