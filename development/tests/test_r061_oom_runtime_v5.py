import importlib.util,json,sys,os,types
from pathlib import Path

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('r061v5',DEV/'r061_oom_fault_prepare_v5.py');m=importlib.util.module_from_spec(s);assert s.loader;sys.modules[s.name]=m;s.loader.exec_module(m);return m

def test_v5_source_closure_has_recursive_ordinary_and_bootstrap_sources():
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

def test_filedry_and_child_share_backend_handle_startup_writer(tmp_path):
 m=load();runtime=tmp_path/'runtime';runtime.mkdir();target=runtime/'r061_fault_startup.py';target.write_text('original\n')
 def original(directory): return {'startup':str(target)}
 value=m.backend_startup_writer(original)(tmp_path)
 text=target.read_text();assert value['startup']==str(target) and 'r061_handles' in text and (runtime/'r061_oom_backend_handle_hook_v1.py').is_file()

def test_backend_hook_installs_on_real_supervisor_callable_and_records_restart(tmp_path,monkeypatch):
 hook_path=DEV/'r061_oom_backend_handle_hook_v1.py';s=importlib.util.spec_from_file_location('hook',hook_path);hook=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(hook)
 supervisor=types.ModuleType('freetoken.server.supervisor');calls=[]
 def original(handle,*args,**kw):
  calls.append(handle);kw['restart_backend']();return 'done'
 supervisor.run_backend_supervisor=original
 monkeypatch.setitem(sys.modules,'freetoken',types.ModuleType('freetoken'));monkeypatch.setitem(sys.modules,'freetoken.server',types.ModuleType('freetoken.server'));monkeypatch.setitem(sys.modules,'freetoken.server.supervisor',supervisor)
 proc=types.SimpleNamespace(pid=os.getpid(),name='real-fixture-worker');handle=types.SimpleNamespace(processes=[proc])
 monkeypatch.setattr(hook,'_birth',lambda pid:{'pid':pid,'start_ticks':1,'execution_id':str(pid)})
 hook.install(tmp_path);assert supervisor.run_backend_supervisor(handle,restart_backend=lambda:handle)=='done'
 assert json.loads((tmp_path/'backend_handles/epoch-0.json').read_text())['workers'][0]['name']=='real-fixture-worker'
 assert (tmp_path/'backend_handles/epoch-1.json').is_file() and calls==[handle]
