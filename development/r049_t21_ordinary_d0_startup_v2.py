"""Spawn-safe D0 plus ordinary-v3 diagnostic worker wrapper."""
from __future__ import annotations
import argparse,atexit,importlib.util,json,os,runpy,signal,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def mods():return load('r049_d0_child',HERE/'r049_d0_startup.py'),load('r049_ordinary_child',HERE/'r046c_t06_ordinary_startup_v3.py')
def observer_install(scheduler,ordinary,directory):
 service=json.loads(os.environ['R046C_T06_SERVICE_BIRTH']);o=ordinary.WorkerObserver(directory,service);process,reply=scheduler._process_one_msg,scheduler._reply_tokenizer_rank0
 def seen_process(msg,*args,**kwargs):
  if type(msg).__name__=='UserMsg':o.record_input(msg)
  return process(msg,*args,**kwargs)
 def seen_reply(replies,*args,**kwargs):
  for message in replies:
   for item in getattr(message,'data',(message,)):
    if type(item).__name__=='DetokenizeMsg':o.record_token(item)
  return reply(replies,*args,**kwargs)
 scheduler._process_one_msg=seen_process;scheduler._reply_tokenizer_rank0=seen_reply;atexit.register(o.flush);return o
def worker_run_scheduler(args,ack_queue):
 """Module-level target re-imported by spawn; no parent closure exists."""
 d0,ordinary=mods();journal=d0.Journal(os.environ['FT_T21_DIAG_JOURNAL']);installed=[False];previous=signal.getsignal(signal.SIGTERM)
 def on_term(signum,frame):
  if installed[0]:raise KeyboardInterrupt
  raise RuntimeError('T21 diagnostic worker received SIGTERM before scheduler install')
 signal.signal(signal.SIGTERM,on_term)
 try:
  startup=d0._startup_module()
  def callback(scheduler):
   result=d0._worker_install(scheduler,journal);observer_install(result,ordinary,Path(os.environ['R046C_T06_OBSERVER_DIR']));installed[0]=True;return result
  startup.install_scheduler_capture=callback
  return startup.run_scheduler(args,ack_queue)
 except BaseException as exc:
  if not journal.f.closed:journal.terminal('failed',exc)
  raise
 finally:
  signal.signal(signal.SIGTERM,previous)
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--observer-dir',type=Path,required=True);p.add_argument('candidate',nargs=argparse.REMAINDER);a=p.parse_args(argv)
 if len(a.candidate)<2 or a.candidate[0]!='--':p.error('pass candidate startup after --')
 _,ordinary=mods();os.environ['R046C_T06_OBSERVER_DIR']=str(a.observer_dir);os.environ['R046C_T06_SERVICE_BIRTH']=json.dumps(ordinary.birth(),sort_keys=True)
 module_dir=str(HERE)
 if module_dir not in sys.path:sys.path.insert(0,module_dir)
 prior=os.environ.get('PYTHONPATH','');os.environ['PYTHONPATH']=module_dir+(os.pathsep+prior if prior else '')
 stable=__import__('r049_t21_ordinary_d0_startup_v2')
 from freetoken.server import launch as launch
 launch._run_scheduler=stable.worker_run_scheduler;sys.argv=[a.candidate[1],*a.candidate[2:]];runpy.run_path(a.candidate[1],run_name='__main__')
if __name__=='__main__':main()
