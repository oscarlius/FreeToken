"""T21 D0-only cache counter hook; production does not import this module."""
from __future__ import annotations
import hashlib,importlib.util,json,os,runpy,sys,signal
from pathlib import Path
CANDIDATE=Path('/data2/FreeToken/wt/e2d15')
SOURCE=CANDIDATE/'python/freetoken/moe/offload_cache.py'
SOURCE_SHA='5d7a9b6267baff692f58597dcbad0aceaae2eedad21b44e8b929f6c1f2865df0'
STARTUP_SOURCE=CANDIDATE/'scripts/equiv_suite/service_capture_startup.py'
STARTUP_SHA='91102843e3d2b3464b78e7a0431165ab3ca32d488a59e17f8c818f7c2879ee12'
METHODS=('_d0_begin_decode','_d0_end_decode','_d0_decode_counts','reset_stats','apply_profile_adaptation')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_pin(path=SOURCE):
 raw=Path(path).read_text(); missing=[x for x in METHODS if 'def '+x not in raw]
 if sha(path)!=SOURCE_SHA: raise RuntimeError('T21 D0 candidate source SHA differs')
 if missing: raise RuntimeError('T21 D0 candidate methods unavailable: '+','.join(missing))
 return {'path':str(path),'sha256':SOURCE_SHA,'methods':list(METHODS)}
def ints(x):
 if hasattr(x,'tolist'): x=x.tolist()
 if isinstance(x,(list,tuple)): return [int(v) for v in x]
 return [int(x)]
def batch_meta(batch):
 reqs=getattr(batch,'reqs',None) or []
 return {'rids':[int(getattr(r,'uid')) for r in reqs],'batch_size':len(reqs)}
def worker_birth():
 pid=os.getpid(); ticks=None
 stat=Path(f'/proc/{pid}/stat')
 if stat.exists():
  fields=stat.read_text().split();ticks=int(fields[21])
 return {'pid':pid,'start_ticks':ticks,'execution_id':f'{pid}:{ticks}' if ticks is not None else None}
def snapshot(cache):
 if getattr(cache,'decode_target',None)=='hybrid': raise RuntimeError('T21 D0 wrapper requires offload decode target')
 from flashlib.kernels.slot_cache import Stat
 missing,fetched=cache._d0_decode_counts(); cols=ints(cache.lru_stats.sum(0)); active=cols[int(Stat.ACTIVE)]
 return {'active':active,'missing':sum(int(x) for x in missing),'fetched':sum(int(x) for x in fetched)}
class Journal:
 def __init__(self,path):
  self.path=Path(path)
  if self.path.is_symlink() or self.path.exists(): raise RuntimeError('T21 diagnostic journal already exists or is symlink')
  self.path.parent.mkdir(parents=True,exist_ok=True);self.f=self.path.open('x',encoding='utf-8');self.seq=0;self.birth=worker_birth()
 def append(self,row):
  self.seq+=1;row={**row,'seq':self.seq,'worker_birth':self.birth};self.f.write(json.dumps(row,sort_keys=True)+'\n');self.f.flush();os.fsync(self.f.fileno())
 def terminal(self,status,error=None): self.append({'schema':'ft_t21_d0_terminal/v1','kind':'terminal','status':status,**({'error':repr(error)} if error else {})});self.f.close()
def install(cache_cls,journal):
 source_pin(); begin,end,reset,adapt=(getattr(cache_cls,n) for n in ('_d0_begin_decode','_d0_end_decode','reset_stats','apply_profile_adaptation'))
 states={}
 def wrapped_reset(self,*a,**k): state=states.setdefault(id(self),{'n':0,'last':None,'step':0});state['n']+=1;state['last']=None;journal.append({'schema':'ft_t21_d0_reset/v1','kind':'reset','generation':state['n']});return reset(self,*a,**k)
 def wrapped_begin(self,batch,*a,**k):
  state=states.setdefault(id(self),{'n':0,'last':None,'step':0});state['step']+=1;state['last']=(state['n'],snapshot(self),batch_meta(batch));return begin(self,batch,*a,**k)
 def wrapped_end(self,*a,**k):
  result=end(self,*a,**k); state=states.setdefault(id(self),{'n':0,'last':None,'step':0}); prior=state['last']; now=snapshot(self)
  if prior is None or prior[0]!=state['n']: raise RuntimeError('T21 D0 decode boundary reset/unknown')
  delta={k:now[k]-prior[1][k] for k in now}
  if any(v<0 for v in delta.values()): raise RuntimeError('T21 D0 counter reset produced negative delta')
  row_bytes=sum(int(cache[0].numel())*int(cache[0].element_size()) for _,cache in self.banks)
  journal.append({'schema':'ft_t21_d0_step/v1','kind':'decode','generation':state['n'],'step':state['step'],**prior[2],**delta,'hits':delta['active']-delta['missing'],'expert_row_bytes':row_bytes,'h2d_bytes':delta['fetched']*row_bytes})
  return result
 def wrapped_adapt(self,plan,proof,*a,**k):
  before=int(self.policy_swap_bytes.item()); boundary=getattr(proof,'boundary_seq',None); out=adapt(self,plan,proof,*a,**k); after=int(self.policy_swap_bytes.item()); delta=after-before
  status=getattr(out,'status',None)
  if delta<0:
   if status=='rolled_back': delta=0
   else: raise RuntimeError('T21 adaptation counter decreased without rollback')
  state=states.setdefault(id(self),{'n':0,'last':None,'step':0})
  if state.get('last') is None: raise RuntimeError('T21 adaptation lacks preceding decode UID binding')
  journal.append({'schema':'ft_t21_d0_swap/v1','kind':'adapt','generation':state['n'],'step':state['step'],'rids':state['last'][2]['rids'],'boundary_seq':boundary,'status':status,'swaps':getattr(out,'swaps',None),'policy_swap_bytes_before':before,'policy_swap_bytes_after':after,'policy_swap_bytes_delta':delta})
  return out
 cache_cls.reset_stats=wrapped_reset;cache_cls._d0_begin_decode=wrapped_begin;cache_cls._d0_end_decode=wrapped_end;cache_cls.apply_profile_adaptation=wrapped_adapt
 return source_pin()
