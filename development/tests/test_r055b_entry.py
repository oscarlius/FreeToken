import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).parents[1]
def load():
 p=ROOT/'r055b_owned_launch.py';s=importlib.util.spec_from_file_location('r055b_entry',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_pause_only_startup_installs_engine_memory_observer(tmp_path):
 m=load();startup=m._freeze_pause_observer(tmp_path)
 observer=(tmp_path/'r055b_pause_observer.py').read_text()
 assert startup.name=='r055b_pause_startup.py'
 assert 'Engine.__init__=loaded' in observer and 'torch.cuda.mem_get_info(0)' in observer
 assert 'DevPauseCancelBackendMsg' in observer and 'request_before' in observer and 'request_after' in observer
 assert not ((tmp_path/'r055b_pause_observer.py').stat().st_mode&0o222)
def test_file_only_pause_uses_same_writer_without_trace(monkeypatch,tmp_path):
 m=load()
 class Gate:
  VENV=tmp_path/'venv'
  def dynamic_fixture_port(self):return 43123
  def serve_argv(self,p):return ['ft','serve','--port',str(p)]
  def clean_environment(self,wt,trace_dir=None):assert trace_dir is None;return {'PATH':'p','VIRTUAL_ENV':'v','PYTHONPATH':'x','CUDA_VISIBLE_DEVICES':'','FT_DEV_PAUSE_ENDPOINT':'1','FT_DEV_ROUTE_TRACE':'bad'}
 class Legacy:
  ROOT=tmp_path;RID=m.RID;CANDIDATE_COMMIT='c'
  def require_candidate(self):return tmp_path/'wt'
 monkeypatch.setattr(m,'_legacy',lambda:Legacy())
 result=m.pause_smoke(Legacy(),Gate(),1,tmp_path/'dry',file_dry_run=True,worktree_override=tmp_path/'wt')
 assert result['service_started'] is False
 assert (tmp_path/'dry/model_process_cuda.jsonl').is_file()
 assert 'FT_DEV_ROUTE_TRACE' not in (tmp_path/'dry/SERVE_CMD.txt').read_text()
def test_legacy_adapter_replaces_six_arm_execute_with_pause_only(monkeypatch,tmp_path):
 m=load();legacy=m._legacy();klass=legacy.adapter_module().CandidateRunner
 runner=klass.__new__(klass);runner.directory=tmp_path/'round';runner.set_status=lambda **kw:None
 result=runner.execute()
 assert result['cold_arms_replayed'] is False and (tmp_path/'round').is_dir()
