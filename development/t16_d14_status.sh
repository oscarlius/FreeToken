set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken')
receipt=json.loads((root/'runs/dev_D14/launch_E2-R021-gate-D14.json').read_text())
pid=receipt['batch_pid']; directory=pathlib.Path('/data2/_shared/runs/ft_rounds')/receipt['rid']
proc=pathlib.Path('/proc')/str(pid)
handle={'pid':pid,'present':proc.exists()}
if proc.exists():
    fields=(proc/'stat').read_text().rpartition(') ')[2].split()
    handle.update(state=fields[0],pgid=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]),
                  argv=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode())
    if (handle['pgid']!=receipt['batch_pgid'] or handle['session']!=receipt['batch_pgid']
            or handle['start_ticks']!=121621035 or receipt['frozen_runner'] not in handle['argv']):
        raise ValueError('batch process identity differs from the receipt')
status=directory/('status_batch'+str(receipt['batch'])+'.json')
lock=pathlib.Path('/data2/_shared/gpu.lock')
print(json.dumps({'receipt':receipt['rid'],'process':handle,
                  'status':json.loads(status.read_text()) if status.exists() else None,
                  'lock':json.loads(lock.read_text()) if lock.exists() else None,
                  'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader']).decode().strip()},indent=2))
for arm in sorted(directory.iterdir()) if directory.exists() else []:
    if not arm.is_dir():continue
    log=arm/'serve.log'
    files={name:(arm/name).stat().st_size for name in ('health.json','det.json','tax.json','d0_prefill.jsonl') if (arm/name).exists()}
    print(json.dumps({'arm':arm.name,'files':files}))
    if log.exists():
        lines=log.read_text(errors='replace').splitlines()
        print('\n'.join(lines[-6:]))
batchlog=pathlib.Path(receipt['batch_log'])
if batchlog.exists():
    print('BATCH_LOG_TAIL')
    print('\n'.join(batchlog.read_text(errors='replace').splitlines()[-12:]))
PY
