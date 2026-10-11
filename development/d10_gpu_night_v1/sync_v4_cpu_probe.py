"""Exclusive-create v4 sync and Linux spawn-only validation (no service/GPU)."""
from __future__ import annotations
import hashlib, importlib.util, json, posixpath
from pathlib import Path

HERE=Path(__file__).resolve().parent; REMOTE='/data2/FreeToken/development/d10_gpu_night_v1'
NAMES=('d10_prototype_owned_parent_v4.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d10_aiperf_parse_v4.py','d10_aiperf_runner_v5.py','test_d10_prototype_owned_parent_v4.py','AUTHOR_HANDOFF_V10_D10_PROTOTYPE_V4.md')
def ops():
 p=HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py';s=importlib.util.spec_from_file_location('d10ops',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 o=ops(); client=o.connect()
 try:
  sftp=client.open_sftp()
  for name in NAMES:
   source=HERE/name; target=posixpath.join(REMOTE,name)
   try:
    with sftp.open(target,'rb') as h: existing=h.read()
    if existing != source.read_bytes():
     # Only this v4 packet may be corrected before its immutable CPU receipt.
     try: sftp.stat(posixpath.join(REMOTE,'LINUX_CPU_SPAWN_RECEIPT_V4.json'))
     except OSError:
      sftp.chmod(target,0o644)
      with sftp.open(target,'wb') as h: h.write(source.read_bytes())
     else: raise AssertionError('sealed remote source differs: '+name)
   except FileNotFoundError: o.put_new(sftp,target,source.read_bytes())
   sftp.chmod(target,0o444)
  sftp.close()
  code=r'''import hashlib,json,os,subprocess,time
from pathlib import Path
p=Path('/data2/FreeToken/development/d10_gpu_night_v1'); names='''+repr(NAMES)+r'''
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest()
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',FT_D10_CPU_PROBE='1',PYTHONPATH='/data2/FreeToken/wt/d10-staggered-v1/python:'+str(p))
run=subprocess.run(['/data2/FreeToken/venv/bin/python','d10_branch_startup_v4.py','--cpu-spawn-probe'],cwd=p,text=True,capture_output=True,env=env,timeout=120)
assert run.returncode==0,(run.stdout,run.stderr)
proof=json.loads(run.stdout.strip().splitlines()[-1]); assert proof['gpu_started'] is False and proof['http_started'] is False and proof['proof']['probe_installed']
receipt={'schema':'ft_d10_v4_linux_cpu_spawn_receipt/v1','timestamp_utc':time.time(),'source_sha256':{n:sha(p/n) for n in names},'command':['d10_branch_startup_v4.py','--cpu-spawn-probe'],'stdout':run.stdout,'stderr':run.stderr,'exit_code':run.returncode,'gpu_started':False,'http_started':False,'service_started':False,'compile_started':False}
with (p/'LINUX_CPU_SPAWN_RECEIPT_V4.json').open('x') as h:json.dump(receipt,h,sort_keys=True,indent=2);h.write('\\n')
print(json.dumps({'receipt_sha256':sha(p/'LINUX_CPU_SPAWN_RECEIPT_V4.json'),'proof':proof},sort_keys=True))'''
  output=o.run(client,code)
  sftp=client.open_sftp(); sftp.get(posixpath.join(REMOTE,'LINUX_CPU_SPAWN_RECEIPT_V4.json'),str(HERE/'LINUX_CPU_SPAWN_RECEIPT_V4.json'));sftp.close()
  print(output)
 finally: client.close()
if __name__=='__main__':main()
