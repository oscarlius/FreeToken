"""Fail-closed D09 T17 v2 runner.  GPU execution requires a sealed root admission."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, shutil, signal, socket, struct, subprocess, sys, time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

HERE=Path(__file__).resolve().parent; RID='E2-D09-T17-night-20261009'; ROOT=Path('/data2/FreeToken')
INPUTS=HERE/'D09_T17_EXACT_INPUTS.json'; PROVENANCE=HERE.parent/'d09_t16_night_v1/d09_native_provenance_v1.json'
WT=ROOT/'wt/d09-message-boundary-v1'; CANDIDATE='c17b69a46cd512fbf3d127d3879bce92caae457b'
RUNROOT=Path(os.environ.get('FT_D09_T17_V2_RUNROOT',str(ROOT/'runs/dev_D09'))); PORTS=(31501,31502,31503,31504,31505,31506,31507,31508,31509,31510,31511,31512)
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
 for cell in data['cells']:
  for kind in ('coldA','coldB','hot'):
   api,tcp=PORTS[i*2:i*2+2];i+=1; arm=RUNROOT/RID/'services'/f'{kind}_p{cell["boundary"]}_t{cell["tail"]}'
   argv=['numactl','--cpunodebind=0,1','--interleave=all',str(ROOT/'venv/bin/python'),'-u',str(arm/'t17_d14_startup.py'),'serve','--port',str(api),'--model-path',str(ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'),'--host','127.0.0.1','--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d','--ple-backend','pinned','--moe-strategy','offload','--max-running-requests','2','--kv-reserve-tokens','49152','--max-seq-len-override','49152','--max-prefill-length','4096','--enable-cache-report','--enable-special-token-ckpt','--enable-message-boundary-ckpt','--prefill-layer-major','--mamba-host-slots','0']
   q=[{'role':'target','ids':cell['target_ids'],'sha256':cell['target_ids_sha256']}];
   if kind=='hot':q.insert(0,{'role':'donor','ids':cell['donor_ids'],'sha256':cell['donor_ids_sha256']})
   out.append({'name':arm.name,'kind':kind,'boundary':cell['boundary'],'tail':cell['tail'],'ports':[api,tcp],'arm':str(arm),'argv':argv,'argv_sha256':hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest(),'requests':q})
 return {'schema':'ft_d09_t17_v2/v1','rid':RID,'candidate':CANDIDATE,'inputs_sha256':sha(INPUTS),'provenance_sha256':sha(PROVENANCE),'runner_sha256':sha(__file__),'tooling_sha256':tooling(),'services':out,'budget':{'services':6,'calls':8,'max_tokens':32}}
def check_admission(path,c):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222: raise RuntimeError('sealed root admission required')
 a=json.loads(path.read_text()); wanted={'root_approved':True,'rid':RID,'candidate':CANDIDATE,'inputs_sha256':c['inputs_sha256'],'runner_sha256':c['runner_sha256'],'tooling_sha256':c['tooling_sha256'],'required_gates':{'T16':'passed','T17':'passed'}}
 if any(a.get(k)!=v for k,v in wanted.items()):raise RuntimeError('root admission binding differs')
 return a
def pair_probe(ports):
 held=[]
 try:
  for p in ports:s=socket.socket();s.bind(('127.0.0.1',p));held.append(s)
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
 uid=str(len(list(arm.glob('request_*.json')))+1); receipt={'uid':int(uid),'int32le_sha256':item['sha256']};put(arm/f'input_receipts/{uid}.json',receipt)
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
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--admission',type=Path);a=p.parse_args()
 if a.filedry and not a.run:print(filedry());return
 if not(a.run and a.admission):p.error('select --filedry or --run --admission')
 c=cfg();check_admission(a.admission,c);g=d07()
 if g.LOCK.exists() or g.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists; R047 remains owner')
 raise RuntimeError('v2 GPU execution requires controller-owned child receipt; no direct launch')
if __name__=='__main__':main()
