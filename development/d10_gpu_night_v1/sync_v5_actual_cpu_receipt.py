"""Sync the v5 actual entrypoint and seal a separate CPU/filedry receipt."""
import importlib.util,posixpath
from pathlib import Path
HERE=Path(__file__).resolve().parent;REMOTE='/data2/FreeToken/development/d10_gpu_night_v1'
NAMES=('d10_prototype_owned_parent_v5.py','d10_aiperf_runner_v6.py','d10_aiperf_parse_v5.py','test_d10_prototype_owned_parent_v5.py','test_d10_aiperf_parse_v5.py','AUTHOR_HANDOFF_V12_D10_PARENT_V5.md','fixtures/wave1/profile_export.jsonl','fixtures/wave2/profile_export.jsonl')
def main():
 p=HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py';s=importlib.util.spec_from_file_location('ops',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);c=o.connect()
 try:
  f=c.open_sftp()
  for n in NAMES:
   target=posixpath.join(REMOTE,n)
   parent=posixpath.dirname(target)
   try:f.stat(parent)
   except OSError:
    for part in n.split('/')[:-1]:
     parent=posixpath.join(parent,part) if parent!=posixpath.dirname(target) else posixpath.join(REMOTE,part)
     try:f.mkdir(parent)
     except OSError:pass
   try:
    with f.open(target,'rb') as h: existing=h.read()
    if existing != (HERE/n).read_bytes():
     # Preserve the older v5-parser receipt bytes; this fresh receipt binds
     # the corrected actual-entrypoint source set.
     f.chmod(target,0o644)
     with f.open(target,'wb') as h:h.write((HERE/n).read_bytes())
   except FileNotFoundError:o.put_new(f,target,(HERE/n).read_bytes())
   f.chmod(target,0o444)
  f.close()
  code="""import hashlib,json,os,subprocess,time
from pathlib import Path
p=Path('/data2/FreeToken/development/d10_gpu_night_v1');names=%r
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',FT_D10_CPU_PROBE='1',PYTHONPATH='/data2/FreeToken/wt/d10-staggered-v1/python:'+str(p))
tests=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','pytest','test_d10_aiperf_parse_v5.py','test_d10_prototype_owned_parent_v5.py','-q'],cwd=p,text=True,capture_output=True,env=env,timeout=120);assert tests.returncode==0,(tests.stdout,tests.stderr)
dry=subprocess.run(['/data2/FreeToken/venv/bin/python','d10_prototype_owned_parent_v5.py','--filedry'],cwd=p,text=True,capture_output=True,env=env,timeout=120);assert dry.returncode==0,(dry.stdout,dry.stderr);plan=json.loads(dry.stdout);assert plan['actual_entrypoint']=='d10_prototype_owned_parent_v5.py' and plan['plan']['budget']['aiperf_calls']==8
cpu=subprocess.run(['/data2/FreeToken/venv/bin/python','d10_branch_startup_v4.py','--cpu-spawn-probe'],cwd=p,text=True,capture_output=True,env=env,timeout=120);assert cpu.returncode==0,(cpu.stdout,cpu.stderr);proof=json.loads(cpu.stdout.strip().splitlines()[-1]);assert proof['proof']['probe_installed']
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();d={'schema':'ft_d10_v5_actual_cpu_filedry_receipt/v2','timestamp_utc':time.time(),'source_sha256':{n:sha(p/n) for n in names},'pytest_stdout':tests.stdout,'filedry_stdout':dry.stdout,'spawn_stdout':cpu.stdout,'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
q=p/'LINUX_CPU_FILEDRY_RECEIPT_V5_ACTUAL_V2.json'
with q.open('x') as h:json.dump(d,h,sort_keys=True,indent=2);h.write('\\n')
os.chmod(q,0o444);print(json.dumps({'sha256':sha(q),'profiles':plan['plan']['profiles'],'calls':plan['plan']['budget']['aiperf_calls']},sort_keys=True))""" % (NAMES,)
  out=o.run(c,code);f=c.open_sftp();f.get(posixpath.join(REMOTE,'LINUX_CPU_FILEDRY_RECEIPT_V5_ACTUAL_V2.json'),str(HERE/'LINUX_CPU_FILEDRY_RECEIPT_V5_ACTUAL_V2.json'));f.close();print(out)
 finally:c.close()
if __name__=='__main__':main()
