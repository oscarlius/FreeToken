set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/runs/dev_D03/gpu_selfcheck_c30ae0d')
for rel in ['candidate_logits_a/logits_capture.log','candidate_logits_a/serve.log']:
    p=root/rel
    print('D03_FAILURE_TAIL',rel)
    print(subprocess.run(['tail','-n','65',str(p)],capture_output=True,text=True).stdout)
dump=root/'candidate_logits_a/logits'
if dump.is_dir(): print('D03_CAPTURE_FILES',[(p.name,p.stat().st_size) for p in dump.iterdir()])
print('D03_SELFCHECK_PROC',subprocess.run(['ps','-p','2209743','-o','pid,stat,etime,args'],capture_output=True,text=True).stdout)
print('D03_GPU',subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout)
print('D03_LOCK_EXISTS',pathlib.Path('/data2/_shared/gpu.lock').exists())
PY