def startup_pin(path=STARTUP_SOURCE):
 if sha(path)!=STARTUP_SHA: raise RuntimeError('T21 D0 startup source SHA differs')
 raw=Path(path).read_text()
 if 'def run_scheduler' not in raw or 'install_scheduler_capture(scheduler)' not in raw: raise RuntimeError('T21 D0 startup callback seam unavailable')
 return {'path':str(path),'sha256':STARTUP_SHA}

def _startup_module():
 startup_pin(); spec=importlib.util.spec_from_file_location('r049_scheduler_startup',STARTUP_SOURCE)
 module=importlib.util.module_from_spec(spec)
 assert spec and spec.loader
 spec.loader.exec_module(module)
 return module

def _worker_install(scheduler,journal):
 engine=getattr(scheduler,'engine',None); cache=getattr(engine,'moe_offload_cache',None)
 if cache is None: raise RuntimeError('T21 D0 scheduler has no MoE offload cache')
 install(type(cache),journal)
 journal.append({'schema':'ft_t21_d0_install/v1','kind':'install','cache_type':f'{type(cache).__module__}.{type(cache).__qualname__}'})
 original=getattr(scheduler,'shutdown',None)
 if not callable(original): raise RuntimeError('T21 D0 scheduler lacks shutdown')
 closed=False
 def shutdown(*args,**kwargs):
  nonlocal closed
  status='complete'; error=None
  try:return original(*args,**kwargs)
  except BaseException as exc:
   status='failed';error=exc;raise
  finally:
   if not closed:
    closed=True;journal.terminal(status,error)
 scheduler.shutdown=shutdown
 return scheduler

def worker_run_scheduler(args,ack_queue):
 """Spawn-pickleable D0 worker; SIGTERM follows the pinned graceful shutdown path."""
 journal_path=os.environ.get('FT_T21_DIAG_JOURNAL')
 if not journal_path: raise RuntimeError('FT_T21_DIAG_JOURNAL is required for D0 startup wrapper')
 journal=Journal(journal_path); installed=[False]; previous=signal.getsignal(signal.SIGTERM)
 def on_term(signum,frame):
  if installed[0]: raise KeyboardInterrupt
  raise RuntimeError('T21 D0 worker received SIGTERM before scheduler install')
 signal.signal(signal.SIGTERM,on_term)
 try:
  startup=_startup_module()
  def callback(scheduler):
   value=_worker_install(scheduler,journal);installed[0]=True;return value
  startup.install_scheduler_capture=callback
  return startup.run_scheduler(args,ack_queue)
 except BaseException as error:
  if not journal.f.closed: journal.terminal('failed',error)
  raise
 finally:
  signal.signal(signal.SIGTERM,previous)

def main():
 argv=sys.argv[1:]
 if not argv: raise SystemExit('usage: r049_d0_startup.py <candidate-cli> ...')
 # Spawn resolves a module-level target.  Do not install hooks in this parent process.
 module_dir=str(Path(__file__).resolve().parent)
 if module_dir not in sys.path: sys.path.insert(0,module_dir)
 old=os.environ.get('PYTHONPATH','');os.environ['PYTHONPATH']=module_dir+(os.pathsep+old if old else '')
 sys.path.insert(0,str(CANDIDATE/'python'))
 stable=__import__('r049_d0_startup')
 from freetoken.server import launch as launch_module
 launch_module._run_scheduler=stable.worker_run_scheduler
 sys.argv=argv
 runpy.run_path(argv[0],run_name='__main__')
if __name__=='__main__': main()
