set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,subprocess
dev=pathlib.Path('/data2/FreeToken/runs/dev_D03')
record=json.loads((dev/'t16_launch_c30ae0d.json').read_text())
print('D03_T16_LAUNCH',json.dumps(record))
subprocess.run(['ps','-p',str(record['batch_pid']),'-o','pid,ppid,stat,etime,args'])
round_dir=pathlib.Path('/data2/_shared/runs/ft_rounds')/record['rid']
for filename in [f"status_batch{record['batch']}.json",f"gate_batch{record['batch']}.json"]:
    path=round_dir/filename
    if path.exists(): print('D03_T16_ARTIFACT',filename,path.read_text()[:16000])
for arm in sorted(round_dir.glob('*_b*')):
    if not arm.is_dir():continue
    print('D03_T16_ARM',arm.name)
    log=arm/'serve.log'
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-800))
            print(stream.read().decode(errors='replace'))
log=pathlib.Path(record['log'])
if log.exists():
    with log.open('rb') as stream:
        stream.seek(max(0,log.stat().st_size-1600))
        print('D03_T16_LOG_TAIL',stream.read().decode(errors='replace'))
PY
