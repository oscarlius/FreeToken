"""R040a's actual file-only collector path; no service, request, lock, or batch."""
from __future__ import annotations
import getpass, hashlib, importlib.util, json, os, socket
from pathlib import Path

HERE=Path(__file__).resolve().parent; RID='E2-R040a'; ROOT=Path('/data2/FreeToken'); WT=ROOT/'wt/e2base1'
SOURCES=('r040a_d16_dryrun_v1.py','r040a_d16_supplement_prepare_v2.py','r040a_d16_process_collection_v3.py','r040a_d16_supplement_prepare.py','d16_native_capture_shutdown_v3.py','d16_native_process_collection_v2.py')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def _load():
 p=HERE/'r040a_d16_supplement_prepare.py';s=importlib.util.spec_from_file_location('r040a_dry_source',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def _derived():
 p=HERE/'r040a_d16_process_collection_v3.py';s=importlib.util.spec_from_file_location('r040a_dry_collector',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class FileOnlyOwner:
 def __init__(self,directory,worktree):self.directory=Path(directory);self.worktree=Path(worktree);self.options=type('Options',(),{'rid':RID})()
 def environment(self,wt,arm,d0):return {k:os.environ[k] for k in ('PATH','PYTHONPATH','PYTHONUNBUFFERED','VIRTUAL_ENV','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES') if k in os.environ}
 def serve_argv(self,arm,kind):return [str(self.worktree/'venv/bin/python'),'freetoken','serve','--host','127.0.0.1','--port',str(self.port),'--r040a-file-only',kind]
 def service(self,name,operation,**kwargs):
  if not kwargs.pop('file_only',False):raise RuntimeError('file-only owner refuses formal service')
  kwargs.pop('health_only',None);kwargs.pop('max_running_requests',None);kwargs.pop('mamba_host_slots',None)
  return _derived()._pre_popen_service(self,name,operation,**kwargs)
def dry_run(directory,*,final_entry=None):
 out=Path(directory)
 formal=ROOT/'runs/dev_D16'/RID
 if (out.exists() or out.is_symlink() or out.parent!=formal.parent or not out.name.startswith('.dryrun_R040a_')
     or out.resolve()==formal.resolve() or formal.resolve() in out.resolve().parents or out.resolve() in formal.resolve().parents): raise RuntimeError('dry path is not a new sibling')
 src={n:sha(HERE/n) for n in SOURCES}; _load().prepare(HERE)
 out.mkdir(parents=True)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 if port==8095:raise RuntimeError('forbidden port')
 owner=FileOnlyOwner(out,WT);owner.port=port;collector=_derived();inputs=[[1]*512,[2]*512,[3]*512,[4]*512];long=[5]*5000;wrapper=HERE/'d16_native_capture_shutdown_v3.py'
 results={'batch2':collector.collect_native_processes(owner,inputs[:2],slots=2,wrapper=wrapper,file_dry_run=True),'batch4':collector.collect_native_processes(owner,inputs,slots=4,wrapper=wrapper,file_dry_run=True),'parking':collector.collect_parking_processes(owner,inputs[0],wrapper=wrapper,file_dry_run=True),'cache':collector.collect_cache_processes(owner,inputs[0],wrapper=wrapper,file_dry_run=True),'interleave':collector.collect_native_processes(owner,[inputs[0],long],slots=2,wrapper=wrapper,interleave=True,file_dry_run=True)}
 anchor=[]
 for rep in range(1,4):
  for mode in ('OFF','ON'):
   name=f'{mode}_p{rep}';anchor.append(owner.service(name,lambda arm,current:collector._output_probe(arm,'requests/file_only_output.pt'),file_only=True,arm_root=out,execution=f'{RID}:anchor:{name}',inputs=[],kind='anchor'))
 files=sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
 final_entry=Path(final_entry or HERE/'r040a_d16_supplement_prepare_v2.py').resolve()
 receipt={'schema':'ft_r040a_dry_run/v2','rid':RID,'candidate_commit':'0aa23431e5b800797543bdecbf35a01045131d7d','worktree':str(WT),'script':str(final_entry),'formal_entry':str(final_entry),'dry_runner':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:-1)(),'user':getpass.getuser(),'cwd':os.getcwd(),'port':port,'formal_round_path':str(formal),'receipt_path':str((out/'dry_run_receipt.json').resolve()),'sources':src,'files':files,'arms':results,'anchor_pre_popen':anchor,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'passed':True}
 p=out/'dry_run_receipt.json';p.write_text(json.dumps(receipt,sort_keys=True)+'\n');p.chmod(0o444);return receipt
