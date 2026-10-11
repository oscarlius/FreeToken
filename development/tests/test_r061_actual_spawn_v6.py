import importlib.util, os, subprocess, sys, types, json
from pathlib import Path

DEV=Path(__file__).parents[1]
def load():
 s=importlib.util.spec_from_file_location('v6',DEV/'r061_oom_fault_prepare_v6.py');m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m

def test_v6_writer_keeps_wrapper_as_spawn_main_and_separates_backend_handles(tmp_path):
 m=load();runtime=tmp_path/'runtime';runtime.mkdir();observer=runtime/'observer.py';observer.write_text('def install(p): open(p.parent/"installed", "w").write(str(p))\ndef main(): pass\n');startup=runtime/'startup.py';startup.write_text('old')
 def original(_):return {'startup':str(startup),'observer':str(observer)}
 value=m.backend_startup_writer(original)(tmp_path);text=startup.read_text()
 assert value['startup']==str(startup) and "__mp_main__" in text and "workers" in text and "run_path" not in text
 assert 'ordinary_observer' in text and (runtime/'r061_oom_backend_handle_hook_v1.py').is_file()

def test_generated_wrapper_is_actual_multiprocessing_spawn_main(tmp_path):
 m=load();runtime=tmp_path/'runtime';runtime.mkdir();observer=runtime/'observer.py'
 observer.write_text("import multiprocessing as mp,os\n"
 "def install(p): p.mkdir(parents=True,exist_ok=True);(p/'spawn-main').write_text(str(os.getpid()))\n"
 "def child(): pass\n"
 "def main():\n mp.set_start_method('spawn',force=True);p=mp.Process(target=child);p.start();p.join();assert p.exitcode==0\n")
 startup=runtime/'startup.py';startup.write_text('old')
 def original(_):return {'startup':str(startup),'observer':str(observer)}
 m.backend_startup_writer(original)(tmp_path)
 pkg=runtime/'freetoken'/'server';pkg.mkdir(parents=True);(runtime/'freetoken'/'__init__.py').write_text('');(pkg/'__init__.py').write_text('');(pkg/'supervisor.py').write_text('def run_backend_supervisor(*a,**k): pass\n')
 env={**os.environ,'R046C_T06_OBSERVER_DIR':str(tmp_path/'ordinary_observer'),'PYTHONPATH':str(runtime)}
 result=subprocess.run([sys.executable,str(startup)],env=env,capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stderr
 workers=list((tmp_path/'ordinary_observer'/'workers').glob('*/spawn-main'))
 assert len(workers)==1 and workers[0].parent.name!=str(os.getpid())

def test_real_worker_observer_records_input_and_token_with_preexisting_backend_handles(tmp_path,monkeypatch):
 root=tmp_path/'ordinary_observer';(root/'backend_handles').mkdir(parents=True);(root/'backend_handles'/'epoch-0.json').write_text('{}')
 class Engine: 
  def __init__(self): pass
 class Scheduler:
  def _process_one_msg(self,x): return x
 class IO:
  def _reply_tokenizer_rank0(self,x): return x
 class User:
  def __init__(self):self.uid=0;self.input_ids=[1,2]
 class DetokenizeMsg:
  def __init__(self):self.uid=0;self.next_token=3;self.finished=True;self.finish_reason='stop'
 def mod(name,**attrs):x=types.ModuleType(name);[setattr(x,k,v) for k,v in attrs.items()];monkeypatch.setitem(sys.modules,name,x)
 mod('freetoken');mod('freetoken.engine');mod('freetoken.engine.engine',Engine=Engine);mod('freetoken.message');mod('freetoken.message.backend',UserMsg=User);mod('freetoken.scheduler');mod('freetoken.scheduler.scheduler',Scheduler=Scheduler);mod('freetoken.scheduler.io',SchedulerIOMixin=IO)
 obs=importlib.util.spec_from_file_location('actual_obs',DEV/'r046c_t06_ordinary_startup_v4.py');o=importlib.util.module_from_spec(obs);assert obs.loader;obs.loader.exec_module(o)
 monkeypatch.setattr(o,'birth',lambda:{'pid':2,'start_ticks':2,'execution_id':'2:2','pgid':2,'session':2});monkeypatch.setenv('R046C_T06_SERVICE_BIRTH',json.dumps({'pid':1,'start_ticks':1,'execution_id':'1:1','pgid':1,'session':1}));worker=root/'workers'/str(os.getpid());o.install(worker);Engine();s=Scheduler();s._process_one_msg(User());IO()._reply_tokenizer_rank0([types.SimpleNamespace(data=[DetokenizeMsg()])])
 assert (worker/'inputs.jsonl').is_file() and (worker/'tokens.jsonl').is_file() and not (root/'inputs.jsonl').exists()
