set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json, pathlib, subprocess
r=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R009-p64k')
for p in sorted(r.glob('status_batch*.json')):
    print(p.name, p.read_text())
    status=json.loads(p.read_text())
    if status.get('arm'):
        service=r/status['arm']/'serve.log'
        if service.exists():
            lines=subprocess.run(['tail','-n','6',str(service)],capture_output=True,text=True).stdout.replace('\r','\n').splitlines()
            print('SERVICE TAIL', '\n'.join(line[:300] for line in lines[-3:]))
log=pathlib.Path('/data2/_shared/runs/ft_rounds/batch37.log')
for name in ['quality.json','soak.json','measurement_summary.json']:
    for p in r.glob('*/'+name):
        print('PUBLISHED',p.relative_to(r),p.stat().st_size)
if log.exists():
    print('BATCH37 TAIL', '\n'.join(line[:300] for line in log.read_text(errors='replace').splitlines()[-6:]))
print(subprocess.run(['ps','-p','2185365','-o','pid,ppid,stat,etime,args'],capture_output=True,text=True).stdout)
print(subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout)
PY
