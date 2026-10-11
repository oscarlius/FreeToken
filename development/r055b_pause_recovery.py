"""R055b pause/cancel/recovery supplement for the sealed R055a cold arms.

It never replays the six R055a cold arms.  The caller supplies the already
owned private-port request and pause functions; every CUDA measurement is made
by this process immediately around those calls.
"""
from __future__ import annotations
import json, os, time
from pathlib import Path

RID='E2-R055b-gate-D06'; COLD_TOKENS=32052; ACTUAL_INPUT_TOKENS=32064; MAX_TOKENS=128; MEMORY_RATIO='0.88'

def _append(path,row):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True)+'\n')

class ModelProcessMemory:
 """Records only the serving process's torch CUDA allocator state."""
 def __init__(self,path,torch_module,device=0):self.path=Path(path);self.torch=torch_module;self.device=device
 def record(self,event,uid=None,*,error=None):
  try:
   free,total=self.torch.cuda.mem_get_info(self.device)
   row={'schema':'ft_r055b_model_process_cuda/v1','event':event,'uid':uid,'device':self.device,'time_ns':time.time_ns(),'free_bytes':int(free),'total_bytes':int(total),'allocated_peak_bytes':int(self.torch.cuda.max_memory_allocated(self.device)),'reserved_peak_bytes':int(self.torch.cuda.max_memory_reserved(self.device))}
  except BaseException as exc:
   row={'schema':'ft_r055b_model_process_cuda/v1','event':'error','requested_event':event,'uid':uid,'device':self.device,'time_ns':time.time_ns(),'error':repr(error or exc)}
  _append(self.path,row);return row

def request_with_memory(memory,event,uid,request):
 memory.record(event+'_before',uid)
 try:
  value=request();memory.record(event+'_after',uid);return value
 except BaseException as exc:
  memory.record(event+'_error',uid,error=exc);raise

def run_pause_cancel_recovery(*,memory,cold_request,pause_request,uid_before,uid_pause,uid_recovery):
 """Run the approved before -> pause -> cancellation -> recovery sequence."""
 before=request_with_memory(memory,'cold_before',uid_before,cold_request)
 normal=request_with_memory(memory,'pause_request',uid_pause,lambda:pause_request(1.0,5.0))
 cancelled=request_with_memory(memory,'pause_cancel',uid_pause,lambda:pause_request(30.0,0.05))
 recovery=request_with_memory(memory,'recovery_request',uid_recovery,cold_request)
 return {'before':before,'pause':normal,'cancel':cancelled,'recovery':recovery,'built_tokens':COLD_TOKENS,'actual_input_tokens':ACTUAL_INPUT_TOKENS,'max_tokens':MAX_TOKENS,'memory_ratio':MEMORY_RATIO}

def file_dry_run(directory):
 """Exercise the same JSONL/output destinations without torch, network, or service."""
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
 for name in ('model_process_cuda.jsonl','before.json','pause_completed.json','pause_cancel.json','recovery.json'):
  path=directory/name
  with path.open('x',encoding='utf-8') as f:f.write('CPU_FILE_PROBE_ONLY\n')
  if not os.access(path,os.W_OK):raise RuntimeError('unwritable R055b output: '+str(path))
 return {'directory':str(directory),'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False}
