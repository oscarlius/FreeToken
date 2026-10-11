"""Fail-closed D09 T17 v2 runner.  GPU execution requires a sealed root admission."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, signal, socket, struct, subprocess, sys, time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

HERE=Path(__file__).resolve().parent; RID='E2-D09-T17-reapply-bd57-20261010'; ROOT=Path('/data2/FreeToken')
INPUTS=HERE/'D09_T17_EXACT_INPUTS.json'; PROVENANCE=HERE.parent/'protocol_t16/d09_native_provenance_bd57.json'
WT=ROOT/'wt/d09-page-conservation-20261010'; CANDIDATE='bd57cfdccc2a935d46cb0a89b8b36be7a18706de'
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
 data=json.loads(INPUTS.read_text()); assert sha(PROVENANCE)=='aaf7a1d1ee3f329affb1458da917bc689e05c01fbda53dcaaa9ed42fe747c18f'
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
 if native.get('candidate_commit')!=CANDIDATE or sha(PROVENANCE)!=aaf7a1d1ee3f329affb1458da917bc689e05c01fbda53dcaaa9ed42fe747c18f:raise RuntimeError('native provenance differs')
 checked={}
 for name,wanted in native['regular_extensions']['candidate']['sha256'].items():
  p=WT/'python/freetoken/kernel'/(name+'.cpython-310-x86_64-linux-gnu.so')
  if not p.is_file() or sha(p)!=wanted or p.stat().st_size!=native['regular_extensions']['candidate']['size'][name]:raise RuntimeError('native extension manifest differs: '+name)
  checked[name]={'sha256':wanted,'size':p.stat().st_size}
 return {'head':head,'tracked_clean':True,'feature_flag':'--enable-message-boundary-ckpt','native_extensions':checked,'provenance_sha256':sha(PROVENANCE)}

def require_t16_closure(g, closure):
 """Validate the actual sealed night closure without modifying its archive.

 The night D04 closer archived history and the manifest but no per-round copy
 of the writer or old D07 registration pin. Use its pinned external checker.
 """
 if isinstance(g,FileDryGate):
  return g.require_closed_round(closure['rid'],closure['verdict'])
 directory=Path('/data2/_shared/runs/ft_rounds')/closure['rid']
 round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256'
 for path in (directory,round_json,manifest):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222:
   raise RuntimeError('T16 sealed closure path differs')
 if sha(round_json)!=closure['round_json_sha256'] or sha(manifest)!=closure['manifest_sha256']:
  raise RuntimeError('T16 sealed closure hashes differ')
 doc=json.loads(round_json.read_text())
 if (doc.get('round_id')!=closure['rid'] or doc.get('verdict')!='kept'
     or doc.get('actual_services')!=8 or doc.get('actual_generation_calls')!=100
     or doc.get('experimental',{}).get('candidate_commit')!=CANDIDATE):
  raise RuntimeError('T16 formal result identity or count differs')
 for path in directory.rglob('*'):
  if path.is_symlink() or path.stat().st_mode&0o222:
   raise RuntimeError('T16 archive has writable or symlinked member')
 for line in manifest.read_text().splitlines():
  digest,name=line.split(None,1);name=name.lstrip('* ')
  path=directory/name
  if path.is_absolute() and directory.resolve() not in path.resolve().parents:
   raise RuntimeError('T16 manifest escapes archive')
  if not path.is_file() or sha(path)!=digest:
   raise RuntimeError('T16 manifest member changed: '+name)
 for item in doc.get('result_binding',{}).values():
  path=directory/item['path']
  if directory.resolve() not in path.resolve().parents or sha(path)!=item['sha256']:
   raise RuntimeError('T16 result binding differs')
 checker=ROOT/'scripts/round_json_append.py'
 if checker.is_symlink() or not checker.is_file() or sha(checker)!=g.ROUND_WRITER_SHA:
  raise RuntimeError('T16 external history checker changed')
 subprocess.run([str(ROOT/'venv/bin/python'),str(checker),str(directory),'check'],check=True,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return round_json
def check_admission(path,c,g=None):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('sealed root admission required')
 a=json.loads(path.read_text()); wanted={'root_approved':True,'rid':RID,'candidate':CANDIDATE,'inputs_sha256':c['inputs_sha256'],'runner_sha256':c['runner_sha256'],'tooling_sha256':c['tooling_sha256'],'required_gates':{'T16':'passed'}}
 if any(a.get(k)!=v for k,v in wanted.items()):raise RuntimeError('root admission binding differs')
 closure=a.get('t16_closure')
 if not isinstance(closure,dict) or set(closure)!={'rid','verdict','round_json_sha256','manifest_sha256'}:raise RuntimeError('sealed T16 closure binding absent')
 if closure['rid']!='E2-D09-T16-reapply-bd57-20261010' or closure['verdict']!='kept':raise RuntimeError('T17 requires the formal kept D09 T16 retry1 closure')
 if g is not None:
  round_json=require_t16_closure(g,closure);manifest=round_json.with_name('MANIFEST.sha256')
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
class BoundaryStateError(RuntimeError):
 pass

STATE_ROLES=("conv_states","recurrent_states","slot:ple_conv","slot:ple_ngram_ctx")
def _json_lines(path):
 try:return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
 except (OSError,json.JSONDecodeError) as exc:raise BoundaryStateError(f"unreadable boundary evidence: {path}") from exc
def boundary_state_hash(dump, *, source, uid, length, input_sha256, prefix_sha256):
 """Bind a complete real FT boundary dump before output equality is considered.

 FT writes conv/recurrent state plus the PLE slot states; GDN is the algorithm,
 not a separate dump key.  The receipt is emitted by the startup observer after
 snapshot_message_boundary and binds the exact-ID input receipt to the index row.
 """
 dump=Path(dump); receipts=_json_lines(dump/'boundary_receipts.jsonl'); matches=[x for x in receipts if x.get('source')==source and x.get('uid')==uid and x.get('length')==length and x.get('input_ids_sha256')==input_sha256 and x.get('prefix_int32le_sha256')==prefix_sha256]
 if len(matches)!=1:raise BoundaryStateError(f"missing or ambiguous boundary receipt for {source} uid={uid} length={length}")
 receipt=matches[0]; rows=_json_lines(dump/'index.jsonl'); rows=[x for x in rows if x.get('seq')==receipt.get('index_seq') and x.get('kind')=='t17-boundary' and str(x.get('uid'))==str(uid) and x.get('length')==length]
 if len(rows)!=1:raise BoundaryStateError(f"missing or ambiguous boundary index row for {source}")
 files=rows[0].get('files');
 if not isinstance(files,dict) or set(files)!=set(STATE_ROLES):raise BoundaryStateError(f"incomplete FT state roles for {source}")
 digests={}
 for role in STATE_ROLES:
  name=files[role]
  if not isinstance(name,str) or Path(name).name!=name:raise BoundaryStateError(f"unsafe FT state filename for {source}")
  path=dump/name
  if not path.is_file() or path.is_symlink():raise BoundaryStateError(f"missing FT state file {role} for {source}")
  digests[role]=sha(path)
 return hashlib.sha256(json.dumps({'roles':digests,'length':length,'prefix_int32le_sha256':prefix_sha256},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def judge_boundary(c, cell_index, boundary, bindings):
 """Fail before hot/cold output comparison when any real boundary state is absent or differs."""
 hashes=[]
 for source in ('coldA','coldB','hot'):
  service=next(x for x in c['services'] if x['kind']==source and x['cell_index']==cell_index)
  bind=bindings[source]
  hashes.append(boundary_state_hash(Path(service['arm'])/'state_dump',source=source,uid=bind['uid'],length=boundary,input_sha256=bind['input_sha256'],prefix_sha256=bind['prefix_sha256']))
 if len(set(hashes))!=1:raise BoundaryStateError('boundary state mismatch; discard output comparison')
 return hashes[0]

def evaluate_cell(c, cell_index, evidence):
 x=json.loads(INPUTS.read_text())['cells'][cell_index];p,t=x['boundary'],x['tail']
 a=evidence[('coldA',cell_index,'target')];b=evidence[('coldB',cell_index,'target')]
 h=evidence[('hot',cell_index,'target')];donor=evidence[('hot',cell_index,'donor')]
 target=c['services'][cell_index*3]['requests'][0];prefix=idsha(target['ids'][:p])
 bindings={'coldA':{'uid':a['uid'],'input_sha256':a['input_sha256'],'prefix_sha256':prefix},
           'coldB':{'uid':b['uid'],'input_sha256':b['input_sha256'],'prefix_sha256':prefix},
           'hot':{'uid':donor['uid'],'input_sha256':donor['input_sha256'],'prefix_sha256':prefix}}
 state_hash=judge_boundary(c,cell_index,p,bindings)
 stable=a['ids']==b['ids'] and a['text']==b['text']
 return {'cell_index':cell_index,'boundary':p,'tail':t,'boundary_state_sha256':state_hash,
         'cold_stable':stable,'hot_equals_cold':stable and a['ids']==h['ids'] and a['text']==h['text']}
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
 states=Path(run)/'boundary_states';states.mkdir(exist_ok=True)
 for cell_index,x in enumerate(json.loads(INPUTS.read_text())['cells']):
  for source in ('coldA','coldB','hot'):
   put(states/f'{source}_c{cell_index}.json',{'kind':'boundary','uid':7,'length':x['boundary'],'source':source,'state':{'gdn':[cell_index],'conv':[cell_index],'recurrent':[cell_index],'ple':[cell_index]}})
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
 for cell_index,x in enumerate(json.loads(INPUTS.read_text())['cells']):
  target=c['services'][cell_index*3]['requests'][0];hot_donor=next(v for v in c['services'] if v['kind']=='hot' and v['cell_index']==cell_index)['requests'][0]
  for source in ('coldA','coldB','hot'):
   service=next(v for v in c['services'] if v['kind']==source and v['cell_index']==cell_index);dump=Path(service['arm'])/'state_dump';dump.mkdir()
   files={}
   for role in STATE_ROLES:
    filename=f't17-boundary_{cell_index}_{source}_{role.replace(":","_")}.bin';(dump/filename).write_bytes(f'{cell_index}:shared:{role}'.encode());files[role]=filename
   (dump/'index.jsonl').write_text(json.dumps({'seq':1,'kind':'t17-boundary','length':x['boundary'],'uid':str(1),'files':files},sort_keys=True)+'\n',encoding='utf-8')
   with (dump/'boundary_receipts.jsonl').open('x',encoding='utf-8') as h:h.write(json.dumps({'source':source,'uid':1,'length':x['boundary'],'input_ids_sha256':(hot_donor if source=='hot' else target)['sha256'],'prefix_int32le_sha256':idsha(target['ids'][:x['boundary']]),'index_seq':1},sort_keys=True)+'\n')
 cells=[]
 for cell_index,x in enumerate(json.loads(INPUTS.read_text())['cells']):
  p,t=x['boundary'],x['tail'];a=evidence[('coldA',cell_index,'target')];b=evidence[('coldB',cell_index,'target')];h=evidence[('hot',cell_index,'target')];donor=evidence[('hot',cell_index,'donor')];prefix=idsha(c['services'][cell_index*3]['requests'][0]['ids'][:p]);state_hash=judge_boundary(c,cell_index,p,{'coldA':{'uid':a['uid'],'input_sha256':a['input_sha256'],'prefix_sha256':prefix},'coldB':{'uid':b['uid'],'input_sha256':b['input_sha256'],'prefix_sha256':prefix},'hot':{'uid':donor['uid'],'input_sha256':donor['input_sha256'],'prefix_sha256':prefix}});stable=a['ids']==b['ids'] and a['text']==b['text'];cells.append({'cell_index':cell_index,'boundary':p,'tail':t,'boundary_state_sha256':state_hash,'cold_stable':stable,'hot_equals_cold':stable and a['ids']==h['ids'] and a['text']==h['text']})
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
  assert (rid,verdict)==('E2-D09-T16-reapply-bd57-20261010','kept');p=self.root/'sealed_t16'/rid;p.mkdir(parents=True,exist_ok=True);q=p/'round.json';m=p/'MANIFEST.sha256'
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

def filedry_v6_e2e(name='evidence_cpu_filedry_corrected4',fail_rebind=False):
 """Run the production controller and child functions with only task-owned fakes."""
 root=HERE/name;assert not root.exists();root.mkdir();deps=FileDryDeps(root,fail_rebind);old=RUNROOT
 try:
  globals()['RUNROOT']=deps.runroot;c=cfg();closure=deps.g.require_closed_round('E2-D09-T16-reapply-bd57-20261010','kept');manifest=closure.with_name('MANIFEST.sha256');admission=root/'admission.json';put(admission,{'root_approved':True,'rid':RID,'candidate':CANDIDATE,'inputs_sha256':c['inputs_sha256'],'runner_sha256':c['runner_sha256'],'tooling_sha256':c['tooling_sha256'],'required_gates':{'T16':'passed'},'t16_closure':{'rid':'E2-D09-T16-reapply-bd57-20261010','verdict':'kept','round_json_sha256':sha(closure),'manifest_sha256':sha(manifest)}});os.chmod(admission,0o444)
  binding=controller(admission,deps=deps);child(admission,binding['batch'],root/'launch.json',deps=deps)
  terminal=deps.runroot/RID/'terminal.json';value=json.loads(terminal.read_text());put(root/'e2e_terminal.json',value|{'controller_child_chain':{'controller':True,'child':True,'sealed_t16':True,'candidate_source_native':True,'atomic_receipt':True,'task_owned_lock':str(deps.g.LOCK),'post_cleanup_lock_released':not deps.g.LOCK.exists()}});return root/'e2e_terminal.json'
 finally:globals()['RUNROOT']=old

def child_argv(admission,batch,receipt): return [str(ROOT/'venv/bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--admission',str(admission),'--batch',str(batch),'--launch-receipt',str(receipt)]
def wait_gpu_idle(g, timeout=120, clock=time.monotonic, sleep=time.sleep):
 deadline=clock()+timeout
 while True:
  try:return g.require_gpu_idle()
  except RuntimeError:
   if clock()>=deadline:raise
   sleep(min(1, max(0, deadline-clock())))
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
 got=lifecycle.reserve_process(helper,batch,RID,argv,receipt,reserved);birth=g.process_identity(got['batch_pid'])
 if birth is None:raise RuntimeError('child exited before birth binding')
 identity={key:birth[key] for key in ('pid','start_ticks','execution_id')} if 'pid' in birth else birth
 return g.publish_child_binding(receipt,got,identity,lifecycle=lifecycle)
def child(admission,batch,receipt,deps=None):
 global RUNROOT
 c=cfg();g=deps.g if deps else d07();check_admission(admission,c,g);candidate=deps.validate_candidate() if deps else validate_candidate();require_receipt(g,receipt,batch,admission);RUNROOT=(deps.runroot if deps else HERE/'runs'/f'{RID}_batch{batch}');c=cfg();run=RUNROOT/RID;assert not run.exists();owner=g.take_d07_gpu_lock(RID,batch);calls=0;clean=[];cells=[];error=None;boundary_failed=False;safe_cleanup=True
 try:
  g.require_gpu_idle();run.mkdir(parents=True);put(run/'config.json',c);put(run/'candidate_validation.json',candidate)
  if deps:
   calls,clean,cells=deps.execute(c,run)
   for cell in cells:put(run/f"cell_c{cell['cell_index']}_p{cell['boundary']}_t{cell['tail']}.json",cell)
  else:
   opener=build_opener(ProxyHandler({}));ev={}
   for s in c['services']:
    arm=arm_files(s,c);(arm/'input_receipts').mkdir();(arm/'observations.jsonl').touch();(arm/'state_dump').mkdir();held=reserve_pair(s['ports']);release_pair(held);env=g.clean_environment(WT);env.update(PYTHONPATH=str(WT/'python'),FT_T17_INPUT_RECEIPTS=str(arm/'input_receipts'),FT_T17_OBSERVATIONS=str(arm/'observations.jsonl'),FT_DEV_STATE_DUMP=str(arm/'state_dump'),FT_T17_ARM_SOURCE=s['kind'])
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
     clean.append(s['name']);wait_gpu_idle(g)
     try:
      rebound=reserve_pair(s['ports']);release_pair(rebound)
     except BaseException as exc:
      put(arm/'post_cleanup_rebind_failure.json',{'arm':s['name'],'exception':repr(exc),'unsafe':True})
      raise PostCleanupRebindFailure(s['name'],exc) from exc
     put(arm/'post_cleanup_rebind.json',{'api_port':s['ports'][0],'tcpstore_port':s['ports'][1],'both_rebound_and_released':True})
     put(arm/'cleanup.json',{'pid':proc.pid,'group_alive':False,'post_cleanup_rebind':True})
    if s['kind']=='hot':
     cell=evaluate_cell(c,s['cell_index'],ev)
     put(run/f"cell_c{cell['cell_index']}_p{cell['boundary']}_t{cell['tail']}.json",cell);cells.append(cell)
     if not cell['cold_stable'] or not cell['hot_equals_cold']:
      break  # independently defined product failure ends this round immediately
 except PostCleanupRebindFailure as exc:error=repr(exc);safe_cleanup=False
 except BoundaryStateError as exc:error=repr(exc);boundary_failed=True
 except BaseException as exc:error=repr(exc)
 finally:
  try:
   wait_gpu_idle(g)
   if not safe_cleanup:raise RuntimeError('post-cleanup rebind failed')
   g.release_d07_gpu_lock(owner)
  except BaseException as exc:
   if run.exists():put(run/'unsafe_cleanup.json',{'error':repr(exc),'gpu_lock_preserved':True,'outcome':'failed_harness','product_acceptance':False,'post_cleanup_closed':False})
   raise RuntimeError('unsafe cleanup preserves lock: '+repr(exc))
  if run.exists():
   artifacts={str(p.relative_to(run)):sha(p) for p in run.rglob('*') if p.is_file() and p.name!='terminal.json'}
   proposed='failed_harness' if error is not None else ('kept' if all(x['cold_stable'] and x['hot_equals_cold'] for x in cells) else 'not_met')
   put(run/'terminal.json',{'schema':'ft_d09_t17_terminal/v4','rid':RID,'error':error,'services_cleaned':clean,'calls':calls,'cells':cells,'proposed_verdict':proposed,'artifact_sha256':artifacts,'post_cleanup_closed':True,'gpu_lock_released':True,'independent_review_required':True,'product_acceptance':False})
 if error:raise RuntimeError(error)
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args()
 if a.filedry and not a.run:print(filedry_v6_e2e());return
 if a.run and a.admission and a.owned_child and a.batch and a.launch_receipt:child(a.admission,a.batch,a.launch_receipt);return
 if a.run and a.admission and not a.owned_child and a.batch is None and a.launch_receipt is None:controller(a.admission);return
 p.error('select --filedry or --run --admission')
if __name__=='__main__':main()


