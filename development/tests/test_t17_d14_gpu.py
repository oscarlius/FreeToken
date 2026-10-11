import importlib.util
import json
from pathlib import Path
import sys

import pytest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('t17_real_gpu',HERE/'t17_d14_gpu.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def response(ids,cached=64,completion=128):
    return {'status':200,'response':{'uid':3,'finished':True,'text':'output','usage':{
        'prompt_tokens':len(ids),'cached_tokens':cached,'completion_tokens':completion},'input_ids_sha256':runner.ids_sha(ids)}}


@pytest.mark.parametrize('field,value', [('finished',False),('input_ids_sha256','0'*64),('status',400),
    ('prompt_tokens',12),('cached_tokens',0),('completion_tokens',0),('completion_tokens',127),('completion_tokens',129)])
def test_actual_hit_receipt_rejects_terminal_id_and_usage_errors(field,value):
    ids=[1]*129;record=response(ids)
    if field=='status':record[field]=value
    elif field in ('prompt_tokens','cached_tokens','completion_tokens'):record['response']['usage'][field]=value
    else:record['response'][field]=value
    with pytest.raises(ValueError):runner.validate_response(record,ids,64,128)


def test_input_identity_and_prefix_cache_boundary_are_exact():
    assert runner.ids_sha([1469,17])!=runner.ids_sha([17,1469])
    assert runner.common_prefix([1]*8193+[2]*64,[1]*8193+[3]*4160)//64*64==8192
    assert runner.validate_response(response([1]*129),[1]*129,64,128)['uid']==3


def test_gpu_lifecycle_has_all_real_boundary_and_cold_process_requirements():
    source=(HERE/'t17_d14_gpu.py').read_text()
    assert 'self.service(cold_name' in source and 'self.stop()' in source
    assert "('--cpu-startup-probe')" not in source
    assert '--mamba-host-slots' in source and "for variant in ('short','long')" in source
    assert 'FT_T17_OBSERVATIONS' in source and 'artifacts.validate_case' in source
    assert {row['length'] for row in runner.helper.BOUNDARY_PLAN}=={8192,12416,12736,18944}
