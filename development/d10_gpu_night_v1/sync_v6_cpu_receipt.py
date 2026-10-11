import importlib.util,posixpath
from pathlib import Path
HERE=Path(__file__).resolve().parent;REMOTE='/data2/FreeToken/development/d10_gpu_night_v1';N=('d10_prototype_owned_parent_v6.py','d10_aiperf_runner_v7.py','d10_aiperf_parse_v6.py','test_d10_v6_contract.py','fixtures/wave1/profile_export.jsonl','fixtures/wave2/profile_export.jsonl')
def main():
 p=HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py';s=importlib.util.spec_from_file_location('o',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);c=o.connect()
 try:
  f=c.open_sftp()
  for n in N:
   t=posixpath.join(REMOTE,n)
   try:
    with f.open(t,'rb') as h:old=h.read()
    if old!=(HERE/n).read_bytes():f.chmod(t,0o644);f.open(t,'wb').write((HERE/n).read_bytes())
   except FileNotFoundError:
    parent=posixpath.dirname(t)
    try:f.mkdir(parent)
    except OSError:pass
    o.put_new(f,t,(HERE/n).read_bytes())
   f.chmod(t,0o444)
  f.close()
  code="""import hashlib,json,os,subprocess,time
from pathlib import Path
p=Path('/data2/FreeToken/development/d10_gpu_night_v1');names=%r;env=dict(os.environ,CUDA_VISIBLE_DEVICES='',FT_D10_CPU_PROBE='1',PYTHONPATH='/data2/FreeToken/wt/d10-staggered-v1/python:'+str(p))
t=subprocess.run(['/data2/FreeToken/venv/bin/python','-m','pytest','test_d10_v6_contract.py','-q'],cwd=p,text=True,capture_output=True,env=env);assert t.returncode==0,(t.stdout,t.stderr)
d=subprocess.run(['/data2/FreeToken/venv/bin/python','d10_prototype_owned_parent_v6.py','--filedry'],cwd=p,text=True,capture_output=True,env=env);assert d.returncode==0,(d.stdout,d.stderr)
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();q=p/'LINUX_CPU_RECEIPT_V6.json';z={'schema':'ft_d10_v6_cpu/v1','timestamp_utc':time.time(),'source_sha256':{n:sha(p/n) for n in names},'pytest_stdout':t.stdout,'filedry_stdout':d.stdout,'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
with q.open('x') as h:json.dump(z,h,sort_keys=True,indent=2);h.write('\\n')
os.chmod(q,0o444);print(sha(q))""" % (N,)
  print(o.run(c,code))
 finally:c.close()
if __name__=='__main__':main()
