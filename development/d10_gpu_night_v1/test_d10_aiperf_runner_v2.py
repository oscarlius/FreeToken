import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('d10a',Path(__file__).with_name('d10_aiperf_runner_v2.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_filedry_binds_actual_r045_record_and_d10_input():
    x=m.filedry();assert x['r045']['request_count']==2 and x['r045']['concurrency']==2
    assert x['command'][x['command'].index('--input-file')+1]==str(m.INPUT)
    assert x['service_started'] is False and x['requests_sent'] is False
