"""Fail-closed D09 T17 v2 runner.  GPU execution requires a sealed root admission."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, signal, socket, struct, subprocess, sys, time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

HERE=Path(__file__).resolve().parent; RID='E2-D09-T17-night-20261009'; ROOT=Path('/data2/FreeToken')
INPUTS=HERE/'D09_T17_EXACT_INPUTS.json'; PROVENANCE=HERE.parent/'d09_t16_night_v1/d09_native_provenance_v1.json'
WT=ROOT/'wt/d09-message-boundary-v1'; CANDIDATE='c17b69a46cd512fbf3d127d3879bce92caae457b'
RUNROOT=Path(os.environ.get('FT_D09_T17_V3_RUNROOT',str(ROOT/'runs/dev_D09'))); PORTS=(31501,31502,31503,31504,31505,31506,31507,31508,31509,31510,31511,31512)
ROW=__import__('re').compile(r'Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def idsha(ids): return hashlib.sha256(struct.pack('<%di'%len(ids),*ids)).hexdigest()
def put(p,v):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as h: json.dump(v,h,ensure_ascii=False,sort_keys=True,indent=2);h.write('\n')
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);assert s and s.loader;s.loader.exec_module(m);return m
def d07():
 m=load(PROVENANCE.parent/'d07_g3g4_prepare.py','d09_t17_d07');m.CANDIDATE=CANDIDATE;m.RID=RID;return m
def tooling(): return {n:sha(HERE/'tooling'/n) for n in ('t17_d14_exact_ids.py','t17_d14_observe.py','t17_d14_startup.py')}
def cfg():
 data=json.loads(INPUTS.read_text()); assert sha(PROVENANCE)=='ed58778c314e6d6def818445b0040d173591eb86868d572a6585d18eab4a60f5'
 out=[];i=0
 for cell_index,cell in enumerate(data['cells']):
  for kind in ('coldA','coldB','hot'):
   api,tcp=PORTS[i*2:i*2+2];i+=1; arm=RUNROOT/RID/'services'/f'{kind}_c{cell_index}_p{cell["boundary"]}_t{cell["tail"]}'
   argv=['numactl','--cpunodebind=0,1','--interleave=all',str(ROOT/'venv/bin/python'),'-u',str(arm/'t17_d14_startup.py'),'serve','--port',str(api),'--model-path',str(ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'),'--host','127.0.0.1','--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--max-running-requests','2','--kv-reserve-tokens','49152','--max-seq-len-override','49152','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--enable-message-boundary-ckpt','--prefill-layer-major','--mamba-host-slots','0']
   q=[{'role':'target','ids':cell['target_ids'],'sha256':cell['target_ids_sha256']}];
   if kind=='hot':q.insert(0,{'role':'donor','ids':cell['donor_ids'],'sha256':cell['donor_ids_sha256']})
   out.append({'name':arm.name,'kind':kind,'cell_index':cell_index,'boundary':cell['boundary'],'tail':cell['tail'],'ports':[api,tcp],'arm':str(arm),'argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'requests':q})
 return {'schema':'ft_d09_t17_v2/v1','rid':RID,'candidate':CANDIDATE,'inputs_sha256':sha(INPUTS),'provenance_sha256':sha(PROVENANCE),'runner_sha256':sha(__file__),'tooling_sha256':tooling(),'services':out,'budget':{'services':6,'calls':8,'max_tokens':32}}
def validate_candidate():
 """Read the actual candidate tree, feature source, and pinned native bytes."""
 if WT.is_symlink():raise RuntimeError('candidate worktree is symlinked')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 if head!=CANDIDATE or dirty:raise RuntimeError('candidate HEAD or tracked cleanliness differs')
 source=(WT/'python/freetoken/server/args.py').read_text(encoding='utf-8')
 if '--enable-message-boundary-ckpt' not in source or 'message_boundary_ckpt' not in source:raise RuntimeError('D09 flag source missing')
 native=json.loads(PROVENANCE.read_text())
 if native.get('candidate_commit')!=CANDIDATE or sha(PROVENANCE)!='ed58778c314e6d6def818445b0040d173591eb86868d572a6585d18eab4a60f5':raise RuntimeError('native provenance differs')
 checked={}
 for name,wanted in native['regular_extensions']['candidate']['sha256'].items():
  p=WT/'python/freetoken/kernel'/(name+'.cpython-310-x86_64-linux-gnu.so')
  if not p.is_file() or sha(p)!=wanted or p.stat().st_size!=native['regular_extensions']['candidate']['size'][name]:raise RuntimeError('native extension manifest differs: '+name)
  checked[name]={'sha256':wanted,'size':p.stat().st_size}
 return {'head':head,'tracked_clean':True,'feature_flag':'--enable-message-boundary-ckpt','native_extensions':checked,'provenance_sha256':sha(PROVENANCE)}
def check_admission(path,c,g=None):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('sealed root admission required')
 a=json.loads(path.read_text()); wanted={'root_approved':True,'rid':RID,'candidate':CANDIDATE,'inputs_sha256':c['inputs_sha256'],'runner_sha256':c['runner_sha256'],'tooling_sha256':c['tooling_sha256'],'required_gates':{'T16':'passed'}}
 if any(a.get(k)!=v for k,v in wanted.items()):raise RuntimeError('root admission binding differs')
 closure=a.get('t16_closure')
 if not isinstance(closure,dict) or set(closure)!={'rid','verdict','round_json_sha256','manifest_sha256'}:raise RuntimeError('sealed T16 closure binding absent')
 if closure['rid']!='E2-D09-T16-night-20261009' or closure['verdict']!='kept':raise RuntimeError('T17 requires the formal kept D09 T16 closure')
 if g is not None:
  round_json=g.require_closed_round(closure['rid'],closure['verdict']);manifest=round_json.with_name('MANIFEST.sha256')
  if sha(round_json)!=closure['round_json_sha256'] or sha(manifest)!=closure['manifest_sha256']:raise RuntimeError('sealed T16 closure hash differs')
 return a
def pair_probe(ports):
 held=[]
 try:
  for p in ports:s=socket.socket();held.append(s);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',p))
 finally:
  for s in held:s.close()
def arm_files(s,c):
 arm=Path(s['arm']);arm.mkdir(parents=True); 
 for n,h in c['tooling_sha256'].items(): shutil.copyfile(HERE/'tooling'/n,arm/n);assert sha(arm/n)==h
 return arm
def parse_observations(path,uid):
 rows=[json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]; tokens=[x['token'] for x in rows if x.get('kind')=='token' and str(x.get('uid'))==str(uid)]; errors=[x for x in rows if x.get('kind')=='error' and str(x.get('uid'))==str(uid)]
 return tokens,errors
def evaluate(s,item,raw,window,receipt,obs):
 assert raw['input_ids_sha256']==item['sha256']==receipt['int32le_sha256']; uid=raw['uid']; tokens,errors=parse_observations(obs,uid); assert not errors and len(tokens)==32
 cache=s['boundary'] if s['kind']=='hot' and item['role']=='target' else 0; fresh=s['tail'] if cache else len(item['ids']); u=raw['usage']; assert u=={'prompt_tokens':cache+fresh,'cached_tokens':cache,'completion_tokens':32}
 r=[tuple(map(int,x)) for x in ROW.findall(window)];assert r and all(x[0]==1 and x[2]==cache for x in r) and sum(x[1] for x in r)==fresh
 return {'ids':tokens,'text':raw['text'],'backend_rows':r,'uid':uid,'input_sha256':item['sha256']}
def fake_sender(arm,s,item):
 uid=str(len(list(arm.glob('request_*.json')))+len(list(arm.glob('call_*.request.json')))+1); receipt={'uid':int(uid),'int32le_sha256':item['sha256']};put(arm/f'input_receipts/{uid}.json',receipt)
 with (arm/'observations.jsonl').open('a',encoding='utf-8') as h:
  for _ in range(32):h.write(json.dumps({'kind':'token','uid':uid,'token':0})+'\n')
 cache=s['boundary'] if s['kind']=='hot' and item['role']=='target' else 0;fresh=s['tail'] if cache else len(item['ids']);window=f'Prefill batch, #new-seq: 1, #new-token: {fresh}, #cached-token: {cache}\n';return {'uid':int(uid),'text':'FILEDRY','input_ids_sha256':item['sha256'],'usage':{'prompt_tokens':cache+fresh,'cached_tokens':cache,'completion_tokens':32}},window,receipt
def filedry():
 c=cfg(); root=HERE/'evidence_cpu_filedry_v4';assert not root.exists(); os.environ['FT_D09_T17_V2_RUNROOT']=str(root); global RUNROOT;RUNROOT=root/'runs';c=cfg(); run=RUNROOT/RID;run.mkdir(parents=True);put(run/'config.json',c);ev={};calls=0
 for s in c['services']:
  arm=arm_files(s,c);(arm/'input_receipts').mkdir();(arm/'observations.jsonl').touch();pair_probe(s['ports']);put(arm/'startup_import.json',{'module_names':['t17_d14_exact_ids','t17_d14_observe'],'arm_files':True})
  for item in s['requests']:
   raw,w,rec=fake_sender(arm,s,item);calls+=1;put(arm/f'request_{calls}.json',{'role':item['role'],'uid':raw['uid']});ev[s['name']+'/'+item['role']]=evaluate(s,item,raw,w,rec,arm/'observations.jsonl')
 cells=[]
 for x in json.loads(INPUTS.read_text())['cells']:
  p,t=x['boundary'],x['tail'];a=ev[f'coldA_p{p}_t{t}/target'];b=ev[f'coldB_p{p}_t{t}/target'];h=ev[f'hot_p{p}_t{t}/target'];same=a['ids']==b['ids'] and a['text']==b['text'];cells.append({'boundary':p,'tail':t,'cold_stable':same,'hot_equals_cold':same and a['ids']==h['ids'] and a['text']==h['text']})
 put(run/'terminal.json',{'rid':RID,'verdict':'cpu_filedry_pass','services':6,'calls':calls,'cells':cells,'real_schema_producer_consumer':True,'gpu_started':False,'service_started':False,'http_started':False,'product_acceptance':False});return run/'terminal.json'
def reserve_pair(ports):
 held=[]
 try:
  for port in ports:
   s=socket.socket();held.append(s);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port))
  return held
 except BaseException:
  for s in held:s.close()
  raise
def release_pair(held):
 for s in held:s.close()

def filedry_v3(name='evidence_cpu_filedry_v7'):
 """Actual fake processes and transport calls exercise all six service arms."""
 global RUNROOT
 root=HERE/name;assert not root.exists();RUNROOT=root/'runs';c=cfg();run=RUNROOT/RID;run.mkdir(parents=True);put(run/'config.json',c)
 evidence={};calls=0;clean=[]
 for s in c['services']:
  arm=arm_files(s,c);(arm/'input_receipts').mkdir();(arm/'observations.jsonl').touch();held=reserve_pair((0,0)); ports=[x.getsockname()[1] for x in held]
  proc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  put(arm/'pid_birth.json',{'pid':proc.pid,'fake_process':True,'ports':ports,'pair_reserved':True})
  try:
   for item in s['requests']:
    raw,w,rec=fake_sender(arm,s,item);calls+=1;put(arm/f'request_{calls}.json',{'role':item['role'],'transport':'fake_exact_ids','uid':raw['uid']});evidence[s['name']+'/'+item['role']]=evaluate(s,item,raw,w,rec,arm/'observations.jsonl')
  finally:
   proc.terminate();proc.wait(timeout=15);release_pair(held);clean.append(s['name']);put(arm/'cleanup.json',{'pid':proc.pid,'returncode':proc.returncode,'ports_released':True})
 cells=[]
 for x in json.loads(INPUTS.read_text())['cells']:
  p,t=x['boundary'],x['tail'];a=evidence[f'coldA_p{p}_t{t}/target'];b=evidence[f'coldB_p{p}_t{t}/target'];h=evidence[f'hot_p{p}_t{t}/target'];stable=a['ids']==b['ids'] and a['text']==b['text'];cells.append({'boundary':p,'tail':t,'cold_stable':stable,'hot_equals_cold':stable and a['ids']==h['ids'] and a['text']==h['text']})
 assert calls==8 and len(clean)==6
 terminal={'schema':'ft_d09_t17_filedry/v3','rid':RID,'runner_sha256':sha(__file__),'services':6,'calls':calls,'cells':cells,'fake_processes_cleaned':clean,'post_cleanup_closed':True,'gpu_started':False,'service_started':False,'http_started':False,'compile_started':False,'product_acceptance':False}
 put(run/'terminal.json',terminal);return run/'terminal.json'

class PostCleanupRebindFailure(RuntimeError):
 def __init__(self,arm,cause):super().__init__(f'post-cleanup port rebind failed for {arm}: {cause!r}');self.arm=arm;self.cause=repr(cause)

def fake_service_loop(c,run,fail_rebind=False):
 """CPU transport substitute used only by the injected FILEdry child."""
 evidence={};calls=0;clean=[]
 for s in c['services']:
  arm=arm_files(s,c);(arm/'input_receipts').mkdir();(arm/'observations.jsonl').touch();held=reserve_pair((0,0));ports=[x.getsockname()[1] for x in held]
  proc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  put(arm/'pid_birth.json',{'pid':proc.pid,'fake_process':True,'ports':ports,'pair_reserved':True})
  try:
   for item in s['requests']:
    raw,w,rec=fake_sender(arm,s,item);calls+=1;put(arm/f'call_{calls}.request.json',{'role':item['role'],'transport':'fake_exact_ids','uid':raw['uid'],'input_sha256':item['sha256']});put(arm/f'call_{calls}.response.json',raw);evidence[(s['kind'],s['cell_index'],item['role'])]=evaluate(s,item,raw,w,rec,arm/'observations.jsonl')
  finally:
   proc.terminate();proc.wait(timeout=15);release_pair(held)
   try:
    if fail_rebind and not clean: raise OSError(98,'Address already in use')
    rebound=reserve_pair((0,0));rebound_ports=[x.getsockname()[1] for x in rebound];release_pair(rebound)
   except BaseException as exc:
    put(arm/'post_cleanup_rebind_failure.json',{'arm':s['name'],'exception':repr(exc),'unsafe':True})
    raise PostCleanupRebindFailure(s['name'],exc) from exc
   put(arm/'post_cleanup_rebind.json',{'api_port':rebound_ports[0],'tcpstore_port':rebound_ports[1],'both_rebound_and_released':True})
   clean.append(s['name']);put(arm/'cleanup.json',{'pid':proc.pid,'returncode':proc.returncode,'ports_released':True,'post_cleanup_rebind':True})
 cells=[]
 for cell_index,x in enumerate(json.loads(INPUTS.read_text())['cells']):
  p,t=x['boundary'],x['tail'];a=evidence[('coldA',cell_index,'target')];b=evidence[('coldB',cell_index,'target')];h=evidence[('hot',cell_index,'target')];stable=a['ids']==b['ids'] and a['text']==b['text'];cells.append({'cell_index':cell_index,'boundary':p,'tail':t,'cold_stable':stable,'hot_equals_cold':stable and a['ids']==h['ids'] and a['text']==h['text']})
 assert calls==8 and len(clean)==6
 return calls,clean,cells

class FileDryLifecycle:
 def __init__(self,g):self.g=g
 def verified_module(self,*_):return self
 def next_batch(self,_):return 1
 def reserve_process(self,helper,batch,rid,argv,receipt,reserved):
  put(receipt,reserved|{'state':'launched','batch_pid':71});return json.loads(receipt.read_text())

class FileDryGate:
 def __init__(self,root):self.root=root;self.LOCK=root/'task_owned_fake.lock';self.ROUNDS=root/'rounds';self.ATOMIC_HELPER_SHA='filedry';self.owner=None
 def require_closed_round(self,rid,verdict):
  assert (rid,verdict)==('E2-D09-T16-night-20261009','kept');p=self.root/'sealed_t16'/rid;p.mkdir(parents=True,exist_ok=True);q=p/'round.json';m=p/'MANIFEST.sha256'
  if not q.exists():q.write_text('{"formal_verdict":"kept"}\n',encoding='utf-8');m.write_text('round.json\n',encoding='utf-8')
  return q
 def argv_sha256(self,argv):return hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()
 def process_birth(self):return {'fake_pid':71,'identity':'filedry-child'}
 def process_identity(self,_):return self.process_birth()
 def publish_child_binding(self,receipt,got,identity,lifecycle=None):
  d=json.loads(receipt.read_text());d['child']=identity;receipt.write_text(json.dumps(d,sort_keys=True,indent=2)+'\n',encoding='utf-8');return d
 def load_owned_lifecycle(self):return FileDryLifecycle(self)
 def take_d07_gpu_lock(self,rid,batch):
  assert not self.LOCK.exists();self.LOCK.write_text(json.dumps({'rid':rid,'batch':batch}),encoding='utf-8');self.owner={'rid':rid,'batch':batch};return self.owner
 def release_d07_gpu_lock(self,owner):
  assert owner==self.owner and self.LOCK.exists();self.LOCK.unlink()
 def require_gpu_idle(self):return {'fake_gpu_idle':True}

class FileDryDeps:
 def __init__(self,root,fail_rebind=False):self.root=root;self.g=FileDryGate(root);self.runroot=root/'runs';self.fail_rebind=fail_rebind
 def validate_candidate(self):
  return {'head':CANDIDATE,'tracked_clean':True,'feature_flag':'--enable-message-boundary-ckpt','native_extensions':'filedry-bound','provenance_sha256':sha(PROVENANCE),'source_sha256':sha(Path(__file__))}
 def execute(self,c,run):return fake_service_loop(c,run,self.fail_rebind)

def filedry_v6_e2e(name='evidence_cpu_filedry_v15',fail_rebind=False):
 """Run the production controller and child functions with only task-owned fakes."""
 root=HERE/name;assert not root.exists();root.mkdir();deps=FileDryDeps(root,fail_rebind);old=RUNROOT
 try:
  globals()['RUNROOT']=deps.runroot;c=cfg();closure=deps.g.require_closed_round('E2-D09-T16-night-20261009','kept');manifest=closure.with_name('MANIFEST.sha256');admission=root/'admission.json';put(admission,{'root_approved':True,'rid':RID,'candidate':CANDIDATE,'inputs_sha256':c['inputs_sha256'],'runner_sha256':c['runner_sha256'],'tooling_sha256':c['tooling_sha256'],'required_gates':{'T16':'passed'},'t16_closure':{'rid':'E2-D09-T16-night-20261009','verdict':'kept','round_json_sha256':sha(closure),'manifest_sha256':sha(manifest)}});os.chmod(admission,0o444)
  binding=controller(admission,deps=deps);child(admission,binding['batch'],root/'launch.json',deps=deps)
  terminal=deps.runroot/RID/'terminal.json';value=json.loads(terminal.read_text());put(root/'e2e_terminal.json',value|{'controller_child_chain':{'controller':True,'child':True,'sealed_t16':True,'candidate_source_native':True,'atomic_receipt':True,'task_owned_lock':str(deps.g.LOCK),'post_cleanup_lock_released':not deps.g.LOCK.exists()}});return root/'e2e_terminal.json'
 finally:globals()['RUNROOT']=old

def child_argv(admission,batch,receipt): return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--admission',str(admission),'--batch',str(batch),'--launch-receipt',str(receipt)]
def require_receipt(g,receipt,batch,admission):
 deadline=time.monotonic()+30;expected=g.argv_sha256(child_argv(admission,batch,receipt));mine=g.process_birth()
 while time.monotonic()<deadline:
  if receipt.is_file() and not receipt.is_symlink():
   d=json.loads(receipt.read_text())
   if d.get('state')=='launched' and d.get('child')==mine:
    if d.get('rid')!=RID or d.get('batch')!=batch or d.get('candidate_commit')!=CANDIDATE or d.get('argv_sha256')!=expected:raise RuntimeError('child receipt binding differs')
    return d
  time.sleep(.05)
 raise RuntimeError('child receipt was not published')
def controller(admission,deps=None):
 c=cfg();g=deps.g if deps else d07();check_admission(admission,c,g);(deps.validate_candidate() if deps else validate_candidate())
 if g.LOCK.exists() or g.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists; R047 remains owner')
 lifecycle=g.load_owned_lifecycle();helper=lifecycle.verified_module(ROOT/'runs/plan_batches/e2_launch.py',g.ATOMIC_HELPER_SHA,'d09_t17_atomic');batch=helper.next_batch(g.ROUNDS);receipt=(deps.root/'launch.json') if deps else HERE/'runs'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(admission,batch,receipt)
 reserved={'schema':'ft_d09_t17_launch/v3','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':g.argv_sha256(argv),'controller':g.process_birth(),'scope':{'services_max':6,'generation_calls_max':8}}
 got=lifecycle.reserve_process(helper,batch,RID,argv,receipt,reserved);return g.publish_child_binding(receipt,got,g.process_identity(got['batch_pid']),lifecycle=lifecycle)
def child(admission,batch,receipt,deps=None):
 global RUNROOT
 c=cfg();g=deps.g if deps else d07();check_admission(admission,c,g);candidate=deps.validate_candidate() if deps else validate_candidate();require_receipt(g,receipt,batch,admission);RUNROOT=(deps.runroot if deps else HERE/'runs'/f'{RID}_batch{batch}');c=cfg();run=RUNROOT/RID;assert not run.exists();owner=g.take_d07_gpu_lock(RID,batch);calls=0;clean=[];cells=[];error=None;safe_cleanup=True
 try:
  g.require_gpu_idle();run.mkdir(parents=True);put(run/'config.json',c);put(run/'candidate_validation.json',candidate)
  if deps:
   calls,clean,cells=deps.execute(c,run)
   for cell in cells:put(run/f"cell_c{cell['cell_index']}_p{cell['boundary']}_t{cell['tail']}.json",cell)
  else:
   opener=build_opener(ProxyHandler({}));ev={}
   for s in c['services']:
    arm=arm_files(s,c);(arm/'input_receipts').mkdir();(arm/'observations.jsonl').touch();held=reserve_pair(s['ports']);release_pair(held);env=g.clean_environment(WT);env.update(PYTHONPATH=str(WT/'python'),FT_T17_INPUT_RECEIPTS=str(arm/'input_receipts'),FT_T17_OBSERVATIONS=str(arm/'observations.jsonl'),FT_DEV_STATE_DUMP=str(arm/'state_dump'))
    with (arm/'serve.log').open('xb') as log:proc=subprocess.Popen(s['argv'],cwd=arm,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    put(arm/'pid_birth.json',{'pid_identity':g.process_identity(proc.pid),'argv':s['argv'],'owner':owner})
    try:
     endpoint='http://127.0.0.1:'+str(s['ports'][0]);deadline=time.monotonic()+1800
     while True:
      if proc.poll() is not None:raise RuntimeError('service exited before health')
      if time.monotonic()>deadline:raise TimeoutError('health timeout')
      try:
       with opener.open(endpoint+'/health',timeout=10) as r:
        if json.loads(r.read()).get('status')=='ok':break
      except (OSError,ValueError):time.sleep(2)
     for item in s['requests']:
      req=Request(endpoint+'/internal/t17/exact-ids',data=json.dumps({'input_ids':item['ids'],'max_tokens':32}).encode(),headers={'Content-Type':'application/json'});offset=(arm/'serve.log').stat().st_size
      with opener.open(req,timeout=1800) as response:raw=json.loads(response.read())
      window=(arm/'serve.log').read_bytes()[offset:].decode(errors='strict');receipt_doc=json.loads(next((arm/'input_receipts').glob(str(raw['uid'])+'.json')).read_text());calls+=1;put(arm/f'call_{calls}.response.json',raw);put(arm/f'call_{calls}.binding.json',{'role':item['role'],'input_sha256':item['sha256'],'receipt_sha256':sha(next((arm/'input_receipts').glob(str(raw['uid'])+'.json'))),'observations_path':str(arm/'observations.jsonl'),'serve_window_sha256':hashlib.sha256(window.encode()).hexdigest()});ev[(s['kind'],s['cell_index'],item['role'])]=evaluate(s,item,raw,window,receipt_doc,arm/'observations.jsonl')
    finally:
     g.load_owned_lifecycle().stop_owned_process(proc,120,30)
     if g.load_owned_lifecycle().owned_group_alive(proc.pid):raise RuntimeError('owned group alive')
     clean.append(s['name']);g.require_gpu_idle()
     try:
      rebound=reserve_pair(s['ports']);release_pair(rebound)
     except BaseException as exc:
      put(arm/'post_cleanup_rebind_failure.json',{'arm':s['name'],'exception':repr(exc),'unsafe':True})
      raise PostCleanupRebindFailure(s['name'],exc) from exc
     put(arm/'post_cleanup_rebind.json',{'api_port':s['ports'][0],'tcpstore_port':s['ports'][1],'both_rebound_and_released':True})
     put(arm/'cleanup.json',{'pid':proc.pid,'group_alive':False,'post_cleanup_rebind':True})
   for cell_index,x in enumerate(json.loads(INPUTS.read_text())['cells']):
    p,t=x['boundary'],x['tail'];a=ev[('coldA',cell_index,'target')];b=ev[('coldB',cell_index,'target')];h=ev[('hot',cell_index,'target')];stable=a['ids']==b['ids'] and a['text']==b['text'];cell={'cell_index':cell_index,'boundary':p,'tail':t,'cold_stable':stable,'hot_equals_cold':stable and a['ids']==h['ids'] and a['text']==h['text']};put(run/f'cell_c{cell_index}_p{p}_t{t}.json',cell);cells.append(cell)
 except PostCleanupRebindFailure as exc:error=repr(exc);safe_cleanup=False
 except BaseException as exc:error=repr(exc)
 finally:
  try:
   g.require_gpu_idle()
   if not safe_cleanup:raise RuntimeError('post-cleanup rebind failed')
   g.release_d07_gpu_lock(owner)
  except BaseException as exc:
   if run.exists():put(run/'unsafe_cleanup.json',{'error':repr(exc),'gpu_lock_preserved':True,'outcome':'failed_harness','product_acceptance':False,'post_cleanup_closed':False})
   raise RuntimeError('unsafe cleanup preserves lock: '+repr(exc))
  if run.exists():
   artifacts={str(p.relative_to(run)):sha(p) for p in run.rglob('*') if p.is_file() and p.name!='terminal.json'}
   proposed='kept' if error is None and all(x['cold_stable'] and x['hot_equals_cold'] for x in cells) else 'not_met'
   put(run/'terminal.json',{'schema':'ft_d09_t17_terminal/v4','rid':RID,'error':error,'services_cleaned':clean,'calls':calls,'cells':cells,'proposed_verdict':proposed,'artifact_sha256':artifacts,'post_cleanup_closed':True,'gpu_lock_released':True,'independent_review_required':True,'product_acceptance':False})
 if error:raise RuntimeError(error)
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args()
 if a.filedry and not a.run:print(filedry_v6_e2e());return
 if a.run and a.admission and a.owned_child and a.batch and a.launch_receipt:child(a.admission,a.batch,a.launch_receipt);return
 if a.run and a.admission and not a.owned_child and a.batch is None and a.launch_receipt is None:controller(a.admission);return
 p.error('select --filedry or --run --admission')
if __name__=='__main__':main()
