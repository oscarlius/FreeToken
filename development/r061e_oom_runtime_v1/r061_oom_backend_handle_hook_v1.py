"""Startup-only recorder for the product's real BackendHandle.processes boundary."""
import json, os
from pathlib import Path

def _birth(pid):
 fields=(Path('/proc')/str(pid)/'stat').read_text().rpartition(') ')[2].split()
 ticks=int(fields[19]);return {'pid':pid,'start_ticks':ticks,'execution_id':f'{pid}:{ticks}'}
def install(root):
 from freetoken.server import supervisor
 original=supervisor.run_backend_supervisor
 def record(handle, *args, **kwargs):
  epoch=0
  def snap(value, number):
   rows=[]
   for process in value.processes:
    row=_birth(process.pid);row['name']=process.name;rows.append(row)
   target=Path(root)/'backend_handles'/f'epoch-{number}.json';target.parent.mkdir(parents=True,exist_ok=True)
   with target.open('x') as f:json.dump({'schema':'ft_r061_backend_handle/v1','epoch':number,'workers':rows},f,sort_keys=True);f.write('\n')
  snap(handle,epoch); restart=kwargs.get('restart_backend')
  if restart:
   def wrapped():
    nonlocal epoch;fresh=restart();epoch+=1;snap(fresh,epoch);return fresh
   kwargs['restart_backend']=wrapped
  return original(handle,*args,**kwargs)
 supervisor.run_backend_supervisor=record
