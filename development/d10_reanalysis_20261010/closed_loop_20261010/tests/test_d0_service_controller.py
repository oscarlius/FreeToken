import importlib.util,json,time
from pathlib import Path
ROOT=Path(__file__).parents[1];s=importlib.util.spec_from_file_location('c',ROOT/'d0_service_controller.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def test_prepare_projects_exact_private_98k(monkeypatch):
 class R:
  WT='/wt'
  def prepare(self):return {'arms':[{'arm':'W98K','argv':['ft','--port','32101'],'environment':{}}]}
 monkeypatch.setattr(c,'load',lambda p,n:R());r=c.prepare({'d0_path':'/d0'})
 assert r['port']==32103 and r['master_port']==32203 and r['argv'][-1]=='32103' and r['environment']['FT_DEV_D0']=='1'
class P:pid=123
class L:
 def process_identity(self,p):return {'pid':p,'start_ticks':77,'pgid':p,'session':p}
 def stop_owned_process(self,*a,**k):pass
 def owned_group_alive(self,p):return False
class D:
 def __init__(self):self.lifecycle=L();self.released=[];self.service_arg=None
 def now(self):return time.monotonic()
 def take_lock(self,*a):return 'lock'
 def release_lock(self,a):self.released.append(a)
 def require_gpu_idle(self):pass
 def gpu_idle(self):return True
 def start_owned(self,record,service,*a):
  self.service_arg=service;assert not service.exists() # actual window.start requires a fresh directory
  service.mkdir();(service/'owned_process.json').write_text(json.dumps({'pid':123}));return P(),None,None,self.lifecycle.process_identity(123)
 def wait_ready(self,*a):pass
def admission(tmp):
 template=tmp/'template.json';template.write_text(json.dumps({'admit':True,'calls_per_phase':4,'concurrency':2,'inputs':{},'phases':{'d0':{}},'output_root':str(tmp/'measure')}));template.chmod(0o444)
 return {'rid':'r','batch':1,'output_root':str(tmp/'out'),'allxy_admission':str(template),'d0_path':'/d0'}
def setup(monkeypatch,a):
 monkeypatch.setattr(c,'prepare',lambda a:{'argv':[],'port':32103,'environment':{'FT_DEV_D0':'1','FT_DEV_D0_PATH':'/d0'}});monkeypatch.setattr(c,'require',lambda *a:None);monkeypatch.setattr(c,'sha',lambda p:'pin')
def test_execute_derives_readonly_pid_bound_doc_and_releases(monkeypatch,tmp_path):
 a=admission(tmp_path);d=D();setup(monkeypatch,a);seen={}
 class A:
  def run(self,doc,phase):seen.update(doc=doc,phase=phase)
 monkeypatch.setattr(c,'load',lambda *x:A())
 c.execute(a,d)
 actual=tmp_path/'out'/'d0_actual_admission.json'
 assert d.service_arg==tmp_path/'out'/'service' and d.released==['lock'] and seen['phase']=='d0'
 assert seen['doc']['phases']['d0']['service_pid']==123 and seen['doc']['phases']['d0']['service_start_ticks']==77
 assert seen['doc']['phases']['d0']['endpoint']=='http://127.0.0.1:32103'
 assert actual.stat().st_mode&0o222==0
def test_start_failure_uses_ownedproof_before_lock_release(monkeypatch,tmp_path):
 a=admission(tmp_path);d=D();setup(monkeypatch,a)
 def start(record,service,*x):
  service.mkdir();(service/'owned_process.json').write_text(json.dumps({'pid':123}));raise RuntimeError('health fail')
 d.start_owned=start;monkeypatch.setattr(c,'load',lambda *x:None)
 try:c.execute(a,d)
 except RuntimeError:pass
 else:assert False
 assert d.released==['lock'] and json.loads((tmp_path/'out'/'terminal.json').read_text())['lock_retained'] is False
def test_not_met_preserved_and_bounded_cleanup_retains_on_failure(monkeypatch,tmp_path):
 a=admission(tmp_path);d=D();setup(monkeypatch,a)
 class A:
  def run(self,*x):raise RuntimeError('lower-7.8 anomaly')
 monkeypatch.setattr(c,'load',lambda *x:A())
 monkeypatch.setattr(c,'bounded_cleanup',lambda *x:False)
 try:c.execute(a,d)
 except RuntimeError:pass
 else:assert False
 term=json.loads((tmp_path/'out'/'terminal.json').read_text())
 assert term['status']=='not_met' and term['lock_retained'] is True and d.released==[]
def test_startup_timeout_has_proc_and_runs_cleanup_once(monkeypatch,tmp_path):
 a=admission(tmp_path);d=D();setup(monkeypatch,a);calls=[]
 def timeout(*x):raise TimeoutError('startup deadline')
 d.wait_ready=timeout
 monkeypatch.setattr(c,'bounded_cleanup',lambda *x:calls.append(x) or True)
 try:c.execute(a,d)
 except TimeoutError:pass
 else:assert False
 assert len(calls)==1 and d.released==['lock']
def test_remaining_is_absolute():
 try:c.remaining(0)
 except TimeoutError:pass
 else:assert False


def test_loading_health_is_not_ready(monkeypatch):
 import io
 seen=[]; states=iter(['loading','serving'])
 def health(*args,**kwargs):
  state=next(states);seen.append(state);return io.StringIO(json.dumps({'status':'ok','maintenance':state}))
 monkeypatch.setattr(c.urllib.request,'urlopen',health);monkeypatch.setattr(c.time,'sleep',lambda n:None)
 class Proc:
  def poll(self):return None
 c.wait_ready({'port':32103},Proc(),time.monotonic()+10)
 assert seen==['loading','serving']
