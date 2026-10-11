import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('d10v3',Path(__file__).with_name('d10_aiperf_runner_v3.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_filedry_is_four_profiles_eight_calls_without_runtime():
    x=m.filedry();assert len(x['commands'])==4 and x['budget']['aiperf_calls']==8
    assert all(x[k] is False for k in ('gpu_started','service_started','requests_sent','http_started'))
def test_admission_rejects_writable_or_unbound(tmp_path):
    p=tmp_path/'admission.json';p.write_text('{}')
    try:m.require_admission(p)
    except RuntimeError:pass
    else:raise AssertionError('unbound admission accepted')
