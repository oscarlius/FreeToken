import importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('v5',HERE/'d10_prototype_owned_parent_v5.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_filedry_actual_entry_binds_v6_and_v5():
 d=m.filedry();assert d['actual_entrypoint']=='d10_prototype_owned_parent_v5.py';assert d['plan']['budget']['aiperf_calls']==8;assert d['parser_sha256']==m.sha(HERE/'d10_aiperf_parse_v5.py')
def test_v5_child_argv_targets_v5_entrypoint(tmp_path):
 assert Path(m.child_argv(tmp_path/'a',7,tmp_path/'r')[1]).name=='d10_prototype_owned_parent_v5.py'
