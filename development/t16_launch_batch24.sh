set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,subprocess
script=pathlib.Path('/data2/FreeToken/runs/plan_batches/batch24_E2-pre-gate-D01_python.sh')
subprocess.run(['bash','-n',str(script)],check=True)
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-pre-gate-D01')
with (d/'batch24.sh').open('xb') as dst: dst.write(script.read_bytes())
log=pathlib.Path('/data2/_shared/runs/ft_rounds/batch24.log')
with log.open('x') as stream:
    process=subprocess.Popen(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=stream,
                             stderr=subprocess.STDOUT,start_new_session=True)
print(f'BATCH_PID={process.pid} LOG={log}',flush=True)
PY
