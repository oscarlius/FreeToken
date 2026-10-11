"""Test-private CPU hardware backend for the actual D17 adapter lifecycle.

Endpoint receipts and tiny tensors here are explicitly synthetic. They prove
reader and cleanup interfaces, never real model generation or R041 admission.
"""
import argparse, hashlib, importlib.util, json, os
from pathlib import Path
import subprocess, sys
from types import SimpleNamespace
import torch

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec)
 sys.modules[name]=obj;spec.loader.exec_module(obj);return obj

def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as f:json.dump(value,f)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--stage',type=Path,required=True)
 parser.add_argument('--scenario',choices=('success','cold_not_met','warm_not_met','request_error','cold_stop_error','warm_stop_error'),required=True)
 args=parser.parse_args();stage=args.stage.resolve();assert stage.is_relative_to(Path('/data2/FreeToken/runs/dev_D16'))
 assert os.environ['CUDA_VISIBLE_DEVICES']=='' and not torch.cuda.is_initialized()
 source=stage/'source_tools';sys.path.insert(0,str(source))
 adapter=module('d17_fixture_adapter',source/'d17_gpu_gate_runner.py')
 gpu,artifacts,raw=adapter.retained_modules()
 inherited=gpu.Run; protocol=gpu.protocol
 globals_=protocol['Runner'].__init__.__globals__
 lock=stage/(args.scenario+'.cpu_fixture.lock');assert lock!=Path('/data2/_shared/gpu.lock')
 protocol['LOCK']=globals_['LOCK']=lock;globals_['SCR']=source/'helpers'
 owned=module('d17_fixture_owned_stop',source/'t17_owned_launch_protocol.py')
 selection=module('d17_fixture_selection',source/'t17_continuation_selection.py')
 doc=selection.load_realinput28(stage/'real_inputs.json');rows={row['name']:row for row in doc['cases']}
 cases=adapter.execution_cases(doc)
 assert all(case['context']==rows[case['name']]['expected_ngram'] for case in cases)
 calls=[];instances=[]
 class CPU(inherited):
  def __init__(self,options):
   super().__init__(options);instances.append(self);self.active_case=None;self.active_label=None
   self.parser=lambda path: {'model_path':'fixture-model','server_port':'fixture-port','special_token_ckpt':'True','_unique_suffix':repr('.pid=1' if 'CONTROL' in path else '.pid=2')}
  def spawn(self,label):
   assert self.proc is None
   self.active_label=label
   self.proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],start_new_session=True,env=dict(os.environ,CUDA_VISIBLE_DEVICES=''))
   identity=adapter._identity(self);calls.append({'kind':'spawn','label':label,'identity':identity})
  def run_arm(self,name,wt,commit,d0,**kwargs):
   assert d0 is False and kwargs['layer_major'] is True
   arm=self.directory/name;arm.mkdir();self.spawn(name)
   try:
    (arm/'prefill_seq.txt').write_text('CPU synthetic business sequence')
    mismatch=args.scenario=='cold_not_met' and name.startswith('CANDIDATE')
    write(arm/'det.json',{'text':'other' if mismatch else 'CPU synthetic cold','events':1,'record':{'built_tokens':32052,'cached_tokens':0,'prompt_tokens':32052,'completion_tokens':128,'ttft_s':1,'cold_id':'CPU fixture cold'}})
    calls.append({'kind':'cold_fixture','label':name,'d0':False})
    return arm
   finally:self.stop()
  def service(self,name,operation,**kwargs):
   assert kwargs['health_only'] is True
   arm=self.directory/name;arm.mkdir();(arm/'dump').mkdir()
   self.active_case=next(case for case in cases if name.startswith(case['name']+'-'))
   self.spawn(name)
   for filename in ('SERVE_CMD.txt','environment.json'):
    (arm/filename).write_text('CPU synthetic '+filename)
   write(arm/'compiled_extensions.json',self.extensions)
   try:return operation(arm)
   finally:self.stop()
  def request(self,arm,label,ids,cached,maximum):
   case=self.active_case;assert ids==case['donor' if label=='donor' else 'query']
   assert cached==(0 if label=='donor' else case['length']) and maximum==(2 if label=='donor' else 128)
   if args.scenario=='request_error' and label=='hit':raise RuntimeError('CPU fixture request error')
   uid=label;sha=artifacts.ids_sha(ids);obs=arm/'observations.jsonl'
   current=[json.loads(line) for line in obs.read_text().splitlines()] if obs.exists() else []
   start=len(current)
   current.extend([{'kind':'input','uid':uid,'input_ids':ids,'input_length':len(ids),'ids_int32le_sha256':sha,'sampling':{'temperature':0.0,'max_tokens':maximum}},
                   {'kind':'admitted','uid':uid,'prompt_tokens':len(ids),'cached_tokens':cached},
                   {'kind':'prefill','uid':uid,'cached_tokens':cached}])
   if label=='hit':current.append({'kind':'restore-device','uid':uid,'cached_tokens':cached,'src':0,'dst':1})
   tokens=[17]*maximum
   mismatch=args.scenario=='warm_not_met' and '-d17-' in self.active_label and label=='hit'
   if mismatch:tokens[0]=18
   current.extend({'kind':'token','uid':uid,'token':token,'finished':index==maximum-1} for index,token in enumerate(tokens))
   obs.write_text(''.join(json.dumps(row)+'\n' for row in current))
   response={'uid':uid,'text':'CPU synthetic output','finished':True,'finish_reason':'length','usage':{'prompt_tokens':len(ids),'cached_tokens':cached,'completion_tokens':maximum},'input_ids_sha256':sha}
   raw_response=arm/(label+'_response.json');write(raw_response,response)
   write(arm/(label+'.json'),{'payload':{'input_ids':ids,'max_tokens':maximum},'response':response,'status':200,'response_sha256':artifacts.sha(raw_response),'expected_input_ids_sha256':sha,'observation_range':{'start':start,'end':len(current)},'raw_response_file':raw_response.name})
   files={}
   for role in adapter.ROLES:
    name=label+'_'+role.replace(':','_')+'.pt'
    before=torch.tensor(case['context'],dtype=torch.int32).reshape(1,1,2) if role=='slot:ple_ngram_ctx' else torch.arange(6,dtype=torch.float32).reshape(2,1,3)
    value=before if label=='donor' else before.repeat(1,2,1)
    torch.save(value,arm/'dump'/name);files[role]=name
   record={'kind':'donate' if label=='donor' else 'resume-device','uid':uid,'length':case['length'],'dev_slots':[0] if label=='donor' else [0,1],'seq':1 if label=='donor' else 2,'files':files}
   if label=='hit':record['note']=json.dumps({'src':0,'dst':1})
   with (arm/'dump/index.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
   # The retained raw reader, rather than this backend, validates each receipt.
   evidence=artifacts.request_evidence(arm,label,cached,maximum)
   assert len(evidence['tokens'])==maximum
   calls.append({'kind':'synthetic_receipt','label':label,'input_sha256':sha})
   return response
  def stop(self):
   if self.proc is None:return
   fail=(args.scenario=='cold_stop_error' and self.active_label.startswith('CONTROL')) or (args.scenario=='warm_stop_error' and '-warm' in self.active_label)
   if fail:
    calls.append({'kind':'stop_failed','pid':self.proc.pid,'lock_present':lock.exists()})
    raise RuntimeError('CPU fixture stop failure')
   proc=self.proc;owned.stop_owned_process(proc,term_timeout=5,kill_timeout=5);proc.wait(timeout=5)
   assert not owned.owned_group_alive(proc.pid);calls.append({'kind':'stop','pid':proc.pid});self.proc=None
 gpu.Run=CPU
 options=SimpleNamespace(run=True,rid='CPU-D17-'+args.scenario,gate='D17',batch=1,directory=stage/('replay_'+args.scenario),control_worktree=Path('/data2/FreeToken/wt/e2d14-schedule'),candidate_worktree=Path('/data2/FreeToken/wt/e2base1'))
 result=None;error=None
 try:result=adapter.execute(options,protocol=protocol,gpu=gpu,artifacts=artifacts,raw=raw,cases=cases)
 except RuntimeError as caught:error=str(caught);assert 'CPU fixture' in error
 owner=instances[0]
 if args.scenario.endswith('stop_error'):
  assert error and owner.proc is not None and lock.exists() and owned.owned_group_alive(owner.proc.pid)
  proc=owner.proc;owned.stop_owned_process(proc,term_timeout=5,kill_timeout=5);proc.wait(timeout=5);assert not owned.owned_group_alive(proc.pid)
  owner.proc=None;owner.lock_release();calls.append({'kind':'fixture_recovery','pid':proc.pid})
 assert owner.proc is None and not lock.exists() and not torch.cuda.is_initialized()
 status=json.loads(owner.status.read_text());assert status['card']=='T16' and status['gate']=='D17'
 if args.scenario=='success':
  assert result['verdict']=='measurements_pass_pending_independent_review' and len(result['cases'])==4
  assert len([row for row in calls if row['kind']=='spawn'])==10
  origins=[]
  for case in cases:
   left=json.loads((owner.directory/(case['name']+'-d14-warm')/'compiled_extensions.json').read_text())
   right=json.loads((owner.directory/(case['name']+'-d17-warm')/'compiled_extensions.json').read_text())
   assert {k:v['sha256'] for k,v in left.items()}=={k:v['sha256'] for k,v in right.items()}
   assert {k:v['path'] for k,v in left.items()}!={k:v['path'] for k,v in right.items()}
   origins.append({'case':case['name'],'control':left,'candidate':right})
  write(stage/'actual_compiled_origins.json',{'cpu_import_only':True,'origins':origins})
 elif args.scenario.endswith('not_met'):assert result['verdict']=='not_met'
 else:
  assert error and status['state']=='failed' and (owner.directory/'failed_harness.json').is_file()
 births=[row['identity']['execution_id'] for row in calls if row['kind']=='spawn'];assert len(births)==len(set(births))
 write(stage/(args.scenario+'_lifecycle.json'),{'verdict':'PASS','fixture_only':True,'synthetic_endpoints':True,'synthetic_states':True,'admitted':False,'gpu_started':False,'model_generation':False,'scenario':args.scenario,'calls':calls,'error':error})
 print(json.dumps({'scenario':args.scenario,'verdict':'PASS','fixture_only':True}))
if __name__=='__main__':main()
