set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/runs/dev_D03')
launch=json.loads((root/'gpu_selfcheck_launch_c30ae0d_urlfix.json').read_text())
print('D03_LAUNCH',json.dumps(launch))
print(subprocess.run(['ps','-p',str(launch['pid']),'-o','pid,ppid,stat,etime,args'],capture_output=True,text=True).stdout)
out=pathlib.Path(launch['output'])
for name in ['selfcheck.json','selfcheck_error.json','admission.json']:
 p=out/name
 if p.exists(): print('D03_ARTIFACT',name,p.stat().st_size)
if out.exists():
 arms=sorted([p for p in out.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime)
 for arm in arms[-2:]:
  owner=arm/'owned_process.json'
  if owner.exists():
   pid=json.loads(owner.read_text())['pid']
   print('D03_ARM',arm.name,subprocess.run(['ps','-p',str(pid),'-o','pid,stat,etime,args'],capture_output=True,text=True).stdout)
  log=arm/'serve.log'
  if log.exists():
   lines=subprocess.run(['tail','-n','6',str(log)],capture_output=True,text=True).stdout.replace('\r','\n').splitlines()
   print('D03_SERVE_TAIL',arm.name,'\n'.join(line[:300] for line in lines[-3:]))
print('D03_BATCH_TAIL',subprocess.run(['tail','-n','6',launch['log']],capture_output=True,text=True).stdout)
print(subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout)
PY
