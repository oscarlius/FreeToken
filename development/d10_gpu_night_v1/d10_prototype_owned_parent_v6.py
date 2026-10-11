"""Independent v6 D10 actual driver; never inherits v4 terminal accounting."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,socket,subprocess,time
from pathlib import Path
from urllib.request import ProxyHandler,build_opener
HERE=Path(__file__).resolve().parent;ROOT=Path('/data2/FreeToken');WT=ROOT/'wt/d10-staggered-v1';RID='E2-D10-PROTOTYPE-night-20261010-v6';CANDIDATE='22ff3a389eae3724cdca9a45f2e19577082a2032';FLAG='--d10-staggered-decode';MAX_CALLS=8
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,n):s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def runner():return load(HERE/'d10_aiperf_runner_v7.py','d10runner7')
def d07():m=load(HERE/'d07_g3g4_prepare.py','d10v6d07');m.CANDIDATE=CANDIDATE;m.RID=RID;return m
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as h:json.dump(v,h,sort_keys=True,indent=2);h.write('\n')
def append(p,v):
 with p.open('a',encoding='utf-8') as h:h.write(json.dumps(v,sort_keys=True)+'\n')
def reserve(port):s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port));return s
ACTUAL=('d10_prototype_owned_parent_v6.py','d10_aiperf_runner_v7.py','d10_aiperf_parse_v6.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py')
def require_admission(path,run):
 if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222:raise RuntimeError('sealed admission required')
 doc=run.require_admission(path);want={'admit':True,'prototype_rid':RID,'candidate':CANDIDATE,'d10_flag':FLAG,'calls_max':8,'services_max':1}
 if any(doc.get(k)!=v for k,v in want.items()):raise RuntimeError('v6 admission differs')
 if set(doc.get('source_sha256',{}))!=set(ACTUAL) or any(doc['source_sha256'][n]!=sha(HERE/n) for n in ACTUAL):raise RuntimeError('v6 source SHA binding differs')
 svc=doc['service'];a=svc['argv'];api=svc['api_port']
 if a[:2]!=['ft','serve'] or FLAG not in a or a.count('--port')!=1 or int(a[a.index('--port')+1])!=api or svc['tcpstore_port']!=api+1 or any('tcpstore' in x.lower() for x in a):raise RuntimeError('service binding differs')
 if not doc.get('t16_closure') or not doc.get('d09_completed_terminals'):raise RuntimeError('closure bindings missing')
 return doc
class Default:
 def __init__(self):self.gate=d07();self.run=runner()
 def start(self,a,c,e,l):
  with l.open('xb') as h:return subprocess.Popen(a,cwd=c,env=e,stdin=subprocess.DEVNULL,stdout=h,stderr=subprocess.STDOUT,start_new_session=True)
 def health(self,e):
  with build_opener(ProxyHandler({})).open(e+'/health',timeout=10) as r:return json.loads(r.read())
 def dispatch(self,endpoint,out,index):
  r=self.run;inp=r.ORIGINAL if index<2 else r.INPUT;cmd=r.argv(endpoint,str(out/f'profile{index}'),inp);put(out/f'profile{index}.command.json',{'argv':cmd});z=subprocess.run(cmd,timeout=1800);put(out/f'profile{index}.exit.json',{'exit_code':z.returncode});
  if z.returncode:raise RuntimeError('AIPerf group failed')
 def stop(self,p):self.gate.load_owned_lifecycle().stop_owned_process(p,120,30)
 def alive(self,p):return self.gate.load_owned_lifecycle().owned_group_alive(p)
def child(admission,batch,receipt,deps=None):
 deps=deps or Default();g=deps.gate;doc=require_admission(admission,deps.run);out=Path(doc['prototype_output']);svc=doc['service'];calls=0;proc=None;error=None;cleanup=None;owner=None
 if out.exists() or out.is_symlink():raise RuntimeError('fresh output required')
 try:
  data=json.loads(receipt.read_text());
  if data.get('state')!='launched' or data.get('batch')!=batch:raise RuntimeError('launch receipt differs')
  owner=g.take_d07_gpu_lock(RID,batch);out.mkdir();put(out/'admission_snapshot.json',doc);h=reserve(svc['api_port']);h.close()
  env=g.clean_environment(WT);event=out/'d10_branch_event.json';env.update({'PYTHONPATH':str(HERE)+os.pathsep+str(WT/'python'),'FT_D10_BRANCH_EVENT':str(event),'FT_D10_CANDIDATE':CANDIDATE,'PYTHONDONTWRITEBYTECODE':'1'})
  proc=deps.start([str(ROOT/'venv/bin/python'),str(HERE/'d10_branch_startup_v4.py'),*svc['argv'][2:]],svc['cwd'],env,out/'serve.log');deadline=time.monotonic()+1800
  while time.monotonic()<deadline:
   if proc.poll() is not None:raise RuntimeError('service exited before health')
   try:
    if deps.health(svc['endpoint']).get('status')=='ok':break
   except OSError:time.sleep(2)
  else:raise TimeoutError('health timeout')
  a=out/'aiperf';a.mkdir()
  for i in range(4):
   append(out/'budget.jsonl',{'event':'dispatch_reserved','group':i,'calls_before':calls,'calls_after':calls+2});calls+=2;deps.dispatch(svc['endpoint'],a,i)
  rows=deps.run.require_raw_profiles(a);eventdoc=json.loads(event.read_text())
  if eventdoc.get('actual_batch_reqs')!=2 or not eventdoc.get('actual_can_use_d10_staggered'):raise ValueError('branch proof not met')
  put(out/'raw_response_records.json',{'profiles':rows,'actual_generation_calls':calls})
 except ValueError as e:error=('not_met',repr(e))
 except BaseException as e:error=('failed_harness',repr(e))
 finally:
  try:
   if proc:deps.stop(proc);assert not deps.alive(proc.pid)
   g.require_gpu_idle();q=reserve(svc['api_port']);q.close()
  except BaseException as e:cleanup=repr(e)
  verdict='failed_harness' if cleanup or (error and error[0]=='failed_harness') else ('not_met' if error else 'measured_pending_independent_review')
  if out.exists():put(out/'terminal.json',{'rid':RID,'verdict':verdict,'error':None if not error else error[1],'cleanup_error':cleanup,'actual_services':1 if proc else 0,'actual_generation_calls':calls,'candidate_meets_prototype_threshold':verdict=='measured_pending_independent_review','product_acceptance':False,'lock_retained':bool(cleanup)})
  if owner and not cleanup:g.release_d07_gpu_lock(owner)
 if cleanup:raise RuntimeError(cleanup)
 if error:raise RuntimeError(error[1])
 return out/'terminal.json'
def filedry():return {'schema':'ft_d10_parent_v6_filedry/v1','entrypoint':Path(__file__).name,'plan':runner().filedry(),'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args()
 if a.filedry:print(json.dumps(filedry(),sort_keys=True));return
 p.error('v6 runtime is root-controller only')
if __name__=='__main__':main()
