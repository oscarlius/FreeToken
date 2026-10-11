"""R040a file-only mirror of frozen v2 pre-service operations.

Normal calls delegate to frozen v2.  File-only calls preserve its actual arm
loops and stop before service spawn, client work, or evidence collection.
"""
from __future__ import annotations
import hashlib, importlib.util, json, os, shlex
from pathlib import Path
HERE=Path(__file__).resolve().parent; FROZEN=HERE/'d16_native_process_collection_v2.py'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def md5(p): return hashlib.md5(Path(p).read_bytes()).hexdigest()
def _frozen():
 s=importlib.util.spec_from_file_location('r040a_frozen_collector_v2',FROZEN);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def _write_new(path,value,*,text=False):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f:f.write(value if text else json.dumps(value,sort_keys=True)+'\n')
def _probe(path,value='CPU_FILE_PROBE_ONLY\n'):
 _write_new(path,value,text=True)
 if not os.access(path,os.W_OK):raise RuntimeError('unwritable file-only output: '+str(path))
def _copy_sources(root,wrapper):
 copied={}
 for label,source in {'collector_v2':FROZEN,'startup_wrapper':Path(wrapper)}.items():
  source=Path(source)
  if source.is_symlink() or not source.is_file():raise ValueError('regular frozen source required: '+str(source))
  target=Path(root)/'execution_sources'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as f:f.write(source.read_bytes())
  target.chmod(0o444)
  if target.stat().st_mode&0o222:raise RuntimeError('file-only source copy is writable')
  copied[label]={'path':str(target),'sha256':sha(target),'md5':md5(target),'mode':oct(target.stat().st_mode&0o777)}
 _write_new(Path(root)/'execution_source.json',copied);return copied
def _pre_popen_service(owner,name,operation,*,arm_root,execution,inputs,kind):
 arm=Path(arm_root)/name;arm.mkdir(exist_ok=False);env=owner.environment(owner.worktree,arm,False)
 selected=('PYTHONPATH','PYTHONUNBUFFERED','VIRTUAL_ENV','PATH','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES');safe={key:env[key] for key in selected if key in env}
 _write_new(arm/'ENV.txt',safe);argv=owner.serve_argv(arm,kind)
 _probe(arm/'SERVE_CMD.txt','env '+' '.join(key+'='+shlex.quote(value) for key,value in safe.items())+' '+shlex.join(argv)+'\n')
 _probe(arm/'serve.log');_probe(arm/'capture'/'.writable');_probe(arm/'capture'/'admissions'/'.writable');_probe(arm/'observations.jsonl')
 _write_new(arm/'file_only_service.json',{'schema':'ft_r040a_file_only_service/v1','execution_id':execution,'kind':kind,'service_started':False,'requests_sent':False,'argv':argv,'environment_keys':sorted(safe)})
 operation(arm,inputs);return {'file_only':True,'arm':str(arm),'service_started':False}
def _output_probe(arm,name):
 path=Path(arm)/name;path.parent.mkdir(parents=True,exist_ok=True);import torch
 with path.open('xb') as f:torch.save(torch.empty(0,dtype=torch.int32),f)
 if not os.access(path,os.W_OK):raise RuntimeError('unwritable tensor output: '+str(path))
def _operation(arm,inputs):
 _write_new(Path(arm)/'input_binding.json',{'input_count':len(inputs),'input_ids_sha256':[hashlib.sha256(json.dumps(x).encode()).hexdigest() for x in inputs]});_output_probe(arm,'collection/file_only_output.pt')
def _file_collect(owner,inputs,*,slots,wrapper,interleave=False):
 if type(slots)is not int or slots not in (2,4) or len(inputs)!=slots:raise ValueError('D16 requires exactly two or four input slots')
 root=Path(owner.directory)/'dev_D16'/('native_interleave' if interleave else 'native_slots_'+str(slots));root.mkdir(parents=True,exist_ok=False);copied=_copy_sources(root,wrapper);arms=[]
 for kind,repeat,slot in [('batch',r,None) for r in (0,1)]+[('single',r,s) for r in (0,1) for s in range(slots)]:
  name='dev_D16_%d_%s_%d_%s'%(slots,kind,repeat,slot);chosen=inputs if slot is None else [inputs[slot]]
  value=owner.service(name,lambda arm,current:_operation(arm,current),health_only=True,max_running_requests=4,file_only=True,arm_root=root,execution=owner.options.rid+':'+name,inputs=chosen,kind='native');arms.append({'name':name,'kind':kind,'repeat':repeat,'slot':slot,'pre_popen':value})
 _write_new(root/'file_only_collection.json',{'schema':'ft_r040a_d16_file_only/v1','slots':slots,'interleave':interleave,'arms':arms,'source_copy':copied,'measurement_created':False});return {'root':str(root),'arms':arms,'file_only':True,'measurement_created':False}
def _file_state(owner,ids,*,kind,wrapper):
 if kind not in ('parking','cache'):raise ValueError('unsupported D16 state kind')
 root=Path(owner.directory)/'dev_D16'/('native_'+kind);root.mkdir(parents=True,exist_ok=False);copied=_copy_sources(root,wrapper);arms=[]
 for restored in (False,True):
  for repeat in (0,1):
   name=(('restore' if restored else 'control') if kind=='parking' else ('warm' if restored else 'cold'))+'_'+str(repeat)
   value=owner.service(name,lambda arm,current:_operation(arm,current),health_only=True,max_running_requests=4,file_only=True,arm_root=root,execution=owner.options.rid+':'+kind+':'+name,inputs=[ids],kind=kind);arms.append({'name':name,'pre_popen':value})
 _write_new(root/'file_only_collection.json',{'schema':'ft_r040a_d16_file_only/v1','kind':kind,'arms':arms,'source_copy':copied,'measurement_created':False});return {'root':str(root),'arms':arms,'file_only':True,'measurement_created':False}
def collect_native_processes(owner,inputs,*,slots,wrapper,file_dry_run=False,**kwargs):
 if not file_dry_run:return _frozen().collect_native_processes(owner,inputs,slots=slots,wrapper=wrapper,**kwargs)
 return _file_collect(owner,inputs,slots=slots,wrapper=wrapper,interleave=kwargs.get('interleave',False))
def collect_parking_processes(owner,ids,*,wrapper,file_dry_run=False,**kwargs):
 if not file_dry_run:return _frozen().collect_parking_processes(owner,ids,wrapper=wrapper,**kwargs)
 return _file_state(owner,ids,kind='parking',wrapper=wrapper)
def collect_cache_processes(owner,ids,*,wrapper,file_dry_run=False,**kwargs):
 if not file_dry_run:return _frozen().collect_cache_processes(owner,ids,wrapper=wrapper,**kwargs)
 return _file_state(owner,ids,kind='cache',wrapper=wrapper)
