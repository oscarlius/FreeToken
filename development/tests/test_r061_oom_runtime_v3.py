import importlib.util,json,sys
from pathlib import Path

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('r061v3',DEV/'r061_oom_fault_prepare_v3.py');m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m

def test_v3_source_closure_has_recursive_ordinary_and_bootstrap_sources():
 m=load(); names={p.name for p in m.closure()}
 assert {'r061_oom_fault_prepare_v1.py','r060_oom_t16_prepare_v1.py','r046c_t06_ordinary_client_v3.py','r046c_t06_ordinary_client_v2.py','r046c_t06_ordinary_startup_v4.py','r061_oom_backend_handle_hook_v1.py'} <= names

def test_epoch_index_never_moves_raw_worker_or_breaks_absolute_ids(tmp_path):
 m=load();root=tmp_path/'ordinary_observer';raw=root/'workers'/'42';raw.mkdir(parents=True)
 ids=raw/'input-0.json';ids.write_text('[1,2]');(raw/'inputs.jsonl').write_text(json.dumps({'uid':0,'input_ids_path':str(ids)})+'\n');(raw/'tokens.jsonl').write_text(json.dumps({'uid':0})+'\n')
 got=m.epoch_observer_index(root,0,0);assert got==raw and ids.is_file() and (root/'epoch-0-uid-0.json').is_file()

def test_worker_births_use_observer_pid_receipts_not_api_group_helpers(tmp_path):
 m=load();root=tmp_path/'ordinary_observer'/'workers';(root/'101').mkdir(parents=True);(root/'102').mkdir()
 class Life:
  def process_identity(self,pid): return {'pid':pid,'start_ticks':pid+100}
 # A persistent resource_tracker would share the process group but has no observer PID dir.
 got=m.observed_worker_births(Life(),root.parent,999)
 assert got==[{'pid':101,'start_ticks':201},{'pid':102,'start_ticks':202}]

def test_backend_handle_receipt_is_the_exact_old_worker_set(tmp_path):
 m=load();root=tmp_path/'ordinary_observer'/'backend_handles';root.mkdir(parents=True)
 (root/'epoch-0.json').write_text(json.dumps({'schema':'ft_r061_backend_handle/v1','epoch':0,'workers':[{'pid':7,'start_ticks':70,'name':'scheduler'},{'pid':8,'start_ticks':80,'name':'tokenizer'}]}))
 class Life:
  def process_identity(self,pid): return {'pid':pid,'start_ticks':pid*10,'execution_id':str(pid)}
 assert [x['pid'] for x in m.backend_handle_births(Life(),root.parent,0)]==[7,8]
