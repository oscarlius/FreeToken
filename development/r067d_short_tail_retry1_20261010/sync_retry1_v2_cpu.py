"""Exclusive-create V2 CPU evidence on the canonical Linux control chain."""
from __future__ import annotations
import hashlib, importlib.util, json, posixpath, shlex
from pathlib import Path

HERE=Path(__file__).resolve().parent; REMOTE='/data2/FreeToken/development/'+HERE.name
NEW=('r067d_retry1_v2_tools.py','prepare_retry1_v2_packet.py','retry1_v2_cpu_filedry.py','CPU_FAILURE_ADMISSION_RETRACTION_V2.json')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ops():
 p=HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py'; spec=importlib.util.spec_from_file_location('ops',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
 o=ops(); c=o.connect()
 try:
  s=c.open_sftp()
  for name in NEW:
   target=posixpath.join(REMOTE,name); body=(HERE/name).read_bytes()
   try:
    with s.open(target,'rb') as h: existing=h.read()
    assert existing==body, target
   except FileNotFoundError: o.put_new(s,target,body)
  s.close()
  code=r'''import hashlib,json,subprocess,time
from pathlib import Path
p=Path('/data2/FreeToken/development/r067d_short_tail_retry1_20261010'); sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest()
assert sha(p/'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json')==json.loads((p/'CPU_FAILURE_ADMISSION_RETRACTION_V2.json').read_text())['v2_packet_sha256']
run=subprocess.run(['/data2/FreeToken/venv/bin/python','retry1_v2_cpu_filedry.py','--out','evidence_cpu_filedry_remote_v2'],cwd=p,text=True,capture_output=True,check=True)
r={'schema':'ft_r067d_retry1_linux_cpu_receipt/v2','rid':'E2-R067d-d20-short-tail-retry1','command':['/data2/FreeToken/venv/bin/python','retry1_v2_cpu_filedry.py','--out','evidence_cpu_filedry_remote_v2'],'stdout':run.stdout,'stderr':run.stderr,'sha256':{n:sha(p/n) for n in ('R067D_RETRY1_CONFIG_CPU_ONLY.json','R067D_RETRY1_PREPARED_RUNNER_PACKET.json','R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json','r067d_retry1_v2_tools.py','CPU_FAILURE_ADMISSION_RETRACTION_V2.json','evidence_cpu_filedry_remote_v2/receipt.json')},'gpu_started':False,'service_started':False,'http_generation':False,'at_utc':time.time()}
with (p/'LINUX_CPU_RECEIPT_v2.json').open('x') as h:json.dump(r,h,indent=2,sort_keys=True);h.write('\n')
print(json.dumps({'receipt_sha256':sha(p/'LINUX_CPU_RECEIPT_v2.json'),'filedry':run.stdout}))'''
  _,out,err=c.exec_command('/data2/FreeToken/venv/bin/python -c '+shlex.quote(code)); stdout,stderr=out.read().decode(),err.read().decode();status=out.channel.recv_exit_status(); print(stdout); print(stderr); assert status==0,status
  s=c.open_sftp()
  for name in ('R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json','LINUX_CPU_RECEIPT_v2.json'):
   s.get(posixpath.join(REMOTE,name),str(HERE/name))
  (HERE/'evidence_cpu_filedry_remote_v2').mkdir()
  for name in ('receipt.json','prepared_child_cpu_mode.json'):s.get(posixpath.join(REMOTE,'evidence_cpu_filedry_remote_v2',name),str(HERE/'evidence_cpu_filedry_remote_v2'/name))
  s.close()
 finally: c.close()
if __name__=='__main__':main()
