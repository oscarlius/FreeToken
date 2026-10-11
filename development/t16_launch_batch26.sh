set -euo pipefail
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t16_runner.py --self-test
/data2/FreeToken/venv/bin/python /data2/FreeToken/runs/plan_batches/t16_runner.py --gate D00 --rid E2-pre-gate-D00 --batch 26
/data2/FreeToken/venv/bin/python - <<'PY'
import pathlib,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
assert not (root/'E2-pre-gate-D00').exists()
assert not (root/'batch26.log').exists()
script=pathlib.Path('/data2/FreeToken/runs/plan_batches/batch26_E2-pre-gate-D00_python.sh')
subprocess.run(['bash','-n',str(script)],check=True)
with (root/'batch26.log').open('x') as stream:
    process=subprocess.Popen(['bash',str(script)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
print(f'BATCH_PID={process.pid} LOG={root}/batch26.log',flush=True)
PY
