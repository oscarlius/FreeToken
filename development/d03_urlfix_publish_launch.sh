set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,os,pathlib,socket,subprocess,sys,time
root=pathlib.Path('/data2/FreeToken');dev=root/'runs/dev_D03'
commit='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def live(pid):
    stat=pathlib.Path(f'/proc/{pid}/stat')
    return stat.exists() and stat.read_text().partition(') ')[2][0]!='Z'

old_launch=json.loads((dev/'gpu_selfcheck_launch_c30ae0d.json').read_text())
assert not live(old_launch['pid']), 'original selfcheck remains live'
failed=dev/'gpu_selfcheck_c30ae0d'
assert (failed/'selfcheck_error.json').is_file() and not (failed/'selfcheck.json').exists()
assert 'HTTP Error 404' in (failed/'candidate_logits_a/logits_capture.log').read_text()
for owner in failed.glob('*/owned_process.json'):
    assert not live(json.loads(owner.read_text())['pid']), str(owner)
assert (failed/'MANIFEST.sha256').is_file()
assert not pathlib.Path('/data2/_shared/gpu.lock').exists()
with socket.socket() as s: assert s.connect_ex(('127.0.0.1',8095)) != 0
gpu=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
assert all(int(v)<1000 for v in gpu.splitlines()),gpu
assert subprocess.check_output(['git','-C',str(root/'wt/e1r003st'),'rev-parse','HEAD'],text=True).strip()==commit
assert not subprocess.check_output(['git','-C',str(root/'wt/e1r003st'),'status','--porcelain','--untracked-files=no'],text=True).strip()

script=dev/'d03_gpu_selfcheck.py';version=dev/'d03_gpu_selfcheck_c30ae0d_urlfix.py'
assert sha(script)=='2f9f7f46b87a5b0a3ab46019df489ad1d6302d0bf2b2c7e01ec0d1c1bc2a61ee'
assert script.read_bytes()==(dev/'d03_gpu_selfcheck_c30ae0d.py').read_bytes()
assert sha(version)=='4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453'
raw=dev/'historical_raw_ids_c30ae0d.json'
assert sha(raw)=='6a08e2e855acacab103eeb4ea0d07972f3e477506020783ec930dbca744fa1e2'
out=dev/'gpu_selfcheck_c30ae0d_urlfix';log=dev/'gpu_selfcheck_c30ae0d_urlfix.log'
record_path=dev/'gpu_selfcheck_launch_c30ae0d_urlfix.json'
assert not out.exists() and not log.exists() and not record_path.exists()
poststop={'previous_pid':old_launch['pid'],'pid_gone':True,'port8095_free':True,'lock_absent':True,
          'gpu_mib':[int(v) for v in gpu.splitlines()],'failure_error_sha256':sha(failed/'selfcheck_error.json'),
          'failed_manifest_sha256':sha(failed/'MANIFEST.sha256'),'time':time.strftime('%F %T %Z')}
with (dev/'gpu_selfcheck_c30ae0d_failure_poststop.json').open('x') as f:json.dump(poststop,f,indent=2);f.write('\n')
script.write_bytes(version.read_bytes())
env=dict(os.environ);env['CUDA_VISIBLE_DEVICES']=''
subprocess.run([sys.executable,str(script),'--self-test'],env=env,check=True)
subprocess.run([sys.executable,'-m','py_compile',str(script)],check=True)
argv=[sys.executable,'-u',str(script),'--run','--raw-ids',str(raw),'--tail-k','64']
with log.open('xb') as sink:
    process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=sink,stderr=subprocess.STDOUT,start_new_session=True,cwd=root)
record={'pid':process.pid,'pgid':process.pid,'candidate_commit':commit,'argv':argv,'log':str(log),'output':str(out),
        'runner_sha256':sha(script),'runner_md5':hashlib.md5(script.read_bytes()).hexdigest(),
        'raw_manifest_sha256':sha(raw),'previous_failure_output':str(failed),'poststop_proof':poststop}
with record_path.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print('D03_URLFIX_SELFCHECK_LAUNCHED',json.dumps(record),flush=True)
PY
