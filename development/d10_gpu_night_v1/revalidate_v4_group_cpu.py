"""Create a fresh immutable CPU receipt after the v4 group-binding correction."""
import importlib.util, json, posixpath
from pathlib import Path
HERE=Path(__file__).resolve().parent; REMOTE='/data2/FreeToken/development/d10_gpu_night_v1'
NAMES=('d10_prototype_owned_parent_v4.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d10_aiperf_parse_v4.py','d10_aiperf_runner_v5.py','test_d10_prototype_owned_parent_v4.py','AUTHOR_HANDOFF_V10_D10_PROTOTYPE_V4.md')
def main():
 p=HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py'; s=importlib.util.spec_from_file_location('ops',p);o=importlib.util.module_from_spec(s);s.loader.exec_module(o);c=o.connect()
 try:
  f=c.open_sftp()
  for n in NAMES:
   target=posixpath.join(REMOTE,n);f.chmod(target,0o644)
   with f.open(target,'wb') as h:h.write((HERE/n).read_bytes())
   f.chmod(target,0o444)
  f.close()
  code="""import hashlib,json,os,subprocess,time
from pathlib import Path
p=Path('/data2/FreeToken/development/d10_gpu_night_v1');names=%r
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',FT_D10_CPU_PROBE='1',PYTHONPATH='/data2/FreeToken/wt/d10-staggered-v1/python:'+str(p))
r=subprocess.run(['/data2/FreeToken/venv/bin/python','d10_branch_startup_v4.py','--cpu-spawn-probe'],cwd=p,text=True,capture_output=True,env=env,timeout=120);assert r.returncode==0,(r.stdout,r.stderr)
proof=json.loads(r.stdout.strip().splitlines()[-1]);assert proof['proof']['probe_installed'] and not proof['gpu_started'] and not proof['http_started']
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest();doc={'schema':'ft_d10_v4_group_linux_cpu_receipt/v1','timestamp_utc':time.time(),'source_sha256':{n:sha(p/n) for n in names},'stdout':r.stdout,'stderr':r.stderr,'exit_code':0,'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
with (p/'LINUX_CPU_SPAWN_RECEIPT_V4_GROUP.json').open('x') as h:json.dump(doc,h,sort_keys=True,indent=2);h.write('\\n')
print(json.dumps({'sha256':sha(p/'LINUX_CPU_SPAWN_RECEIPT_V4_GROUP.json'),'proof':proof}))""" % (NAMES,)
  out=o.run(c,code);f=c.open_sftp();f.get(posixpath.join(REMOTE,'LINUX_CPU_SPAWN_RECEIPT_V4_GROUP.json'),str(HERE/'LINUX_CPU_SPAWN_RECEIPT_V4_GROUP.json'));f.close();print(out)
 finally:c.close()
if __name__=='__main__':main()
